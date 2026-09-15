"""Unified buy/sell evaluator for stocks, funds and gold (股/基/金统一买卖评估).

The original StockEvaluator only handled A-share main-board stocks with
cross-sectional ranking. This evaluator generalizes the methodology to
three asset classes with one consistent output:

    - stock  个股（日线 OHLCV）
    - fund   场外基金（单位净值 NAV，无盘中价，评分基于净值序列）
    - gold   黄金（黄金ETF 行情优先，上金所现货兜底）

Scoring uses each metric's percentile within its own trailing history
(typically 3 years), which makes scores comparable across asset classes
without requiring a cross-section — a single gold ETF or a single fund
can be evaluated on its own. When a universe list is supplied, results
are additionally ranked against peers (选股模式).

Output: strong_buy / buy / hold / sell / strong_sell with confidence,
suggested weight, ATR-based stop-loss / take-profit levels, reasons,
and risk flags. Every run can be persisted to data/evaluations/ and
exported as a Markdown report.

Usage::

    ev = AssetEvaluator()
    results = ev.evaluate(
        [("600519", "stock"), ("017103", "fund"), ("518880", "gold")],
        date="2026-09-15",
    )
    path = ev.save(results)            # -> data/evaluations/eval_*.parquet
    md = ev.to_markdown(results)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

import numpy as np
import pandas as pd

from quantsys.data.sources.cache import CacheManager

logger = logging.getLogger(__name__)


class AssetAction(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


@dataclass
class AssetEvaluation:
    """Evaluation result for one asset."""

    symbol: str
    asset_type: str            # stock | fund | gold
    date: str = ""
    name: str = ""
    price: float = 0.0

    # Dimension scores 0-100
    momentum_score: float = 50.0
    trend_score: float = 50.0
    risk_score: float = 50.0       # higher = safer (low vol, shallow dd)
    position_score: float = 50.0   # higher = cheaper entry vs own history
    total_score: float = 50.0

    action: AssetAction = AssetAction.HOLD
    confidence: float = 0.5
    target_weight: float = 0.0

    # Trade levels
    stop_loss: float = 0.0
    take_profit: float = 0.0

    # Diagnostics
    metrics: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)


class AssetEvaluator:
    """Evaluate buy/sell decisions for stock / fund / gold."""

    DEFAULT_WEIGHTS = {
        "momentum": 0.30,
        "trend": 0.30,
        "risk": 0.20,
        "position": 0.20,
    }
    DEFAULT_THRESHOLDS = {"strong_buy": 75, "buy": 60, "sell": 40, "strong_sell": 25}
    HISTORY_LOOKBACK = 756   # ~3 years of trading days for self-percentile
    MIN_HISTORY = 60

    def __init__(self, cache_dir: str | Path = None, config: dict = None):
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / "data" / "raw"
        self._cache_dir = Path(cache_dir)
        self._cache = CacheManager(self._cache_dir)

        cfg = (config or {}).get("asset_evaluation", {})
        self._weights = {**self.DEFAULT_WEIGHTS, **(cfg.get("score_weights") or {})}
        self._thresholds = {**self.DEFAULT_THRESHOLDS, **(cfg.get("thresholds") or {})}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        assets: list[tuple[str, str]] | list[str],
        date: str,
        asset_type: str = "stock",
        names: dict | None = None,
    ) -> list[AssetEvaluation]:
        """Evaluate a list of assets.

        Args:
            assets: [(symbol, asset_type), ...] or plain symbol list
                    (then ``asset_type`` applies to all).
            date: Reference date 'YYYY-MM-DD'.
            asset_type: Default asset type for plain symbol lists.
            names: Optional {symbol: display_name} map.

        Returns:
            List of AssetEvaluation sorted by total_score descending.
        """
        normalized = []
        for item in assets:
            if isinstance(item, (tuple, list)):
                normalized.append((str(item[0]), str(item[1])))
            else:
                normalized.append((str(item), asset_type))

        results = []
        for symbol, atype in normalized:
            try:
                r = self._evaluate_one(symbol, atype, date)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(f"Evaluation failed for {symbol} ({atype}): {e}")
                r = AssetEvaluation(symbol=symbol, asset_type=atype, date=date)
                r.risk_flags.append(f"评估失败: {e}")
            if names and symbol in names:
                r.name = names[symbol]
            results.append(r)

        results.sort(key=lambda r: r.total_score, reverse=True)
        return results

    def evaluate_positions(self, positions: list[dict], date: str) -> list[AssetEvaluation]:
        """Evaluate current portfolio holdings (data/positions.json format)."""
        assets = [(p["symbol"], p.get("asset_type", "stock")) for p in positions]
        names = {p["symbol"]: p.get("name", "") for p in positions}
        results = self.evaluate(assets, date, names=names)
        # Attach cost-based context
        by_symbol = {p["symbol"]: p for p in positions}
        for r in results:
            pos = by_symbol.get(r.symbol, {})
            cost = pos.get("avg_cost", 0)
            if cost and r.price:
                pnl = r.price / cost - 1
                r.metrics["pnl_pct"] = round(pnl * 100, 2)
                r.metrics["avg_cost"] = cost
                if pnl <= -0.08:
                    r.risk_flags.append(f"浮亏 {pnl:.1%}，接近硬止损线")
                elif pnl >= 0.15:
                    r.reasons.append(f"浮盈 {pnl:.1%}，可考虑移动止盈")
        return results

    def select_stocks(self, symbols: list[str], date: str, top_n: int = 20) -> list[AssetEvaluation]:
        """选股模式：全市场/股票池横截面打分，返回前 top_n。"""
        return self.evaluate(symbols, date, asset_type="stock")[:top_n]

    # ------------------------------------------------------------------
    # Data loading per asset class
    # ------------------------------------------------------------------

    def _load_series(self, symbol: str, asset_type: str) -> tuple[pd.Series | None, str]:
        """Load the price series for an asset. Returns (series, source_note)."""
        if asset_type == "stock":
            df = self._cache.get("stock_daily", symbol=symbol)
            if df is not None and not df.empty and "close" in df.columns:
                return df["close"].sort_index(), "stock_daily"

        elif asset_type == "etf":
            for cache_type, col in (("etf_daily", "close"), ("gold_etf", "close")):
                df = self._cache.get(cache_type, symbol=symbol)
                if df is not None and not df.empty and col in df.columns:
                    return df[col].sort_index(), cache_type
            # On-demand fetch for ETFs not yet cached (gold ETFs included)
            if symbol.startswith(("15", "16", "51", "56", "58")):
                try:
                    from quantsys.data.sources.akshare import AKShareSource
                    src = AKShareSource()
                    df = src.get_etf_daily(symbol)
                    if df is not None and not df.empty and "close" in df.columns:
                        cache_type = "gold_etf" if symbol in ("518880", "159934", "518800") else "etf_daily"
                        self._cache.put(df, cache_type, symbol=symbol)
                        return df["close"].sort_index(), cache_type
                except Exception:
                    pass

        elif asset_type == "fund":
            df = self._cache.get("fund_nav", symbol=symbol)
            if df is not None and not df.empty and "nav" in df.columns:
                return df["nav"].sort_index(), "fund_nav"
            # Legacy nav_cache fallback (accumulated NAV parquet)
            nav_file = self._cache_dir / "nav_cache" / f"etf_{symbol}.parquet"
            if nav_file.exists():
                try:
                    nav_df = pd.read_parquet(nav_file)
                    for col in ("单位净值", "nav", "close"):
                        if col in nav_df.columns:
                            s = pd.to_numeric(nav_df[col], errors="coerce")
                            d = pd.to_datetime(nav_df.get("净值日期", nav_df.index))
                            return pd.Series(s.values, index=pd.DatetimeIndex(d)).dropna().sort_index(), "nav_cache"
                except Exception:
                    pass

        elif asset_type == "gold":
            for cache_type, col in (("gold_etf", "close"), ("gold_spot", "close"),
                                    ("etf_daily", "close")):
                df = self._cache.get(cache_type, symbol=symbol)
                if df is not None and not df.empty and col in df.columns:
                    return df[col].sort_index(), cache_type

        return None, ""

    # ------------------------------------------------------------------
    # Single-asset evaluation
    # ------------------------------------------------------------------

    def _evaluate_one(self, symbol: str, asset_type: str, date: str) -> AssetEvaluation:
        result = AssetEvaluation(symbol=symbol, asset_type=asset_type, date=date)
        target = pd.Timestamp(date)

        close, source = self._load_series(symbol, asset_type)
        if close is None or close.empty:
            result.risk_flags.append("无本地数据，请先运行 scripts/update_assets.py / update_data.py")
            result.action = AssetAction.HOLD
            return result

        available = close.index[close.index <= target]
        if len(available) < self.MIN_HISTORY:
            result.risk_flags.append(f"历史数据不足 ({len(available)} < {self.MIN_HISTORY} 条)")
            result.action = AssetAction.HOLD
            return result

        trade_date = available[-1]
        hist = close.loc[:trade_date].tail(self.HISTORY_LOOKBACK)
        current = float(hist.iloc[-1])
        result.price = round(current, 4)
        result.metrics["data_source"] = source
        result.metrics["as_of"] = str(trade_date.date())

        m = self._compute_metrics(hist)
        result.metrics.update({k: (round(v, 4) if isinstance(v, (int, float)) else v)
                               for k, v in m.items()})

        # Scores: percentile of current value within own history
        result.momentum_score = self._hist_percentile(hist.pct_change().rolling(60).apply(
            lambda x: (1 + x).prod() - 1, raw=True).dropna(), m["ret_60d"], higher_better=True)
        result.trend_score = float(np.mean([
            self._hist_percentile(hist / hist.rolling(20).mean() - 1, m["ma20_dev"], True),
            self._hist_percentile(hist / hist.rolling(60).mean() - 1, m["ma60_dev"], True),
        ]))
        vol_series = hist.pct_change().rolling(20).std().dropna() * np.sqrt(252)
        result.risk_score = float(np.mean([
            self._hist_percentile(vol_series, m["ann_vol"], higher_better=False),
            100 - min(abs(m["dd_from_high"]) / 0.5 * 100, 100),  # deeper dd = worse
        ]))
        range_pos_series = ((hist - hist.rolling(252, min_periods=60).min())
                            / (hist.rolling(252, min_periods=60).max()
                               - hist.rolling(252, min_periods=60).min()))
        result.position_score = self._hist_percentile(
            range_pos_series.dropna(), m["range_position"], higher_better=False,
        )

        w = self._weights
        result.total_score = float(np.clip(
            result.momentum_score * w["momentum"]
            + result.trend_score * w["trend"]
            + result.risk_score * w["risk"]
            + result.position_score * w["position"],
            0, 100,
        ))

        self._decide(result, m, hist)
        result.reasons = self._reasons(result, m)
        result.risk_flags.extend(self._risk_flags(m, hist))
        return result

    @staticmethod
    def _compute_metrics(hist: pd.Series) -> dict:
        current = float(hist.iloc[-1])
        ret = hist.pct_change()

        def _ret(n: int) -> float:
            return float(current / hist.iloc[-n] - 1) if len(hist) >= n else 0.0

        ma20 = float(hist.rolling(20).mean().iloc[-1])
        ma60 = float(hist.rolling(60).mean().iloc[-1])
        vol20 = float(ret.tail(20).std() * np.sqrt(252))
        high_52w = float(hist.tail(252).max())
        low_52w = float(hist.tail(252).min())
        # RSI(14)
        delta = hist.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean().iloc[-1]
        rsi = float(100 - 100 / (1 + gain / loss)) if loss > 0 else 100.0
        # ATR(14) in percent
        tr = pd.concat([
            hist.diff().abs(),
            (hist - hist.shift(2)).abs(),
        ], axis=1).max(axis=1)
        atr_pct = float(tr.tail(14).mean() / current)

        return {
            "ret_5d": _ret(5), "ret_20d": _ret(20), "ret_60d": _ret(60),
            "ann_vol": vol20,
            "ma20": ma20, "ma60": ma60,
            "ma20_dev": current / ma20 - 1 if ma20 else 0.0,
            "ma60_dev": current / ma60 - 1 if ma60 else 0.0,
            "rsi": rsi,
            "dd_from_high": current / high_52w - 1 if high_52w else 0.0,
            "range_position": ((current - low_52w) / (high_52w - low_52w))
                              if high_52w > low_52w else 0.5,
            "atr_pct": atr_pct,
        }

    @staticmethod
    def _hist_percentile(series: pd.Series, current_value: float,
                         higher_better: bool) -> float:
        """Percentile rank of current_value within its own history (0-100)."""
        s = series.dropna()
        if len(s) < 30 or not np.isfinite(current_value):
            return 50.0
        pct = float((s < current_value).mean() * 100)
        return pct if higher_better else 100.0 - pct

    def _decide(self, r: AssetEvaluation, m: dict, hist: pd.Series):
        th = self._thresholds
        if r.total_score >= th["strong_buy"]:
            r.action = AssetAction.STRONG_BUY
        elif r.total_score >= th["buy"]:
            r.action = AssetAction.BUY
        elif r.total_score <= th["strong_sell"]:
            r.action = AssetAction.STRONG_SELL
        elif r.total_score <= th["sell"]:
            r.action = AssetAction.SELL
        else:
            r.action = AssetAction.HOLD

        # Confidence: data depth + volatility regime + signal dispersion
        depth = min(len(hist) / self.HISTORY_LOOKBACK, 1.0)
        vol_penalty = min(m["ann_vol"] / 0.6, 0.5)     # very volatile → less sure
        dispersion = np.std([r.momentum_score, r.trend_score, r.risk_score,
                             r.position_score]) / 50.0  # agreement boost
        r.confidence = round(float(np.clip(0.45 + 0.25 * depth + 0.2 * dispersion
                                           - 0.3 * vol_penalty, 0.3, 0.95)), 2)

        # Target weight: score-graded, scaled by confidence
        if r.action in (AssetAction.STRONG_BUY, AssetAction.BUY):
            base = 0.10 + (r.total_score - th["buy"]) * 0.004
            r.target_weight = round(min(base, 0.30) * r.confidence, 3)
        elif r.action in (AssetAction.SELL, AssetAction.STRONG_SELL):
            r.target_weight = 0.0
        else:
            r.target_weight = round(0.05 * r.confidence, 3)

        # ATR-based trade levels (funds: wider bands, no intraday stops)
        width = max(m["atr_pct"] * 2, 0.04)
        if r.asset_type == "fund":
            width = max(width, 0.08)
        r.stop_loss = round(r.price * (1 - width), 4)
        r.take_profit = round(r.price * (1 + width * 1.8), 4)

    @staticmethod
    def _reasons(r: AssetEvaluation, m: dict) -> list[str]:
        reasons = []
        dims = [("动量", r.momentum_score), ("趋势", r.trend_score),
                ("风险", r.risk_score), ("位置", r.position_score)]
        strengths = [f"{n}({s:.0f})" for n, s in dims if s >= 65]
        weaknesses = [f"{n}({s:.0f})" for n, s in dims if s <= 35]
        if strengths:
            reasons.append("优势维度: " + ", ".join(strengths))
        if weaknesses:
            reasons.append("劣势维度: " + ", ".join(weaknesses))

        if m["ma20_dev"] > 0:
            reasons.append(f"价格高于MA20 {m['ma20_dev']:.1%}，短期趋势向上")
        else:
            reasons.append(f"价格低于MA20 {abs(m['ma20_dev']):.1%}，短期趋势向下")
        if m["ret_20d"] > 0.05:
            reasons.append(f"近20日上涨 {m['ret_20d']:.1%}")
        elif m["ret_20d"] < -0.05:
            reasons.append(f"近20日下跌 {abs(m['ret_20d']):.1%}")
        if m["rsi"] >= 75:
            reasons.append(f"RSI {m['rsi']:.0f}，超买区域，追高需谨慎")
        elif m["rsi"] <= 25:
            reasons.append(f"RSI {m['rsi']:.0f}，超卖区域，或现反弹机会")
        reasons.append(
            f"距52周高点 {m['dd_from_high']:.1%}，处于自身历史区间 "
            f"{m['range_position']:.0%} 分位"
        )
        return reasons

    @staticmethod
    def _risk_flags(m: dict, hist: pd.Series) -> list[str]:
        flags = []
        if m["ann_vol"] > 0.45:
            flags.append(f"年化波动率 {m['ann_vol']:.0%}，高风险")
        if m["dd_from_high"] < -0.40:
            flags.append(f"距高点回撤 {m['dd_from_high']:.0%}，趋势可能反转")
        recent = hist.pct_change().tail(20).dropna()
        if len(recent) >= 5 and (recent.abs() > 0.095).any():
            flags.append("近期出现单日异常波动")
        return flags

    # ------------------------------------------------------------------
    # Persistence & reporting
    # ------------------------------------------------------------------

    def save(self, results: list[AssetEvaluation],
             out_dir: str | Path | None = None) -> Path:
        """Persist evaluation results as Parquet + JSON summary.

        Returns the Parquet path (data/evaluations/eval_YYYYMMDD_HHMMSS.parquet).
        """
        if out_dir is None:
            out_dir = self._cache_dir.parent / "evaluations"
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        stamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        rows = []
        for r in results:
            d = asdict(r)
            d["action"] = r.action.value
            for k, v in d.pop("metrics").items():
                d[f"m_{k}"] = v
            rows.append(d)
        df = pd.DataFrame(rows)

        parquet_path = out_dir / f"eval_{stamp}.parquet"
        df.to_parquet(parquet_path, compression="snappy")

        json_path = out_dir / f"eval_{stamp}.json"
        json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2,
                                        default=str))
        logger.info(f"Saved {len(rows)} evaluations to {parquet_path}")
        return parquet_path

    @staticmethod
    def to_markdown(results: list[AssetEvaluation]) -> str:
        lines = [
            "# 股/基/金 买卖评估报告",
            "",
            f"生成时间: {pd.Timestamp.now():%Y-%m-%d %H:%M}",
            f"评估标的数: {len(results)}",
            "",
            "| 标的 | 类型 | 现价 | 总分 | 动量 | 趋势 | 风险 | 位置 | 建议 | 置信度 | 建议仓位 |",
            "|------|------|------|------|------|------|------|------|------|--------|----------|",
        ]
        action_cn = {
            "strong_buy": "强烈买入", "buy": "买入", "hold": "持有",
            "sell": "卖出", "strong_sell": "强烈卖出",
        }
        for r in results:
            name = f"{r.name}({r.symbol})" if r.name else r.symbol
            lines.append(
                f"| {name} | {r.asset_type} | {r.price} | {r.total_score:.1f} "
                f"| {r.momentum_score:.0f} | {r.trend_score:.0f} "
                f"| {r.risk_score:.0f} | {r.position_score:.0f} "
                f"| {action_cn.get(r.action.value, r.action.value)} "
                f"| {r.confidence:.0%} | {r.target_weight:.0%} |"
            )

        lines.append("")
        for r in results:
            title = f"## {r.name or r.symbol} ({r.asset_type}) — {r.action.value}"
            lines += [title, ""]
            lines.append(
                f"- 现价 {r.price}，止损参考 {r.stop_loss}，止盈参考 {r.take_profit}"
            )
            for reason in r.reasons:
                lines.append(f"- {reason}")
            for flag in r.risk_flags:
                lines.append(f"- ⚠️ {flag}")
            lines.append("")
        return "\n".join(lines)
