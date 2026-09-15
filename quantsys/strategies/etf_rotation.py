"""ETF rotation strategy (ETF轮动策略).

Momentum-based ETF rotation with risk parity allocation.
Core-satellite structure: 90% core (diversified allocation) + 10% satellite (rotation).

Based on:
- Pomelo-ETF project (18.7% annual return, 9.4% max drawdown)
- CITIC Securities ETF full-scenario allocation framework
"""

import logging

import numpy as np
import pandas as pd

from quantsys.strategies.base import BaseStrategy
from quantsys.portfolio.risk_parity import RiskParityOptimizer

logger = logging.getLogger(__name__)

# Default ETF basket with categories
DEFAULT_ETF_BASKET = {
    # Broad market (宽基)
    "510300": "沪深300", "510500": "中证500", "159915": "创业板",
    "588000": "科创50", "510050": "上证50",
    # Style (风格)
    "510880": "红利",
    # Sector (行业)
    "512880": "证券", "512010": "医药", "159995": "芯片",
    "515790": "光伏", "512660": "军工", "512800": "银行",
    # Bond (债券)
    "511260": "十年国债", "511220": "城投债",
    # Commodity (商品)
    "518880": "黄金",
    # Money market (货币)
    "511880": "货币",
}


class ETFRotationStrategy(BaseStrategy):
    """ETF momentum rotation with risk parity.

    Process:
    1. Compute momentum scores for all ETFs in the basket
    2. Select top-K ETFs by momentum
    3. Allocate using risk parity based on recent volatility
    4. Rebalance monthly

    Config options:
        top_k: Number of ETFs to hold (default 5)
        momentum_period: Lookback days for momentum (default 20)
        volatility_period: Lookback days for volatility (default 60)
        allocation_method: 'risk_parity' or 'equal_weight' or 'momentum_weighted'
        core_satellite.core_pct: Core portfolio allocation (default 0.90)
    """

    name = "etf_rotation"

    def __init__(self, config: dict = None, cache_dir: str = None):
        super().__init__(config, cache_dir)
        self.rp_optimizer = RiskParityOptimizer()

        cfg = self.config.get("etf_rotation", {})
        self.top_k = cfg.get("top_k", 5)
        self.momentum_period = cfg.get("momentum_period", 20)
        self.volatility_period = cfg.get("volatility_period", 60)
        self.allocation_method = cfg.get("allocation_method", "risk_parity")

        # Load ETF basket
        self.etf_basket = DEFAULT_ETF_BASKET

    def _compute_momentum_scores(
        self, etf_codes: list[str], date: str
    ) -> pd.Series:
        """Compute momentum scores for ETFs.

        Momentum = (price_t - price_{t-N}) / price_{t-N}

        Args:
            etf_codes: List of ETF codes.
            date: Reference date.

        Returns:
            Series mapping ETF code -> momentum score.
        """
        scores = {}
        date_ts = pd.Timestamp(date)
        lookback_end = date_ts
        lookback_start = date_ts - pd.DateOffset(days=self.momentum_period * 2)

        for code in etf_codes:
            df = self.cache.get("etf_daily", symbol=code)
            if df is None or df.empty:
                continue

            df = df.sort_index()
            if lookback_end not in df.index:
                # Find nearest previous trading day
                prev_dates = df.index[df.index <= lookback_end]
                if len(prev_dates) == 0:
                    continue
                actual_end = prev_dates[-1]
            else:
                actual_end = lookback_end

            # Find price N days before
            all_dates = df.index[df.index <= actual_end]
            if len(all_dates) <= self.momentum_period:
                continue

            start_idx = len(all_dates) - 1 - self.momentum_period
            actual_start = all_dates[max(0, start_idx)]

            if actual_start >= actual_end:
                continue

            p_start = df.loc[actual_start, "close"]
            p_end = df.loc[actual_end, "close"]

            if isinstance(p_start, pd.Series):
                p_start = p_start.iloc[0]
            if isinstance(p_end, pd.Series):
                p_end = p_end.iloc[0]

            if p_start > 0:
                momentum = (p_end / p_start) - 1.0
                scores[code] = momentum

        return pd.Series(scores)

    def generate_signals(self, universe: list[str], date: str) -> pd.Series:
        """Generate ETF position weights.

        Args:
            universe: Not used (ETF basket is predefined).
            date: Reference date 'YYYY-MM-DD'.

        Returns:
            Series mapping ETF code -> target weight.
        """
        etf_codes = list(self.etf_basket.keys())

        # Step 1: Compute momentum scores
        scores = self._compute_momentum_scores(etf_codes, date)
        if scores.empty:
            logger.warning(f"No ETF momentum data for {date}")
            return pd.Series(dtype=float)

        # Step 2: Select top-K ETFs
        top_etfs = scores.nlargest(self.top_k)

        # Step 3: Compute allocation
        if self.allocation_method == "risk_parity":
            weights = self._allocate_risk_parity(top_etfs.index.tolist(), date)
        elif self.allocation_method == "momentum_weighted":
            weights = top_etfs / top_etfs.sum()
        else:
            weights = pd.Series(1.0 / len(top_etfs), index=top_etfs.index)

        # Step 4: Scale to satellite allocation if using core-satellite
        core_satellite = self.config.get("etf_rotation", {}).get("core_satellite", {})
        satellite_pct = core_satellite.get("satellite_pct", 0.10)

        weights = weights * satellite_pct

        logger.info(f"ETF rotation ({date}): selected {len(weights)} ETFs")
        return weights

    def _allocate_risk_parity(
        self, symbols: list[str], date: str, lookback: int = 60
    ) -> pd.Series:
        """Compute risk parity weights for selected ETFs.

        Args:
            symbols: Selected ETF codes.
            date: Reference date.
            lookback: Volatility estimation window.

        Returns:
            Series of risk parity weights.
        """
        returns_data = {}
        date_ts = pd.Timestamp(date)

        for code in symbols:
            df = self.cache.get("etf_daily", symbol=code)
            if df is None or df.empty:
                continue

            df = df.sort_index()
            start_date = date_ts - pd.DateOffset(days=lookback * 2)
            df = df.loc[start_date:date_ts]

            if len(df) < lookback // 2:
                continue

            returns = df["close"].pct_change().dropna().tail(lookback)
            returns_data[code] = returns

        if len(returns_data) < 2:
            return pd.Series(1.0 / len(symbols), index=symbols)

        returns_df = pd.DataFrame(returns_data).dropna()
        if returns_df.empty or returns_df.shape[1] < 2:
            return pd.Series(1.0 / len(symbols), index=symbols)

        rp = RiskParityOptimizer()
        weights = rp.equal_risk_contribution(returns_df)
        return weights.reindex(symbols).fillna(0)
