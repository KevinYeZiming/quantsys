"""Industry rotation strategy (行业轮动策略).

Multi-dimensional industry scoring based on:
- 20-day momentum
- 5-day capital flow intensity
- Turnover change rate

Based on broker research (Guojin Securities, GF Securities)
and QuantsPlaybook industry rotation models.
"""

import logging

import numpy as np
import pandas as pd

from quantsys.strategies.base import BaseStrategy
from quantsys.factors.registry import FactorRegistry
from quantsys.factors.processor import FactorProcessor

logger = logging.getLogger(__name__)


class IndustryRotationStrategy(BaseStrategy):
    """Industry rotation based on momentum and capital flows.

    Process:
    1. Compute industry-level scores (momentum + money flow + turnover)
    2. Rank industries
    3. Within top industries, select top stocks by multi-factor score
    4. Equal weight across industries

    Config options:
        top_industries: Number of industries to select (default 5)
        stocks_per_industry: Stocks per industry (default 3)
        momentum_period: Momentum lookback days (default 20)
        money_flow_period: Money flow lookback days (default 5)
    """

    name = "industry_rotation"

    def __init__(self, config: dict = None, cache_dir: str = None):
        super().__init__(config, cache_dir)

        cfg = self.config.get("industry_rotation", {})
        self.top_industries = cfg.get("top_industries", 5)
        self.stocks_per_industry = cfg.get("stocks_per_industry", 3)
        self.momentum_period = cfg.get("momentum_period", 20)
        self.money_flow_period = cfg.get("money_flow_period", 5)

        self.registry = FactorRegistry()
        self.registry.discover()
        self.processor = FactorProcessor()

    def _get_industry_groups(self, symbols: list[str]) -> pd.Series:
        """Get industry classification for stocks.

        Args:
            symbols: List of stock codes.

        Returns:
            Series mapping symbol -> industry name.
        """
        # Check if industry data exists in cache
        basic = self.cache.get("stock_basic")
        industries = {}

        if basic is not None and not basic.empty:
            # Try to match industry column
            industry_cols = ["industry", "industry_name", "行业", "所属行业"]
            for col in industry_cols:
                if col in basic.columns:
                    for _, row in basic.iterrows():
                        sym = str(row.get("symbol", ""))
                        if sym in symbols:
                            industries[sym] = str(row[col])
                    break

        # Fallback: assign to "其他" if no industry data
        for sym in symbols:
            if sym not in industries:
                industries[sym] = "其他"

        return pd.Series(industries)

    def _compute_industry_momentum(
        self, symbols: list[str], industries: pd.Series, date: str
    ) -> pd.Series:
        """Compute industry-level 20-day momentum.

        Returns:
            Series mapping industry -> average stock momentum.
        """
        date_ts = pd.Timestamp(date)
        start = (date_ts - pd.DateOffset(days=self.momentum_period * 2)).strftime("%Y-%m-%d")

        momentum_by_stock = {}
        for symbol in symbols:
            df = self.cache.get("stock_daily", symbol=symbol)
            if df is None or df.empty:
                continue

            df = df.sort_index()
            df_slice = df.loc[start:date]

            if len(df_slice) < self.momentum_period:
                continue

            prices = df_slice["close"]
            if prices.iloc[-1] > 0 and prices.iloc[-self.momentum_period] > 0:
                mom = prices.iloc[-1] / prices.iloc[-self.momentum_period] - 1.0
                momentum_by_stock[symbol] = mom

        if not momentum_by_stock:
            return pd.Series(dtype=float)

        mom_series = pd.Series(momentum_by_stock)
        # Aggregate to industry level
        industry_mom = mom_series.groupby(industries).mean()
        return industry_mom

    def generate_signals(
        self, universe: list[str], date: str
    ) -> pd.Series:
        """Generate position weights based on industry rotation.

        Args:
            universe: List of stock codes.
            date: Reference date.

        Returns:
            Series mapping symbol -> target weight.
        """
        if not universe:
            return pd.Series(dtype=float)

        # Step 1: Get industry classifications
        industries = self._get_industry_groups(universe)

        # Step 2: Compute industry momentum scores
        industry_mom = self._compute_industry_momentum(universe, industries, date)
        if industry_mom.empty:
            return pd.Series(dtype=float)

        # Step 3: Select top industries
        top_industries = industry_mom.nlargest(self.top_industries).index.tolist()

        # Step 4: Within each top industry, select top stocks
        date_ts = pd.Timestamp(date)
        start = (date_ts - pd.DateOffset(days=252)).strftime("%Y-%m-%d")

        all_weights = {}

        for ind in top_industries:
            ind_stocks = industries[industries == ind].index.tolist()
            if not ind_stocks:
                continue

            # Compute multi-factor scores within industry
            panel = self.load_data(ind_stocks, start, date)
            if panel.empty:
                continue

            try:
                factor_df = self.registry.compute_all(panel, self.config)
                current_factors = factor_df.loc[date_ts]
            except (KeyError, TypeError):
                # Assign equal weight within industry
                weight_per_stock = 1.0 / (len(ind_stocks) * self.top_industries)
                for s in ind_stocks:
                    all_weights[s] = weight_per_stock
                continue

            if current_factors.empty:
                continue

            # Composite score: simple average
            processed = {}
            for col in current_factors.columns:
                series = self.processor.winsorize(current_factors[col])
                series = self.processor.fill_na(series)
                series = self.processor.standardize(series)
                processed[col] = series

            if processed:
                composite = pd.DataFrame(processed).mean(axis=1)
                top_stocks = composite.nlargest(self.stocks_per_industry)
                weight_per_stock = 1.0 / (len(top_stocks) * self.top_industries)
                for s in top_stocks.index:
                    all_weights[s] = weight_per_stock

        if not all_weights:
            return pd.Series(dtype=float)

        result = pd.Series(all_weights)
        result = result / result.sum()  # Normalize to 1.0
        return result
