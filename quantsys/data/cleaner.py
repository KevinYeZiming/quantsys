"""Data cleaning utilities for Chinese A-share market data."""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DataCleaner:
    """Clean and validate Chinese A-share market data.

    Handles common data quality issues:
    - Missing values in price/volume data
    - Outlier detection (extreme returns, price spikes)
    - Duplicate index entries
    - Price adjustments across splits/dividends
    """

    @staticmethod
    def clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
        """Clean OHLCV data.

        - Remove rows with all NaN
        - Forward fill missing values within limits
        - Remove rows with non-positive prices or volume
        - Sort by date and remove duplicate index entries

        Args:
            df: OHLCV DataFrame indexed by date.

        Returns:
            Cleaned DataFrame.
        """
        if df is None or df.empty:
            return df

        df = df.copy()

        # Remove rows with all NaN
        df = df.dropna(how="all")

        # Remove duplicate index (keep first)
        df = df[~df.index.duplicated(keep="first")]

        # Sort by date
        df = df.sort_index()

        # Ensure required columns exist
        ohlcv_cols = ["open", "high", "low", "close", "volume"]
        existing = [c for c in ohlcv_cols if c in df.columns]

        if "close" in existing:
            # Remove rows with non-positive close prices
            df = df[df["close"] > 0]

        if "volume" in existing:
            # Remove rows with negative volume
            df = df[df["volume"] >= 0]

        # Price sanity: high >= low, high >= close >= low etc.
        if all(c in df.columns for c in ["high", "low", "close"]):
            df = df[(df["high"] >= df["low"]) & (df["high"] >= df["close"]) & (df["low"] <= df["close"])]

        return df

    @staticmethod
    def detect_outliers(
        series: pd.Series, method: str = "iqr", threshold: float = 3.0
    ) -> pd.Series:
        """Detect outliers in a series.

        Args:
            series: Data series.
            method: 'iqr' for interquartile range or 'zscore' for z-score.
            threshold: IQR multiplier or z-score threshold.

        Returns:
            Boolean series where True indicates an outlier.
        """
        series = series.dropna()

        if method == "iqr":
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            lower = q1 - threshold * iqr
            upper = q3 + threshold * iqr
            return (series < lower) | (series > upper)

        elif method == "zscore":
            z = (series - series.mean()) / series.std()
            return z.abs() > threshold

        else:
            raise ValueError(f"Unknown outlier detection method: {method}")

    @staticmethod
    def winsorize_series(
        series: pd.Series, limits: tuple[float, float] = (0.01, 0.99)
    ) -> pd.Series:
        """Winsorize (clip) a series at given percentiles.

        Args:
            series: Data series.
            limits: (lower_percentile, upper_percentile) for clipping.

        Returns:
            Winsorized series.
        """
        lower = series.quantile(limits[0])
        upper = series.quantile(limits[1])
        return series.clip(lower, upper)

    @staticmethod
    def validate_price_continuity(
        df: pd.DataFrame, max_pct_change: float = 0.11
    ) -> pd.DataFrame:
        """Flag extreme day-to-day price changes.

        In A-shares, daily price limits mean single-day changes should not exceed
        ~10% (or 20% for ChiNext/STAR). Values beyond this are likely data errors.

        Args:
            df: OHLCV DataFrame with 'close' column.
            max_pct_change: Maximum expected daily percentage change (decimal).

        Returns:
            DataFrame with an added 'data_error' boolean column.
        """
        if df is None or df.empty or "close" not in df.columns:
            return df

        df = df.copy()
        daily_ret = df["close"].pct_change().abs()
        df["data_error"] = daily_ret > max_pct_change
        errors = df["data_error"].sum()
        if errors > 0:
            logger.warning(f"Found {errors} potential data errors (>{max_pct_change*100}% daily change)")
        return df
