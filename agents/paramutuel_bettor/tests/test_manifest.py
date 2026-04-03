import json
import unittest
from pathlib import Path


class TestSubagentManifest(unittest.TestCase):
    def test_manifest_parses_and_has_bettor(self) -> None:
        path = Path(__file__).resolve().parents[2] / "subagent-manifest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("version"), 1)
        subs = data.get("subagents")
        self.assertIsInstance(subs, list)
        self.assertTrue(any(s.get("id", "").endswith(".bettor") for s in subs))
        inv = subs[0].get("invocation") or {}
        self.assertEqual(inv.get("type"), "stdio_json")


if __name__ == "__main__":
    unittest.main()
