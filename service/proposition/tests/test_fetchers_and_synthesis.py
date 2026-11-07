"""Feed fetching and draft wording (ADR-0020, AGENTS.md #2).

Feed content is untrusted and its shape varies by publisher, so a surprising response must degrade
to fewer drafts rather than an exception that stops the whole ingest.
"""
import unittest
from datetime import datetime, timezone
from unittest import mock

from service.proposition import json_sources, rss, synthesize


def fake_response(payload: bytes):
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = payload
    return response


class RssFetchTests(unittest.TestCase):
    def test_fetch_identifies_itself_and_parses_the_feed(self):
        xml = b"<rss><channel><item><title>T</title><link>https://a</link><guid>g</guid></item></channel></rss>"
        with mock.patch.object(rss.request, "urlopen", return_value=fake_response(xml)) as urlopen:
            items = rss.fetch_rss_items("https://feed.example/rss", timeout=3)
        self.assertEqual([i.title for i in items], ["T"])
        req = urlopen.call_args.args[0]
        self.assertEqual(req.full_url, "https://feed.example/rss")
        self.assertIn("ParamutuelPropositionService", req.headers["User-agent"])
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 3)

    def test_atom_entry_without_a_link_uses_its_id(self):
        xml = b"""<feed xmlns="http://www.w3.org/2005/Atom">
          <title>Feed title is not an entry</title>
          <entry><title>E</title><id>urn:x:1</id></entry>
        </feed>"""
        items = rss.parse_feed_xml(xml)
        self.assertEqual(len(items), 1, "only <entry> children become items")
        self.assertEqual((items[0].title, items[0].link, items[0].external_id), ("E", "urn:x:1", "urn:x:1"))

    def test_an_unrecognised_document_has_no_items(self):
        self.assertEqual(rss.parse_feed_xml(b"<html><body>Blocked</body></html>"), [])

    def test_a_date_with_no_timezone_is_read_as_utc(self):
        expected = int(datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc).timestamp())
        self.assertEqual(rss.published_ts("2026-01-02T03:04:05"), expected)


class HttpGetTests(unittest.TestCase):
    def test_get_decodes_json_and_identifies_itself(self):
        with mock.patch.object(json_sources.request, "urlopen", return_value=fake_response(b'{"a": 1}')) as urlopen:
            self.assertEqual(json_sources._http_get("https://x", timeout=2), {"a": 1})
        req = urlopen.call_args.args[0]
        self.assertIn("ParamutuelPropositionService", req.headers["User-agent"])


class HackerNewsTests(unittest.TestCase):
    def _fetch(self, stories, **kw):
        def fake_get(url, timeout=25):
            if url.endswith("topstories.json"):
                return list(stories) if isinstance(stories, dict) else stories
            return stories[int(url.rsplit("/", 1)[1].split(".")[0])]

        with mock.patch.object(json_sources, "_http_get", side_effect=fake_get) as get:
            return json_sources.fetch_hackernews_top(**kw), get

    def test_keeps_only_stories_and_links_text_posts_to_their_discussion(self):
        items, _ = self._fetch(
            {
                1: {"id": 1, "type": "story", "title": " A ", "url": "https://a"},
                2: {"id": 2, "type": "comment", "title": "not a story"},
                3: {"id": 3, "type": "story"},
                4: None,
            }
        )
        self.assertEqual([i.external_id for i in items], ["1", "3"])
        self.assertEqual(items[0].title, "A")
        self.assertEqual(items[0].link, "https://a")
        self.assertEqual(items[1].title, "(no title)")
        self.assertEqual(items[1].link, "https://news.ycombinator.com/item?id=3")

    def test_requests_are_bounded(self):
        """One HTTP request per story, so this must not be open-ended."""
        stories = {i: {"id": i, "type": "story", "title": "t"} for i in range(80)}
        items, get = self._fetch(stories, limit=500)
        self.assertEqual(len(items), 50)
        self.assertEqual(get.call_count, 51)

    def test_an_unexpected_top_list_means_no_items(self):
        with mock.patch.object(json_sources, "_http_get", return_value={"error": "rate limited"}):
            self.assertEqual(json_sources.fetch_hackernews_top(), [])


class JsonArrayTests(unittest.TestCase):
    def _fetch(self, payload, **kw):
        with mock.patch.object(json_sources, "_http_get", return_value=payload):
            return json_sources.fetch_json_array("https://x", **kw)

    def test_a_response_with_no_list_means_no_items(self):
        self.assertEqual(self._fetch({"error": "nope"}), [])
        self.assertEqual(self._fetch("text"), [])

    def test_rows_that_are_not_objects_are_skipped(self):
        self.assertEqual([i.title for i in self._fetch([1, "x", {"title": "kept"}])], ["kept"])

    def test_a_non_string_link_is_kept_as_text(self):
        self.assertEqual(self._fetch([{"title": "t", "url": 42}])[0].link, "42")

    def test_a_row_with_no_id_uses_its_title_so_it_still_deduplicates(self):
        self.assertEqual(self._fetch([{"title": "stable title"}])[0].external_id, "stable title")

    def test_prefix_applies_to_relative_links_and_slugs_but_not_absolute_links(self):
        items = self._fetch(
            [
                {"title": "rel", "url": "/a"},
                {"title": "abs", "url": "https://other/b"},
                {"title": "slug", "slug": "/c"},
                {"title": "none"},
            ],
            link_prefix="https://site/e/",
        )
        self.assertEqual([i.link for i in items], ["https://site/e/a", "https://other/b", "https://site/e/c", ""])


class SynthesisTests(unittest.TestCase):
    def test_truncate_marks_what_it_cut(self):
        self.assertEqual(synthesize._truncate("  short  ", 10), "short")
        self.assertEqual(synthesize._truncate("x" * 20, 5), "xxxx…")

    def test_explicit_cadence_wins_when_valid(self):
        monday = datetime(2026, 1, 5, tzinfo=timezone.utc)
        self.assertEqual(synthesize.infer_cadence({"default_cadence": " Daily "}, now=monday), "daily")
        self.assertEqual(synthesize.infer_cadence({"default_cadence": "hourly"}, now=monday), "weekly", "unknown values are ignored")

    def test_cadence_inferred_from_the_calendar(self):
        self.assertEqual(synthesize.infer_cadence({}, now=datetime(2026, 1, 5, tzinfo=timezone.utc)), "weekly", "a Monday")
        self.assertEqual(synthesize.infer_cadence({}, now=datetime(2026, 7, 1, tzinfo=timezone.utc)), "monthly", "a first of the month")
        self.assertEqual(synthesize.infer_cadence({}, now=datetime(2026, 7, 2, tzinfo=timezone.utc)), "event")

    def test_a_headline_phrased_as_a_question_stays_one(self):
        prop, outcomes, _, _ = synthesize.build_proposition_bundle(
            headline="Will it rain?", source_label="s", category="c", link="https://x", cadence="event"
        )
        self.assertTrue(prop.startswith("Will it rain? "))
        self.assertEqual(prop.count("—"), 0)
        self.assertEqual(outcomes, ["Yes", "No"])

    def test_unknown_calendar_kind_has_no_templates(self):
        self.assertEqual(synthesize.template_calendar_propositions(kind="yearly"), [])

    def test_calendar_defaults_to_today(self):
        self.assertTrue(synthesize.template_calendar_propositions(kind="daily"))


if __name__ == "__main__":
    unittest.main()
