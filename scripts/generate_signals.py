#!/usr/bin/env python3
"""Generate trading signals for current date.

Usage:
    python scripts/generate_signals.py
    python scripts/generate_signals.py --date 2024-01-15
    python scripts/generate_signals.py --strategy multifactor
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from tabulate import tabulate

from quantsys.data.sources.cache import CacheManager
from quantsys.data.calendar import TradingCalendar
from quantsys.data.universe import UniverseBuilder
from quantsys.strategies.multifactor import MultiFactorStrategy
from quantsys.strategies.etf_rotation import ETFRotationStrategy
from quantsys.strategies.trend_following import TrendFollowingStrategy
from quantsys.strategies.industry_rotation import IndustryRotationStrategy
from quantsys.utils.config import load_all_configs
from quantsys.utils.logging import setup_logging


STRATEGIES = {
    "multifactor": ("Multi-Factor Stock Selection", MultiFactorStrategy),
    "etf_rotation": ("ETF Rotation", ETFRotationStrategy),
    "trend_following": ("Trend Following", TrendFollowingStrategy),
    "industry_rotation": ("Industry Rotation", IndustryRotationStrategy),
}


def main():
    parser = argparse.ArgumentParser(description="Generate trading signals")
    parser.add_argument("--date", type=str, default=None, help="Date YYYY-MM-DD (default: today)")
    parser.add_argument("--strategy", type=str, default=None, help="Specific strategy to run")
    parser.add_argument("--top", type=int, default=10, help="Number of top picks to show")
    args = parser.parse_args()

    if args.date is None:
        args.date = pd.Timestamp.now().strftime("%Y-%m-%d")

    project_root = Path(__file__).parent.parent
    configs = load_all_configs(project_root / "config")
    logger = setup_logging()

    # Validate date
    raw_dir = project_root / "data" / "raw"
    cache = CacheManager(raw_dir)
    calendar = TradingCalendar(cache)

    if calendar.is_loaded() and not calendar.is_trading_day(args.date):
        logger.warning(f"{args.date} is not a trading day")

    universe_builder = UniverseBuilder(cache)
    strategies_config = configs.get("strategies", {})

    strategy_names = [args.strategy] if args.strategy else list(STRATEGIES.keys())

    print("=" * 60)
    print(f"  Trading Signals for {args.date}")
    print("=" * 60)

    for name in strategy_names:
        if name not in STRATEGIES:
            logger.warning(f"Unknown strategy: {name}")
            continue

        label, strategy_cls = STRATEGIES[name]

        if not strategies_config.get(name, {}).get("enabled", True):
            continue

        print(f"\n## {label}")
        print("-" * 40)

        try:
            strategy = strategy_cls(config=strategies_config, cache_dir=str(raw_dir))

            universe = universe_builder.build(args.date)
            signals = strategy.generate_signals(universe, args.date)

            if signals.empty:
                print("  No signals generated")
                continue

            # Get stock names
            basic = cache.get("stock_basic")
            name_map = {}
            if basic is not None and not basic.empty and "symbol" in basic.columns and "name" in basic.columns:
                name_map = dict(zip(basic["symbol"], basic["name"]))

            # Format output
            rows = []
            for sym, weight in signals.nlargest(args.top).items():
                sname = name_map.get(str(sym), str(sym))
                rows.append([sname, str(sym), f"{weight:.4f}"])

            print(tabulate(rows, headers=["Name", "Code", "Weight"],
                          tablefmt="simple", floatfmt=".4f"))

            # Risk warnings
            if len(signals) > 0 and signals.max() > 0.10:
                print(f"\n  Warning: max single position weight = {signals.max():.1%}")

        except Exception as e:
            logger.error(f"Signal generation failed for {name}: {e}", exc_info=True)

    print("\n" + "=" * 60)
    print("  Done. Note: All signals are for reference only.")
    print("  Past performance does not guarantee future results.")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
