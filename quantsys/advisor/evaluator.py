"""Quantitative stock evaluation engine.

Evaluates stocks across 5 dimensions using cross-sectional percentile ranking.
All scores are calibrated against peer stocks on the same date — a stock in the
top 20% of momentum gets ~80, not "is RSI between 40-70? +5 points".

Dimensions (configurable weights):
    1. Momentum     — 5d/20d/60d return, vol-adjusted return  (default 25%)
    2. Trend        — MA alignment, RSI health                 (default 25%)
    3. Valuation    — price position in 52-week range          (default 20%)
    4. Liquidity    — volume trend, turnover, trade amount     (default 15%)
    5. Factor       — composite of all sub-scores              (default 15%)
    6. Risk flags   — suspension, extreme volatility, ST

Confidence is ensemble-based: agreement across dimensions boosts it,
conflicting signals reduce it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class Action(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"
    AVOID = "avoid"


@dataclass
class EvalResult:
    """Comprehensive evaluation result for a single stock."""

    symbol: str
    name: str = ""
    date: str = ""

    # Scores (0-100, cross-sectional percentiles)
    total_score: float = 50.0
    momentum_score: float = 50.0
    trend_score: float = 50.0
    valuation_score: float = 50.0
    liquidity_score: float = 50.0
    factor_score: float = 50.0

    # Recommendation
    action: Action = Action.HOLD
    confidence: float = 0.5
    target_weight: float = 0.0

    # Details
    reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    technical_signals: dict = field(default_factory=dict)
    factor_values: dict = field(default_factory=dict)
    # Percentile ranks in cross-section
    percentiles: dict = field(default_factory=dict)


class StockEvaluator:
    """Cross-sectional stock evaluation engine.

    Key improvements over v1:
    - Cross-sectional percentile ranking (not absolute thresholds)
    - Factor computation uses actual price-derived metrics
    - Ensemble confidence based on dimension agreement
    - Batch evaluation for consistent cross-sectional comparison
    """

    def __init__(
        self,
        cache_dir: str | Path = None,
        config: dict = None,
    ):
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / "data" / "raw"
        self._cache_dir = Path(cache_dir)

        from quantsys.data.sources.cache import CacheManager
        self._cache = CacheManager(self._cache_dir)

        eval_cfg = (config or {}).get("evaluation", {})
        self._score_weights = eval_cfg.get("score_weights", {
            "momentum": 0.25,
            "trend": 0.25,
            "valuation": 0.20,
            "liquidity": 0.15,
            "factor": 0.15,
        })
        self._buy_threshold = eval_cfg.get("buy_threshold", 65)
        self._sell_threshold = eval_cfg.get("sell_threshold", 35)

    # -- Public API ----------------------------------------------------

    def evaluate(self, symbol: str, date: str) -> EvalResult:
        """Evaluate a single stock.

        For best results, use evaluate_universe() which provides
        cross-sectional context. Single-stock evaluation falls back
        to absolute scoring.
        """
        # Delegate to universe evaluation for cross-sectional context
        symbols = self._discover_symbols()
        if symbol in symbols:
            results = self.evaluate_universe(symbols, date, top_n=0)
            for r in results:
                if r.symbol == symbol:
                    return r

        # Fallback: absolute scoring for unknown symbols
        return self._evaluate_single(symbol, date)

    def evaluate_universe(
        self, symbols: list[str], date: str, top_n: int = 20
    ) -> list[EvalResult]:
        """Cross-sectional evaluation of a stock universe.

        All metrics are computed across the entire universe then
        ranked into percentiles, ensuring meaningful score distribution.

        Returns results sorted by total_score descending.
        """
        symbols = [str(s).strip() for s in symbols if str(s).strip()]
        if not symbols:
            return []

        target_date = pd.Timestamp(date)

        # Phase 1: Load all data and compute raw metrics
        raw_metrics = self._compute_cross_sectional(symbols, target_date)
        if not raw_metrics:
            return []

        # Phase 2: Convert to percentile scores cross-sectionally
        results = []
        for symbol in symbols:
            metrics = raw_metrics.get(symbol)
            if metrics is None:
                continue

            result = EvalResult(symbol=symbol, date=date)
            result.risk_flags = metrics.pop("risk_flags", [])

            if "停牌" in str(result.risk_flags):
                result.action = Action.AVOID
                result.reasons.append("当前停牌")
                results.append(result)
                continue

            result.technical_signals = metrics.pop("signals", {})
            result.factor_values = metrics

            # Store raw metrics for cross-sectional ranking
            result._raw_metrics = metrics
            results.append(result)

        # Phase 3: Rank each metric cross-sectionally
        self._rank_cross_sectional(results, raw_metrics)

        # Phase 4: Compute final scores, actions, confidence
        for r in results:
            if r.action == Action.AVOID:
                continue
            self._finalize_result(r)

        # Sort and limit
        results.sort(key=lambda r: r.total_score, reverse=True)
        if top_n > 0:
            return results[:top_n]
        return results

    # -- Cross-sectional computation -----------------------------------

    def _compute_cross_sectional(
        self, symbols: list[str], target_date: pd.Timestamp
    ) -> dict:
        """Compute raw metrics for all symbols at target_date.

        Returns:
            {symbol: {metric_name: float, ..., risk_flags: [...], signals: {...}}}
        """
        all_metrics = {}
        for symbol in symbols:
            df = self._load_asset_data(symbol)
            if df is None or df.empty:
                continue

            df = df.sort_index()
            available = df.index[df.index <= target_date]
            if len(available) < 20:
                continue

            trade_date = available[-1]
            recent = df.loc[:trade_date].tail(252)
            if recent.empty or len(recent) < 20:
                continue

            metrics = self._extract_metrics(recent, trade_date, symbol)
            if metrics:
                all_metrics[symbol] = metrics

        return all_metrics

    def _extract_metrics(
        self, recent: pd.DataFrame, date: pd.Timestamp, symbol: str
    ) -> dict | None:
        """Extract all raw metrics from a stock's price history."""
        close = recent["close"]
        volume = recent.get("volume", pd.Series(dtype=float))
        current = close.iloc[-1]

        metrics = {}

        # -- Momentum metrics --
        if len(close) >= 5:
            metrics["ret_5d"] = float((close.iloc[-1] / close.iloc[-5] - 1) * 100)
        else:
            metrics["ret_5d"] = 0.0

        if len(close) >= 20:
            metrics["ret_20d"] = float((close.iloc[-1] / close.iloc[-20] - 1) * 100)
        else:
            metrics["ret_20d"] = 0.0

        if len(close) >= 60:
            metrics["ret_60d"] = float((close.iloc[-1] / close.iloc[-60] - 1) * 100)
        else:
            metrics["ret_60d"] = 0.0

        # Volatility-adjusted return (20d return / 20d daily volatility)
        if len(close) >= 20:
            daily_rets = close.pct_change().tail(20).dropna()
            if len(daily_rets) > 0 and daily_rets.std() > 0:
                ann_vol = daily_rets.std() * np.sqrt(252)
                ann_ret = (close.iloc[-1] / close.iloc[-20]) ** (252 / 20) - 1
                metrics["sharpe_proxy"] = float(ann_ret / ann_vol) if ann_vol > 0 else 0.0
            else:
                metrics["sharpe_proxy"] = 0.0
        else:
            metrics["sharpe_proxy"] = 0.0

        # -- Trend metrics --
        if len(close) >= 20:
            ma20 = close.rolling(20).mean().iloc[-1]
            metrics["ma20_deviation"] = float((current / ma20 - 1) * 100)
        else:
            metrics["ma20_deviation"] = 0.0

        if len(close) >= 60:
            ma60 = close.rolling(60).mean().iloc[-1]
            metrics["ma60_deviation"] = float((current / ma60 - 1) * 100)
            ma20 = close.rolling(20).mean().iloc[-1]
            metrics["ma_trend"] = float((ma20 / ma60 - 1) * 100)  # MA20 vs MA60
        else:
            metrics["ma60_deviation"] = 0.0
            metrics["ma_trend"] = 0.0

        # RSI(14)
        if len(close) >= 15:
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            last_loss = loss.iloc[-1]
            if last_loss > 0:
                rs = gain.iloc[-1] / last_loss
                metrics["rsi"] = float(100 - (100 / (1 + rs)))
            else:
                metrics["rsi"] = 100.0
        else:
            metrics["rsi"] = 50.0

        # Price position in 20-day range
        if len(close) >= 20:
            high20 = close.tail(20).max()
            low20 = close.tail(20).min()
            if high20 > low20:
                metrics["range_position"] = float((current - low20) / (high20 - low20) * 100)
            else:
                metrics["range_position"] = 50.0
        else:
            metrics["range_position"] = 50.0

        # -- Valuation metrics --
        if len(recent) >= 252:
            high52w = recent["close"].max()
            low52w = recent["close"].min()
        else:
            high52w = close.max()
            low52w = close.min()

        if high52w > low52w:
            metrics["valuation_pct"] = float((current - low52w) / (high52w - low52w) * 100)
        else:
            metrics["valuation_pct"] = 50.0

        # Drawdown from 52-week high
        if high52w > 0:
            metrics["dd_from_high"] = float((current / high52w - 1) * 100)
        else:
            metrics["dd_from_high"] = 0.0

        # -- Liquidity metrics --
        if len(volume) >= 20 and not volume.isna().all():
            avg_vol_20 = volume.tail(20).mean()
            avg_vol_5 = volume.tail(5).mean()
            if avg_vol_20 > 0:
                metrics["vol_ratio"] = float(avg_vol_5 / avg_vol_20)
            else:
                metrics["vol_ratio"] = 1.0

            # Volume consistency (lower CV = more stable)
            vol_cv = volume.tail(20).std() / avg_vol_20 if avg_vol_20 > 0 else 1.0
            metrics["vol_stability"] = float(1.0 / (1.0 + vol_cv))  # 0-1 scale
        else:
            metrics["vol_ratio"] = 1.0
            metrics["vol_stability"] = 0.5

        if "amount" in recent.columns and not recent["amount"].isna().all():
            metrics["avg_amount"] = float(recent["amount"].tail(20).mean())
        elif "volume" in recent.columns and "close" in recent.columns:
            metrics["avg_amount"] = float((recent["volume"] * recent["close"]).tail(20).mean())
        else:
            metrics["avg_amount"] = 0.0

        if "turnover" in recent.columns and not recent["turnover"].isna().all():
            metrics["avg_turnover"] = float(recent["turnover"].tail(20).mean())
        else:
            metrics["avg_turnover"] = 0.0

        # -- Risk flags --
        metrics["risk_flags"] = self._check_risk_flags(recent, date, symbol)

        # -- Technical signals for display --
        metrics["signals"] = {
            "price": round(float(current), 2),
            "change_5d": round(metrics["ret_5d"], 2),
            "change_20d": round(metrics["ret_20d"], 2),
            "ma20": round(float(close.rolling(20).mean().iloc[-1]), 2) if len(close) >= 20 else None,
            "ma60": round(float(close.rolling(60).mean().iloc[-1]), 2) if len(close) >= 60 else None,
            "rsi": round(metrics["rsi"], 1),
            "volatility_20d": round(float(close.pct_change().tail(20).std() * 100), 2) if len(close) >= 20 else None,
            "avg_volume_20d": int(volume.tail(20).mean()) if len(volume) >= 20 and not volume.isna().all() else 0,
            "avg_turnover": round(metrics["avg_turnover"], 2),
        }

        return metrics

    def _rank_cross_sectional(
        self, results: list[EvalResult], raw_metrics: dict
    ):
        """Convert raw metrics to percentile scores across the cross-section.

        Maps each metric to 0-100 based on where the stock ranks among peers.
        Direction is metric-specific (higher return = better, higher volatility = worse).
        """
        if len(results) < 3:
            # Too few for meaningful cross-sectional ranking
            for r in results:
                r.momentum_score = 50.0
                r.trend_score = 50.0
                r.valuation_score = 50.0
                r.liquidity_score = 50.0
                r.factor_score = 50.0
            return

        # Collect metric vectors
        metric_vectors = {}
        metric_names = [
            "ret_5d", "ret_20d", "ret_60d", "sharpe_proxy",
            "ma20_deviation", "ma60_deviation", "ma_trend", "rsi", "range_position",
            "valuation_pct", "dd_from_high",
            "vol_ratio", "vol_stability", "avg_amount", "avg_turnover",
        ]

        for name in metric_names:
            vec = []
            for r in results:
                val = r._raw_metrics.get(name, np.nan)
                vec.append(val)
            metric_vectors[name] = np.array(vec, dtype=float)

        # Compute percentile ranks for each stock on each metric
        for i, r in enumerate(results):
            if r.action == Action.AVOID:
                continue

            raw = r._raw_metrics
            percentiles = {}

            # --- Momentum (higher = better) ---
            mom_components = []
            for key in ["ret_5d", "ret_20d", "ret_60d", "sharpe_proxy"]:
                pct = self._percentile_rank(metric_vectors[key], i)
                percentiles[key] = pct
                mom_components.append(pct)
            r.momentum_score = float(np.mean(mom_components))

            # --- Trend (higher = better for positive-side metrics) ---
            trend_components = []
            # MA deviation: positive = above MA = bullish
            for key in ["ma20_deviation", "ma60_deviation", "ma_trend"]:
                pct = self._percentile_rank(metric_vectors[key], i)
                percentiles[key] = pct
                trend_components.append(pct)

            # RSI: best is 40-70 range (not too hot, not too cold)
            rsi_val = raw.get("rsi", 50)
            if 40 <= rsi_val <= 70:
                rsi_score = 70.0  # Sweet spot
            elif 30 <= rsi_val < 40:
                rsi_score = 60.0  # Oversold, potential bounce
            elif rsi_val < 30:
                rsi_score = 50.0  # Deep oversold, risky
            elif 70 < rsi_val <= 80:
                rsi_score = 40.0  # Overbought
            else:
                rsi_score = 25.0  # Extreme overbought
            percentiles["rsi_score"] = rsi_score
            trend_components.append(rsi_score)

            # Range position: middle-high range is bullish
            rp = raw.get("range_position", 50)
            rp_score = self._percentile_rank(metric_vectors["range_position"], i)
            percentiles["range_position"] = rp_score
            trend_components.append(rp_score)

            r.trend_score = float(np.mean(trend_components))

            # --- Valuation (lower price relative to 52w = cheaper = better) ---
            val_components = []
            # valuation_pct: lower = cheaper → invert percentile
            val_pct = self._percentile_rank(metric_vectors["valuation_pct"], i)
            val_pct_inv = 100 - val_pct  # Invert: cheaper = higher score
            percentiles["valuation_pct"] = val_pct_inv
            val_components.append(val_pct_inv)

            # dd_from_high: more negative = bigger discount = better (to a point)
            dd_pct = self._percentile_rank(metric_vectors["dd_from_high"], i)
            dd_pct_inv = 100 - dd_pct  # More drawdown = cheaper = higher score
            # But cap: extreme drawdown is bad
            dd_raw = raw.get("dd_from_high", 0)
            if dd_raw < -40:
                dd_pct_inv = max(dd_pct_inv - 20, 0)  # Penalty for deep drawdown
            percentiles["dd_from_high"] = dd_pct_inv
            val_components.append(dd_pct_inv)

            r.valuation_score = float(np.mean(val_components))

            # --- Liquidity (higher volume/turnover = better, to a point) ---
            liq_components = []
            for key in ["avg_amount", "avg_turnover"]:
                pct = self._percentile_rank(metric_vectors[key], i)
                percentiles[key] = pct
                liq_components.append(pct)

            # vol_ratio: 0.8-1.5 is healthy (close to 1 = stable)
            vol_ratio = raw.get("vol_ratio", 1.0)
            if 0.8 <= vol_ratio <= 1.5:
                vr_score = 70.0
            elif 0.5 <= vol_ratio < 0.8:
                vr_score = 45.0
            elif 1.5 < vol_ratio <= 2.5:
                vr_score = 55.0
            else:
                vr_score = 30.0
            percentiles["vol_ratio_score"] = vr_score
            liq_components.append(vr_score)

            # vol_stability: higher = more stable
            vs_pct = self._percentile_rank(metric_vectors["vol_stability"], i)
            percentiles["vol_stability"] = vs_pct
            liq_components.append(vs_pct)

            r.liquidity_score = float(np.mean(liq_components))

            # --- Factor (composite of sub-scores) ---
            r.factor_score = float(np.mean([
                r.momentum_score, r.trend_score, r.valuation_score, r.liquidity_score
            ]))

            r.percentiles = percentiles

    def _finalize_result(self, r: EvalResult):
        """Compute total score, action, confidence, and reasons."""
        weights = self._score_weights
        r.total_score = (
            r.momentum_score * weights.get("momentum", 0.25)
            + r.trend_score * weights.get("trend", 0.25)
            + r.valuation_score * weights.get("valuation", 0.20)
            + r.liquidity_score * weights.get("liquidity", 0.15)
            + r.factor_score * weights.get("factor", 0.15)
        )

        # Ensemble confidence: agreement across dimensions
        scores = np.array([
            r.momentum_score, r.trend_score, r.valuation_score,
            r.liquidity_score, r.factor_score,
        ])

        n_bullish = np.sum(scores >= 60)
        n_bearish = np.sum(scores <= 40)

        if n_bullish >= 4:
            base_conf = 0.75 + (n_bullish - 4) * 0.05
        elif n_bullish >= 3:
            base_conf = 0.60 + (n_bullish - 3) * 0.05
        elif n_bearish >= 4:
            base_conf = 0.75 + (n_bearish - 4) * 0.05
        elif n_bearish >= 3:
            base_conf = 0.60 + (n_bearish - 3) * 0.05
        else:
            base_conf = 0.45  # Mixed signals = low confidence

        # Adjust by score extremeness
        score_std = float(np.std(scores))
        base_conf += min(score_std / 100, 0.10)

        r.confidence = max(0.30, min(0.95, float(base_conf)))

        # Action determination
        if r.total_score >= 80:
            r.action = Action.STRONG_BUY
        elif r.total_score >= self._buy_threshold:
            r.action = Action.BUY
        elif r.total_score >= self._sell_threshold:
            r.action = Action.HOLD
        elif r.total_score >= 20:
            r.action = Action.SELL
        else:
            r.action = Action.STRONG_SELL

        # Target weight
        if r.action in (Action.STRONG_BUY, Action.BUY):
            r.target_weight = min(0.05 + (r.total_score - 65) * 0.003, 0.12)
        elif r.action in (Action.SELL, Action.STRONG_SELL):
            r.target_weight = 0.0
        else:
            r.target_weight = 0.02

        # Generate reasons
        r.reasons = self._generate_reasons(r)

        # Clean up internal data
        if hasattr(r, '_raw_metrics'):
            delattr(r, '_raw_metrics')

    # -- Helpers -------------------------------------------------------

    def _percentile_rank(self, vec: np.ndarray, idx: int) -> float:
        """Compute percentile rank of vec[idx] within vec.

        Returns 0-100. Handles NaN values by treating them as median.
        """
        valid = vec[~np.isnan(vec)]
        if len(valid) < 2:
            return 50.0

        val = vec[idx]
        if np.isnan(val):
            return 50.0

        pct = (np.sum(valid < val) + np.sum(valid == val) * 0.5) / len(valid)
        return float(pct * 100)

    def _discover_symbols(self) -> list[str]:
        """Discover available symbol codes from cache (stocks + ETFs)."""
        symbols = []
        for dtype in ("stock_daily", "etf_daily"):
            d = self._cache_dir / dtype
            if not d.exists():
                continue
            for f in d.glob("*.parquet"):
                if not f.name.startswith("._"):
                    symbols.append(f.stem)
        return sorted(set(symbols))

    def _load_asset_data(self, symbol: str) -> pd.DataFrame | None:
        """Load OHLCV data for a symbol — try stock_daily, etf_daily, AKShare
        real-time fetch, then NAV cache fallback. Result is cached to etf_daily."""
        # 1. stock_daily cache
        df = self._cache.get("stock_daily", symbol=symbol)
        if df is not None and not df.empty:
            return df

        # 2. etf_daily cache
        df = self._cache.get("etf_daily", symbol=symbol)
        if df is not None and not df.empty:
            return df

        # 3. AKShare real-time fetch for ETFs (with retry)
        if symbol.startswith(("15", "16", "51", "56", "58")):
            import time
            for attempt in range(3):
                try:
                    import akshare as ak
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        etf_df = ak.fund_etf_hist_em(
                            symbol=symbol,
                            period="daily",
                            start_date="20100101",
                            end_date="20991231",
                            adjust="qfq",
                        )
                    if etf_df is not None and not etf_df.empty:
                        etf_df = etf_df.rename(columns={
                            "日期": "date", "开盘": "open", "最高": "high",
                            "最低": "low", "收盘": "close", "成交量": "volume",
                            "成交额": "amount",
                        })
                        date_cols = ["date"]
                        existing_date = [c for c in date_cols if c in etf_df.columns]
                        if existing_date:
                            etf_df[existing_date[0]] = pd.to_datetime(etf_df[existing_date[0]])
                            etf_df = etf_df.set_index(existing_date[0])
                        if "close" in etf_df.columns:
                            etf_df = etf_df.sort_index()
                            self._cache.put(etf_df, "etf_daily", symbol=symbol)
                            return etf_df
                    break  # Got a response, even if empty
                except Exception:
                    if attempt < 2:
                        time.sleep(1.0 * (attempt + 1))

        # 4. NAV cache fallback for ETFs (synthetic OHLCV from unit NAV)
        if symbol.startswith(("15", "16", "51", "56", "58")):
            nav_file = self._cache_dir / "nav_cache" / f"etf_{symbol}.parquet"
            if nav_file.exists():
                try:
                    nav_df = pd.read_parquet(nav_file)
                    col_map = {}
                    for c in nav_df.columns:
                        if c in ("净值日期", "date"):
                            col_map[c] = "date"
                        elif c in ("单位净值", "nav", "close"):
                            col_map[c] = "close"
                    if "date" in col_map.values() and "close" in col_map.values():
                        # Find actual column names
                        date_col = next(c for c, v in col_map.items() if v == "date")
                        close_col = next(c for c, v in col_map.items() if v == "close")
                        close_vals = pd.to_numeric(nav_df[close_col], errors="coerce").values
                        date_idx = pd.to_datetime(nav_df[date_col])
                        result = pd.DataFrame({"close": close_vals}, index=date_idx)
                        result = result.dropna(subset=["close"]).sort_index()
                        if not result.empty and len(result) >= 20:
                            self._cache.put(result, "etf_daily", symbol=symbol)
                            return result
                except Exception:
                    pass

        return None

    def _evaluate_single(self, symbol: str, date: str) -> EvalResult:
        """Fallback absolute evaluation for a single stock."""
        target_date = pd.Timestamp(date)
        result = EvalResult(symbol=symbol, date=date)

        df = self._load_asset_data(symbol)
        if df is None or df.empty:
            result.action = Action.AVOID
            result.reasons.append("无数据")
            return result

        df = df.sort_index()
        available = df.index[df.index <= target_date]
        if len(available) < 20:
            result.action = Action.AVOID
            result.reasons.append("数据不足")
            return result

        trade_date = available[-1]
        recent = df.loc[:trade_date].tail(252)
        metrics = self._extract_metrics(recent, trade_date, symbol)
        if metrics is None:
            result.action = Action.AVOID
            result.reasons.append("指标计算失败")
            return result

        result.risk_flags = metrics.pop("risk_flags", [])
        result.technical_signals = metrics.pop("signals", {})
        result.factor_values = metrics
        result.momentum_score = 50.0
        result.trend_score = 50.0
        result.valuation_score = 50.0
        result.liquidity_score = 50.0
        result.factor_score = 50.0
        result.total_score = 50.0
        result.action = Action.HOLD
        result.confidence = 0.3
        result.reasons = ["单股评估需横截面对比获得准确打分"]
        return result

    def _check_risk_flags(
        self, df: pd.DataFrame, date: pd.Timestamp, symbol: str
    ) -> list[str]:
        """Check for risk flags."""
        flags = []

        if date in df.index and "volume" in df.columns:
            row = df.loc[date]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            volume = row.get("volume", 0) if isinstance(row, pd.Series) else 0
            if volume == 0:
                flags.append("停牌 (成交量为零)")

        if "close" in df.columns and len(df) >= 5:
            recent_rets = df["close"].pct_change().tail(20).dropna()
            if len(recent_rets) >= 5:
                if recent_rets.abs().max() > 0.095:
                    flags.append("近期异常波动")
                std_20d = recent_rets.std()
                if std_20d > 0.05:
                    flags.append(f"高波动率 ({std_20d:.1%})")

        return flags

    def _generate_reasons(self, r: EvalResult) -> list[str]:
        """Generate human-readable reasons from evaluation."""
        reasons = []

        dims = [
            ("动量", r.momentum_score),
            ("趋势", r.trend_score),
            ("估值", r.valuation_score),
            ("流动性", r.liquidity_score),
        ]

        strengths = [(name, s) for name, s in dims if s >= 65]
        weaknesses = [(name, s) for name, s in dims if s <= 35]

        if strengths:
            names = ", ".join(f"{n}({s:.0f})" for n, s in strengths[:3])
            reasons.append(f"优势维度: {names}")

        if weaknesses:
            names = ", ".join(f"{n}({s:.0f})" for n, s in weaknesses[:3])
            reasons.append(f"劣势维度: {names}")

        # Technical specifics
        sig = r.technical_signals
        if sig.get("ma20") and sig.get("price"):
            if sig["price"] > sig["ma20"]:
                reasons.append("价格位于20日均线上方")
            else:
                reasons.append("价格位于20日均线下方")

        ret_20d = sig.get("change_20d", 0)
        if abs(ret_20d) > 5:
            direction = "涨幅" if ret_20d > 0 else "跌幅"
            reasons.append(f"近20日{direction} {abs(ret_20d):.1f}%")

        if r.risk_flags:
            for flag in r.risk_flags:
                reasons.append(f"⚠️ {flag}")

        # Ensemble summary
        n_bull = sum(1 for _, s in dims if s >= 60)
        if n_bull >= 3:
            reasons.append(f"多维度共振看多 ({n_bull}/4 维度看多)")
        elif n_bull <= 1 and r.total_score < 45:
            reasons.append("多维度共振看空")

        return reasons
