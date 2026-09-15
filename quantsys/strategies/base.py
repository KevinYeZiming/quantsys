"""Abstract base class for all trading strategies."""

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from quantsys.data.sources.cache import CacheManager
from quantsys.utils.config import load_config


class BaseStrategy(ABC):
    """Abstract strategy interface.

    Each strategy operates on a universe of stocks/ETFs and produces
    position weight signals (0.0 to 1.0 for long-only).

    Usage::

        strategy = MultiFactorStrategy(config)
        signals = strategy.generate_signals(universe, "2024-01-15")
    """

    name: str = "base"

    def __init__(self, config: dict = None, cache_dir: str | Path = None):
        """Initialize strategy.

        Args:
            config: Strategy-specific configuration dict.
            cache_dir: Path to data cache directory.
        """
        self.config = config or {}

        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / "data" / "raw"
        self.cache = CacheManager(Path(cache_dir))

    @abstractmethod
    def generate_signals(
        self, universe: list[str], date: str
    ) -> pd.Series:
        """Generate position weight signals for a given date.

        Args:
            universe: List of tradeable symbols.
            date: Reference date string 'YYYY-MM-DD'.

        Returns:
            Series mapping symbol -> target weight (0.0 to 1.0, sums to <= 1.0).
        """
        ...

    def get_rebalance_dates(
        self, start: str, end: str, frequency: str = "monthly"
    ) -> list[pd.Timestamp]:
        """Get scheduled rebalance dates.

        Args:
            start: Start date.
            end: End date.
            frequency: 'daily', 'weekly', 'monthly'.

        Returns:
            List of rebalance dates.
        """
        freq_map = {"daily": "B", "weekly": "W-FRI", "monthly": "BME"}
        freq = freq_map.get(frequency, "BM")

        dates = pd.date_range(start, end, freq=freq)
        return [pd.Timestamp(d) for d in dates]

    def load_data(
        self, symbols: list[str], start: str, end: str
    ) -> pd.DataFrame:
        """Load OHLCV data for a list of symbols from cache.

        Args:
            symbols: List of stock/ETF codes.
            start: Start date.
            end: End date.

        Returns:
            DataFrame with MultiIndex (date, symbol).
        """
        dfs = []
        for symbol in symbols:
            df = self.cache.get("stock_daily", symbol=symbol)
            if df is not None and not df.empty:
                df = df.sort_index()
                df = df.loc[start:end]
                if not df.empty:
                    df["symbol"] = symbol
                    dfs.append(df)

        if not dfs:
            return pd.DataFrame()

        combined = pd.concat(dfs)
        combined = combined.reset_index().set_index(["date", "symbol"])
        return combined
