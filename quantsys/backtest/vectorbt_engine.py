"""VectorBT backtest engine for fast signal-based and weight-based backtesting.

Complements the existing Backtrader engine with VectorBT's speed and
parameter optimization capabilities. Outputs VBTResult matching the
BacktestResult shape for consistent downstream consumption.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class VBTResult:
    """Structured backtest output matching BacktestResult shape."""

    strategy_name: str = ""
    start_date: str = ""
    end_date: str = ""

    # Performance metrics
    total_return: float = 0.0
    annual_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    calmar_ratio: float = 0.0
    sortino_ratio: float = 0.0
    win_rate: float = 0.0
    annual_volatility: float = 0.0

    # Trading statistics
    total_trades: int = 0
    turnover_rate: float = 0.0

    # Time series
    daily_returns: pd.Series = field(default_factory=pd.Series)
    equity_curve: pd.Series = field(default_factory=pd.Series)
    benchmark_returns: pd.Series = field(default_factory=pd.Series)
    drawdown_curve: pd.Series = field(default_factory=pd.Series)

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "total_return": f"{self.total_return:.2%}",
            "annual_return": f"{self.annual_return:.2%}",
            "max_drawdown": f"{self.max_drawdown:.2%}",
            "sharpe_ratio": f"{self.sharpe_ratio:.2f}",
            "calmar_ratio": f"{self.calmar_ratio:.2f}",
            "sortino_ratio": f"{self.sortino_ratio:.2f}",
            "win_rate": f"{self.win_rate:.2%}",
            "annual_volatility": f"{self.annual_volatility:.2%}",
            "total_trades": self.total_trades,
            "turnover_rate": f"{self.turnover_rate:.2%}",
        }

    def summary(self) -> str:
        d = self.to_dict()
        lines = [
            f"Strategy: {d['strategy_name']}",
            f"Period: {d['start_date']} to {d['end_date']}",
            f"Total Return: {d['total_return']}",
            f"Annual Return: {d['annual_return']}",
            f"Annual Volatility: {d['annual_volatility']}",
            f"Max Drawdown: {d['max_drawdown']}",
            f"Sharpe Ratio: {d['sharpe_ratio']}",
            f"Calmar Ratio: {d['calmar_ratio']}",
            f"Win Rate: {d['win_rate']}",
            f"Total Trades: {d['total_trades']}",
        ]
        return "\n".join(lines)


class VBTBacktestEngine:
    """Fast backtest engine using VectorBT for signal/weight-based strategies.

    Supports:
    - Signal backtesting (entry/exit boolean arrays)
    - Weight backtesting (target weight arrays)
    - Parameter optimization via grid search

    Usage::

        engine = VBTBacktestEngine()
        result = engine.run_signal_backtest(close_prices, entries, exits)
        print(result.summary())
    """

    def __init__(self, initial_capital: float = 1_000_000.0,
                 commission: float = 0.00025,
                 slippage: float = 0.001,
                 risk_free: float = 0.015):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.risk_free = risk_free

    # -- public API -----------------------------------------------------------

    def run_signal_backtest(self, close: pd.DataFrame,
                             entries: pd.DataFrame,
                             exits: pd.DataFrame,
                             strategy_name: str = "signal_strategy",
                             freq: str = "1D") -> VBTResult:
        """Run a signal-based backtest.

        Args:
            close: Price DataFrame (dates x symbols).
            entries: Boolean DataFrame, True where to enter.
            exits: Boolean DataFrame, True where to exit.
            strategy_name: Label for the result.
            freq: Rebalancing frequency ('1D', 'W', 'M').

        Returns:
            VBTResult with performance metrics and curves.
        """
        import vectorbt as vbt

        if close.empty:
            return VBTResult(strategy_name=strategy_name)

        # Ensure datetime index without BusinessDay freq (breaks VectorBT)
        close, entries, exits = self._normalize_index(close, entries, exits)

        # VectorBT portfolio from signals
        try:
            pf = vbt.Portfolio.from_signals(
                close=close,
                entries=entries,
                exits=exits,
                init_cash=self.initial_capital,
                fees=self.commission,
                slippage=self.slippage,
                freq=freq,
            )
        except Exception as e:
            logger.error(f"VectorBT signal backtest failed: {e}")
            return VBTResult(strategy_name=strategy_name)

        return self._extract_result(pf, strategy_name, close)

    def run_weight_backtest(self, close: pd.DataFrame,
                             weights: pd.DataFrame,
                             strategy_name: str = "weight_strategy",
                             freq: str = "1D") -> VBTResult:
        """Run a weight-based backtest.

        Args:
            close: Price DataFrame (dates x symbols).
            weights: Target weight DataFrame (dates x symbols), rows sum to 1.
            strategy_name: Label for the result.
            freq: Rebalancing frequency.

        Returns:
            VBTResult with performance metrics and curves.
        """
        import vectorbt as vbt

        if close.empty or weights.empty:
            return VBTResult(strategy_name=strategy_name)

        close, weights = self._normalize_index(close, weights)
        if not isinstance(weights.index, pd.DatetimeIndex):
            weights = weights.copy()
            weights.index = pd.to_datetime(weights.index)

        try:
            pf = vbt.Portfolio.from_orders(
                close=close,
                size=weights,
                size_type="targetpercent",
                init_cash=self.initial_capital,
                fees=self.commission,
                slippage=self.slippage,
                freq=freq,
            )
        except Exception as e:
            logger.error(f"VectorBT weight backtest failed: {e}")
            return VBTResult(strategy_name=strategy_name)

        return self._extract_result(pf, strategy_name, close)

    def optimize_params(self, close: pd.Series,
                         param_grid: dict,
                         entry_func,
                         exit_func,
                         metric: str = "sharpe_ratio") -> dict:
        """Grid search parameter optimization.

        Args:
            close: Single-asset price series.
            param_grid: Dict of parameter names to lists of values.
                         e.g. {'fast': [5,10,20], 'slow': [30,60,120]}
            entry_func: Callable(close, **params) -> entries (pd.Series bool).
            exit_func: Callable(close, **params) -> exits (pd.Series bool).
            metric: Metric to optimize ('sharpe_ratio', 'total_return',
                    'calmar_ratio', 'sortino_ratio').

        Returns:
            Dict with 'best_params', 'best_value', 'param_results' DataFrame.
        """
        import vectorbt as vbt

        if close.empty:
            return {"best_params": {}, "best_value": 0.0, "param_results": pd.DataFrame()}

        if not isinstance(close.index, pd.DatetimeIndex):
            close = close.copy()
            close.index = pd.to_datetime(close.index)

        # Strip BusinessDay freq which VectorBT can't handle
        if hasattr(close.index, 'freq') and close.index.freq is not None:
            close = close.copy()
            close.index.freq = None

        # Generate signals for each param combination
        best_value = -np.inf
        best_params = {}
        results = []

        from itertools import product

        keys = list(param_grid.keys())
        values = list(param_grid.values())
        for combo in product(*values):
            params = dict(zip(keys, combo))

            try:
                entries = entry_func(close, **params)
                exits = exit_func(close, **params)

                pf = vbt.Portfolio.from_signals(
                    close=close,
                    entries=entries,
                    exits=exits,
                    init_cash=self.initial_capital,
                    fees=self.commission,
                    slippage=self.slippage,
                    freq="D",
                )

                metrics = self._compute_metrics_from_stats(pf.stats())
                val = metrics.get(metric, 0)

                results.append({**params, "value": val, **metrics})

                if val > best_value:
                    best_value = val
                    best_params = params
            except Exception as e:
                logger.debug(f"Param combo {params} failed: {e}")

        result_df = pd.DataFrame(results)
        return {
            "best_params": best_params,
            "best_value": best_value,
            "param_results": result_df,
        }

    # -- internal ------------------------------------------------------------

    @staticmethod
    def _normalize_index(*dfs: pd.DataFrame) -> list[pd.DataFrame]:
        """Ensure DatetimeIndex without BusinessDay freq (incompatible with VectorBT)."""
        result = []
        for df in dfs:
            if not isinstance(df.index, pd.DatetimeIndex):
                df = df.copy()
                df.index = pd.to_datetime(df.index)
            if hasattr(df.index, 'freq') and df.index.freq is not None:
                df = df.copy()
                df.index.freq = None
            result.append(df)
        return result

    def _extract_result(self, pf, strategy_name: str,
                         close: pd.DataFrame) -> VBTResult:
        """Extract VBTResult from a VectorBT Portfolio object."""
        result = VBTResult(strategy_name=strategy_name)

        try:
            stats = pf.stats()
        except Exception:
            return result

        result.total_return = float(stats.get("Total Return [%]", 0.0)) / 100.0
        result.max_drawdown = float(stats.get("Max Drawdown [%]", 0.0)) / 100.0
        result.sharpe_ratio = float(stats.get("Sharpe Ratio", 0.0))

        # Annual return
        # VectorBT doesn't always show annual return, estimate from total
        if "Start" in stats and "End" in stats:
            result.start_date = str(stats["Start"])[:10]
            result.end_date = str(stats["End"])[:10]
            days = (pd.Timestamp(result.end_date) - pd.Timestamp(result.start_date)).days
            years = days / 365.25
            if years > 0 and result.total_return > -1:
                result.annual_return = (1 + result.total_return) ** (1 / years) - 1

        result.win_rate = float(stats.get("Win Rate [%]", 0.0)) / 100.0
        result.total_trades = int(stats.get("Total Trades", 0))

        # Compute additional metrics
        equity = pf.value()
        if isinstance(equity, pd.DataFrame):
            equity = equity.iloc[:, 0] if equity.shape[1] > 0 else equity.squeeze()
        result.equity_curve = equity

        if len(equity) > 1:
            daily_rets = equity.pct_change().dropna()
            if isinstance(daily_rets, pd.DataFrame):
                daily_rets = daily_rets.squeeze()
            result.daily_returns = daily_rets

            # Annual volatility
            vol = daily_rets.std()
            result.annual_volatility = float(vol * np.sqrt(252))

            # Sortino ratio
            downside = daily_rets[daily_rets < 0]
            if len(downside) > 0 and downside.std() > 0:
                result.sortino_ratio = float(
                    (daily_rets.mean() * 252 - self.risk_free) / (downside.std() * np.sqrt(252))
                )

            # Calmar ratio
            if abs(result.max_drawdown) > 0:
                result.calmar_ratio = result.annual_return / abs(result.max_drawdown)

            # Drawdown curve
            result.drawdown_curve = (equity / equity.cummax() - 1)

        # Turnover
        if result.total_trades > 0 and len(close.columns) > 0:
            result.turnover_rate = result.total_trades / (len(close) * len(close.columns))

        logger.info(f"VBT backtest complete: return={result.total_return:.2%}, "
                     f"sharpe={result.sharpe_ratio:.2f}, maxDD={result.max_drawdown:.2%}")

        return result

    @staticmethod
    def _compute_metrics_from_stats(stats: pd.Series) -> dict:
        """Extract key metrics from VectorBT stats Series."""
        total_return = float(stats.get("Total Return [%]", 0.0)) / 100.0
        max_dd = float(stats.get("Max Drawdown [%]", 0.0)) / 100.0
        sharpe = float(stats.get("Sharpe Ratio", 0.0))
        return {
            "total_return": total_return,
            "max_drawdown": max_dd,
            "sharpe_ratio": sharpe,
            "win_rate": float(stats.get("Win Rate [%]", 0.0)) / 100.0,
            "total_trades": int(stats.get("Total Trades", 0)),
        }
