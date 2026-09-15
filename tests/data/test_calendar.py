"""Tests for TradingCalendar."""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from quantsys.data.sources.cache import CacheManager
from quantsys.data.calendar import TradingCalendar


@pytest.fixture
def calendar_with_data():
    """Create calendar with mock trading days."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = CacheManager(Path(tmpdir))

        # Create mock trading calendar
        dates = pd.date_range("2024-01-01", "2024-12-31", freq="B")
        cal_df = pd.DataFrame({"trade_date": dates})
        cache.put(cal_df, "trade_calendar")

        yield TradingCalendar(cache)


class TestTradingCalendar:
    def test_load(self, calendar_with_data):
        """Test calendar loading."""
        assert calendar_with_data.is_loaded()

    def test_is_trading_day(self, calendar_with_data):
        """Test trading day detection."""
        # Monday Jan 1 2024 is not a business day, so first B day is Jan 2
        assert calendar_with_data.is_trading_day("2024-01-02")  # Tuesday
        assert not calendar_with_data.is_trading_day("2024-01-06")  # Saturday

    def test_next_trading_day(self, calendar_with_data):
        """Test next trading day navigation."""
        next_day = calendar_with_data.next_trading_day("2024-01-02", 5)
        assert isinstance(next_day, pd.Timestamp)
        assert next_day >= pd.Timestamp("2024-01-02")

    def test_trading_days_between(self, calendar_with_data):
        """Test counting trading days between dates."""
        days = calendar_with_data.trading_days_between("2024-01-01", "2024-01-31")
        assert len(days) > 0
        assert all(isinstance(d, pd.Timestamp) for d in days)

    def test_month_end_dates(self, calendar_with_data):
        """Test getting month-end dates."""
        month_ends = calendar_with_data.month_end_dates("2024-01-01", "2024-03-31")
        assert len(month_ends) == 3


class TestTradingCalendarEmpty:
    def test_empty_calendar(self):
        """Test calendar with no data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheManager(Path(tmpdir))
            cal = TradingCalendar(cache)
            assert not cal.is_loaded()
            # Should not crash with empty calendar
            assert cal.is_trading_day("2024-01-02")  # Falls back to True
