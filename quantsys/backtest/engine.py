"""Backtesting engine for Chinese A-share strategies.

Wraps Backtrader's Cerebro with A-share-specific configuration:
- T+1 settlement
- Stamp duty on sells
- Chinese trading calendar
- Price limit checks
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import backtrader as bt
import pandas as pd

from quantsys.backtest.broker import AShareCommission, T1Sizer
from quantsys.backtest.datafeed import create_datafeed
from quantsys.data.sources.cache import CacheManager

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Structured backtest output."""

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
        """Return a formatted summary string."""
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


class BacktestEngine:
    """High-level backtest runner for A-share strategies.

    Usage::

        cache = CacheManager(Path("data/raw"))
        engine = BacktestEngine(cache, initial_capital=1000000)

        # Add data for stocks
        engine.add_data_from_cache(["600519", "000858"], start="2023-01-01", end="2024-01-01")

        # Add strategy
        engine.add_strategy(MyBacktraderStrategy)

        # Run
        result = engine.run()
        print(result.summary())
    """

    def __init__(
        self,
        cache_manager: CacheManager,
        initial_capital: float = 1_000_000.0,
        commission: float = 0.00025,
        stamp_duty: float = 0.0005,
        benchmark_code: str = "000300",
    ):
        self.cache = cache_manager
        self.initial_capital = initial_capital
        self.commission = commission
        self.stamp_duty = stamp_duty
        self.benchmark_code = benchmark_code
        self._cerebro = None
        self._strategies = []

    def _create_cerebro(self) -> bt.Cerebro:
        """Create and configure a Cerebro engine for A-shares."""
        cerebro = bt.Cerebro()

        # Set initial capital
        cerebro.broker.setcash(self.initial_capital)

        # Add A-share commission scheme
        comminfo = AShareCommission(
            commission=self.commission,
            stamp_duty=self.stamp_duty,
        )
        cerebro.broker.addcommissioninfo(comminfo)

        # Add analyzers
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                            timeframe=bt.TimeFrame.Days, annualize=True,
                            riskfreerate=0.015)
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
        cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
        cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name="annual_return")
        cerebro.addanalyzer(bt.analyzers.VWR, _name="vwr")  # Variability-Weighted Return

        return cerebro

    def add_data_from_cache(
        self, symbols: list[str], start: str, end: str
    ) -> int:
        """Load stock data from cache and add to Cerebro.

        Args:
            symbols: List of stock codes.
            start: Start date 'YYYY-MM-DD'.
            end: End date 'YYYY-MM-DD'.

        Returns:
            Number of data feeds added.
        """
        if self._cerebro is None:
            self._cerebro = self._create_cerebro()

        added = 0
        for symbol in symbols:
            df = self.cache.get("stock_daily", symbol=symbol)
            if df is None or df.empty:
                continue

            # Filter date range
            df = df.sort_index()
            df = df.loc[start:end]
            if df.empty:
                continue

            try:
                feed = create_datafeed(df, symbol=symbol)
                self._cerebro.adddata(feed, name=symbol)
                added += 1
            except Exception as e:
                logger.debug(f"Failed to add feed for {symbol}: {e}")

        return added

    def add_data_dataframe(self, df: pd.DataFrame, symbol: str = None):
        """Add data directly from a DataFrame."""
        if self._cerebro is None:
            self._cerebro = self._create_cerebro()

        feed = create_datafeed(df, symbol=symbol)
        self._cerebro.adddata(feed, name=symbol)

    def add_strategy(self, strategy_cls, **params):
        """Add a Backtrader strategy class with parameters."""
        if self._cerebro is None:
            self._cerebro = self._create_cerebro()

        self._cerebro.addstrategy(strategy_cls, **params)
        self._strategies.append(strategy_cls.__name__)

    def add_sizer(self, sizer_cls=None, **params):
        """Add a position sizer."""
        if self._cerebro is None:
            self._cerebro = self._create_cerebro()

        if sizer_cls is None:
            sizer_cls = T1Sizer
        self._cerebro.addsizer(sizer_cls, **params)

    def run(self) -> BacktestResult:
        """Run the backtest and return structured results.

        Returns:
            BacktestResult with performance metrics and time series.
        """
        if self._cerebro is None or len(self._cerebro.datas) == 0:
            logger.warning("No data or strategy added to backtest engine")
            return BacktestResult()

        logger.info(f"Starting backtest with {len(self._cerebro.datas)} securities")

        start_value = self._cerebro.broker.getvalue()
        start_date = str(self._cerebro.datas[0].datetime.date(0))

        results = self._cerebro.run()
        end_value = self._cerebro.broker.getvalue()
        end_date = str(self._cerebro.datas[0].datetime.date(-1))

        result = BacktestResult(
            strategy_name=", ".join(self._strategies),
            start_date=start_date,
            end_date=end_date,
        )

        if not results:
            return result

        strat = results[0]

        # Extract metrics from analyzers
        try:
            sharpe = strat.analyzers.sharpe.get_analysis()
            result.sharpe_ratio = sharpe.get("sharperatio", 0.0) or 0.0
        except Exception:
            result.sharpe_ratio = 0.0

        try:
            drawdown = strat.analyzers.drawdown.get_analysis()
            result.max_drawdown = drawdown.get("max", {}).get("drawdown", 0.0) / 100.0
        except Exception:
            result.max_drawdown = 0.0

        try:
            trade_analysis = strat.analyzers.trades.get_analysis()
            result.total_trades = trade_analysis.get("total", {}).get("total", 0)
            won = trade_analysis.get("won", {}).get("total", 0)
            lost = trade_analysis.get("lost", {}).get("total", 0)
            if (won + lost) > 0:
                result.win_rate = won / (won + lost)
        except Exception:
            result.total_trades = 0
            result.win_rate = 0.0

        # Compute total return
        result.total_return = (end_value / start_value) - 1.0

        # Approximate annual return
        if start_date and end_date:
            days = (datetime.strptime(end_date[:10], "%Y-%m-%d") -
                    datetime.strptime(start_date[:10], "%Y-%m-%d")).days
            years = days / 365.25
            if years > 0:
                result.annual_return = (end_value / start_value) ** (1 / years) - 1

        # Calmar ratio
        if abs(result.max_drawdown) > 0:
            result.calmar_ratio = result.annual_return / abs(result.max_drawdown)

        logger.info(f"Backtest complete: return={result.total_return:.2%}, "
                    f"sharpe={result.sharpe_ratio:.2f}, maxDD={result.max_drawdown:.2%}")

        return result
