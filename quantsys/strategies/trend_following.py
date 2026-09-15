"""Trend following strategy (趋势跟踪策略).

Dual moving average crossover combined with turtle-style channel breakout,
adapted for Chinese A-share markets.

Entry rules:
- Price breaks above 20-day high
- MA20 > MA60 (uptrend confirmation)
- Volume above 20-day average (volume confirmation)

Exit rules:
- Price breaks below 10-day low
- 2x ATR trailing stop
"""

import logging

import numpy as np
import pandas as pd

from quantsys.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class TrendFollowingStrategy(BaseStrategy):
    """Trend following with dual MA and channel breakout.

    Config options:
        short_ma: Short moving average period (default 20)
        long_ma: Long moving average period (default 60)
        breakout_period: Channel breakout lookback (default 20)
        atr_multiplier: ATR multiplier for stop (default 2.0)
        atr_period: ATR calculation period (default 14)
        max_positions: Max simultaneous positions (default 20)
        risk_per_trade: Risk per trade as fraction of capital (default 0.02)
    """

    name = "trend_following"

    def __init__(self, config: dict = None, cache_dir: str = None):
        super().__init__(config, cache_dir)

        cfg = self.config.get("trend_following", {})
        self.short_ma = cfg.get("short_ma", 20)
        self.long_ma = cfg.get("long_ma", 60)
        self.breakout_period = cfg.get("breakout_period", 20)
        self.atr_multiplier = cfg.get("atr_multiplier", 2.0)
        self.atr_period = cfg.get("atr_period", 14)
        self.max_positions = cfg.get("max_positions", 20)
        self.risk_per_trade = cfg.get("risk_per_trade", 0.02)

    def generate_signals(
        self, universe: list[str], date: str
    ) -> pd.Series:
        """Generate entry/exit signals for trend following.

        Returns:
            Series mapping symbol -> signal value:
            > 0: buy/enter; < 0: sell/exit; 0: no action.
        """
        if not universe:
            return pd.Series(dtype=float)

        date_ts = pd.Timestamp(date)
        # Load enough history for indicator calculation
        lookback = self.long_ma + self.breakout_period + 50
        start = (date_ts - pd.DateOffset(days=lookback)).strftime("%Y-%m-%d")

        signals = {}

        for symbol in universe:
            df = self.cache.get("stock_daily", symbol=symbol)
            if df is None or df.empty:
                continue

            df = df.sort_index()
            df = df.loc[start:date]

            if len(df) < self.long_ma:
                continue

            # Compute indicators
            close = df["close"]
            high = df["high"]
            low = df["low"]
            volume = df["volume"]

            # Moving averages
            ma_short = close.rolling(self.short_ma).mean()
            ma_long = close.rolling(self.long_ma).mean()

            # Channel breakout
            channel_high = high.rolling(self.breakout_period).max()
            channel_low = low.rolling(self.breakout_period).min()

            # ATR for stops
            tr = pd.DataFrame({
                "hl": high - low,
                "hc": abs(high - close.shift(1)),
                "lc": abs(low - close.shift(1)),
            }).max(axis=1)
            atr = tr.rolling(self.atr_period).mean()

            # Volume confirmation
            avg_volume = volume.rolling(self.short_ma).mean()

            # Current values
            current_close = close.iloc[-1]
            current_ma_short = ma_short.iloc[-1]
            current_ma_long = ma_long.iloc[-1]
            current_ch_high = channel_high.iloc[-1]
            current_ch_low = channel_low.iloc[-1]
            current_volume = volume.iloc[-1]
            current_avg_vol = avg_volume.iloc[-1]
            current_atr = atr.iloc[-1]

            if pd.isna(current_ma_short) or pd.isna(current_ma_long):
                continue

            # Entry signal
            trend_up = current_ma_short > current_ma_long
            breakout = current_close >= current_ch_high * 0.99  # 1% tolerance
            volume_confirm = current_volume >= current_avg_vol * 0.8

            if trend_up and breakout and volume_confirm:
                # Entry signal (positive weight)
                signals[symbol] = self._calculate_position_size(
                    current_close, current_atr
                )
            # Exit signal
            elif current_close <= current_ch_low * 1.01:
                signals[symbol] = -1.0  # Exit signal

        if not signals:
            return pd.Series(dtype=float)

        signals_series = pd.Series(signals)

        # Limit number of positions
        buy_signals = signals_series[signals_series > 0]
        if len(buy_signals) > self.max_positions:
            # Keep top signals by strength
            buy_signals = buy_signals.nlargest(self.max_positions)

        return buy_signals

    def _calculate_position_size(
        self, price: float, atr: float
    ) -> float:
        """Calculate position size based on ATR and risk per trade.

        Position size = (capital * risk_per_trade) / (ATR * multiplier)

        Args:
            price: Current stock price.
            atr: Current ATR value.

        Returns:
            Position weight (0 to 1).
        """
        if pd.isna(atr) or atr <= 0 or price <= 0:
            return 0.0

        # Risk amount per trade
        stop_distance = atr * self.atr_multiplier
        position_weight = self.risk_per_trade / (stop_distance / price)
        return min(position_weight, 0.10)  # Cap at 10%
