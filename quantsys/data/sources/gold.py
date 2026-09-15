"""Gold data source with local persistence (黄金数据).

Covers the two mainstream gold price tracks for Chinese investors:

    - SGE spot  (上海黄金交易所现货, e.g. Au99.99) — the onshore
                  benchmark, via ``ak.spot_hist_sge``
    - Gold ETF  (黄金ETF, e.g. 518880) — exchange-traded, tracks
                  domestic gold price with T+0, via the ETF history API

Both are persisted through CacheManager as ``gold_spot`` / ``gold_etf``
cache types with incremental update support. A small default basket of
the most-watched symbols is provided in config/assets.yaml.

AKShare is imported lazily inside calls so the module (and its tests)
works without network access or the akshare package.
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# Shanghai Gold Exchange spot symbols commonly tracked
DEFAULT_SPOT_SYMBOLS = ["Au99.99", "Au99.95", "Au100g", "Pt99.95"]

# Popular gold ETFs (A-share listed)
DEFAULT_GOLD_ETFS = ["518880",  # 华安黄金ETF
                     "159934",  # 易方达黄金ETF
                     "518800"]  # 国泰黄金ETF

SPOT_COLUMN_MAP = {
    "日期": "date",
    "开盘价": "open",
    "最高价": "high",
    "最低价": "low",
    "收盘价": "close",
    "涨跌额": "change",
    "涨跌幅": "pct_change",
    "均价": "vwap",
}


class GoldSource:
    """Gold spot & ETF data source with Parquet persistence.

    Usage::

        source = GoldSource(cache)
        spot = source.update_spot("Au99.99")
        etf = source.update_etf("518880")
    """

    name = "gold"

    def __init__(self, cache=None):
        self._cache = cache

    # -- Internal helpers -------------------------------------------------

    def _call(self, api_name: str, **kwargs) -> pd.DataFrame:
        """Call an AKShare API by name, lazily imported, errors normalized."""
        try:
            import akshare as ak  # lazy import
        except ImportError:
            logger.error("akshare is required for gold data: pip install akshare")
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
    def _normalize(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.rename(columns=col_map)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
        elif "日期" in df.columns:  # fallback: unmapped date column
            df["日期"] = pd.to_datetime(df["日期"])
            df = df.set_index("日期").sort_index()
            df.index.name = "date"
        return df

    def _cached(self, cache_type: str, symbol: str) -> pd.DataFrame:
        if self._cache is None:
            return pd.DataFrame()
        df = self._cache.get(cache_type, symbol=symbol)
        return df if df is not None else pd.DataFrame()

    # -- Public API --------------------------------------------------------

    def get_spot(self, symbol: str = "Au99.99") -> pd.DataFrame:
        """Fetch SGE spot history (uncached raw call)."""
        df = self._call("spot_hist_sge", symbol=symbol)
        return self._normalize(df, SPOT_COLUMN_MAP)

    def get_etf(self, etf_code: str) -> pd.DataFrame:
        """Fetch gold ETF daily OHLCV (uncached raw call)."""
        df = self._call("fund_etf_hist_em", symbol=etf_code, period="daily",
                        start_date="20100101", end_date="20991231", adjust="qfq")
        col_map = {"日期": "date", "开盘": "open", "最高": "high", "最低": "low",
                   "收盘": "close", "成交量": "volume", "成交额": "amount"}
        return self._normalize(df, col_map)

    def update_spot(self, symbol: str = "Au99.99") -> pd.DataFrame:
        """Incrementally update cached SGE spot series."""
        fresh = self.get_spot(symbol)
        if fresh.empty:
            logger.warning(f"No spot data returned for {symbol}")
            return self._cached("gold_spot", symbol)
        if self._cache is None:
            return fresh
        return self._cache.update_incremental(fresh, "gold_spot", symbol=symbol)

    def update_etf(self, etf_code: str) -> pd.DataFrame:
        """Incrementally update cached gold ETF series."""
        fresh = self.get_etf(etf_code)
        if fresh.empty:
            logger.warning(f"No ETF data returned for {etf_code}")
            return self._cached("gold_etf", etf_code)
        if self._cache is None:
            return fresh
        return self._cache.update_incremental(fresh, "gold_etf", symbol=etf_code)

    def update_all(self, spot_symbols: list[str] | None = None,
                   etf_codes: list[str] | None = None) -> dict:
        """Update the whole gold basket.

        Returns dict keyed 'spot:{sym}' / 'etf:{code}' with merged frames.
        """
        spot_symbols = spot_symbols or DEFAULT_SPOT_SYMBOLS
        etf_codes = etf_codes or DEFAULT_GOLD_ETFS
        out = {}
        for s in spot_symbols:
            out[f"spot:{s}"] = self.update_spot(s)
        for c in etf_codes:
            out[f"etf:{c}"] = self.update_etf(c)
        return out
