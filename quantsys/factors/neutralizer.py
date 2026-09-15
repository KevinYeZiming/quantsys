"""Factor neutralization (因子中性化).

Removes the influence of systematic risk factors (industry, market cap)
from alpha factors. This is standard practice in Chinese quant research
to isolate pure stock-specific alpha.

Based on methodology from Zhu Yifeng (2025) and broker research.
"""

import logging

import pandas as pd
from sklearn.linear_model import LinearRegression

logger = logging.getLogger(__name__)


class FactorNeutralizer:
    """Neutralize factors by industry and/or market capitalization.

    Uses cross-sectional regression within each time period:
        factor_i = alpha + beta_1 * log(market_cap_i) + sum(beta_j * industry_dummy_j) + epsilon_i

    The residual epsilon is the neutralized factor value, representing
    the stock-specific component orthogonal to industry and size.

    Usage::

        neutralizer = FactorNeutralizer()
        clean_factor = neutralizer.neutralize_all(
            factor_values, industries, market_caps
        )
    """

    def neutralize_by_industry(
        self,
        factor: pd.Series,
        industries: pd.Series,
    ) -> pd.Series:
        """Neutralize factor by industry dummies.

        Args:
            factor: Factor values with MultiIndex (date, symbol).
            industries: Industry labels with same index as factor.

        Returns:
            Industry-neutralized factor values (regression residuals).
        """
        if factor.empty:
            return factor

        result = factor.copy()
        aligned = pd.DataFrame({"factor": factor, "industry": industries}).dropna()
        if aligned.empty:
            return result

        if isinstance(factor.index, pd.MultiIndex) and "date" in factor.index.names:
            date_level = factor.index.names.index("date")

            def _neutralize(group):
                if len(group) < 10:
                    return group["factor"] - group["factor"].mean()
                industry_dummies = pd.get_dummies(group["industry"], drop_first=True)
                if industry_dummies.shape[1] == 0:
                    return group["factor"] - group["factor"].mean()
                X = industry_dummies.astype(float)
                y = group["factor"]
                try:
                    model = LinearRegression()
                    model.fit(X, y)
                    residuals = y - model.predict(X)
                    return pd.Series(residuals, index=group.index)
                except Exception:
                    return group["factor"] - group["factor"].mean()

            result = aligned.groupby(level=date_level, group_keys=False).apply(
                _neutralize
            )
        else:
            industry_dummies = pd.get_dummies(aligned["industry"], drop_first=True)
            if industry_dummies.shape[1] > 0:
                X = industry_dummies.astype(float)
                y = aligned["factor"]
                model = LinearRegression()
                model.fit(X, y)
                residuals = y - model.predict(X)
                result = pd.Series(residuals, index=aligned.index)

        # Reindex to original
        result = result.reindex(factor.index)
        return result

    def neutralize_by_size(
        self,
        factor: pd.Series,
        market_caps: pd.Series,
    ) -> pd.Series:
        """Neutralize factor by market capitalization (log size).

        Args:
            factor: Factor values.
            market_caps: Market capitalization values.

        Returns:
            Size-neutralized factor values.
        """
        if factor.empty:
            return factor

        result = factor.copy()
        log_mcap = pd.Series(index=market_caps.index, dtype=float)
        valid_mcap = market_caps[market_caps > 0]
        log_mcap[valid_mcap.index] = np.log(valid_mcap.values)

        aligned = pd.DataFrame({"factor": factor, "log_mcap": log_mcap}).dropna()
        if aligned.empty or len(aligned) < 10:
            return result

        if isinstance(factor.index, pd.MultiIndex) and "date" in factor.index.names:
            date_level = factor.index.names.index("date")

            def _neutralize(group):
                if len(group) < 10:
                    return group["factor"] - group["factor"].mean()
                X = group[["log_mcap"]].values
                y = group["factor"].values
                try:
                    model = LinearRegression()
                    model.fit(X, y)
                    residuals = y - model.predict(X)
                    return pd.Series(residuals, index=group.index)
                except Exception:
                    return group["factor"] - group["factor"].mean()

            result = aligned.groupby(level=date_level, group_keys=False).apply(
                _neutralize
            )
        else:
            X = aligned[["log_mcap"]].values
            y = aligned["factor"].values
            model = LinearRegression()
            model.fit(X, y)
            residuals = y - model.predict(X)
            result = pd.Series(residuals, index=aligned.index)

        result = result.reindex(factor.index)
        return result

    def neutralize_all(
        self,
        factor: pd.Series,
        industries: pd.Series = None,
        market_caps: pd.Series = None,
    ) -> pd.Series:
        """Neutralize factor by both industry and market cap simultaneously.

        Uses cross-sectional regression:
            factor_i = alpha + beta * log(mcap_i) + sum(industry_dummies) + epsilon_i

        Args:
            factor: Factor values.
            industries: Industry classification.
            market_caps: Market capitalization.

        Returns:
            Industry-and-size-neutralized factor values.
        """
        if factor.empty:
            return factor

        result = factor.copy()

        # Build regression dataset
        data = {"factor": factor}
        if market_caps is not None:
            import numpy as np
            log_mcap = np.log(market_caps.where(market_caps > 0))
            data["log_mcap"] = log_mcap
        if industries is not None:
            data["industry"] = industries

        aligned = pd.DataFrame(data).dropna()
        if aligned.empty or len(aligned) < 20:
            return result

        if isinstance(factor.index, pd.MultiIndex) and "date" in factor.index.names:
            date_level = factor.index.names.index("date")

            def _neutralize_all(group):
                if len(group) < 20:
                    return group["factor"] - group["factor"].mean()

                features = {}
                if "log_mcap" in group.columns:
                    features["log_mcap"] = group["log_mcap"]
                if "industry" in group.columns:
                    industry_dummies = pd.get_dummies(
                        group["industry"], drop_first=True
                    )
                    for col in industry_dummies.columns:
                        features[f"ind_{col}"] = industry_dummies[col]

                if not features:
                    return group["factor"] - group["factor"].mean()

                X = pd.DataFrame(features).astype(float)
                y = group["factor"]
                try:
                    model = LinearRegression()
                    model.fit(X, y)
                    residuals = y - model.predict(X)
                    return pd.Series(residuals, index=group.index)
                except Exception:
                    return group["factor"] - group["factor"].mean()

            result = aligned.groupby(level=date_level, group_keys=False).apply(
                _neutralize_all
            )
        else:
            features = {}
            if "log_mcap" in aligned.columns:
                features["log_mcap"] = aligned["log_mcap"]
            if "industry" in aligned.columns:
                dummies = pd.get_dummies(aligned["industry"], drop_first=True)
                for col in dummies.columns:
                    features[f"ind_{col}"] = dummies[col]

            if features:
                X = pd.DataFrame(features).astype(float)
                y = aligned["factor"]
                model = LinearRegression()
                model.fit(X, y)
                residuals = y - model.predict(X)
                result = pd.Series(residuals, index=aligned.index)

        result = result.reindex(factor.index)
        return result
