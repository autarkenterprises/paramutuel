-- Proposition Service: ingested items and operator-approved wager candidates.

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS source_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id TEXT NOT NULL,
  external_id TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  link TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  published_at INTEGER,
  fetched_at INTEGER NOT NULL,
  raw_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(source_id, external_id)
);

CREATE TABLE IF NOT EXISTS proposals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending', 'approved', 'rejected', 'dispatched', 'dispatch_failed')),
  cadence TEXT NOT NULL DEFAULT 'event',
  category TEXT NOT NULL DEFAULT 'general',
  proposition TEXT NOT NULL,
  outcomes_json TEXT NOT NULL,
  rationale TEXT NOT NULL DEFAULT '',
  source_refs_json TEXT NOT NULL DEFAULT '[]',
  source_item_ids_json TEXT NOT NULL DEFAULT '[]',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  approved_at INTEGER,
  dispatched_at INTEGER,
  tx_hint TEXT,
  dispatch_error TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
CREATE INDEX IF NOT EXISTS idx_proposals_created ON proposals(created_at DESC);
