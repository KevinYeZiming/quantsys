"""Portfolio rebalancing logic.

Determines when to rebalance and calculates target trades.
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class RebalanceScheduler:
    """Determine rebalance dates and calculate required trades.

    Usage::

        scheduler = RebalanceScheduler()
        next_date = scheduler.next_rebalance_date("2024-01-15", "monthly")
        trades = scheduler.calculate_trades(current_weights, target_weights)
    """

    @staticmethod
    def next_rebalance_date(
        current_date: str, frequency: str = "monthly"
    ) -> pd.Timestamp:
        """Calculate next rebalance date.

        Args:
            current_date: Current date.
            frequency: 'daily', 'weekly', 'monthly', 'quarterly'.

        Returns:
            Next rebalance date.
        """
        freq_map = {
            "daily": "B",
            "weekly": "W-FRI",
            "monthly": "BM",
            "quarterly": "BQ",
        }

        freq = freq_map.get(frequency, "BM")
        dates = pd.date_range(current_date, periods=2, freq=freq)
        return pd.Timestamp(dates[-1])

    @staticmethod
    def calculate_trades(
        current_weights: pd.Series,
        target_weights: pd.Series,
        threshold: float = 0.01,
    ) -> pd.DataFrame:
        """Calculate required trades to move from current to target weights.

        To reduce turnover, only trade if the difference exceeds threshold.

        Args:
            current_weights: Current portfolio weights.
            target_weights: Target portfolio weights.
            threshold: Minimum weight difference to trigger a trade.

        Returns:
            DataFrame with columns ['symbol', 'current_weight', 'target_weight',
            'delta', 'action'] where action is 'buy', 'sell', or 'hold'.
        """
        # Align weights
        all_symbols = current_weights.index.union(target_weights.index)
        current = current_weights.reindex(all_symbols, fill_value=0.0)
        target = target_weights.reindex(all_symbols, fill_value=0.0)

        delta = target - current

        trades = pd.DataFrame({
            "symbol": all_symbols,
            "current_weight": current.values,
            "target_weight": target.values,
            "delta": delta.values,
        })

        trades["action"] = "hold"
        trades.loc[delta > threshold, "action"] = "buy"
        trades.loc[delta < -threshold, "action"] = "sell"

        # Filter out holds
        active_trades = trades[trades["action"] != "hold"]
        return active_trades

    @staticmethod
    def compute_turnover(
        current_weights: pd.Series, target_weights: pd.Series
    ) -> float:
        """Compute one-way turnover between two weight vectors.

        Turnover = 0.5 * sum(|w_new_i - w_old_i|)

        Returns:
            Turnover rate (0.0 to 1.0).
        """
        all_symbols = current_weights.index.union(target_weights.index)
        current = current_weights.reindex(all_symbols, fill_value=0.0)
        target = target_weights.reindex(all_symbols, fill_value=0.0)

        return float((target - current).abs().sum() / 2.0)


class ThresholdRebalancer:
    """Calendar-based rebalancing with tolerance bands.

    Rebalances on schedule but only if any position deviates
    from target by more than the tolerance threshold.
    """

    def __init__(self, tolerance: float = 0.05, frequency: str = "monthly"):
        self.tolerance = tolerance
        self.frequency = frequency
        self._last_rebalance: pd.Timestamp | None = None

    def should_rebalance(
        self,
        date: pd.Timestamp,
        current_weights: pd.Series,
        target_weights: pd.Series,
    ) -> bool:
        """Check if rebalancing is needed.

        Returns True if:
        - It's a scheduled rebalance date AND
        - Any position deviates by more than tolerance

        Args:
            date: Current date.
            current_weights: Current portfolio weights.
            target_weights: Target portfolio weights.

        Returns:
            True if rebalancing should occur.
        """
        # Check if it's a scheduled date
        if not self._is_scheduled_date(date):
            return False

        # Check if deviation exceeds tolerance
        all_symbols = current_weights.index.union(target_weights.index)
        current = current_weights.reindex(all_symbols, fill_value=0.0)
        target = target_weights.reindex(all_symbols, fill_value=0.0)

        max_deviation = (target - current).abs().max()
        return max_deviation > self.tolerance

    def _is_scheduled_date(self, date: pd.Timestamp) -> bool:
        """Check if date is a scheduled rebalance date."""
        if self._last_rebalance is None:
            self._last_rebalance = date
            return True

        freq_map = {
            "daily": pd.Timedelta(days=1),
            "weekly": pd.Timedelta(weeks=1),
            "monthly": pd.DateOffset(months=1),
            "quarterly": pd.DateOffset(months=3),
        }

        offset = freq_map.get(self.frequency, pd.DateOffset(months=1))
        next_date = self._last_rebalance + offset

        if date >= next_date:
            self._last_rebalance = date
            return True

        return False
