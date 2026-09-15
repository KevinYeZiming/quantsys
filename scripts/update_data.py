#!/usr/bin/env python3
"""Daily data update script for Chinese A-share quant system.

Usage:
    python scripts/update_data.py                    # Incremental update
    python scripts/update_data.py --full             # Full historical download
    python scripts/update_data.py --stocks-only      # Only update stock daily data
    python scripts/update_data.py --symbols 600519,000858  # Specific stocks
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from quantsys.data.sources.akshare import AKShareSource
from quantsys.data.fetcher import DataFetcher
from quantsys.utils.config import load_config
from quantsys.utils.logging import setup_logging


def main():
    parser = argparse.ArgumentParser(description="Update A-share quant data")
    parser.add_argument("--full", action="store_true", help="Full historical download")
    parser.add_argument("--start", type=str, default=None, help="Start date YYYYMMDD")
    parser.add_argument("--end", type=str, default=None, help="End date YYYYMMDD")
    parser.add_argument("--stocks-only", action="store_true", help="Only update stock data")
    parser.add_argument("--indices-only", action="store_true", help="Only update index data")
    parser.add_argument("--etfs-only", action="store_true", help="Only update ETF data")
    parser.add_argument("--macro-only", action="store_true", help="Only update macro data")
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated stock codes")
    args = parser.parse_args()

    # Setup
    project_root = Path(__file__).parent.parent
    config = load_config(project_root / "config" / "settings.yaml")
    logger = setup_logging()

    logger.info("=" * 50)
    logger.info("Starting data update")
    logger.info("=" * 50)

    # Initialize
    source_config = config.get("sources", {})
    source = AKShareSource(
        rate_limit=source_config.get("akshare_rate_limit", 1.0),
        retry_count=source_config.get("retry_count", 3),
    )

    cache_dir = project_root / config.get("data", {}).get("raw_dir", "data/raw")
    fetcher = DataFetcher(source, cache_dir)

    # Determine date range
    start = args.start
    if args.full and not start:
        start = config.get("data", {}).get("default_start", "20150101")

    # Parse symbols
    symbols = None
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]

    incremental = not args.full

    # Run updates
    try:
        # Always update calendar and stock basic first
        if not args.indices_only and not args.etfs_only and not args.macro_only:
            try:
                fetcher.update_trade_calendar()
            except Exception as e:
                logger.warning(f"Calendar update failed (non-critical): {e}")
            try:
                fetcher.update_stock_basic()
            except Exception as e:
                logger.warning(f"Stock basic update failed (non-critical): {e}")

        if args.stocks_only or (not args.indices_only and not args.etfs_only and not args.macro_only):
            fetcher.update_stock_daily(symbols=symbols, start=start, end=args.end, incremental=incremental)

        if args.indices_only or (not args.stocks_only and not args.etfs_only and not args.macro_only):
            fetcher.update_index_daily(start=start or "20150101", end=args.end)

        if args.etfs_only or (not args.stocks_only and not args.indices_only and not args.macro_only):
            fetcher.update_etf_daily(start=start or "20150101", end=args.end)

        if args.macro_only or (not args.stocks_only and not args.indices_only and not args.etfs_only):
            fetcher.update_macro()

        logger.info("Data update completed successfully")

    except KeyboardInterrupt:
        logger.info("Data update interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Data update failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
