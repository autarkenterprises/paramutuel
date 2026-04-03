import unittest

from service.proposition import dispatch as dispatchm


class TestDispatchPreview(unittest.TestCase):
    def test_preview_includes_dispatch_fields(self) -> None:
        row = {
            "id": 1,
            "proposition": "P?",
            "outcomes_json": '["Yes","No"]',
            "cadence": "event",
            "category": "news",
            "rationale": "r",
            "source_refs_json": "[]",
            "status": "dispatch_failed",
            "created_at": 100,
            "updated_at": 200,
            "tx_hint": "cast output",
            "dispatch_error": "revert",
        }
        d = dispatchm.proposal_to_preview_dict(row)
        self.assertEqual(d["tx_hint"], "cast output")
        self.assertEqual(d["dispatch_error"], "revert")
        self.assertEqual(d["created_at"], 100)


if __name__ == "__main__":
    unittest.main()
