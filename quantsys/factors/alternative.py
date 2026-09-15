"""Alternative factors (另类因子) for Chinese A-shares.

These factors are derived from behavioral finance and market microstructure
research, adapted for A-share market characteristics.

Based on QuantsPlaybook and Zhu Yifeng (2025):
- Smart Money Flow: capital flow-based factor
- Salience Theory (STR): predicts overpricing of salient stocks
- Max Effect: stocks with extreme daily returns underperform
"""

import numpy as np
import pandas as pd

from quantsys.factors.base import BaseFactor


class SmartMoneyFlow(BaseFactor):
    """Smart money flow factor (聪明钱因子).

    Identifies "smart money" activity based on minute-level trade classification.
    Simplified version uses daily large-order flow data from AKShare.

    The idea: large institutional orders ("smart money") predict future returns.
    Higher net inflow = higher factor value = higher expected return.
    """

    name = "smart_money"
    category = "alternative"
    frequency = "daily"
    requires = ["close", "volume"]

    def __init__(self, period: int = 10):
        self.period = period

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        """Compute smart money flow from available data.

        If money flow data columns exist (主力净流入/超大单净流入 etc.),
        use them directly. Otherwise, use a volume-price relationship proxy.

        The proxy: volume * sign(daily_return) smoothed over period.
        This captures large-volume up days vs down days.
        """
        # Check for direct money flow data
        mf_columns = ["main_net_inflow", "主力净流入", "super_large_net_inflow"]
        for col in mf_columns:
            if col in panel.columns:
                if isinstance(panel.index, pd.MultiIndex):
                    result = panel.groupby(level="symbol")[col].transform(
                        lambda x: x.rolling(self.period, min_periods=5).mean()
                    )
                else:
                    result = panel[col].rolling(self.period, min_periods=5).mean()
                result.name = self.name
                return result

        # Proxy: volume-weighted return direction
        if "close" not in panel.columns:
            return pd.Series(index=panel.index, dtype=float)

        if isinstance(panel.index, pd.MultiIndex):
            ret = panel.groupby(level="symbol")["close"].transform(
                lambda x: x.pct_change()
            )
        else:
            ret = panel["close"].pct_change()

        # Smart money proxy: sign of daily return, averaged
        direction = np.sign(ret)
        volume = panel["volume"] if "volume" in panel.columns else pd.Series(1, index=panel.index)

        proxy = direction * (volume / volume.groupby(level=0).transform("mean") if isinstance(panel.index, pd.MultiIndex) else volume / volume.mean())

        if isinstance(panel.index, pd.MultiIndex):
            result = proxy.groupby(level="symbol").transform(
                lambda x: x.rolling(self.period, min_periods=5).mean()
            )
        else:
            result = proxy.rolling(self.period, min_periods=5).mean()

        result.name = self.name
        return result


class SalienceTheory(BaseFactor):
    """Salience Theory Ranking (STR) factor (凸显性因子).

    Based on Bordalo, Gennaioli & Shleifer's Salience Theory, adapted
    for A-shares by Zhu Yifeng (2025) and broker research.

    Stocks with salient (attention-grabbing) returns tend to be overpriced
    and subsequently underperform. The STR factor captures how "salient"
    a stock's recent returns are relative to the market.

    Factor is negated: higher salience = lower expected return.
    """

    name = "str_factor"
    category = "alternative"
    frequency = "daily"
    requires = ["close"]

    def __init__(self, period: int = 20):
        self.period = period

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        """Compute STR factor.

        Simplified: measure how extreme a stock's returns are vs.
        cross-sectional distribution. Stocks with very high positive
        returns get high salience scores.

        For multi-index panels, compare each stock's return to the
        cross-sectional distribution on each date.
        """
        if "close" not in panel.columns:
            return pd.Series(index=panel.index, dtype=float)

        if isinstance(panel.index, pd.MultiIndex):
            ret = panel.groupby(level="symbol")["close"].transform(
                lambda x: x.pct_change()
            )
            # Cross-sectional z-score of returns per date
            ret_mean = ret.groupby(level="date").transform("mean")
            ret_std = ret.groupby(level="date").transform("std").replace(0, pd.NA)

            # Z-score within the last `period` days
            zscore = (ret - ret_mean) / ret_std

            def _rolling_salience(group):
                return group.rolling(self.period, min_periods=10).mean()

            # Higher absolute z-score = more salient
            salience = np.abs(zscore)
            if isinstance(panel.index, pd.MultiIndex):
                avg_salience = panel.groupby(level="symbol")[salience.name if hasattr(salience, 'name') else 0].transform(_rolling_salience)
            else:
                avg_salience = salience.rolling(self.period, min_periods=10).mean()

        else:
            ret = panel["close"].pct_change()
            # Rolling z-score
            rolling_mean = ret.rolling(self.period).mean()
            rolling_std = ret.rolling(self.period).std()
            zscore = (ret - rolling_mean) / rolling_std.replace(0, pd.NA)
            avg_salience = np.abs(zscore).rolling(self.period, min_periods=10).mean()

        # Negate: higher salience = lower expected return
        result = -avg_salience
        result.name = self.name
        return result


class MaxEffect(BaseFactor):
    """Maximum daily return effect (最大值效应因子).

    Stocks with extreme maximum daily returns in the recent past tend to
    underperform. This "MAX effect" is well-documented in A-shares and
    is attributed to retail investors' lottery preferences.

    Factor is negated: higher max return = lower expected future return.
    """

    name = "max_effect"
    category = "alternative"
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
            max_ret = panel.groupby(level="symbol")[daily_ret.name if hasattr(daily_ret, 'name') else 0].transform(
                lambda x: x.rolling(self.period, min_periods=10).max()
            )
        else:
            daily_ret = panel["close"].pct_change()
            max_ret = daily_ret.rolling(self.period, min_periods=10).max()

        # Negate: higher max return = lower factor value = lower expected return
        result = -max_ret
        result.name = self.name
        return result
