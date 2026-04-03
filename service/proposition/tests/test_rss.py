import unittest

from service.proposition import rss


class TestRss(unittest.TestCase):
    def test_parse_rss_minimal(self) -> None:
        xml = b"""<?xml version="1.0"?>
        <rss><channel>
          <item>
            <title>Test headline</title>
            <link>https://example.com/a</link>
            <guid>g1</guid>
            <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
          </item>
        </channel></rss>"""
        items = rss.parse_feed_xml(xml)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Test headline")
        self.assertEqual(items[0].link, "https://example.com/a")
        self.assertEqual(items[0].external_id, "g1")

    def test_published_ts_epoch_ms(self) -> None:
        self.assertEqual(rss.published_ts("1700000000000"), 1700000000)

    def test_parse_atom_minimal(self) -> None:
        xml = b"""<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Atom title</title>
            <id>urn:entry:1</id>
            <link href="https://example.com/b"/>
            <updated>2024-01-02T00:00:00Z</updated>
          </entry>
        </feed>"""
        items = rss.parse_feed_xml(xml)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Atom title")
        self.assertEqual(items[0].link, "https://example.com/b")


if __name__ == "__main__":
    unittest.main()
