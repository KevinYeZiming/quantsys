"""Record daily market snapshots to the trade journal database."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from quantsys.advisor.index_analyzer import IndexAnalyzer, IndexDashboard
from quantsys.review.db_writer import TradeJournalDB

logger = logging.getLogger(__name__)


class MarketRecorder:
    """Record daily index metrics and market context to SQLite.

    Wraps IndexAnalyzer to capture full market state at each trading day
    for later review and trend analysis.

    Usage::

        recorder = MarketRecorder()
        recorder.record_today()
        history = recorder.get_market_history(30)
    """

    def __init__(self, db: TradeJournalDB = None, analyzer: IndexAnalyzer = None):
        self._db = db or TradeJournalDB()
        self._analyzer = analyzer or IndexAnalyzer()

    # -- public API -----------------------------------------------------------

    def record_today(self, date: str = None) -> int:
        """Record market snapshot for all tracked indices at a given date.

        Args:
            date: Target date. Defaults to today.

        Returns:
            Number of index snapshots recorded.
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        dash = self._analyzer.dashboard(date)
        if not dash.indices:
            logger.warning(f"No index data for {date}")
            return 0

        # Record each index
        count = 0
        for code, snap in dash.indices.items():
            self._db.record_market_snapshot(
                date=date,
                index_code=code,
                index_name=snap.name,
                close=snap.close,
                change_1d=snap.change_1d,
                change_5d=snap.change_5d,
                change_20d=snap.change_20d,
                volatility_20d=snap.volatility_20d,
                trend=snap.trend,
                regime=snap.regime,
                volume_ratio=snap.volume_ratio,
                position_52w=snap.position_52w,
            )
            count += 1

        # Also update daily_snapshot with aggregate market context
        self._db.record_daily_snapshot(
            date=date,
            market_breadth=dash.market_breadth,
            dominant_regime=dash.dominant_regime,
            volatility_regime=dash.volatility_regime,
            signals=dash.signals,
        )

        logger.info(f"Recorded {count} index snapshots + market context for {date}")
        return count

    def get_market_history(self, days: int = 30,
                            index_code: str = None) -> list[dict]:
        """Get recent market snapshots for trend analysis.

        Args:
            days: Lookback window.
            index_code: Filter by index, or None for all.

        Returns:
            List of market snapshot dicts.
        """
        return self._db.get_market_snapshots(days=days, index_code=index_code)

    def get_dashboard(self, date: str = None) -> IndexDashboard:
        """Convenience: get current IndexDashboard."""
        return self._analyzer.dashboard(date)
