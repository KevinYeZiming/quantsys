"""Stop-loss rules for Chinese A-share trading.

Implements various exit conditions to manage downside risk.
"""

import numpy as np
import pandas as pd


class StopLoss:
    """Collection of stop-loss rules.

    Usage::

        sl = StopLoss()
        should_exit = sl.trailing_pct(entry_price=10.0, current_price=9.2, trail_pct=0.08)
        should_exit = sl.atr_stop(entry=10.0, current=9.5, atr=0.3, multiplier=2.0)
    """

    @staticmethod
    def trailing_pct(
        entry_price: float,
        current_price: float,
        highest_price: float = None,
        trail_pct: float = 0.08,
    ) -> bool:
        """Trailing percentage stop-loss.

        Exits when price falls below (highest_price * (1 - trail_pct)).

        Args:
            entry_price: Entry price.
            current_price: Current market price.
            highest_price: Highest price since entry. Uses entry_price if not provided.
            trail_pct: Trail percentage as decimal (e.g. 0.08 = 8%).

        Returns:
            True if stop triggered.
        """
        if highest_price is None:
            highest_price = max(entry_price, current_price)

        stop_level = highest_price * (1 - trail_pct)
        return current_price <= stop_level

    @staticmethod
    def atr_stop(
        entry_price: float,
        current_price: float,
        atr: float,
        multiplier: float = 2.0,
        is_long: bool = True,
    ) -> bool:
        """ATR-based trailing stop.

        For long positions: exit when price falls below (entry - N * ATR).
        For short positions: exit when price rises above (entry + N * ATR).

        Args:
            entry_price: Entry price.
            current_price: Current price.
            atr: Current Average True Range.
            multiplier: ATR multiplier (default 2.0).
            is_long: True for long positions, False for short.

        Returns:
            True if stop triggered.
        """
        if is_long:
            stop_level = entry_price - multiplier * atr
            return current_price <= stop_level
        else:
            stop_level = entry_price + multiplier * atr
            return current_price >= stop_level

    @staticmethod
    def time_stop(
        entry_date: pd.Timestamp,
        current_date: pd.Timestamp,
        max_holding_days: int = 60,
    ) -> bool:
        """Time-based stop: exit if holding period exceeds limit.

        Args:
            entry_date: Date of entry.
            current_date: Current date.
            max_holding_days: Maximum number of calendar days to hold.

        Returns:
            True if time stop triggered.
        """
        return (current_date - entry_date).days >= max_holding_days

    @staticmethod
    def max_drawdown_stop(
        peak_equity: float,
        current_equity: float,
        max_dd_pct: float = 0.20,
    ) -> bool:
        """Portfolio-level maximum drawdown stop.

        Stops all trading when portfolio drawdown exceeds threshold.

        Args:
            peak_equity: Highest portfolio value achieved.
            current_equity: Current portfolio value.
            max_dd_pct: Maximum allowed drawdown (e.g. 0.20 = 20%).

        Returns:
            True if stop triggered.
        """
        if peak_equity <= 0:
            return False
        drawdown = (peak_equity - current_equity) / peak_equity
        return drawdown >= max_dd_pct


class StopLossTracker:
    """Tracks stop-loss levels for multiple positions.

    Usage::

        tracker = StopLossTracker()
        tracker.add_position("600519", entry_price=1500, entry_date=pd.Timestamp.now())
        exits = tracker.check_all({"600519": 1480}, pd.Timestamp.now())
    """

    def __init__(self):
        self._positions: dict[str, dict] = {}
        self._portfolio_peak: float = 0.0

    def add_position(
        self, symbol: str, entry_price: float, entry_date: pd.Timestamp
    ):
        """Register a new position for tracking."""
        self._positions[symbol] = {
            "entry_price": entry_price,
            "entry_date": entry_date,
            "highest_price": entry_price,
        }

    def remove_position(self, symbol: str):
        """Remove a closed position."""
        self._positions.pop(symbol, None)

    def update_highest(self, symbol: str, current_price: float):
        """Update the highest price seen for a position."""
        if symbol in self._positions:
            self._positions[symbol]["highest_price"] = max(
                self._positions[symbol]["highest_price"], current_price
            )

    def check_all(
        self,
        prices: dict[str, float],
        current_date: pd.Timestamp,
        atrs: dict[str, float] = None,
        trail_pct: float = 0.08,
        max_holding_days: int = 60,
    ) -> list[str]:
        """Check all positions for stop triggers.

        Args:
            prices: Dict mapping symbol -> current price.
            current_date: Current date.
            atrs: Optional dict mapping symbol -> current ATR.
            trail_pct: Trailing stop percentage.
            max_holding_days: Maximum holding days.

        Returns:
            List of symbols where stop-loss was triggered.
        """
        triggered = []

        for symbol, pos in self._positions.items():
            if symbol not in prices:
                continue

            current_price = prices[symbol]

            # Update highest
            self.update_highest(symbol, current_price)

            # Check trailing stop
            if StopLoss.trailing_pct(
                pos["entry_price"], current_price,
                pos["highest_price"], trail_pct,
            ):
                triggered.append(symbol)
                continue

            # Check time stop
            if StopLoss.time_stop(pos["entry_date"], current_date, max_holding_days):
                triggered.append(symbol)
                continue

            # Check ATR stop (if ATR data available)
            if atrs and symbol in atrs:
                if StopLoss.atr_stop(pos["entry_price"], current_price, atrs[symbol]):
                    triggered.append(symbol)

        return triggered
