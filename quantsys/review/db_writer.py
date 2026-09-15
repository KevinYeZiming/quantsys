"""SQLite trade journal database with WAL mode and typed accessors."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from quantsys.review.db_schema import ALL_DDL

logger = logging.getLogger(__name__)

DEFAULT_DB_NAME = "trade_journal.db"


class TradeJournalDB:
    """SQLite-backed trade journal with WAL mode for concurrent access.

    Usage::

        db = TradeJournalDB()
        db.log_trade("000001", "BUY", 12.5, 1000, reason="突破买入")
        trades = db.get_trades(days=30)
    """

    def __init__(self, db_path: str | Path = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "data" / DEFAULT_DB_NAME
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._run_ddl()

    # -- public API -----------------------------------------------------------

    def log_trade(self, symbol: str, direction: str, price: float,
                  quantity: int, reason: str = "", strategy: str = "",
                  trade_date: str = "", name: str = "", fee: float = 0.0) -> int:
        """Insert a trade record. Returns the new row id."""
        amount = price * quantity
        if not trade_date:
            from datetime import datetime
            trade_date = datetime.now().strftime("%Y-%m-%d")

        cur = self._conn.execute(
            """INSERT INTO trade_log (symbol, name, direction, price, quantity,
               amount, fee, reason, strategy, trade_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol, name, direction.upper(), price, quantity, amount,
             fee, reason, strategy, trade_date),
        )
        self._conn.commit()
        logger.info(f"Trade logged: {direction} {symbol} {quantity}@{price}")
        return cur.lastrowid

    def record_daily_snapshot(self, date: str, total_asset: float = 0.0,
                               total_cost: float = 0.0, total_pnl: float = 0.0,
                               daily_pnl: float = 0.0, cash: float = 0.0,
                               positions: list[dict] = None,
                               market_breadth: str = "",
                               dominant_regime: str = "",
                               volatility_regime: str = "",
                               signals: list[str] = None,
                               notes: str = "") -> int:
        """Upsert daily portfolio + market summary snapshot."""
        positions_json = json.dumps(positions or [], ensure_ascii=False)
        signals_json = json.dumps(signals or [], ensure_ascii=False)

        cur = self._conn.execute(
            """INSERT OR REPLACE INTO daily_snapshot
               (date, total_asset, total_cost, total_pnl, daily_pnl, cash,
                positions_json, market_breadth, dominant_regime,
                volatility_regime, signals_json, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (date, total_asset, total_cost, total_pnl, daily_pnl, cash,
             positions_json, market_breadth, dominant_regime,
             volatility_regime, signals_json, notes),
        )
        self._conn.commit()
        return cur.lastrowid

    def record_market_snapshot(self, date: str, index_code: str,
                                index_name: str = "", close: float = 0.0,
                                change_1d: float = 0.0, change_5d: float = 0.0,
                                change_20d: float = 0.0,
                                volatility_20d: float = 0.0,
                                trend: str = "", regime: str = "",
                                volume_ratio: float = 0.0,
                                position_52w: float = 0.0) -> int:
        """Insert or replace a single-index market snapshot."""
        cur = self._conn.execute(
            """INSERT OR REPLACE INTO market_snapshot
               (date, index_code, index_name, close, change_1d, change_5d,
                change_20d, volatility_20d, trend, regime, volume_ratio,
                position_52w)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (date, index_code, index_name, close, change_1d, change_5d,
             change_20d, volatility_20d, trend, regime, volume_ratio,
             position_52w),
        )
        self._conn.commit()
        return cur.lastrowid

    def log_decision(self, date: str, decision_type: str, summary: str = "",
                     reasoning: str = "", action_items: list[str] = None,
                     report_path: str = "") -> int:
        """Log an AI or human review decision."""
        action_items_json = json.dumps(action_items or [], ensure_ascii=False)
        cur = self._conn.execute(
            """INSERT INTO decision_log
               (date, decision_type, summary, reasoning, action_items_json,
                report_path)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (date, decision_type, summary, reasoning, action_items_json,
             report_path),
        )
        self._conn.commit()
        return cur.lastrowid

    # -- query methods --------------------------------------------------------

    def get_trades(self, days: int = 30, symbol: str = None) -> list[dict]:
        """Get recent trade records, optionally filtered by symbol."""
        if symbol:
            rows = self._conn.execute(
                """SELECT * FROM trade_log
                   WHERE trade_date >= date('now', ?) AND symbol = ?
                   ORDER BY trade_date DESC, id DESC""",
                (f"-{days} days", symbol),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM trade_log
                   WHERE trade_date >= date('now', ?)
                   ORDER BY trade_date DESC, id DESC""",
                (f"-{days} days",),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_daily_snapshots(self, days: int = 30) -> list[dict]:
        """Get recent daily snapshots."""
        rows = self._conn.execute(
            """SELECT * FROM daily_snapshot
               WHERE date >= date('now', ?)
               ORDER BY date DESC""",
            (f"-{days} days",),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_latest_snapshot(self) -> dict | None:
        """Get the most recent daily snapshot."""
        row = self._conn.execute(
            "SELECT * FROM daily_snapshot ORDER BY date DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def get_market_snapshots(self, days: int = 30,
                              index_code: str = None) -> list[dict]:
        """Get recent market snapshots, optionally filtered by index."""
        if index_code:
            rows = self._conn.execute(
                """SELECT * FROM market_snapshot
                   WHERE date >= date('now', ?) AND index_code = ?
                   ORDER BY date DESC""",
                (f"-{days} days", index_code),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM market_snapshot
                   WHERE date >= date('now', ?)
                   ORDER BY date DESC, index_code""",
                (f"-{days} days",),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_decisions(self, days: int = 30,
                       decision_type: str = None) -> list[dict]:
        """Get recent decision logs."""
        if decision_type:
            rows = self._conn.execute(
                """SELECT * FROM decision_log
                   WHERE date >= date('now', ?) AND decision_type = ?
                   ORDER BY date DESC""",
                (f"-{days} days", decision_type),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM decision_log
                   WHERE date >= date('now', ?)
                   ORDER BY date DESC""",
                (f"-{days} days",),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- maintenance ----------------------------------------------------------

    def close(self):
        """Close the database connection."""
        self._conn.close()

    def _run_ddl(self):
        """Execute all DDL statements."""
        for ddl in ALL_DDL:
            self._conn.executescript(ddl)
