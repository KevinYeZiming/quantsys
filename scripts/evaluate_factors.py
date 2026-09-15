#!/usr/bin/env python3
"""Factor effectiveness evaluation (主流因子有效性评估).

Runs the mainstream single-factor test suite on all enabled factors:
daily IC / RankIC, ICIR, IC decay, decile layered returns, turnover,
factor correlation matrix — and writes a Markdown report plus (optionally)
an IC-IR weight file for the multifactor strategy.

Usage:
    python scripts/evaluate_factors.py --start 2022-01-01
    python scripts/evaluate_factors.py --symbols 600519,000858 --start 2022-01-01
    python scripts/evaluate_factors.py --start 2022-01-01 --save-weights
    python scripts/evaluate_factors.py --start 2022-01-01 --report reports/factor_evaluation.md
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from quantsys.data.sources.cache import CacheManager
from quantsys.factors.evaluation import FactorEvaluator
from quantsys.factors.registry import FactorRegistry
from quantsys.utils.config import load_all_configs
from quantsys.utils.logging import setup_logging


def load_panel(cache, symbols, start, end):
    """Load OHLCV panel (MultiIndex date,symbol) from stock_daily cache."""
    dfs = []
    for sym in symbols:
        df = cache.get("stock_daily", symbol=sym)
        if df is None or df.empty or "close" not in df.columns:
            continue
        df = df.sort_index().loc[start:end]
        if df.empty:
            continue
        df = df.copy()
        df["symbol"] = sym
        dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    combined = pd.concat(dfs)
    return combined.reset_index().set_index(["date", "symbol"]).sort_index()


def main():
    parser = argparse.ArgumentParser(description="Evaluate factor effectiveness (IC/ICIR/分层/换手/衰减)")
    parser.add_argument("--start", type=str, required=True, help="评估起始日 YYYY-MM-DD")
    parser.add_argument("--end", type=str, default=None, help="评估截止日 YYYY-MM-DD")
    parser.add_argument("--symbols", type=str, default=None,
                        help="逗号分隔股票代码；缺省用缓存内全部股票（注意耗时）")
    parser.add_argument("--max-symbols", type=int, default=200,
                        help="缺省模式下最多使用的股票数（控制耗时）")
    parser.add_argument("--save-weights", action="store_true",
                        help="生成 IC-IR 权重文件 data/factor_weights.csv 供多因子策略加载")
    parser.add_argument("--min-cross-section", type=int, default=None,
                        help="每日最小横截面样本数（小样本股票池可降至 10；默认读配置 30）")
    parser.add_argument("--report", type=str, default="reports/factor_evaluation.md",
                        help="Markdown 报告输出路径")
    parser.add_argument("--summary-csv", type=str, default="reports/factor_evaluation_summary.csv",
                        help="汇总表 CSV 输出路径")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    configs = load_all_configs()
    logger = setup_logging()

    settings = configs.get("settings", {})
    cache = CacheManager(project_root / settings.get("data", {}).get("raw_dir", "data/raw"))

    eval_cfg = configs.get("assets", {}).get("factor_evaluation", {})
    evaluator = FactorEvaluator(
        horizons=tuple(eval_cfg.get("horizons", (1, 3, 5, 10, 20))),
        n_quantiles=eval_cfg.get("n_quantiles", 10),
        min_cross_section=args.min_cross_section or eval_cfg.get("min_cross_section", 30),
        primary_horizon=eval_cfg.get("primary_horizon", 5),
    )

    # Universe
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        stock_dir = cache.cache_dir / "stock_daily"
        symbols = sorted(p.stem for p in stock_dir.glob("*.parquet")
                         if not p.name.startswith("._"))[: args.max_symbols]
    if not symbols:
        logger.error("无可用股票数据，请先运行 scripts/update_data.py")
        sys.exit(1)
    logger.info(f"评估 universe: {len(symbols)} 只股票, {args.start} ~ {args.end or '最新'}")

    end = args.end or pd.Timestamp.now().strftime("%Y-%m-%d")
    panel = load_panel(cache, symbols, args.start, end)
    if panel.empty:
        logger.error(f"{args.start}~{end} 区间无数据")
        sys.exit(1)
    logger.info(f"面板: {panel.index.get_level_values('date').nunique()} 个交易日")

    # Compute factors
    registry = FactorRegistry()
    registry.discover()
    factor_config = configs.get("factors", {})
    logger.info("计算因子 ...")
    factor_df = registry.compute_all(panel, factor_config)
    if factor_df.empty:
        logger.error("无因子可计算")
        sys.exit(1)
    logger.info(f"因子矩阵: {factor_df.shape[1]} 个因子 x {len(factor_df)} 行")

    # Evaluate
    logger.info("运行评估（IC/RankIC/ICIR/分层/换手/衰减）...")
    summary, details = evaluator.evaluate_all(factor_df, panel["close"])
    if summary.empty:
        logger.error("评估结果为空（样本可能不足）")
        sys.exit(1)

    # Persist
    report_path = project_root / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path = project_root / args.summary_csv
    summary.to_csv(summary_path, index=False)
    report_path.write_text(evaluator.to_markdown(summary, details), encoding="utf-8")
    logger.info(f"汇总表: {summary_path}")
    logger.info(f"报告: {report_path}")

    # Correlation matrix export
    corr = details.get("_correlation")
    if corr is not None and not corr.empty:
        corr_path = project_root / "reports" / "factor_correlation.csv"
        corr.to_csv(corr_path)
        logger.info(f"相关性矩阵: {corr_path}")

    # Per-factor detail export for the dashboard (decay / quantile means / IC sparkline)
    detail_export = {}
    for factor, det in details.items():
        if factor.startswith("_"):
            continue
        st = det["stats"]
        daily_ic = det.get("daily_rank_ic")
        ic_points = ([None if pd.isna(v) else round(float(v), 5)
                      for v in daily_ic.iloc[::5].tolist()]
                     if daily_ic is not None and len(daily_ic) else [])
        q_ret = det.get("quantile_returns")
        detail_export[factor] = {
            "decay": {str(h): (None if pd.isna(v) else round(float(v), 5))
                      for h, v in st.decay.items()},
            "quantile_means": ([None if pd.isna(v) else round(float(v), 6)
                                for v in q_ret.mean(axis=0).tolist()]
                               if q_ret is not None and not q_ret.empty else []),
            "ic_series": ic_points,
        }
    details_path = project_root / "reports" / "factor_details.json"
    details_path.write_text(__import__("json").dumps(
        detail_export, ensure_ascii=False), encoding="utf-8")
    logger.info(f"因子明细: {details_path}")

    if args.save_weights:
        weights = evaluator.ic_ir_weights(summary)
        weights = weights[weights > 0]
        weights_path = project_root / "data" / "factor_weights.csv"
        weights_path.parent.mkdir(parents=True, exist_ok=True)
        weights.rename("weight").rename_axis("factor").reset_index().to_csv(
            weights_path, index=False)
        logger.info(f"IC-IR 权重已保存: {weights_path}")
        logger.info("多因子策略加载方式：config/strategies.yaml 中 "
                    "multifactor.factor_weights='ic_ir' 且 "
                    f"multifactor.weights_path='{weights_path.name}'（或绝对路径）")

    # Console top table
    cols = ["factor", "rank_ic_mean", "rank_icir", "ic_pos_ratio",
            "monotonicity", "turnover", "grade", "score"]
    with pd.option_context("display.width", 160, "display.max_rows", 50):
        print("\n=== 因子综合评分（按分数降序）===")
        print(summary[cols].to_string(index=False,
                                      float_format=lambda x: f"{x:.3f}"))


if __name__ == "__main__":
    main()
