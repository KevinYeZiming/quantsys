"""Momentum and reversal factors (动量和反转因子) for Chinese A-shares.

Momentum factors measure price continuation. In A-shares, intermediate-term
momentum (6-12 months) and short-term reversal (1-4 weeks) are particularly
well-documented (Zhu, 2025).

For momentum: higher values = stronger recent returns = positive expected future returns.
For reversal: higher values = stronger recent declines = positive expected bounce.
"""

import pandas as pd

from quantsys.factors.base import BaseFactor


class Momentum12M1M(BaseFactor):
    """12-month momentum skipping the most recent month.

    Also known as 12-1 momentum. This is the canonical momentum factor from
    Jegadeesh & Titman (1993), adapted for A-shares.

    Return = cumulative return from t-12 to t-1 months ago.
    Skipping t-1 avoids the short-term reversal confound.
    """

    name = "momentum_12m_1m"
    category = "momentum"
    frequency = "monthly"
    requires = ["close"]

    def __init__(self, period: int = 12, skip_recent: int = 1):
        self.period = period
        self.skip_recent = skip_recent

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        if "close" not in panel.columns:
            return pd.Series(index=panel.index, dtype=float)

        # For monthly frequency: compute returns between month-ends
        close = panel["close"]

        def _calc_momentum(group):
            group = group.sort_index()
            prices = group["close"] if isinstance(group, pd.DataFrame) else group
            if len(prices) < self.period + self.skip_recent + 1:
                return pd.Series([pd.NA] * len(group), index=group.index)

            result = pd.Series(index=group.index, dtype=float)
            for i in range(len(prices)):
                if i < self.period + self.skip_recent:
                    result.iloc[i] = pd.NA
                else:
                    # Price from (period+skip) days ago vs (skip) days ago
                    past_price = prices.iloc[i - self.period - self.skip_recent]
                    recent_price = prices.iloc[i - self.skip_recent]
                    if past_price and past_price > 0:
                        result.iloc[i] = recent_price / past_price - 1.0
            return result

        if isinstance(panel.index, pd.MultiIndex):
            return panel.groupby(level="symbol", group_keys=False).apply(_calc_momentum)
        else:
            return _calc_momentum(panel)


class Momentum60D(BaseFactor):
    """60-day (approximately 3-month) trailing return.

    Intermediate-term momentum is a well-documented factor in A-shares.
    The 60-day window captures the 3-month momentum effect documented
    in broker research (QuantsPlaybook).
    """

    name = "momentum_60d"
    category = "momentum"
    frequency = "daily"
    requires = ["close"]

    def __init__(self, period: int = 60):
        self.period = period

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        if "close" not in panel.columns:
            return pd.Series(index=panel.index, dtype=float)

        if isinstance(panel.index, pd.MultiIndex):
            result = panel.groupby(level="symbol")["close"].transform(
                lambda x: x.pct_change(self.period)
            )
        else:
            result = panel["close"].pct_change(self.period)

        result.name = self.name
        return result


class ShortTermReversal(BaseFactor):
    """Short-term reversal factor.

    Negative of short-term (5-day) return. In A-shares, short-term reversal is
    particularly strong - stocks that dropped recently tend to bounce back,
    especially in small-caps (Zhu, 2025).

    Higher values = more negative recent returns = stronger expected reversal.
    """

    name = "reversal_5d"
    category = "momentum"
    frequency = "daily"
    requires = ["close"]

    def __init__(self, period: int = 5):
        self.period = period

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        if "close" not in panel.columns:
            return pd.Series(index=panel.index, dtype=float)

        if isinstance(panel.index, pd.MultiIndex):
            ret = panel.groupby(level="symbol")["close"].transform(
                lambda x: x.pct_change(self.period)
            )
        else:
            ret = panel["close"].pct_change(self.period)

        # Negative sign: stocks with negative returns get higher factor values
        result = -ret
        result.name = self.name
        return result
