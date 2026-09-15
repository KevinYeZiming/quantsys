"""Liquidity factors (流动性因子) for Chinese A-shares.

Liquidity factors capture trading activity and market impact. In A-shares,
lower liquidity (higher illiquidity) is typically associated with a
liquidity premium - less liquid stocks earn higher returns.

Based on Amihud (2002) and broker research (QuantsPlaybook).
"""

import numpy as np
import pandas as pd

from quantsys.factors.base import BaseFactor


class Turnover20D(BaseFactor):
    """Average 20-day turnover rate (换手率因子).

    Measures average daily trading activity as a percentage of shares outstanding.
    In A-shares, high turnover is associated with speculative retail trading
    and lower subsequent returns.

    Factor is negated: lower turnover = higher factor value = higher expected return.
    """

    name = "turnover_20d"
    category = "liquidity"
    frequency = "daily"
    requires = ["turnover"]

    def __init__(self, period: int = 20):
        self.period = period

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        if "turnover" not in panel.columns:
            return pd.Series(index=panel.index, dtype=float)

        if isinstance(panel.index, pd.MultiIndex):
            avg_turnover = panel.groupby(level="symbol")["turnover"].transform(
                lambda x: x.rolling(self.period, min_periods=5).mean()
            )
        else:
            avg_turnover = panel["turnover"].rolling(self.period, min_periods=5).mean()

        # Negate: lower turnover = higher factor value
        result = -avg_turnover
        result.name = self.name
        return result


class VolumeCorrelation(BaseFactor):
    """Volume-return correlation (量价相关性因子).

    Correlation between daily volume changes and returns over the period.
    Positive correlation suggests volume confirms price moves (trend-following).
    Negative correlation suggests volume against price (potential reversal).

    In A-shares, positive volume-price correlation has been associated with
    momentum continuation (QuantsPlaybook, VolCorr factor).
    """

    name = "volume_corr"
    category = "liquidity"
    frequency = "daily"
    requires = ["close", "volume"]

    def __init__(self, period: int = 20):
        self.period = period

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        if "close" not in panel.columns or "volume" not in panel.columns:
            return pd.Series(index=panel.index, dtype=float)

        if isinstance(panel.index, pd.MultiIndex):
            def _rolling_corr(group):
                group = group.sort_index()
                ret = group["close"].pct_change()
                vol_chg = group["volume"].pct_change()
                valid = ret.notna() & vol_chg.notna()
                if valid.sum() < self.period // 2:
                    return pd.Series([pd.NA] * len(group), index=group.index)
                corr = ret.rolling(self.period, min_periods=10).corr(vol_chg)
                return corr

            result = panel.groupby(level="symbol", group_keys=False).apply(_rolling_corr)
        else:
            ret = panel["close"].pct_change()
            vol_chg = panel["volume"].pct_change()
            result = ret.rolling(self.period, min_periods=10).corr(vol_chg)

        result.name = self.name
        return result


class AmihudIlliq(BaseFactor):
    """Amihud illiquidity measure (Amihud非流动性因子).

    Average of |daily return| / daily dollar volume over the period.
    Higher values indicate greater price impact per unit of trading volume
    (less liquid stocks).

    Based on Amihud (2002) "Illiquidity and stock returns."
    Positive premium expected: less liquid stocks require higher returns.
    """

    name = "amihud_illiquidity"
    category = "liquidity"
    frequency = "daily"
    requires = ["close", "amount"]

    def __init__(self, period: int = 20):
        self.period = period

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        if "close" not in panel.columns or "amount" not in panel.columns:
            return pd.Series(index=panel.index, dtype=float)

        if isinstance(panel.index, pd.MultiIndex):
            ret = panel.groupby(level="symbol")["close"].transform(
                lambda x: x.pct_change()
            )
        else:
            ret = panel["close"].pct_change()

        daily_illiq = np.abs(ret) / (panel["amount"].replace(0, pd.NA))

        # Scale by 10^6 for readability
        daily_illiq = daily_illiq * 1e6

        if isinstance(panel.index, pd.MultiIndex):
            result = daily_illiq.groupby(level="symbol").transform(
                lambda x: x.rolling(self.period, min_periods=10).mean()
            )
        else:
            result = daily_illiq.rolling(self.period, min_periods=10).mean()

        result.name = self.name
        return result
