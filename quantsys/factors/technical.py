"""Technical factors (技术因子) for Chinese A-shares.

Technical factors are derived from price and volume patterns. In A-shares,
technical indicators are widely followed by retail investors and have
been shown to contain incremental information (QuantsPlaybook).
"""

import pandas as pd

from quantsys.factors.base import BaseFactor


class RSIFactor(BaseFactor):
    """14-day Relative Strength Index (RSI).

    RSI = 100 - 100 / (1 + RS), where RS = avg gain / avg loss over period.

    RSI < 30 suggests oversold (potential bounce, positive signal).
    RSI > 70 suggests overbought (potential pullback, negative signal).

    Factor is negated so that lower RSI = higher factor value = higher expected return
    (mean-reversion strategy).
    """

    name = "rsi_14d"
    category = "technical"
    frequency = "daily"
    requires = ["close"]

    def __init__(self, period: int = 14):
        self.period = period

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        if "close" not in panel.columns:
            return pd.Series(index=panel.index, dtype=float)

        if isinstance(panel.index, pd.MultiIndex):
            def _calc_rsi(group):
                group = group.sort_index()
                delta = group["close"].diff()
                gain = delta.where(delta > 0, 0.0)
                loss = (-delta).where(delta < 0, 0.0)
                avg_gain = gain.rolling(self.period, min_periods=self.period).mean()
                avg_loss = loss.rolling(self.period, min_periods=self.period).mean()
                rs = avg_gain / avg_loss.replace(0, pd.NA)
                rsi = 100.0 - 100.0 / (1.0 + rs)
                return rsi

            rsi = panel.groupby(level="symbol", group_keys=False).apply(_calc_rsi)
        else:
            delta = panel["close"].diff()
            gain = delta.where(delta > 0, 0.0)
            loss = (-delta).where(delta < 0, 0.0)
            avg_gain = gain.rolling(self.period, min_periods=self.period).mean()
            avg_loss = loss.rolling(self.period, min_periods=self.period).mean()
            rs = avg_gain / avg_loss.replace(0, pd.NA)
            rsi = 100.0 - 100.0 / (1.0 + rs)

        # Negate: lower RSI = higher factor value (oversold bounce signal)
        result = -rsi
        result.name = self.name
        return result


class MACDDivergence(BaseFactor):
    """MACD divergence (MACD背离因子).

    Measures the divergence between MACD line and signal line, normalized by price.
    When MACD crosses above signal: bullish (positive factor value).
    When MACD crosses below signal: bearish (negative factor value).

    Normalized by close price to make cross-stock comparable.
    """

    name = "macd_divergence"
    category = "technical"
    frequency = "daily"
    requires = ["close"]

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        if "close" not in panel.columns:
            return pd.Series(index=panel.index, dtype=float)

        if isinstance(panel.index, pd.MultiIndex):
            def _calc_macd(group):
                group = group.sort_index()
                price = group["close"]
                ema_fast = price.ewm(span=self.fast, adjust=False).mean()
                ema_slow = price.ewm(span=self.slow, adjust=False).mean()
                macd_line = ema_fast - ema_slow
                signal_line = macd_line.ewm(span=self.signal, adjust=False).mean()
                divergence = (macd_line - signal_line) / price
                return divergence

            result = panel.groupby(level="symbol", group_keys=False).apply(_calc_macd)
        else:
            price = panel["close"]
            ema_fast = price.ewm(span=self.fast, adjust=False).mean()
            ema_slow = price.ewm(span=self.slow, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=self.signal, adjust=False).mean()
            result = (macd_line - signal_line) / price

        result.name = self.name
        return result


class MADeviation(BaseFactor):
    """Moving average deviation (均线偏离).

    (Close - MA_N) / MA_N: how far price deviates from its moving average.

    Positive values = price above MA (trending up). In A-shares, intermediate-term
    MA deviation has momentum continuation properties.

    Standard setting uses 60-day MA (quarterly trend).
    """

    name = "ma_deviation"
    category = "technical"
    frequency = "daily"
    requires = ["close"]

    def __init__(self, period: int = 60):
        self.period = period

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        if "close" not in panel.columns:
            return pd.Series(index=panel.index, dtype=float)

        if isinstance(panel.index, pd.MultiIndex):
            def _calc_ma_dev(group):
                group = group.sort_index()
                price = group["close"]
                ma = price.rolling(self.period, min_periods=self.period // 2).mean()
                return (price - ma) / ma

            result = panel.groupby(level="symbol", group_keys=False).apply(_calc_ma_dev)
        else:
            price = panel["close"]
            ma = price.rolling(self.period, min_periods=self.period // 2).mean()
            result = (price - ma) / ma

        result.name = self.name
        return result
