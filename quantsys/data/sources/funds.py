"""Mutual fund (场外基金) data source with local persistence.

Extends the system's data layer to cover open-end funds (申赎型),
which the original system only fetched ad-hoc inside the position
tracker. Provides:

    - Unit NAV history (单位净值走势)
    - Accumulated NAV history (累计净值走势, includes dividend effect)
    - Fund basic info (类型/成立日/规模/费率/经理)

All data is normalized to standard columns and persisted through
CacheManager as ``fund_nav`` / ``fund_accum_nav`` / ``fund_info``
cache types, with incremental update support.

AKShare is imported lazily inside calls so the module (and its
tests) works without network access or the akshare package.
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# Standard column names for fund NAV data
NAV_COLUMN_MAP = {
    "净值日期": "date",
    "单位净值": "nav",
    "日增长率": "daily_return_pct",
    "累计净值": "accumulated_nav",
    "分红送配": "dividend",
}


class FundSource:
    """Open-end fund data source with Parquet persistence.

    Usage::

        source = FundSource(cache)
        nav = source.update_nav("017103")       # incremental, cached
        info = source.update_info("017103")
    """

    name = "fund"

    def __init__(self, cache=None):
        self._cache = cache

    # -- Internal helpers -------------------------------------------------

    def _call(self, api_name: str, **kwargs) -> pd.DataFrame:
        """Call an AKShare API by name, lazily imported, errors normalized."""
        try:
            import akshare as ak  # lazy: no hard dependency at import time
        except ImportError:
            logger.error("akshare is required for fund data: pip install akshare")
            return pd.DataFrame()

        func = getattr(ak, api_name, None)
        if func is None:
            logger.error(f"akshare has no API named {api_name}")
            return pd.DataFrame()

        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df = func(**kwargs)
            return df if df is not None else pd.DataFrame()
        except Exception as e:
            logger.warning(f"AKShare call failed ({api_name} {kwargs}): {e}")
            return pd.DataFrame()

    @staticmethod
    def _normalize_nav(df: pd.DataFrame) -> pd.DataFrame:
        """Normalize NAV DataFrame to standard schema indexed by date."""
        if df.empty:
            return df
        df = df.rename(columns=NAV_COLUMN_MAP)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
        for col in ("nav", "accumulated_nav", "daily_return_pct"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        keep = [c for c in ("nav", "accumulated_nav", "daily_return_pct", "dividend")
                if c in df.columns]
        return df[keep]

    # -- Public API --------------------------------------------------------

    def get_nav(self, symbol: str) -> pd.DataFrame:
        """Fetch unit NAV history (uncached raw call)."""
        df = self._call("fund_open_fund_info_em",
                        symbol=symbol, indicator="单位净值走势")
        return self._normalize_nav(df)

    def get_accumulated_nav(self, symbol: str) -> pd.DataFrame:
        """Fetch accumulated NAV history (reflects dividends)."""
        df = self._call("fund_open_fund_info_em",
                        symbol=symbol, indicator="累计净值走势")
        return self._normalize_nav(df)

    def get_info(self, symbol: str) -> pd.DataFrame:
        """Fetch fund basic info as a one-row DataFrame.

        AKShare returns a two-column (item, value) table; transpose it
        into a wide one-row record keyed by item name.
        """
        df = self._call("fund_individual_basic_info_xq", symbol=symbol)
        if df.empty or len(df.columns) < 2:
            return pd.DataFrame()
        item_col, value_col = df.columns[0], df.columns[1]
        record = {str(k): v for k, v in zip(df[item_col], df[value_col])}
        record["symbol"] = symbol
        return pd.DataFrame([record])

    def update_nav(self, symbol: str) -> pd.DataFrame:
        """Incrementally update cached unit NAV for a fund.

        Returns the merged (cached + new) DataFrame.
        """
        fresh = self.get_nav(symbol)
        if fresh.empty:
            logger.warning(f"No NAV data returned for fund {symbol}")
            if self._cache is not None:
                cached = self._cache.get("fund_nav", symbol=symbol)
                return cached if cached is not None else pd.DataFrame()
            return pd.DataFrame()

        if self._cache is None:
            return fresh
        return self._cache.update_incremental(fresh, "fund_nav", symbol=symbol)

    def update_accumulated_nav(self, symbol: str) -> pd.DataFrame:
        """Incrementally update cached accumulated NAV."""
        fresh = self.get_accumulated_nav(symbol)
        if fresh.empty:
            if self._cache is not None:
                cached = self._cache.get("fund_accum_nav", symbol=symbol)
                return cached if cached is not None else pd.DataFrame()
            return pd.DataFrame()
        if self._cache is None:
            return fresh
        return self._cache.update_incremental(
            fresh, "fund_accum_nav", symbol=symbol
        )

    def update_info(self, symbol: str) -> pd.DataFrame:
        """Refresh cached fund basic info snapshot."""
        fresh = self.get_info(symbol)
        if fresh.empty:
            if self._cache is not None:
                cached = self._cache.get("fund_info", symbol=symbol)
                return cached if cached is not None else pd.DataFrame()
            return pd.DataFrame()
        if self._cache is None:
            return fresh
        self._cache.put(fresh, "fund_info", symbol=symbol)
        return fresh

    def update_all(self, symbol: str) -> dict:
        """Update NAV, accumulated NAV and info in one call.

        Returns dict of DataFrames keyed by 'nav', 'accum_nav', 'info'.
        """
        return {
            "nav": self.update_nav(symbol),
            "accum_nav": self.update_accumulated_nav(symbol),
            "info": self.update_info(symbol),
        }
