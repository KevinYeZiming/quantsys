"""Portfolio-level evaluation engine.

Provides comprehensive portfolio analysis including risk decomposition,
correlation analysis, efficient frontier, performance attribution,
and weight optimization for small-capital A-share portfolios.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from quantsys.advisor.index_analyzer import IndexAnalyzer
from quantsys.data.sources.cache import CacheManager

logger = logging.getLogger(__name__)


@dataclass
class PortfolioReport:
    """Comprehensive portfolio evaluation report."""

    date: str

    # Portfolio summary
    total_value: float = 0.0
    cash: float = 0.0
    n_positions: int = 0
    is_invested: bool = False

    # Holdings detail
    holdings: list[dict] = field(default_factory=list)

    # Risk metrics
    portfolio_volatility: float = 0.0        # Annualized volatility (%)
    portfolio_var_95: float = 0.0            # 95% daily VaR (%)
    portfolio_cvar_95: float = 0.0           # 95% daily CVaR (%)
    max_drawdown: float = 0.0               # Max drawdown from peak (%)
    current_drawdown: float = 0.0            # Current drawdown (%)

    # Performance ratios (if benchmark available)
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Benchmark-relative metrics
    beta: float = 0.0
    alpha: float = 0.0                     # Annualized (%)
    excess_return: float = 0.0              # Over benchmark (% annualized)
    tracking_error: float = 0.0
    information_ratio: float = 0.0
    benchmark_code: str = ""
    benchmark_name: str = ""
    benchmark_return: float = 0.0           # Benchmark's own return (% annualized)

    # Correlation
    correlation_matrix: list[list[float]] = field(default_factory=list)
    corr_labels: list[str] = field(default_factory=list)
    avg_correlation: float = 0.0             # Average pairwise correlation

    # Risk decomposition
    concentration_hhi: float = 0.0            # Herfindahl-Hirschman Index
    vol_contribution: dict[str, float] = field(default_factory=dict)
    largest_position_pct: float = 0.0

    # Efficient frontier
    frontier_points: list[dict] = field(default_factory=list)  # [{vol, ret, weights}]
    optimal_weights: dict[str, float] = field(default_factory=dict)  # Max Sharpe weights
    min_vol_weights: dict[str, float] = field(default_factory=dict)

    # Warnings and suggestions
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    # Health
    health: str = "unknown"  # healthy, warning, critical


class PortfolioEvaluator:
    """Portfolio-level quantitative evaluation engine.

    Computes risk metrics, correlation structure, efficient frontier,
    and provides weight optimization suggestions.

    Usage::

        pe = PortfolioEvaluator()
        report = pe.evaluate(
            positions=[{"symbol": "600519", "quantity": 100, "avg_cost": 1700}],
            cash=5000,
            date="2025-12-31",
        )
    """

    WARNING_CORRELATION = 0.70       # High avg correlation warning
    WARNING_CONCENTRATION = 0.50    # Single position > 50%
    CRITICAL_CONCENTRATION = 0.80
    WARNING_DRAWDOWN = -0.08
    CRITICAL_DRAWDOWN = -0.15
    RISK_FREE_RATE = 0.025          # 2.5% annual

    def __init__(self, cache_dir: str | Path = None):
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / "data" / "raw"
        self._cache_dir = Path(cache_dir)
        self._cache = CacheManager(self._cache_dir)

    def evaluate(
        self,
        positions: list[dict],
        cash: float = 0.0,
        date: str = None,
        lookback: int = 252,
        benchmark: str = None,
    ) -> PortfolioReport:
        """Run full portfolio evaluation.

        Args:
            positions: List of {symbol, quantity, avg_cost}.
            cash: Available cash.
            date: Evaluation date.
            lookback: Trading days for risk estimation.
            benchmark: Optional index code (e.g. "000300") for benchmark-relative metrics.

        Returns:
            PortfolioReport with all metrics.
        """
        if date is None:
            from datetime import datetime
            date = datetime.now().strftime("%Y-%m-%d")

        positions = positions or []
        report = PortfolioReport(date=date)
        report.cash = cash
        report.n_positions = len(positions)

        target_date = pd.Timestamp(date)

        # Enrich positions with current prices
        total_mv = 0.0
        price_data = {}

        for pos in positions:
            symbol = pos.get("symbol", "")
            qty = pos.get("quantity", 0)
            cost = pos.get("avg_cost", 0)

            current_price = self._get_price(symbol, target_date)
            mv = current_price * qty
            pnl_pct = (current_price / cost - 1) if cost > 0 else 0

            price_data[symbol] = {
                "price": current_price,
                "quantity": qty,
                "cost": cost,
                "mv": mv,
                "pnl_pct": pnl_pct,
            }

            report.holdings.append({
                "symbol": symbol,
                "name": pos.get("name", ""),
                "quantity": qty,
                "avg_cost": cost,
                "current_price": current_price,
                "market_value": mv,
                "pnl_pct": round(pnl_pct * 100, 2),
                "weight": 0.0,
            })

            total_mv += mv

        report.total_value = cash + total_mv
        report.is_invested = total_mv > 0

        # Update weights
        for h in report.holdings:
            h["weight"] = round(h["market_value"] / report.total_value * 100, 1) if report.total_value > 0 else 0.0

        # Concentration
        if report.holdings:
            weights = [h["market_value"] / total_mv for h in report.holdings] if total_mv > 0 else []
            report.concentration_hhi = sum(w ** 2 for w in weights) if weights else 0
            report.largest_position_pct = max(weights) if weights else 0

        # Risk analysis (if invested)
        if report.is_invested and len(report.holdings) >= 1:
            self._compute_risk_metrics(report, price_data, lookback, target_date)

        # Correlation analysis (need 2+ positions)
        if len(report.holdings) >= 2:
            self._compute_correlation(report, price_data, lookback, target_date)

        # Efficient frontier (need 2+ positions)
        if len(report.holdings) >= 2:
            self._compute_efficient_frontier(report, price_data, lookback, target_date)

        # Warnings & suggestions
        self._generate_diagnostics(report)

        # Benchmark-relative metrics
        if benchmark and report.is_invested:
            self._compute_benchmark_metrics(report, price_data, lookback, target_date, benchmark)

        return report

    # -- Internal methods -------------------------------------------------

    def _get_price(self, symbol: str, target_date: pd.Timestamp) -> float:
        df = self._cache.get("stock_daily", symbol=symbol)
        if df is None or df.empty:
            return 0.0
        df = df.sort_index()
        available = df[df.index <= target_date]
        if available.empty or "close" not in available.columns:
            return 0.0
        return float(available["close"].iloc[-1])

    def _get_return_series(
        self, symbols: list[str], lookback: int, target_date: pd.Timestamp
    ) -> pd.DataFrame:
        """Build a returns DataFrame for the portfolio constituents."""
        returns = {}
        for symbol in symbols:
            df = self._cache.get("stock_daily", symbol=symbol)
            if df is None or df.empty:
                continue
            df = df.sort_index()
            available = df[df.index <= target_date]
            if len(available) < lookback:
                continue
            rets = available["close"].pct_change().dropna().tail(lookback)
            if len(rets) >= 20:
                returns[symbol] = rets

        if not returns:
            return pd.DataFrame()

        return pd.DataFrame(returns).dropna()

    def _compute_risk_metrics(
        self, report: PortfolioReport, price_data: dict,
        lookback: int, target_date: pd.Timestamp,
    ):
        """Compute portfolio-level risk metrics."""
        symbols = list(price_data.keys())
        returns_df = self._get_return_series(symbols, lookback, target_date)
        if returns_df.empty:
            return

        # Portfolio weights
        weights = np.array([
            price_data[s]["mv"] / (sum(p["mv"] for p in price_data.values()))
            for s in returns_df.columns
            if s in price_data
        ])
        if len(weights) != len(returns_df.columns):
            return

        returns_df = returns_df[[s for s in returns_df.columns if s in price_data]]

        # Portfolio daily returns
        port_rets = (returns_df * weights).sum(axis=1)

        # Annualized volatility
        report.portfolio_volatility = float(port_rets.std() * np.sqrt(252) * 100)

        # VaR and CVaR (95%)
        if len(port_rets) >= 20:
            report.portfolio_var_95 = float(np.percentile(port_rets, 5) * 100)
            report.portfolio_cvar_95 = float(port_rets[port_rets <= np.percentile(port_rets, 5)].mean() * 100)

        # Max drawdown
        cum_ret = (1 + port_rets).cumprod()
        running_max = cum_ret.cummax()
        drawdown = (cum_ret / running_max - 1)
        report.max_drawdown = float(drawdown.min() * 100)
        report.current_drawdown = float(drawdown.iloc[-1] * 100) if not drawdown.empty else 0.0

        # Sharpe ratio
        excess = port_rets.mean() * 252 - self.RISK_FREE_RATE
        vol = port_rets.std() * np.sqrt(252)
        report.sharpe_ratio = float(excess / vol) if vol > 0 else 0.0

        # Sortino ratio (downside deviation)
        downside = port_rets[port_rets < 0].std() * np.sqrt(252)
        report.sortino_ratio = float(excess / downside) if downside > 0 else 0.0

        # Calmar ratio
        report.calmar_ratio = float(excess / abs(report.max_drawdown / 100)) if report.max_drawdown != 0 else 0.0

        # Volatility contribution per position
        cov = returns_df.cov() * 252
        port_vol = np.sqrt(weights @ cov.values @ weights)
        if port_vol > 0:
            marg_contrib = cov.values @ weights
            vol_contrib = weights * marg_contrib / port_vol
            report.vol_contribution = {
                sym: round(float(vc * 100), 1)
                for sym, vc in zip(returns_df.columns, vol_contrib)
            }

    def _compute_correlation(
        self, report: PortfolioReport, price_data: dict,
        lookback: int, target_date: pd.Timestamp,
    ):
        """Compute correlation matrix."""
        symbols = list(price_data.keys())
        returns_df = self._get_return_series(symbols, min(lookback, 60), target_date)
        if returns_df.empty or len(returns_df.columns) < 2:
            return

        corr = returns_df.corr()
        report.corr_labels = list(corr.columns)
        report.correlation_matrix = corr.values.tolist()

        # Average pairwise correlation (excluding diagonal)
        n = len(corr)
        if n > 1:
            report.avg_correlation = float((corr.values.sum() - n) / (n * (n - 1)))

    def _compute_efficient_frontier(
        self, report: PortfolioReport, price_data: dict,
        lookback: int, target_date: pd.Timestamp,
    ):
        """Generate efficient frontier data points."""
        symbols = list(price_data.keys())
        returns_df = self._get_return_series(symbols, lookback, target_date)
        if returns_df.empty or len(returns_df.columns) < 2:
            return

        # Clip at 2-10 assets
        cols = list(returns_df.columns)[:10]
        returns_df = returns_df[cols]

        mean_rets = returns_df.mean() * 252
        cov = returns_df.cov() * 252
        n = len(cols)

        # Generate random portfolios for efficient frontier visualization
        np.random.seed(42)
        n_portfolios = 200
        frontier = []

        for _ in range(n_portfolios):
            w = np.random.random(n)
            w = w / w.sum()
            port_ret = np.dot(w, mean_rets.values)
            port_vol = np.sqrt(w @ cov.values @ w)
            frontier.append({
                "volatility": round(float(port_vol * 100), 2),
                "return": round(float(port_ret * 100), 2),
                "sharpe": round(float((port_ret - self.RISK_FREE_RATE) / port_vol), 3) if port_vol > 0 else 0,
            })

        report.frontier_points = sorted(frontier, key=lambda x: x["volatility"])

        # Max Sharpe weights (from random portfolios)
        best = max(frontier, key=lambda x: x["sharpe"])
        best_idx = frontier.index(best)
        # Reconstruct weights from the same random seed
        np.random.seed(42)
        for i in range(n_portfolios):
            w = np.random.random(n)
            w = w / w.sum()
            if i == best_idx:
                report.optimal_weights = {
                    col: round(float(w[j]) * 100, 1)
                    for j, col in enumerate(cols)
                }
                break

        # Min volatility weights
        min_vol = min(frontier, key=lambda x: x["volatility"])
        min_idx = frontier.index(min_vol)
        np.random.seed(42)
        for i in range(n_portfolios):
            w = np.random.random(n)
            w = w / w.sum()
            if i == min_idx:
                report.min_vol_weights = {
                    col: round(float(w[j]) * 100, 1)
                    for j, col in enumerate(cols)
                }
                break

    def _compute_benchmark_metrics(
        self, report: PortfolioReport, price_data: dict,
        lookback: int, target_date, benchmark: str,
    ):
        """Compute portfolio beta, alpha, and tracking error vs benchmark."""
        try:
            analyzer = IndexAnalyzer(self._cache_dir)
            bm_rets = analyzer.benchmark_returns(code=benchmark, date=str(target_date.date()), lookback=lookback)
            if bm_rets.empty or len(bm_rets) < 20:
                return

            # Get portfolio returns
            symbols = list(price_data.keys())
            returns_df = self._get_return_series(symbols, lookback, target_date)
            if returns_df.empty:
                return

            weights = np.array([
                price_data[s]["mv"] / (sum(p["mv"] for p in price_data.values()))
                for s in returns_df.columns if s in price_data
            ])
            if len(weights) != len(returns_df.columns):
                return

            returns_df = returns_df[[s for s in returns_df.columns if s in price_data]]
            port_rets = (returns_df * weights).sum(axis=1)

            # Align dates between portfolio and benchmark
            common_idx = port_rets.index.intersection(bm_rets.index)
            if len(common_idx) < 20:
                return
            p = port_rets.loc[common_idx]
            b = bm_rets.loc[common_idx]

            # Beta
            cov_matrix = np.cov(p, b)
            bm_var = np.var(b)
            report.beta = float(cov_matrix[0, 1] / bm_var) if bm_var > 0 else 0.0

            # Alpha (annualized)
            p_annual = p.mean() * 252
            b_annual = b.mean() * 252
            report.alpha = float((p_annual - self.RISK_FREE_RATE) - report.beta * (b_annual - self.RISK_FREE_RATE)) * 100

            # Excess return over benchmark
            report.excess_return = float(p_annual - b_annual) * 100
            report.benchmark_return = float(b_annual) * 100

            # Tracking error
            diff = p - b
            report.tracking_error = float(diff.std() * np.sqrt(252) * 100)

            # Information ratio
            if report.tracking_error > 0:
                report.information_ratio = float(report.excess_return / report.tracking_error)

            # Benchmark name
            report.benchmark_code = benchmark
            report.benchmark_name = IndexAnalyzer.INDEX_NAMES.get(benchmark, benchmark)

        except Exception as e:
            logger.warning(f"Benchmark metrics failed for {benchmark}: {e}")

    def _generate_diagnostics(self, report: PortfolioReport):
        """Generate warnings and suggestions."""
        # Concentration
        if report.largest_position_pct >= self.CRITICAL_CONCENTRATION:
            report.warnings.append(f"单票集中度 {report.largest_position_pct:.0%} 过高，建议分散")
            report.health = "critical"
        elif report.largest_position_pct >= self.WARNING_CONCENTRATION:
            report.warnings.append(f"单票集中度 {report.largest_position_pct:.0%} 偏高")
            if report.health != "critical":
                report.health = "warning"

        # Correlation
        if report.avg_correlation >= self.WARNING_CORRELATION:
            report.warnings.append(f"组合平均相关性 {report.avg_correlation:.2f} 偏高，分散效果有限")

        # Drawdown
        if report.current_drawdown <= self.CRITICAL_DRAWDOWN:
            report.warnings.append(f"当前回撤 {report.current_drawdown:.1f}%，触发严重警告")
            report.health = "critical"
            report.suggestions.append("建议减仓或对冲，控制回撤")
        elif report.current_drawdown <= self.WARNING_DRAWDOWN:
            report.warnings.append(f"当前回撤 {report.current_drawdown:.1f}%，注意风险")
            if report.health != "critical":
                report.health = "warning"

        # Volatility
        if report.portfolio_volatility > 40:
            report.warnings.append(f"组合波动率 {report.portfolio_volatility:.0f}% 偏高")

        # Suggestions
        if report.optimal_weights and report.holdings:
            current_weights = {
                h["symbol"]: h["market_value"] / sum(x["market_value"] for x in report.holdings) * 100
                for h in report.holdings if h["market_value"] > 0
            }
            # Find largest weight differences
            diffs = []
            for sym, opt_w in report.optimal_weights.items():
                cur_w = current_weights.get(sym, 0)
                if abs(opt_w - cur_w) > 10:
                    diffs.append((sym, cur_w, opt_w))
            if diffs:
                diffs.sort(key=lambda x: abs(x[2] - x[1]), reverse=True)
                top_diff = diffs[0]
                direction = "增配" if top_diff[2] > top_diff[1] else "减配"
                report.suggestions.append(
                    f"建议{direction} {top_diff[0]}: 当前 {top_diff[1]:.0f}% → 目标 {top_diff[2]:.0f}%"
                )

        if report.n_positions == 0:
            report.suggestions.append("当前空仓，可关注评估得分 > 65 的标的")

        if report.n_positions == 1:
            report.suggestions.append("仅持有一只标的，建议关注相关性低的第二标的以分散风险")

        # Benchmark-aware diagnostics
        if report.benchmark_code:
            if report.alpha < -5:
                report.warnings.append(f"组合年化alpha为 {report.alpha:.1f}%，显著跑输{report.benchmark_name}")
                report.suggestions.append("主动管理未产生超额收益，考虑简化组合跟踪指数")
            elif report.alpha < 0:
                report.suggestions.append(f"组合略跑输{report.benchmark_name}，alpha {report.alpha:.1f}%")
            else:
                report.suggestions.append(f"组合跑赢{report.benchmark_name}，年化alpha {report.alpha:+.1f}%")

            if report.beta > 1.3:
                report.warnings.append(f"组合beta {report.beta:.1f}，为高beta组合，熊市回撤风险大")
            elif report.beta < 0.7:
                report.suggestions.append(f"组合beta {report.beta:.1f}，偏防御，牛市可能跑输指数")

            if report.information_ratio < 0:
                report.suggestions.append(f"信息比率 {report.information_ratio:.2f} 为负，主动管理未带来正收益")

        # Overall health
        if report.health == "unknown":
            report.health = "healthy" if not report.warnings else "warning"
