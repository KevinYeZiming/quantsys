"""Position sizing methods for Chinese A-share portfolios."""

import numpy as np
import pandas as pd


class PositionSizer:
    """Position sizing strategies.

    Usage::

        weights = PositionSizer.equal_weight(signals)
        weights = PositionSizer.volatility_target(prices, target_vol=0.15)
        kelly_pct = PositionSizer.kelly_criterion(win_rate=0.55, avg_win=0.05, avg_loss=-0.03)
    """

    @staticmethod
    def equal_weight(signals: pd.Series, n_positions: int = None) -> pd.Series:
        """Equal weight allocation.

        Args:
            signals: Series of signal values (symbol -> weight).
            n_positions: Optional max number of positions.

        Returns:
            Series of normalized weights summing to 1.0.
        """
        if n_positions is None:
            n_positions = len(signals)

        top = signals.nlargest(n_positions)
        weights = pd.Series(0.0, index=signals.index)
        weights[top.index] = 1.0 / len(top)
        return weights

    @staticmethod
    def kelly_criterion(
        win_rate: float, avg_win: float, avg_loss: float
    ) -> float:
        """Kelly fraction for optimal bet sizing.

        f* = (p * b - q) / b
        where p = win_rate, q = 1 - p, b = avg_win / |avg_loss|

        Args:
            win_rate: Probability of winning (0 to 1).
            avg_win: Average winning return (positive).
            avg_loss: Average losing return (negative number).

        Returns:
            Kelly fraction (clamped to [0, 0.5] for safety).
        """
        avg_loss = abs(avg_loss)
        if avg_loss == 0:
            return 0.0

        b = avg_win / avg_loss
        q = 1 - win_rate
        f = (win_rate * b - q) / b

        # Half-Kelly for safety
        return max(0.0, min(f / 2.0, 0.5))

    @staticmethod
    def volatility_target(
        close_prices: pd.DataFrame,
        target_vol: float = 0.15,
        lookback: int = 60,
    ) -> pd.Series:
        """Volatility-targeted position sizing.

        Scale positions so that each stock contributes equal risk.

        Args:
            close_prices: DataFrame of close prices (columns = symbols).
            target_vol: Annual target volatility (default 15%).
            lookback: Lookback period for vol estimation.

        Returns:
            Series of position weights.
        """
        returns = close_prices.pct_change().dropna(how="all")
        vol = returns.rolling(lookback).std().iloc[-1] * np.sqrt(252)
        vol = vol.replace(0, pd.NA)

        weights = target_vol / vol
        weights = weights.fillna(0)
        weights = weights.clip(lower=0)

        if weights.sum() > 0:
            weights = weights / weights.sum()

        return weights

    @staticmethod
    def risk_parity_weights(cov_matrix: pd.DataFrame) -> pd.Series:
        """Compute risk parity weights from a covariance matrix.

        Each asset contributes equal risk to the portfolio.

        Args:
            cov_matrix: Covariance matrix of asset returns.

        Returns:
            Series of weights summing to 1.0.
        """
        n = len(cov_matrix)
        if n == 0:
            return pd.Series(dtype=float)

        # Naive risk parity: weight = 1/vol / sum(1/vol)
        vols = np.sqrt(np.diag(cov_matrix.values))
        vols = pd.Series(vols, index=cov_matrix.index)
        vols = vols.replace(0, pd.NA)

        inv_vols = 1.0 / vols
        weights = inv_vols / inv_vols.sum()
        return weights.fillna(0)
