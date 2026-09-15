"""AKShare data source adapter.

AKShare is a free, open-source financial data interface for Chinese markets.
No registration required. Documentation: https://akshare.akfamily.xyz/
"""

import logging
import time

import pandas as pd

from quantsys.data.sources.base import DataSource

logger = logging.getLogger(__name__)


class _LazyAK:
    """Lazy proxy for akshare: imports on first attribute access.

    Keeps the package importable (and tests runnable) in environments
    without akshare installed; a clear error is raised only when a data
    API is actually called.
    """

    def __getattr__(self, name):
        try:
            import importlib
            mod = importlib.import_module("akshare")
        except ImportError as e:
            raise ImportError(
                "akshare is required for live market data "
                "(pip install akshare)"
            ) from e
        return getattr(mod, name)


ak = _LazyAK()

# Standard column names for daily OHLCV data
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume", "amount", "turnover"]

# Map AKShare column names to standard names
AKSHARE_COLUMN_MAP = {
    "日期": "date",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
    "成交额": "amount",
    "换手率": "turnover",
    "振幅": "amplitude",
    "涨跌幅": "pct_change",
    "涨跌额": "change",
}


class AKShareSource(DataSource):
    """AKShare data source for Chinese A-share market data."""

    name = "akshare"

    def __init__(self, rate_limit: float = 1.0, retry_count: int = 3):
        self.rate_limit = rate_limit
        self.retry_count = retry_count
        self._last_call = 0.0

    def _rate_limit_wait(self):
        """Enforce rate limiting between API calls."""
        elapsed = time.time() - self._last_call
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_call = time.time()

    def _retry_call(self, func, *args, **kwargs):
        """Call a function with retry logic."""
        for attempt in range(self.retry_count):
            try:
                self._rate_limit_wait()
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == self.retry_count - 1:
                    raise
                logger.warning(
                    f"AKShare call failed (attempt {attempt + 1}/{self.retry_count}): {e}"
                )
                time.sleep(2 ** attempt)

    def get_stock_daily(
        self, symbol: str, start: str = "20150101", end: str = "20991231"
    ) -> pd.DataFrame:
        """Get daily OHLCV for a single A-share stock.

        Uses Sina API (stock_zh_a_daily) which is more reliable than East Money.
        Falls back to East Money API if Sina fails.

        Args:
            symbol: Stock code, e.g. '600519'.
            start: Start date YYYYMMDD.
            end: End date YYYYMMDD.

        Returns:
            DataFrame with standardized OHLCV columns.
        """
        # Determine exchange prefix for Sina API
        if symbol.startswith(("6", "5", "9")):
            sina_symbol = f"sh{symbol}"
        else:
            sina_symbol = f"sz{symbol}"

        # Try Sina API first (more reliable)
        df = None
        for attempt in range(self.retry_count):
            try:
                self._rate_limit_wait()
                df = ak.stock_zh_a_daily(
                    symbol=sina_symbol,
                    start_date=start.replace("-", "")[:8],
                    end_date=end.replace("-", "")[:8],
                    adjust="qfq",
                )
                break
            except Exception as e:
                if attempt == self.retry_count - 1:
                    logger.debug(f"Sina API failed for {symbol}: {e}")
                else:
                    time.sleep(2 ** attempt)

        # Fallback to East Money API
        if df is None or df.empty:
            try:
                self._rate_limit_wait()
                df = ak.stock_zh_a_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=start,
                    end_date=end,
                    adjust="qfq",
                )
            except Exception:
                pass

        if df is None or df.empty:
            return pd.DataFrame()

        # Normalize columns
        df = df.rename(columns={
            "日期": "date", "开盘": "open", "最高": "high", "最低": "low",
            "收盘": "close", "成交量": "volume", "成交额": "amount",
            "换手率": "turnover", "date": "date", "open": "open",
            "high": "high", "low": "low", "close": "close",
            "volume": "volume",
        })
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
        df["symbol"] = symbol
        return df

    def get_stock_basic(self) -> pd.DataFrame:
        """Get basic info for all A-share stocks."""
        df = self._retry_call(ak.stock_zh_a_spot_em)
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.rename(columns={
            "代码": "symbol",
            "名称": "name",
            "最新价": "latest_price",
            "涨跌幅": "pct_change",
            "涨跌额": "change",
            "成交量": "volume",
            "成交额": "amount",
            "振幅": "amplitude",
            "换手率": "turnover",
            "市盈率-动态": "pe_ttm",
            "市净率": "pb",
            "总市值": "total_mv",
            "流通市值": "circ_mv",
        })
        return df

    def get_index_daily(
        self, index_code: str, start: str = "20150101", end: str = "20991231"
    ) -> pd.DataFrame:
        """Get daily OHLCV for an index.

        Uses stock_zh_index_daily which is the current working API in AKShare.
        Prefix 'sh' for Shanghai indices (e.g. 'sh000300'), 'sz' for Shenzhen (e.g. 'sz399006').
        """
        # Map index codes to exchange-prefixed symbols
        sh_indices = {"000300", "000905", "000001", "000016", "000688"}
        if index_code in sh_indices:
            symbol = f"sh{index_code}"
        elif index_code.startswith("399"):
            symbol = f"sz{index_code}"
        else:
            symbol = f"sh{index_code}"

        df = self._retry_call(
            ak.stock_zh_index_daily,
            symbol=symbol,
        )
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.rename(columns={"date": "date", "open": "open", "high": "high",
                                 "low": "low", "close": "close", "volume": "volume"})
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")

        # Filter date range
        if start != "20150101" or end != "20991231":
            df = df.loc[start:end]
        return df

    def get_etf_daily(
        self, etf_code: str, start: str = "20150101", end: str = "20991231"
    ) -> pd.DataFrame:
        """Get daily OHLCV for an ETF."""
        df = self._retry_call(
            ak.fund_etf_hist_em,
            symbol=etf_code,
            period="daily",
            start_date=start,
            end_date=end,
            adjust="qfq",
        )
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.rename(columns=AKSHARE_COLUMN_MAP)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
        return df

    def get_financials(self, symbol: str) -> pd.DataFrame:
        """Get key financial indicators for a stock."""
        try:
            df = self._retry_call(
                ak.stock_financial_abstract_ths,
                symbol=symbol,
            )
            return df if df is not None else pd.DataFrame()
        except Exception:
            logger.debug(f"Failed to get financials for {symbol}")
            return pd.DataFrame()

    def get_money_flow(self, symbol: str) -> pd.DataFrame:
        """Get individual stock capital flow data."""
        try:
            market = "sh" if symbol.startswith(("6", "9")) else "sz"
            df = self._retry_call(
                ak.stock_individual_fund_flow,
                stock=symbol,
                market=market,
            )
            if df is not None and not df.empty and "日期" in df.columns:
                df["日期"] = pd.to_datetime(df["日期"])
                df = df.set_index("日期")
            return df if df is not None else pd.DataFrame()
        except Exception:
            logger.debug(f"Failed to get money flow for {symbol}")
            return pd.DataFrame()

    def get_macro(self, indicator: str = "cpi") -> pd.DataFrame:
        """Get macro-economic indicator.

        Supported indicators: cpi, ppi, pmi, money_supply, shibor, gdp.
        """
        macro_map = {
            "cpi": (ak.macro_china_cpi_yearly, {}),
            "ppi": (ak.macro_china_ppi_yearly, {}),
            "pmi": (ak.macro_china_pmi, {}),
            "money_supply": (ak.macro_china_money_supply, {}),
            "shibor": (ak.rate_interbank, {"market": "上海银行间同业拆放利率", "symbol": "Shibor"}),
            "gdp": (ak.macro_china_gdp, {}),
        }
        if indicator not in macro_map:
            raise ValueError(f"Unknown macro indicator: {indicator}. Options: {list(macro_map)}")

        func, kwargs = macro_map[indicator]
        df = self._retry_call(func, **kwargs)
        return df if df is not None else pd.DataFrame()

    def get_trade_calendar(self) -> pd.DataFrame:
        """Get A-share trading calendar."""
        df = self._retry_call(ak.tool_trade_date_hist_sina)
        if df is not None and not df.empty:
            df = pd.DataFrame({"trade_date": pd.to_datetime(df["trade_date"])})
        return df if df is not None else pd.DataFrame()

    def get_index_constituents(self, index_code: str) -> list[str]:
        """Get constituent stocks of an index (e.g. CSI 300 = '000300')."""
        try:
            df = self._retry_call(
                ak.index_stock_cons_csindex,
                symbol=index_code,
            )
            if df is not None and not df.empty:
                # CSI index constituent API returns different column names
                for col in ["成分券代码", "成分代码", "constituent_code", "symbol"]:
                    if col in df.columns:
                        return df[col].tolist()
            return []
        except Exception:
            logger.warning(f"Failed to get constituents for index {index_code}")
            return []

    def get_industry_classification(self) -> pd.DataFrame:
        """Get Shenwan (申万) 2021 industry classification."""
        try:
            df = self._retry_call(ak.stock_board_industry_name_em)
            return df if df is not None else pd.DataFrame()
        except Exception:
            logger.warning("Failed to get industry classification")
            return pd.DataFrame()

    def get_all_stock_codes(self) -> list[str]:
        """Get list of all A-share stock codes."""
        basic = self.get_stock_basic()
        if basic.empty or "symbol" not in basic.columns:
            return []
        return basic["symbol"].tolist()

    def get_etf_list(self) -> pd.DataFrame:
        """Get list of all ETFs."""
        try:
            df = self._retry_call(ak.fund_etf_category_sina, symbol="ETF基金")
            return df if df is not None else pd.DataFrame()
        except Exception:
            logger.warning("Failed to get ETF list")
            return pd.DataFrame()
