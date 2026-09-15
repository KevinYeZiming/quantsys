"""Abstract base class for data source adapters."""

from abc import ABC, abstractmethod

import pandas as pd


class DataSource(ABC):
    """Abstract data source adapter.

    All data adapters (AKShare, Tushare, etc.) must implement this interface.
    """

    name: str = "base"

    @abstractmethod
    def get_stock_daily(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """Get daily OHLCV for a single stock."""

    @abstractmethod
    def get_stock_basic(self) -> pd.DataFrame:
        """Get basic info for all A-share stocks (code, name, industry, list_date, etc.)."""

    @abstractmethod
    def get_index_daily(self, index_code: str, start: str, end: str) -> pd.DataFrame:
        """Get daily OHLCV for an index."""

    @abstractmethod
    def get_etf_daily(self, etf_code: str, start: str, end: str) -> pd.DataFrame:
        """Get daily OHLCV for an ETF."""

    @abstractmethod
    def get_financials(self, symbol: str) -> pd.DataFrame:
        """Get quarterly financial statements for a stock."""

    @abstractmethod
    def get_money_flow(self, symbol: str) -> pd.DataFrame:
        """Get capital flow data for a stock."""

    @abstractmethod
    def get_macro(self, indicator: str) -> pd.DataFrame:
        """Get macro-economic indicator data."""

    @abstractmethod
    def get_trade_calendar(self) -> pd.DataFrame:
        """Get A-share trading calendar."""

    @abstractmethod
    def get_index_constituents(self, index_code: str) -> list[str]:
        """Get constituent stocks of an index."""

    @abstractmethod
    def get_industry_classification(self) -> pd.DataFrame:
        """Get Shenwan industry classification for all stocks."""

    @abstractmethod
    def get_all_stock_codes(self) -> list[str]:
        """Get list of all A-share stock codes."""
