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
        complements = subs[0].get("complements") or []
        self.assertTrue(
            any("quote_place_bet" in str(c.get("note", "")) for c in complements),
            "manifest should point integrators at MCP quote_place_bet",
        )
        self.assertTrue(
            any("v3" in str(c.get("note", "")).lower() for c in complements)
            or any("protocol_version" in str(c.get("note", "")) for c in complements),
            "manifest MCP note should mention v3 or protocol_version awareness",
        )


if __name__ == "__main__":
    unittest.main()
