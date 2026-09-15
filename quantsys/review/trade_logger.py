"""Trade logger for manual trades and position sync."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from quantsys.review.db_writer import TradeJournalDB

logger = logging.getLogger(__name__)


class TradeLogger:
    """Log trades manually or sync from position tracker.

    Usage::

        logger = TradeLogger()
        logger.log_manual_trade("000001", "BUY", 12.5, 1000, reason="突破买入")
        trades = logger.get_recent_trades(30)
    """

    def __init__(self, db: TradeJournalDB = None):
        self._db = db or TradeJournalDB()

    # -- public API -----------------------------------------------------------

    def log_manual_trade(self, symbol: str, direction: str, price: float,
                          quantity: int, reason: str = "",
                          strategy: str = "", trade_date: str = "",
                          name: str = "", fee: float = 0.0) -> int:
        """Log a manually entered trade.

        Args:
            symbol: Stock/ETF code.
            direction: 'BUY' or 'SELL'.
            price: Execution price.
            quantity: Number of shares/lots.
            reason: Trade rationale.
            strategy: Strategy that generated this trade.
            trade_date: Trade date (default: today).
            name: Stock/ETF name.
            fee: Commission/fees.

        Returns:
            New trade record id.
        """
        return self._db.log_trade(
            symbol=symbol,
            name=name,
            direction=direction,
            price=price,
            quantity=quantity,
            reason=reason,
            strategy=strategy,
            trade_date=trade_date,
            fee=fee,
        )

    def get_recent_trades(self, days: int = 30, symbol: str = None) -> list[dict]:
        """Get recent trades from the journal.

        Args:
            days: Lookback window.
            symbol: Filter by symbol, or None for all.

        Returns:
            List of trade record dicts.
        """
        return self._db.get_trades(days=days, symbol=symbol)

    def get_trade_summary(self, days: int = 30) -> dict:
        """Get a summary of recent trading activity.

        Returns:
            Dict with total_trades, buy_count, sell_count,
            total_buy_amount, total_sell_amount, symbols_traded.
        """
        trades = self.get_recent_trades(days=days)
        if not trades:
            return {
                "total_trades": 0,
                "buy_count": 0,
                "sell_count": 0,
                "total_buy_amount": 0.0,
                "total_sell_amount": 0.0,
                "symbols_traded": [],
            }

        buys = [t for t in trades if t["direction"] == "BUY"]
        sells = [t for t in trades if t["direction"] == "SELL"]
        symbols = list(set(t["symbol"] for t in trades))

        return {
            "total_trades": len(trades),
            "buy_count": len(buys),
            "sell_count": len(sells),
            "total_buy_amount": sum(t["amount"] for t in buys),
            "total_sell_amount": sum(t["amount"] for t in sells),
            "symbols_traded": symbols,
        }
