"""Trading calendar for Chinese A-share market.

Handles irregular holidays (Lunar New Year, National Day, etc.) and
provides date navigation utilities.
"""

import logging
from pathlib import Path

import pandas as pd

from quantsys.data.sources.cache import CacheManager

logger = logging.getLogger(__name__)


class TradingCalendar:
    """A-share trading calendar management.

    Usage::

        cal = TradingCalendar(cache_dir)
        cal.is_trading_day("2024-01-15")  # True if trading day
        cal.next_trading_day("2024-01-15", 5)  # 5 trading days later
    """

    def __init__(self, cache_manager: CacheManager):
        self._cache = cache_manager
        self._calendar: pd.DatetimeIndex | None = None
        self._load()

    def _load(self):
        """Load trading calendar from cache."""
        df = self._cache.get("trade_calendar")
        if df is not None and not df.empty:
            date_col = "trade_date" if "trade_date" in df.columns else df.columns[0]
            self._calendar = pd.DatetimeIndex(pd.to_datetime(df[date_col]).sort_values())
            logger.info(f"Loaded trading calendar: {len(self._calendar)} days")
        else:
            logger.warning("No trading calendar found in cache")

    def is_loaded(self) -> bool:
        """Check if calendar is loaded."""
        return self._calendar is not None and len(self._calendar) > 0

    def is_trading_day(self, date: str | pd.Timestamp) -> bool:
        """Check if a date is a trading day."""
        if not self.is_loaded():
            return True  # Assume trading day if no calendar
        date = pd.Timestamp(date)
        return date in self._calendar

    def next_trading_day(self, date: str | pd.Timestamp, n: int = 1) -> pd.Timestamp:
        """Get the nth trading day after (or before) a given date.

        Args:
            date: Reference date.
            n: Number of trading days forward (positive) or backward (negative).

        Returns:
            The nth trading day.
        """
        if not self.is_loaded():
            return pd.Timestamp(date) + pd.Timedelta(days=n)

        date = pd.Timestamp(date)

        if n >= 0:
            future = self._calendar[self._calendar >= date]
            if len(future) > n:
                return future[n]
            return future[-1] if len(future) > 0 else date
        else:
            # Go backward
            past = self._calendar[self._calendar <= date]
            n = abs(n)
            if len(past) > n:
                return past[-(n + 1)]
            return past[0] if len(past) > 0 else date

    def prev_trading_day(self, date: str | pd.Timestamp, n: int = 1) -> pd.Timestamp:
        """Get the nth previous trading day."""
        return self.next_trading_day(date, n=-n)

    def trading_days_between(self, start: str | pd.Timestamp, end: str | pd.Timestamp) -> list[pd.Timestamp]:
        """Get all trading days between start and end (inclusive)."""
        if not self.is_loaded():
            return pd.date_range(start, end, freq="B").tolist()

        start = pd.Timestamp(start)
        end = pd.Timestamp(end)
        mask = (self._calendar >= start) & (self._calendar <= end)
        return self._calendar[mask].tolist()

    def month_end_dates(self, start: str, end: str) -> list[pd.Timestamp]:
        """Get the last trading day of each month between start and end."""
        all_days = self.trading_days_between(start, end)
        if not all_days:
            return []

        df = pd.DataFrame({"date": all_days})
        df["year_month"] = df["date"].dt.to_period("M")
        return df.groupby("year_month")["date"].max().tolist()

    def month_start_dates(self, start: str, end: str) -> list[pd.Timestamp]:
        """Get the first trading day of each month between start and end."""
        all_days = self.trading_days_between(start, end)
        if not all_days:
            return []

        df = pd.DataFrame({"date": all_days})
        df["year_month"] = df["date"].dt.to_period("M")
        return df.groupby("year_month")["date"].min().tolist()

    def days_between(self, start: str | pd.Timestamp, end: str | pd.Timestamp) -> int:
        """Count trading days between two dates."""
        days = self.trading_days_between(start, end)
        return len(days)
