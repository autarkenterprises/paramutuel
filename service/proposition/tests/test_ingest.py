import json
import tempfile
import unittest
from pathlib import Path

from service.proposition import db as dbm
from service.proposition import ingest


class TestIngestCalendar(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        self.schema = Path(__file__).resolve().parents[1] / "schema.sql"
        self.sources = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        json.dump({"sources": []}, self.sources)
        self.sources.close()
        self.sources_path = Path(self.sources.name)

    def tearDown(self) -> None:
        Path(self.db_path).unlink(missing_ok=True)
        self.sources_path.unlink(missing_ok=True)

    def test_calendar_dedupes_identical_text(self) -> None:
        conn = dbm.connect(self.db_path)
        dbm.init_schema(conn, self.schema)
        s1 = ingest.run_ingest(conn=conn, sources_path=self.sources_path, include_calendar=True)
        s2 = ingest.run_ingest(conn=conn, sources_path=self.sources_path, include_calendar=True)
        conn.close()
        self.assertGreaterEqual(s1["new_proposals"], 1)
        self.assertEqual(s2["new_proposals"], 0)
        self.assertGreaterEqual(s2["calendar_skipped_duplicates"], s1["new_proposals"])


if __name__ == "__main__":
    unittest.main()
