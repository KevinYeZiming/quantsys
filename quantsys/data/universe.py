"""Build tradeable stock universe with Chinese market filters.

Filters out:
- ST and *ST stocks (Special Treatment)
- New listings (IPO within N days)
- Suspended stocks (volume = 0)
- Non-index-constituent stocks (optional)
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


class UniverseBuilder:
    """Build tradeable stock universe for A-share strategies.

    Usage::

        builder = UniverseBuilder(cache_manager)
        universe = builder.build("2024-01-15", index_code="000300")
    """

    def __init__(self, cache_manager):
        self._cache = cache_manager

    def _is_st_stock(self, name: str) -> bool:
        """Check if a stock is ST or *ST based on its name."""
        if not isinstance(name, str):
            return False
        return "ST" in name.upper() and "*ST" not in name

    def _is_star_st_stock(self, name: str) -> bool:
        """Check if a stock is *ST based on its name."""
        if not isinstance(name, str):
            return False
        return "*ST" in name.upper()

    def filter_st(
        self, stock_info: pd.DataFrame, date: str = None
    ) -> pd.DataFrame:
        """Filter out ST and *ST stocks.

        Args:
            stock_info: DataFrame with 'symbol' and 'name' columns.
            date: Not used (ST flag from name). Kept for API consistency.

        Returns:
            Filtered DataFrame.
        """
        if stock_info.empty or "name" not in stock_info.columns:
            return stock_info

        mask = stock_info["name"].apply(
            lambda x: not self._is_st_stock(x) and not self._is_star_st_stock(x)
        )
        excluded = (~mask).sum()
        if excluded > 0:
            logger.debug(f"Filtered {excluded} ST/*ST stocks")
        return stock_info[mask]

    def filter_new_listings(
        self, stock_info: pd.DataFrame, date: str, min_days: int = 60
    ) -> pd.DataFrame:
        """Filter out stocks listed less than min_days ago.

        This avoids the IPO anomaly where new listings experience high initial returns
        followed by long-term underperformance.

        Args:
            stock_info: DataFrame with 'symbol' column.
            date: Reference date string 'YYYY-MM-DD'.
            min_days: Minimum listing days required.

        Returns:
            Filtered DataFrame.
        """
        if stock_info.empty:
            return stock_info

        date = pd.Timestamp(date)
        cutoff_date = date - pd.Timedelta(days=min_days)

        # Try to get listing date from basic info
        basic = self._cache.get("stock_basic")
        if basic is not None and not basic.empty:
            if "symbol" not in basic.columns:
                return stock_info

            # Look for listing date column
            list_col = None
            for col in ["上市日期", "list_date", "listed_date"]:
                if col in basic.columns:
                    list_col = col
                    break

            if list_col:
                basic[list_col] = pd.to_datetime(basic[list_col], errors="coerce")
                valid = basic[basic[list_col] <= cutoff_date]
                valid_symbols = set(valid["symbol"].tolist())
                mask = stock_info["symbol"].isin(valid_symbols)
                excluded = (~mask).sum()
                if excluded > 0:
                    logger.debug(f"Filtered {excluded} new listings (<{min_days} days)")
                return stock_info[mask]

        logger.debug("Cannot filter new listings: no listing date data available")
        return stock_info

    def filter_suspension(
        self, symbols: list[str], date: str
    ) -> list[str]:
        """Filter out suspended stocks (those with zero volume on the date).

        Args:
            symbols: List of stock codes.
            date: Reference date.

        Returns:
            Filtered list of stock codes.
        """
        if not symbols:
            return symbols

        date = pd.Timestamp(date)
        active = []

        for symbol in symbols:
            try:
                df = self._cache.get("stock_daily", symbol=symbol)
                if df is not None and not df.empty:
                    if date in df.index:
                        row = df.loc[date]
                        # Handle duplicate index
                        if isinstance(row, pd.DataFrame):
                            row = row.iloc[0]
                        volume = row.get("volume", 0) if isinstance(row, pd.Series) else 0
                        if volume > 0:
                            active.append(symbol)
                    else:
                        # Date not in data, include by default
                        active.append(symbol)
                else:
                    active.append(symbol)
            except Exception:
                active.append(symbol)

        filtered = len(symbols) - len(active)
        if filtered > 0:
            logger.debug(f"Filtered {filtered} suspended stocks")
        return active

    def filter_by_index(
        self, stock_info: pd.DataFrame, index_code: str = "000300"
    ) -> pd.DataFrame:
        """Filter stocks to only those in a specific index.

        Args:
            stock_info: DataFrame with 'symbol' column.
            index_code: Index code (default: CSI 300 '000300').

        Returns:
            Filtered DataFrame.
        """
        if stock_info.empty:
            return stock_info

        # Load index constituents from cache or compute
        index_df = self._cache.get("index_constituents", symbol=index_code)
        if index_df is not None and not index_df.empty:
            # Find the symbol column
            for col in ["成分券代码", "成分代码", "symbol"]:
                if col in index_df.columns:
                    constituents = set(index_df[col].tolist())
                    mask = stock_info["symbol"].isin(constituents)
                    logger.debug(
                        f"Index filter ({index_code}): {mask.sum()}/{len(stock_info)} stocks"
                    )
                    return stock_info[mask]

        logger.debug(f"No constituent data for index {index_code}, skipping filter")
        return stock_info

    def build(
        self,
        date: str,
        index_code: str = None,
        min_listing_days: int = 60,
        exclude_st: bool = True,
    ) -> list[str]:
        """Build the tradeable universe for a given date.

        Processing order:
        1. Get all A-share stocks (or index constituents)
        2. Exclude ST/*ST stocks
        3. Exclude new listings (< min_listing_days)
        4. Exclude suspended stocks (zero volume)

        Args:
            date: Reference date string 'YYYY-MM-DD'.
            index_code: Optional index code to restrict universe to index constituents.
            min_listing_days: Minimum days since listing.
            exclude_st: Whether to exclude ST stocks.

        Returns:
            List of tradeable stock symbols.
        """
        logger.info(f"Building universe for {date} (index={index_code or 'all'})")

        # Step 1: Get basic stock info
        basic = self._cache.get("stock_basic")
        if basic is None or basic.empty:
            # Fallback: discover symbols from cache directory
            logger.warning("No stock basic info in cache, discovering from cached data")
            stock_dir = self._cache.cache_dir / "stock_daily"
            if stock_dir.exists():
                symbols = [p.stem for p in stock_dir.glob("*.parquet") if not p.name.startswith("._")]
                if symbols:
                    logger.info(f"Discovered {len(symbols)} stocks from cache")
                    stock_info = pd.DataFrame({"symbol": symbols, "name": symbols})
                else:
                    return []
            else:
                return []

        # Step 2: Filter by index if specified
        if index_code:
            # Try loading constituents from cache
            const_df = self._cache.get("index_constituents", symbol=index_code)
            if const_df is not None and not const_df.empty:
                for col in ["成分券代码", "成分代码", "symbol"]:
                    if col in const_df.columns:
                        constituents = set(const_df[col].tolist())
                        stock_info = stock_info[stock_info["symbol"].isin(constituents)]
                        break

        # Step 3: Exclude ST stocks
        if exclude_st:
            stock_info = self.filter_st(stock_info, date)

        # Step 4: Exclude new listings
        stock_info = self.filter_new_listings(stock_info, date, min_listing_days)

        symbols = stock_info["symbol"].tolist()

        # Step 5: Exclude suspended stocks
        symbols = self.filter_suspension(symbols, date)

        logger.info(f"Universe for {date}: {len(symbols)} stocks")
        return symbols
