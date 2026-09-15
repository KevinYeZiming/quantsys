"""Orchestrate data downloads with caching."""

import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from quantsys.data.sources.akshare import AKShareSource
from quantsys.data.sources.cache import CacheManager

logger = logging.getLogger(__name__)


class DataFetcher:
    """Orchestrates data acquisition from sources with local caching.

    Usage::

        source = AKShareSource(rate_limit=1.0)
        cache = CacheManager(Path("data/raw"))
        fetcher = DataFetcher(source, cache)

        # Incremental daily update
        fetcher.update_stock_daily(incremental=True)

        # Full historical download for specific symbols
        fetcher.update_stock_daily(symbols=["600519", "000858"], start="2020-01-01")
    """

    def __init__(self, source: AKShareSource, cache_dir: Path):
        self.source = source
        self.cache_dir = Path(cache_dir)
        self.cache = CacheManager(self.cache_dir)

    def update_stock_basic(self) -> pd.DataFrame:
        """Update basic stock info (code, name, industry, market cap, etc.)."""
        logger.info("Fetching stock basic info...")
        df = self.source.get_stock_basic()
        self.cache.put(df, "stock_basic")
        logger.info(f"Updated basic info for {len(df)} stocks")
        return df

    def update_stock_daily(
        self,
        symbols: list[str] = None,
        start: str = None,
        end: str = None,
        incremental: bool = True,
    ) -> int:
        """Update daily OHLCV data for stocks.

        Args:
            symbols: List of stock codes to update. If None, updates all A-shares.
            start: Start date YYYYMMDD. Defaults to yesterday if incremental.
            end: End date YYYYMMDD. Defaults to today.
            incremental: If True, only fetch new dates since last cached data point.

        Returns:
            Number of stocks updated.
        """
        if end is None:
            end = datetime.now().strftime("%Y%m%d")

        if symbols is None:
            logger.info("Getting all stock codes...")
            symbols = self.source.get_all_stock_codes()
            logger.info(f"Found {len(symbols)} stocks")

        if incremental and start is None:
            start = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        elif start is None:
            start = "20150101"

        updated = 0
        for symbol in tqdm(symbols, desc="Updating stock daily data"):
            try:
                df = self.source.get_stock_daily(symbol, start=start, end=end)
                if df is not None and not df.empty:
                    self.cache.update_incremental(df, "stock_daily", symbol=symbol)
                    updated += 1
            except Exception as e:
                logger.debug(f"Failed to update {symbol}: {e}")

        logger.info(f"Updated {updated}/{len(symbols)} stocks")
        return updated

    def update_index_daily(
        self, index_codes: list[str] = None, start: str = "20150101", end: str = None
    ) -> int:
        """Update daily OHLCV for market indices.

        Args:
            index_codes: Index codes. Default: CSI 300, CSI 500, SSE Composite, ChiNext, STAR 50.
            start: Start date.
            end: End date.

        Returns:
            Number of indices updated.
        """
        if index_codes is None:
            index_codes = ["000300", "000905", "000001", "399006", "000688"]

        if end is None:
            end = datetime.now().strftime("%Y%m%d")

        updated = 0
        for code in tqdm(index_codes, desc="Updating index data"):
            try:
                df = self.source.get_index_daily(code, start=start, end=end)
                if df is not None and not df.empty:
                    self.cache.put(df, "index_daily", symbol=code)
                    updated += 1
            except Exception as e:
                logger.debug(f"Failed to update index {code}: {e}")

        logger.info(f"Updated {updated}/{len(index_codes)} indices")
        return updated

    def update_etf_daily(
        self, etf_codes: list[str] = None, start: str = "20150101", end: str = None
    ) -> int:
        """Update daily OHLCV for ETFs.

        Args:
            etf_codes: ETF codes. If None, uses default ETF basket.
            start: Start date.
            end: End date.

        Returns:
            Number of ETFs updated.
        """
        if etf_codes is None:
            etf_codes = _default_etf_basket()

        if end is None:
            end = datetime.now().strftime("%Y%m%d")

        updated = 0
        for code in tqdm(etf_codes, desc="Updating ETF data"):
            try:
                df = self.source.get_etf_daily(code, start=start, end=end)
                if df is not None and not df.empty:
                    self.cache.put(df, "etf_daily", symbol=code)
                    updated += 1
            except Exception as e:
                logger.debug(f"Failed to update ETF {code}: {e}")

        logger.info(f"Updated {updated}/{len(etf_codes)} ETFs")
        return updated

    def update_macro(self) -> dict[str, pd.DataFrame]:
        """Update macro-economic indicators."""
        indicators = ["cpi", "ppi", "pmi", "money_supply", "shibor", "gdp"]
        results = {}
        for ind in tqdm(indicators, desc="Updating macro data"):
            try:
                df = self.source.get_macro(ind)
                if df is not None and not df.empty:
                    self.cache.put(df, "macro", symbol=ind)
                    results[ind] = df
            except Exception as e:
                logger.warning(f"Failed to update macro indicator {ind}: {e}")
        return results

    def update_trade_calendar(self) -> pd.DataFrame:
        """Update A-share trading calendar."""
        logger.info("Updating trading calendar...")
        df = self.source.get_trade_calendar()
        if df is not None and not df.empty:
            self.cache.put(df, "trade_calendar")
        return df

    def update_all(self, incremental: bool = True) -> dict[str, int]:
        """Run all data updates.

        Returns:
            Dictionary mapping update type to count of items updated.
        """
        results = {}

        results["calendar"] = 1 if self.update_trade_calendar() is not None else 0
        results["stock_basic"] = 1 if self.update_stock_basic() is not None else 0
        results["stock_daily"] = self.update_stock_daily(incremental=incremental)
        results["index_daily"] = self.update_index_daily()
        results["etf_daily"] = self.update_etf_daily()
        results["macro"] = len(self.update_macro())

        return results


def _default_etf_basket() -> list[str]:
    """Default ETF basket for rotation strategy.

    Covers broad indices, styles, sectors, bonds, and commodities.
    """
    return [
        # Broad market (宽基)
        "510300",  # 沪深300ETF
        "510500",  # 中证500ETF
        "159915",  # 创业板ETF
        "588000",  # 科创50ETF
        "510050",  # 上证50ETF
        "159949",  # 创业板50ETF
        # Style (风格)
        "510880",  # 红利ETF
        "159905",  # 深红利ETF
        # Sector (行业)
        "512880",  # 证券ETF
        "512010",  # 医药ETF
        "159995",  # 芯片ETF
        "515790",  # 光伏ETF
        "512660",  # 军工ETF
        "512690",  # 酒ETF
        "512800",  # 银行ETF
        "516510",  # 云计算ETF
        # Bond (债券)
        "511260",  # 十年国债ETF
        "511220",  # 城投债ETF
        # Commodity (商品)
        "518880",  # 黄金ETF
        # Money market (货币)
        "511880",  # 银华日利ETF
    ]
