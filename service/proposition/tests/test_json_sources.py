import unittest
from unittest.mock import patch

from service.proposition import json_sources


class TestJsonSources(unittest.TestCase):
    @patch.object(json_sources, "_http_get")
    def test_unwrap_markets_envelope(self, mock_get) -> None:
        mock_get.return_value = {
            "markets": [
                {"id": "1", "question": "Q1?", "slug": "q1"},
            ]
        }
        items = json_sources.fetch_json_array(
            "https://example.invalid/x",
            title_key="question",
            id_key="id",
            link_key="slug",
            link_prefix="https://pm.example/e/",
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Q1?")
        self.assertEqual(items[0].link, "https://pm.example/e/q1")


if __name__ == "__main__":
    unittest.main()
