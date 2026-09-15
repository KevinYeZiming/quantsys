#!/usr/bin/env python3
"""Unified buy/sell evaluation for stocks, funds and gold (股/基/金买卖评估).

Evaluates assets with the 4-dimension history-percentile scoring model
and outputs actions, confidence, suggested weights, stop-loss/take-profit
levels. Results are persisted to data/evaluations/ and a Markdown report.

Usage:
    python scripts/evaluate_assets.py --positions            # 评估当前持仓
    python scripts/evaluate_assets.py --symbols 600519,518880
    python scripts/evaluate_assets.py --fund 017103,110022   # 指定为基金
    python scripts/evaluate_assets.py --gold 518880,Au99.99  # 指定为黄金
    python scripts/evaluate_assets.py --symbols 600519 --date 2026-09-15
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from quantsys.advisor.asset_evaluator import AssetEvaluator
from quantsys.utils.config import load_all_configs
from quantsys.utils.logging import setup_logging

ACTION_CN = {
    "strong_buy": "强烈买入", "buy": "买入", "hold": "持有",
    "sell": "卖出", "strong_sell": "强烈卖出",
}


def main():
    parser = argparse.ArgumentParser(description="Unified buy/sell evaluation for stock/fund/gold")
    parser.add_argument("--positions", action="store_true", help="评估 data/positions.json 中的持仓")
    parser.add_argument("--symbols", type=str, default=None, help="逗号分隔代码，默认按股票评估")
    parser.add_argument("--fund", type=str, default=None, help="逗号分隔基金代码")
    parser.add_argument("--gold", type=str, default=None, help="逗号分隔黄金标的（ETF或现货）")
    parser.add_argument("--date", type=str, default=None, help="评估基准日 YYYY-MM-DD，缺省为今天")
    parser.add_argument("--no-save", action="store_true", help="不保存评估结果")
    args = parser.parse_args()

    import pandas as pd
    date = args.date or pd.Timestamp.now().strftime("%Y-%m-%d")

    project_root = Path(__file__).parent.parent
    configs = load_all_configs()
    logger = setup_logging()

    evaluator = AssetEvaluator(
        cache_dir=project_root / configs.get("settings", {}).get("data", {}).get("raw_dir", "data/raw"),
        config=configs.get("assets", {}),
    )

    assets: list[tuple[str, str]] = []
    if args.positions:
        positions_file = project_root / "data" / "positions.json"
        if not positions_file.exists():
            logger.error(f"持仓文件不存在: {positions_file}")
            sys.exit(1)
        positions = json.loads(positions_file.read_text(encoding="utf-8"))
        results = evaluator.evaluate_positions(positions, date)
    else:
        if args.symbols:
            assets += [(s.strip(), "stock") for s in args.symbols.split(",") if s.strip()]
        if args.fund:
            assets += [(s.strip(), "fund") for s in args.fund.split(",") if s.strip()]
        if args.gold:
            assets += [(s.strip(), "gold") for s in args.gold.split(",") if s.strip()]
        if not assets:
            logger.error("请提供 --positions 或 --symbols/--fund/--gold 之一")
            sys.exit(1)
        results = evaluator.evaluate(assets, date)

    if not results:
        logger.warning("无评估结果")
        sys.exit(0)

    # Console output
    print(f"\n=== {date} 买卖评估（按总分降序）===\n")
    print(f"{'标的':<14}{'类型':<8}{'现价':>10}{'总分':>7}{'建议':<8}{'置信':>6}{'仓位':>6}  关键理由")
    for r in results:
        name = (r.name or r.symbol)
        reason = r.reasons[0] if r.reasons else ""
        flag = " ⚠️" if r.risk_flags else ""
        print(f"{name:<14}{r.asset_type:<8}{r.price:>10}{r.total_score:>7.1f}"
              f"{ACTION_CN.get(r.action.value, r.action.value):<8}"
              f"{r.confidence:>6.0%}{r.target_weight:>6.0%}  {reason}{flag}")

    # Persist
    if not args.no_save:
        path = evaluator.save(results)
        md_path = path.with_suffix(".md")
        md_path.write_text(evaluator.to_markdown(results), encoding="utf-8")
        print(f"\n评估结果已保存: {path}")
        print(f"Markdown 报告: {md_path}")


if __name__ == "__main__":
    main()
