"""SQLite DDL schema for the trade journal database.

Four tables:
  - trade_log: individual trade records
  - daily_snapshot: end-of-day portfolio + market summary
  - market_snapshot: per-index daily metrics
  - decision_log: AI/human review decisions and action items
"""

DDL_TRADE_LOG = """
CREATE TABLE IF NOT EXISTS trade_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    name            TEXT    DEFAULT '',
    direction       TEXT    NOT NULL CHECK(direction IN ('BUY', 'SELL')),
    price           REAL    NOT NULL,
    quantity        INTEGER NOT NULL,
    amount          REAL    NOT NULL,
    fee             REAL    DEFAULT 0.0,
    reason          TEXT    DEFAULT '',
    strategy        TEXT    DEFAULT '',
    trade_date      TEXT    NOT NULL,
    created_at      TEXT    DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_trade_log_date ON trade_log(trade_date);
CREATE INDEX IF NOT EXISTS idx_trade_log_symbol ON trade_log(symbol);
"""

DDL_DAILY_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS daily_snapshot (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    date              TEXT    NOT NULL UNIQUE,
    total_asset       REAL    DEFAULT 0.0,
    total_cost        REAL    DEFAULT 0.0,
    total_pnl         REAL    DEFAULT 0.0,
    daily_pnl         REAL    DEFAULT 0.0,
    cash              REAL    DEFAULT 0.0,
    positions_json    TEXT    DEFAULT '[]',
    market_breadth    TEXT    DEFAULT '',
    dominant_regime   TEXT    DEFAULT '',
    volatility_regime TEXT    DEFAULT '',
    signals_json      TEXT    DEFAULT '[]',
    notes             TEXT    DEFAULT '',
    created_at        TEXT    DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_daily_snapshot_date ON daily_snapshot(date);
"""

DDL_MARKET_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS market_snapshot (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT    NOT NULL,
    index_code    TEXT    NOT NULL,
    index_name    TEXT    DEFAULT '',
    close         REAL    DEFAULT 0.0,
    change_1d     REAL    DEFAULT 0.0,
    change_5d     REAL    DEFAULT 0.0,
    change_20d    REAL    DEFAULT 0.0,
    volatility_20d REAL   DEFAULT 0.0,
    trend         TEXT    DEFAULT '',
    regime        TEXT    DEFAULT '',
    volume_ratio  REAL    DEFAULT 0.0,
    position_52w  REAL    DEFAULT 0.0,
    UNIQUE(date, index_code)
);
CREATE INDEX IF NOT EXISTS idx_market_snapshot_date ON market_snapshot(date);
CREATE INDEX IF NOT EXISTS idx_market_snapshot_code ON market_snapshot(index_code);
"""

DDL_DECISION_LOG = """
CREATE TABLE IF NOT EXISTS decision_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    date             TEXT    NOT NULL,
    decision_type    TEXT    NOT NULL CHECK(decision_type IN ('daily_review', 'weekly_review', 'adjustment')),
    summary          TEXT    DEFAULT '',
    reasoning        TEXT    DEFAULT '',
    action_items_json TEXT   DEFAULT '[]',
    report_path      TEXT    DEFAULT '',
    created_at       TEXT    DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_decision_log_date ON decision_log(date);
CREATE INDEX IF NOT EXISTS idx_decision_log_type ON decision_log(decision_type);
"""

ALL_DDL = [DDL_TRADE_LOG, DDL_DAILY_SNAPSHOT, DDL_MARKET_SNAPSHOT, DDL_DECISION_LOG]
