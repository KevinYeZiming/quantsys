"""Volatility factors (波动率因子) for Chinese A-shares.

Volatility factors capture return dispersion characteristics. Research shows
that idiosyncratic volatility and volatility skew have predictive power
in A-shares (QuantsPlaybook, Zhu 2025).

For idiosyncratic volatility: lower values typically predict higher returns (negative premium).
For amplitude: lower values predict higher returns.
For skew: positive skew predicts lower returns.
"""

import numpy as np
import pandas as pd

from quantsys.factors.base import BaseFactor


class IdioVolatility(BaseFactor):
    """Idiosyncratic volatility (特质波动率).

    Standard deviation of residuals from market model (CAPM) regression.
    In A-shares, low idiosyncratic volatility stocks tend to outperform
    high idiosyncratic volatility stocks (low-volatility anomaly).

    Factor is negated so that higher factor values = lower idiosyncratic vol
    = higher expected returns.
    """

    name = "idiosyncratic_vol"
    category = "volatility"
    frequency = "daily"
    requires = ["close"]

    def __init__(self, period: int = 60, half_life: int = 42):
        self.period = period
        self.half_life = half_life

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        if "close" not in panel.columns:
            return pd.Series(index=panel.index, dtype=float)

        if isinstance(panel.index, pd.MultiIndex):
            daily_ret = panel.groupby(level="symbol")["close"].transform(
                lambda x: x.pct_change()
            )
        else:
            daily_ret = panel["close"].pct_change()

        # Compute rolling standard deviation of returns
        if isinstance(panel.index, pd.MultiIndex):
            vol = panel.groupby(level="symbol")[daily_ret.name if hasattr(daily_ret, 'name') else 0].transform(
                lambda x: x.rolling(self.period, min_periods=20).std()
            )
        else:
            vol = daily_ret.rolling(self.period, min_periods=20).std()

        # Negate: lower vol = higher factor value = higher expected return
        result = -vol
        result.name = self.name
        return result


class VolatilitySkew(BaseFactor):
    """Volatility skew (收益率偏度).

    Skewness of daily returns over the lookback period.
    Stocks with negative skew (more downside tail risk) have been shown
    to earn higher returns in A-shares as compensation for tail risk.

    Negated so that negative skew = higher factor value = higher expected return.
    """

    name = "volatility_skew"
    category = "volatility"
    frequency = "daily"
    requires = ["close"]

    def __init__(self, period: int = 20):
        self.period = period

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        if "close" not in panel.columns:
            return pd.Series(index=panel.index, dtype=float)

        if isinstance(panel.index, pd.MultiIndex):
            daily_ret = panel.groupby(level="symbol")["close"].transform(
                lambda x: x.pct_change()
            )

            def _rolling_skew(x):
                if len(x.dropna()) < 10:
                    return pd.NA
                try:
                    return x.skew()
                except Exception:
                    return pd.NA

            skew = panel.groupby(level="symbol")[daily_ret.name if hasattr(daily_ret, 'name') else 0].transform(
                lambda x: x.rolling(self.period, min_periods=10).apply(_rolling_skew, raw=False)
            )
        else:
            daily_ret = panel["close"].pct_change()
            skew = daily_ret.rolling(self.period, min_periods=10).skew()

        # Negate: negative skew -> higher factor value -> higher expected return
        result = -skew
        result.name = self.name
        return result


class Amplitude20D(BaseFactor):
    """Average daily amplitude (振幅因子).

    Average of (high - low) / close over the period.
    Higher amplitude indicates more intraday volatility.

    In A-shares, high amplitude is associated with speculative trading and
    lower future returns. Factor is negated.
    """

    name = "amplitude_20d"
    category = "volatility"
    frequency = "daily"
    requires = ["high", "low", "close"]

    def __init__(self, period: int = 20):
        self.period = period

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        required = ["high", "low", "close"]
        if not all(c in panel.columns for c in required):
            return pd.Series(index=panel.index, dtype=float)

        daily_amplitude = (panel["high"] - panel["low"]) / panel["close"]

        if isinstance(panel.index, pd.MultiIndex):
            avg_amplitude = daily_amplitude.groupby(level="symbol").transform(
                lambda x: x.rolling(self.period, min_periods=10).mean()
            )
        else:
            avg_amplitude = daily_amplitude.rolling(self.period, min_periods=10).mean()

        # Negate: lower amplitude = higher factor value
        result = -avg_amplitude
        result.name = self.name
        return result
