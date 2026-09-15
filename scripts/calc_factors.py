#!/usr/bin/env python3
"""Batch factor calculation script.

Computes all 20 enabled factors for the specified date range
and stores results to data/processed/factors/.

Usage:
    python scripts/calc_factors.py
    python scripts/calc_factors.py --start 2023-01-01 --end 2024-01-01
    python scripts/calc_factors.py --universe csi300
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from tqdm import tqdm

from quantsys.data.sources.cache import CacheManager
from quantsys.data.calendar import TradingCalendar
from quantsys.data.universe import UniverseBuilder
from quantsys.factors.registry import FactorRegistry
from quantsys.factors.processor import FactorProcessor
from quantsys.factors.neutralizer import FactorNeutralizer
from quantsys.utils.config import load_config
from quantsys.utils.logging import setup_logging


def main():
    parser = argparse.ArgumentParser(description="Calculate factors for A-share stocks")
    parser.add_argument("--start", type=str, default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, default=None, help="End date YYYY-MM-DD")
    parser.add_argument("--universe", type=str, default="csi300", help="Stock universe")
    parser.add_argument("--output", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    config = load_config(project_root / "config" / "settings.yaml")
    factor_config = load_config(project_root / "config" / "factors.yaml")
    logger = setup_logging()

    logger.info("=" * 50)
    logger.info("Starting factor calculation")
    logger.info("=" * 50)

    # Initialize
    raw_dir = project_root / config.get("data", {}).get("raw_dir", "data/raw")
    processed_dir = project_root / config.get("data", {}).get("processed_dir", "data/processed")
    output_dir = Path(args.output) if args.output else processed_dir / "factors"
    output_dir.mkdir(parents=True, exist_ok=True)

    cache = CacheManager(raw_dir)
    calendar = TradingCalendar(cache)
    universe_builder = UniverseBuilder(cache)

    # Determine date range
    if args.start is None:
        args.start = "2018-01-01"
    if args.end is None:
        args.end = pd.Timestamp.now().strftime("%Y-%m-%d")

    # Get trading dates (monthly for factor calculation)
    month_ends = calendar.month_end_dates(args.start, args.end)

    index_map = {"csi300": "000300", "csi500": "000905"}
    index_code = index_map.get(args.universe, "000300")

    logger.info(f"Processing {len(month_ends)} month-end dates for {args.universe}")

    # Initialize factor system
    registry = FactorRegistry()
    registry.discover()
    processor = FactorProcessor()
    logger.info(f"Loaded {len(registry.list_all())} factors")

    # Process each month-end
    all_factors = []

    for date in tqdm(month_ends, desc="Calculating factors"):
        date_str = date.strftime("%Y-%m-%d")

        # Build universe
        universe = universe_builder.build(date_str, index_code=index_code)
        if not universe:
            logger.warning(f"No stocks in universe for {date_str}")
            continue

        # Load data (1 year of history for factor computation)
        start_date = (date - pd.DateOffset(days=365)).strftime("%Y-%m-%d")
        dfs = []
        for symbol in universe[:200]:  # Limit to 200 for performance
            df = cache.get("stock_daily", symbol=symbol)
            if df is not None and not df.empty:
                df = df.sort_index()
                df = df.loc[start_date:date_str]
                if not df.empty:
                    df["symbol"] = symbol
                    dfs.append(df)

        if not dfs:
            continue

        panel = pd.concat(dfs)
        panel = panel.reset_index().set_index(["date", "symbol"])

        # Compute factors
        try:
            factor_df = registry.compute_all(panel, factor_config)
        except Exception as e:
            logger.warning(f"Factor computation failed for {date_str}: {e}")
            continue

        if factor_df.empty:
            continue

        # Process factors
        processed = {}
        for col in factor_df.columns:
            try:
                series = processor.process(factor_df[col])
                processed[col] = series
            except Exception as e:
                logger.debug(f"Failed to process {col}: {e}")

        if processed:
            result = pd.DataFrame(processed)
            result["date"] = date
            result = result.reset_index()
            all_factors.append(result)

    if all_factors:
        # Combine and save
        combined = pd.concat(all_factors, ignore_index=True)
        output_path = output_dir / f"factors_{args.universe}_{args.start}_{args.end}.parquet"
        combined.to_parquet(output_path, compression="snappy")
        logger.info(f"Saved {len(combined)} factor records to {output_path}")
        logger.info(f"Factors: {', '.join(registry.list_all())}")

    logger.info("Factor calculation complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
