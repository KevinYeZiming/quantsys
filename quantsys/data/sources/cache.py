"""Caching decorator and cache manager for data sources."""

import functools
import hashlib
import json
import logging
from pathlib import Path
from typing import Callable

import pandas as pd

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages Parquet-based caching of data source results.

    Each data type caches at its natural granularity:
    - OHLCV: one Parquet per stock per year
    - Basic info: one Parquet snapshot
    - Financials: one Parquet per stock
    - Index/ETF: one Parquet per symbol
    """

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _make_key(self, *args, **kwargs) -> str:
        """Generate a deterministic cache key from arguments."""
        raw = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def get(self, cache_type: str, symbol: str = None, **kwargs) -> pd.DataFrame | None:
        """Retrieve cached data if available and fresh.

        Args:
            cache_type: Type of data (stock_daily, stock_basic, index_daily, etc.).
            symbol: Optional symbol for per-symbol caches.
            **kwargs: Additional parameters affecting the query.

        Returns:
            DataFrame if cache hit, None otherwise.
        """
        cache_dir = self.cache_dir / cache_type
        cache_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{symbol}.parquet" if symbol else f"{self._make_key(**kwargs)}.parquet"
        cache_path = cache_dir / filename

        if cache_path.exists():
            try:
                return pd.read_parquet(cache_path)
            except Exception as e:
                logger.warning(f"Failed to read cache {cache_path}: {e}")

        return None

    def put(self, df: pd.DataFrame, cache_type: str, symbol: str = None, **kwargs):
        """Store data in cache.

        Args:
            df: DataFrame to cache.
            cache_type: Type of data.
            symbol: Optional symbol for per-symbol caches.
            **kwargs: Additional parameters.
        """
        if df is None or df.empty:
            return

        cache_dir = self.cache_dir / cache_type
        cache_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{symbol}.parquet" if symbol else f"{self._make_key(**kwargs)}.parquet"
        cache_path = cache_dir / filename

        try:
            df.to_parquet(cache_path, compression="snappy")
        except Exception as e:
            logger.warning(f"Failed to write cache {cache_path}: {e}")

    def update_incremental(
        self, df: pd.DataFrame, cache_type: str, symbol: str = None
    ) -> pd.DataFrame:
        """Update cached data incrementally by appending new rows.

        Deduplicates by index, keeping newest records.

        Returns:
            Merged DataFrame.
        """
        existing = self.get(cache_type, symbol=symbol)
        if existing is not None and not existing.empty:
            combined = pd.concat([existing, df])
            # Remove duplicates, keeping the last (newest)
            combined = combined[~combined.index.duplicated(keep="last")]
            combined = combined.sort_index()
        else:
            combined = df

        self.put(combined, cache_type, symbol=symbol)
        return combined


def cached(cache_type: str):
    """Decorator to cache data source method results.

    Args:
        cache_type: String identifying the type of data being cached.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            cache = getattr(self, "_cache", None)
            if cache is None:
                return func(self, *args, **kwargs)

            # Extract symbol from first arg or kwargs
            symbol = args[0] if args else kwargs.get("symbol")
            if isinstance(symbol, str) and len(symbol) > 20:
                symbol = None

            result = cache.get(cache_type, symbol=symbol)
            if result is not None:
                return result

            result = func(self, *args, **kwargs)
            if result is not None and not (isinstance(result, pd.DataFrame) and result.empty):
                cache.put(result, cache_type, symbol=symbol)
            return result

        return wrapper

    return decorator
