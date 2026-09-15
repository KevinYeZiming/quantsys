"""Factor processing pipeline: winsorize, standardize, neutralize, fill NaN.

Standard preprocessing for cross-sectional factors in Chinese A-share research:
1. Winsorize (去极值): clip at 1st/99th percentiles or 3x MAD
2. Fill NaN (缺失值处理): cross-sectional median or industry median
3. Standardize (标准化): z-score within cross-section
4. The neutralization step is handled by FactorNeutralizer in neutralizer.py
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class FactorProcessor:
    """Standard factor preprocessing pipeline for A-share factors.

    Usage::

        processor = FactorProcessor()
        clean = processor.process(factor_values,
                                   winsorize=True,
                                   standardize=True,
                                   fill_method='cross_sectional_median')
    """

    @staticmethod
    def winsorize(
        series: pd.Series,
        limits: tuple[float, float] = (0.01, 0.99),
        method: str = "percentile",
    ) -> pd.Series:
        """Winsorize (clip) extreme values.

        Args:
            series: Factor values.
            limits: For percentile method: (lower, upper) percentiles.
                    For mad method: multiplier for median absolute deviation.
            method: 'percentile' or 'mad'.

        Returns:
            Winsorized series.
        """
        if series.dropna().empty:
            return series

        result = series.copy()

        if method == "percentile":
            lower = result.quantile(limits[0])
            upper = result.quantile(limits[1])
            if lower == upper:
                return result
            result = result.clip(lower, upper)

        elif method == "mad":
            median = result.median()
            mad = (result - median).abs().median()
            if mad == 0:
                return result
            lower = median - limits[0] * mad
            upper = median + limits[0] * mad
            result = result.clip(lower, upper)

        else:
            raise ValueError(f"Unknown winsorize method: {method}")

        return result

    @staticmethod
    def fill_na(
        series: pd.Series,
        method: str = "cross_sectional_median",
        group: pd.Series = None,
    ) -> pd.Series:
        """Fill missing factor values.

        Args:
            series: Factor values with MultiIndex (date, symbol).
            method: 'cross_sectional_median', 'industry_median', 'zero', or 'ffill'.
            group: Industry/category series for industry_median method.

        Returns:
            Series with NaN values filled.
        """
        if series.isna().sum() == 0:
            return series

        result = series.copy()

        if method == "cross_sectional_median":
            if isinstance(series.index, pd.MultiIndex) and "date" in series.index.names:
                date_level = series.index.names.index("date")
                median_by_date = result.groupby(level=date_level).transform("median")
                result = result.fillna(median_by_date)
            else:
                result = result.fillna(result.median())

        elif method == "industry_median" and group is not None:
            if isinstance(series.index, pd.MultiIndex):
                # Group by date and industry, fill with industry-date median
                combined = pd.DataFrame({"factor": result, "industry": group})
                result = combined.groupby(
                    [pd.Grouper(level="date"), "industry"]
                )["factor"].transform(lambda x: x.fillna(x.median()))
            else:
                result = result.fillna(result.median())

        elif method == "zero":
            result = result.fillna(0.0)

        elif method == "ffill":
            if isinstance(series.index, pd.MultiIndex):
                result = result.groupby(level="symbol").ffill()
            else:
                result = result.ffill()

        # Fallback: fill remaining NaN with 0
        result = result.fillna(0.0)

        return result

    @staticmethod
    def standardize(series: pd.Series) -> pd.Series:
        """Cross-sectional z-score standardization.

        For each date, subtract cross-sectional mean and divide by std.

        Args:
            series: Factor values with MultiIndex (date, symbol).

        Returns:
            Standardized factor values (mean=0, std=1 per cross-section).
        """
        if isinstance(series.index, pd.MultiIndex) and "date" in series.index.names:
            date_level = series.index.names.index("date")
            mean = series.groupby(level=date_level).transform("mean")
            std = series.groupby(level=date_level).transform("std").replace(0, pd.NA)
            result = (series - mean) / std
        else:
            mean = series.mean()
            std = series.std()
            if std == 0:
                return series
            result = (series - mean) / std

        return result.fillna(0.0)

    def process(
        self,
        series: pd.Series,
        winsorize_enabled: bool = True,
        standardize_enabled: bool = True,
        fill_method: str = "cross_sectional_median",
        winsorize_limits: tuple[float, float] = (0.01, 0.99),
    ) -> pd.Series:
        """Run the full factor preprocessing pipeline.

        Order: winsorize -> fill_na -> standardize

        Args:
            series: Raw factor values.
            winsorize_enabled: Whether to clip extreme values.
            standardize_enabled: Whether to z-score normalize.
            fill_method: Method for filling NaN.
            winsorize_limits: Percentile limits for winsorization.

        Returns:
            Processed factor series.
        """
        result = series.copy()

        # Step 1: Winsorize
        if winsorize_enabled:
            result = self.winsorize(result, limits=winsorize_limits)

        # Step 2: Fill NaN
        result = self.fill_na(result, method=fill_method)

        # Step 3: Standardize (cross-sectional z-score)
        if standardize_enabled:
            result = self.standardize(result)

        result.name = series.name
        return result
