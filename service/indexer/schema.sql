PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS markets (
  market_address TEXT PRIMARY KEY,
  factory_address TEXT NOT NULL,
  proposer TEXT NOT NULL,
  resolver TEXT NOT NULL,
  betting_closer TEXT NOT NULL,
  resolution_closer TEXT NOT NULL,
  collateral_token TEXT NOT NULL,
  betting_close_time INTEGER NOT NULL,
  resolution_window INTEGER NOT NULL,
  resolution_deadline INTEGER NOT NULL,
  betting_closed_by_authority INTEGER NOT NULL DEFAULT 0,
  betting_closed_at INTEGER,
  resolution_window_closed INTEGER NOT NULL DEFAULT 0,
  resolution_window_closed_at INTEGER,
  state TEXT NOT NULL CHECK(state IN ('OPEN','RESOLVED','RETRACTED')),
  created_block INTEGER NOT NULL,
  created_tx_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_totals (
  market_address TEXT PRIMARY KEY,
  total_pot TEXT NOT NULL DEFAULT '0',
  total_fee_bps TEXT NOT NULL DEFAULT '0',
  winning_outcome TEXT,
  total_winning_stake TEXT,
  FOREIGN KEY(market_address) REFERENCES markets(market_address)
);

CREATE TABLE IF NOT EXISTS market_outcomes (
  market_address TEXT NOT NULL,
  outcome_index INTEGER NOT NULL,
  outcome_total TEXT NOT NULL DEFAULT '0',
  PRIMARY KEY (market_address, outcome_index),
  FOREIGN KEY(market_address) REFERENCES markets(market_address)
);

CREATE TABLE IF NOT EXISTS events_log (
  event_id TEXT PRIMARY KEY,
  market_address TEXT,
  event_name TEXT NOT NULL,
  block_number INTEGER NOT NULL,
  tx_hash TEXT NOT NULL,
  log_index INTEGER NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_markets_state ON markets(state);
CREATE INDEX IF NOT EXISTS idx_markets_deadline ON markets(resolution_deadline);
CREATE INDEX IF NOT EXISTS idx_events_market ON events_log(market_address, block_number, log_index);

