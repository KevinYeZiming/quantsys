#!/usr/bin/env python3
"""Run strategy backtests and generate performance reports.

Usage:
    python scripts/run_backtest.py --strategy multifactor --start 2018-01-01 --end 2023-12-31
    python scripts/run_backtest.py --strategy etf_rotation
    python scripts/run_backtest.py --strategy trend_following --universe csi500
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from quantsys.data.sources.cache import CacheManager
from quantsys.data.calendar import TradingCalendar
from quantsys.data.universe import UniverseBuilder
from quantsys.strategies.multifactor import MultiFactorStrategy
from quantsys.strategies.etf_rotation import ETFRotationStrategy
from quantsys.strategies.trend_following import TrendFollowingStrategy
from quantsys.strategies.industry_rotation import IndustryRotationStrategy
from quantsys.backtest.engine import BacktestEngine, BacktestResult
from quantsys.backtest.reporter import ReportGenerator
from quantsys.utils.config import load_config, load_all_configs
from quantsys.utils.logging import setup_logging

import numpy as np
import pandas as pd


STRATEGY_MAP = {
    "multifactor": MultiFactorStrategy,
    "etf_rotation": ETFRotationStrategy,
    "trend_following": TrendFollowingStrategy,
    "industry_rotation": IndustryRotationStrategy,
}


def main():
    parser = argparse.ArgumentParser(description="Run A-share strategy backtest")
    parser.add_argument("--strategy", type=str, required=True,
                        choices=list(STRATEGY_MAP.keys()),
                        help="Strategy to backtest")
    parser.add_argument("--start", type=str, default="2018-01-01",
                        help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, default="2023-12-31",
                        help="End date YYYY-MM-DD")
    parser.add_argument("--universe", type=str, default="csi300",
                        choices=["csi300", "csi500"],
                        help="Stock universe")
    parser.add_argument("--capital", type=float, default=1_000_000.0,
                        help="Initial capital")
    parser.add_argument("--output", type=str, default="reports",
                        help="Output directory for reports")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    configs = load_all_configs(project_root / "config")
    logger = setup_logging()

    logger.info("=" * 60)
    logger.info(f"Running backtest: {args.strategy}")
    logger.info(f"Period: {args.start} to {args.end}")
    logger.info("=" * 60)

    # Initialize data layer
    raw_dir = project_root / "data" / "raw"
    cache = CacheManager(raw_dir)
    calendar = TradingCalendar(cache)
    universe_builder = UniverseBuilder(cache)

    if not calendar.is_loaded():
        logger.warning("Trading calendar not loaded. Run /quant-data first.")

    # Initialize strategy
    strategy_config = configs.get("strategies", {})
    strategy_cls = STRATEGY_MAP[args.strategy]
    strategy = strategy_cls(config=strategy_config, cache_dir=str(raw_dir))

    logger.info(f"Strategy: {strategy.name}")

    # Get rebalance dates
    rebalance_freq = strategy_config.get(args.strategy, {}).get("rebalance_frequency", "monthly")
    rebalance_dates = strategy.get_rebalance_dates(args.start, args.end, rebalance_freq)
    logger.info(f"Rebalance dates: {len(rebalance_dates)} ({rebalance_freq})")

    # Build universe for each rebalance date
    index_map = {"csi300": "000300", "csi500": "000905"}
    index_code = index_map.get(args.universe, "000300")

    # Run simplified backtest
    result = BacktestResult(
        strategy_name=strategy.name,
        start_date=args.start,
        end_date=args.end,
    )

    # Track portfolio values
    daily_values = [args.capital]
    daily_dates = []
    current_weights = pd.Series(dtype=float)
    benchmark_values = [args.capital]
    current_capital = args.capital

    # Load benchmark data
    benchmark_df = cache.get("index_daily", symbol="000300")
    benchmark_returns = pd.Series(dtype=float)
    if benchmark_df is not None and not benchmark_df.empty:
        benchmark_df = benchmark_df.sort_index()
        benchmark_df = benchmark_df.loc[args.start:args.end]

    # Vectorized backtest
    all_trade_dates = pd.date_range(args.start, args.end, freq="B")

    for date in all_trade_dates:
        date_str = date.strftime("%Y-%m-%d")

        # Check if rebalance needed
        if date in rebalance_dates or len(daily_dates) == 0:
            try:
                universe = universe_builder.build(date_str, index_code=index_code)
                if universe:
                    new_weights = strategy.generate_signals(universe, date_str)
                    if not new_weights.empty:
                        current_weights = new_weights
            except Exception as e:
                logger.debug(f"Signal generation failed for {date_str}: {e}")

        # Calculate daily portfolio return
        daily_ret = 0.0
        total_weight = current_weights.sum() if len(current_weights) > 0 else 0

        for symbol, weight in current_weights.items():
            df = cache.get("stock_daily", symbol=symbol)
            if df is None or df.empty or total_weight == 0:
                continue

            df = df.sort_index()
            if date in df.index and "close" in df.columns:
                if len(daily_dates) > 0:
                    prev_date = pd.Timestamp(daily_dates[-1])
                    if prev_date in df.index:
                        stock_ret = df.loc[date, "close"] / df.loc[prev_date, "close"] - 1.0
                        if isinstance(stock_ret, pd.Series):
                            stock_ret = stock_ret.iloc[0]
                        daily_ret += (weight / total_weight) * stock_ret

        # Update capital
        current_capital *= (1 + daily_ret)
        daily_values.append(current_capital)
        daily_dates.append(date)

        # Benchmark
        if benchmark_df is not None and not benchmark_df.empty and date in benchmark_df.index:
            bench_ret = benchmark_df.loc[date, "close"] / benchmark_df.loc[benchmark_df.index[0], "close"]
            if isinstance(bench_ret, pd.Series):
                bench_ret = bench_ret.iloc[0]
            benchmark_values.append(args.capital * bench_ret / benchmark_values[0] * args.capital)

    # Populate result
    if len(daily_dates) > 0:
        result.equity_curve = pd.Series(daily_values[1:], index=daily_dates)
        daily_rets = pd.Series(
            np.diff(daily_values) / daily_values[:-1],
            index=daily_dates,
        )
        result.daily_returns = daily_rets

        if benchmark_df is not None and not benchmark_df.empty:
            bench = benchmark_df["close"]
            if isinstance(bench, pd.DataFrame):
                bench = bench.iloc[:, 0]
            benchmark_values = list(bench.values[:len(daily_dates)])
            result.benchmark_returns = pd.Series(
                benchmark_values,
                index=daily_dates[:len(benchmark_values)]
            ).pct_change()

    # Compute metrics
    result.total_return = (current_capital / args.capital) - 1.0
    days = (pd.Timestamp(args.end) - pd.Timestamp(args.start)).days
    years = days / 365.25
    if years > 0 and current_capital > 0:
        result.annual_return = (current_capital / args.capital) ** (1 / years) - 1.0

    if len(daily_rets) > 0:
        result.annual_volatility = daily_rets.std() * np.sqrt(252)
        if result.annual_volatility > 0:
            result.sharpe_ratio = (daily_rets.mean() / daily_rets.std()) * np.sqrt(252)

        eq = result.equity_curve
        running_max = eq.cummax()
        drawdown = (eq - running_max) / running_max
        result.max_drawdown = drawdown.min()
        result.win_rate = (daily_rets > 0).mean()

        if abs(result.max_drawdown) > 0:
            result.calmar_ratio = result.annual_return / abs(result.max_drawdown)

    # Print summary
    print("\n" + "=" * 60)
    print(result.summary())
    print("=" * 60)

    # Generate report
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = ReportGenerator.generate(result, output_dir=output_dir)
    print(f"\nReport saved to: {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
