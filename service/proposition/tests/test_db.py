import json
import tempfile
import unittest
from pathlib import Path

from service.proposition import db as dbm


class TestDb(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        schema = Path(__file__).resolve().parents[1] / "schema.sql"
        conn = dbm.connect(self.db_path)
        dbm.init_schema(conn, schema)
        conn.close()

    def tearDown(self) -> None:
        Path(self.db_path).unlink(missing_ok=True)

    def test_insert_and_list(self) -> None:
        conn = dbm.connect(self.db_path)
        pid = dbm.insert_proposal(
            conn,
            cadence="event",
            category="news",
            proposition="Will X happen?",
            outcomes=["Yes", "No"],
            rationale="test",
            source_refs=[{"label": "src", "url": "https://x"}],
            source_item_ids=[],
        )
        rows = dbm.list_proposals(conn, status="pending", limit=10)
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], pid)
        self.assertEqual(json.loads(rows[0]["outcomes_json"]), ["Yes", "No"])

    def test_edit_pending_only(self) -> None:
        conn = dbm.connect(self.db_path)
        pid = dbm.insert_proposal(
            conn,
            cadence="event",
            category="news",
            proposition="A",
            outcomes=["Yes", "No"],
            rationale="r",
            source_refs=[],
            source_item_ids=[],
        )
        ok = dbm.update_proposal_content(conn, pid, proposition="B", outcomes=["Y", "N"])
        self.assertTrue(ok)
        dbm.update_proposal_status(conn, pid, status="approved")
        ok2 = dbm.update_proposal_content(conn, pid, proposition="C", outcomes=["Y", "N"])
        conn.close()
        self.assertFalse(ok2)


if __name__ == "__main__":
    unittest.main()
