#!/usr/bin/env python3
"""Update fund / gold data and persist locally (基金与黄金数据更新).

Usage:
    python scripts/update_assets.py --type fund          # 更新 config/assets.yaml 基金池
    python scripts/update_assets.py --type fund --symbols 017103,110022
    python scripts/update_assets.py --type gold          # 更新黄金现货+ETF
    python scripts/update_assets.py --type all
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from quantsys.data.sources.cache import CacheManager
from quantsys.data.sources.funds import FundSource
from quantsys.data.sources.gold import GoldSource
from quantsys.utils.config import load_config, load_all_configs
from quantsys.utils.logging import setup_logging


def update_funds(args, cache, logger):
    configs = load_all_configs()
    assets_cfg = configs.get("assets", {})
    fund_cfg = assets_cfg.get("funds", {})

    symbols = args.symbols.split(",") if args.symbols else fund_cfg.get("watchlist", [])
    symbols = [s.strip() for s in symbols if s.strip()]
    if not symbols:
        logger.warning("基金列表为空：请在 config/assets.yaml 的 funds.watchlist 中配置")
        return

    source = FundSource(cache)
    ok, fail = 0, 0
    for sym in symbols:
        logger.info(f"更新基金 {sym} ...")
        nav = source.update_nav(sym)
        if nav is None or nav.empty:
            logger.warning(f"  {sym}: 无数据（代码可能错误或网络不可用）")
            fail += 1
            continue
        ok += 1
        logger.info(f"  {sym}: 单位净值 {len(nav)} 条, 最新 {nav.index[-1].date()} = {nav['nav'].iloc[-1]}")

        if fund_cfg.get("with_accumulated_nav", True):
            anav = source.update_accumulated_nav(sym)
            if anav is not None and not anav.empty:
                logger.info(f"  {sym}: 累计净值 {len(anav)} 条")
        if fund_cfg.get("with_info", True):
            info = source.update_info(sym)
            if info is not None and not info.empty:
                row = info.iloc[0].to_dict()
                logger.info(f"  {sym}: 概况 — "
                            + ", ".join(f"{k}={v}" for k, v in list(row.items())[:5]))

    logger.info(f"基金更新完成: 成功 {ok}, 失败 {fail}")


def update_gold(args, cache, logger):
    configs = load_all_configs()
    gold_cfg = configs.get("assets", {}).get("gold", {})
    spot = args.spot.split(",") if args.spot else gold_cfg.get("spot_symbols")
    etfs = args.etfs.split(",") if args.etfs else gold_cfg.get("etf_codes")

    source = GoldSource(cache)
    results = source.update_all(spot_symbols=spot, etf_codes=etfs)
    for key, df in results.items():
        if df is None or df.empty:
            logger.warning(f"  {key}: 无数据")
        else:
            col = "close" if "close" in df.columns else df.columns[0]
            logger.info(f"  {key}: {len(df)} 条, 最新 {df.index[-1].date()} = {df[col].iloc[-1]}")
    logger.info("黄金数据更新完成")


def main():
    parser = argparse.ArgumentParser(description="Update fund/gold data with local persistence")
    parser.add_argument("--type", choices=["fund", "gold", "all"], required=True)
    parser.add_argument("--symbols", type=str, default=None, help="逗号分隔的基金代码")
    parser.add_argument("--spot", type=str, default=None, help="逗号分隔的上金所现货代码")
    parser.add_argument("--etfs", type=str, default=None, help="逗号分隔的黄金ETF代码")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    settings = load_config(project_root / "config" / "settings.yaml")
    logger = setup_logging()

    cache_dir = project_root / settings.get("data", {}).get("raw_dir", "data/raw")
    cache = CacheManager(cache_dir)

    logger.info("=" * 50)
    logger.info(f"Asset data update: {args.type}")
    logger.info("=" * 50)

    if args.type in ("fund", "all"):
        update_funds(args, cache, logger)
    if args.type in ("gold", "all"):
        update_gold(args, cache, logger)


if __name__ == "__main__":
    main()
