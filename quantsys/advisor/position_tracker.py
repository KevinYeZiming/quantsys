"""Unified position tracker supporting stocks, ETFs, and mutual funds.

Persists positions to a local JSON file, fetches live prices/NAV
(with local caching to avoid slow AKShare calls), calculates P&L,
and generates investment advice.

Refresh strategy (fast by default):
    1. Stocks: use local OHLCV cache (already fast)
    2. ETFs: try local stock cache first, then cached NAV, only hit API as last resort
    3. Funds: cache NAV to local Parquet, only re-fetch if stale (>1 day)
    4. Use force_api=True to bypass all caches
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import os
import sys
import numpy as np
import pandas as pd
from contextlib import contextmanager, redirect_stderr

logger = logging.getLogger(__name__)

os.environ.setdefault("AKSHARE_LOG_LEVEL", "WARNING")


@contextmanager
def _suppress_stderr():
    """Suppress stderr (tqdm progress bars) during AKShare calls."""
    with open(os.devnull, "w") as devnull:
        with redirect_stderr(devnull):
            yield


@dataclass
class Position:
    symbol: str
    name: str = ""
    asset_type: str = "stock"
    quantity: float = 0.0
    avg_cost: float = 0.0
    added_date: str = ""

    current_price: float = 0.0
    market_value: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    day_change_pct: float = 0.0
    last_updated: str = ""

    score: float = 50.0
    action: str = "hold"
    advice: str = ""
    risk_flags: list[str] = field(default_factory=list)


@dataclass
class PortfolioSnapshot:
    date: str
    positions: list[Position] = field(default_factory=list)
    total_cost: float = 0.0
    total_value: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    day_change: float = 0.0
    health: str = "unknown"
    refresh_mode: str = "cache"     # cache | api
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    generated_at: str = ""


class PositionTracker:
    """Track and evaluate a mixed-asset portfolio with local caching.

    Usage::

        tracker = PositionTracker()
        tracker.add("600519", "贵州茅台", qty=100, cost=1700)
        tracker.add("512710", "军工ETF", qty=5000, cost=0.65)
        tracker.add("017103", "大摩数字经济混合C", qty=10000, cost=1.05)
        snapshot = tracker.refresh()           # fast: uses local cache
        snapshot = tracker.refresh(force_api=True)  # slow: hits AKShare
    """

    def __init__(self, data_dir: str | Path = None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent.parent / "data"
        self._data_dir = Path(data_dir)
        self._positions_file = self._data_dir / "positions.json"
        self._nav_cache_dir = self._data_dir / "raw" / "nav_cache"
        self._nav_cache_dir.mkdir(parents=True, exist_ok=True)
        self._positions: dict[str, Position] = {}
        self._load()

    @property
    def positions(self) -> list[Position]:
        return list(self._positions.values())

    @property
    def count(self) -> int:
        return len(self._positions)

    def add(self, symbol: str, name: str = "", qty: float = 0,
            cost: float = 0, asset_type: str = "") -> Position:
        if not asset_type:
            asset_type = self._detect_type(symbol)
        pos = Position(
            symbol=symbol.strip(), name=name.strip(),
            asset_type=asset_type, quantity=qty, avg_cost=cost,
            added_date=datetime.now().strftime("%Y-%m-%d"),
        )
        self._positions[symbol] = pos
        self._save()
        return pos

    def remove(self, symbol: str) -> bool:
        if symbol in self._positions:
            del self._positions[symbol]
            self._save()
            return True
        return False

    # -- Refresh -----------------------------------------------------------

    def refresh(self, force_api: bool = False) -> PortfolioSnapshot:
        """Refresh all positions.

        Args:
            force_api: If True, bypass local cache and hit AKShare.
                       Default False — uses local cache for speed.
        """
        today = datetime.now()
        date_str = today.strftime("%Y-%m-%d")

        snapshot = PortfolioSnapshot(
            date=date_str,
            generated_at=today.strftime("%Y-%m-%d %H:%M"),
            refresh_mode="api" if force_api else "cache",
        )

        if not self._positions:
            snapshot.health = "empty"
            snapshot.suggestions.append("暂无持仓，添加持仓后可查看盈亏和建议")
            return snapshot

        # Step 1: Refresh prices (fast: local cache; slow: API)
        for pos in self._positions.values():
            try:
                if pos.asset_type in ("stock", "etf"):
                    self._refresh_traded(pos, date_str, force_api)
                elif pos.asset_type == "fund":
                    self._refresh_fund(pos, date_str, force_api)
            except Exception as e:
                logger.warning(f"Refresh failed for {pos.symbol}: {e}")
                pos.last_updated = date_str

        # Step 2: Cross-sectional evaluation (only for stocks/ETFs with data)
        eval_results = {}
        traded_symbols = [
            p.symbol for p in self._positions.values()
            if p.asset_type in ("stock", "etf") and p.current_price > 0
        ]
        if traded_symbols:
            try:
                from quantsys.advisor.evaluator import StockEvaluator
                # Only evaluate our symbols + a few cached for context
                stock_dir = self._data_dir / "raw" / "stock_daily"
                if stock_dir.exists():
                    cached = sorted([
                        f.stem for f in stock_dir.glob("*.parquet")
                        if not f.name.startswith("._")
                    ])
                    all_symbols = list(dict.fromkeys(traded_symbols + cached))  # deduplicate
                else:
                    all_symbols = traded_symbols

                evaluator = StockEvaluator()
                results = evaluator.evaluate_universe(all_symbols, date_str, top_n=0)
                eval_results = {r.symbol: r for r in results}
            except Exception as e:
                logger.warning(f"Cross-sectional eval failed: {e}")

        # Step 3: Apply scores and generate advice
        for pos in self._positions.values():
            if pos.asset_type in ("stock", "etf"):
                if pos.symbol in eval_results:
                    r = eval_results[pos.symbol]
                    pos.score = r.total_score
                    pos.action = r.action.value
                    pos.risk_flags = r.risk_flags
                    pos.advice = self._format_advice(pos, r)
                elif pos.asset_type == "etf" and pos.current_price > 0:
                    # ETF fallback: score from NAV data
                    pos.score = self._score_from_nav(pos.symbol, "etf")
                    pos.action = "buy" if pos.score >= 65 else ("sell" if pos.score <= 35 else "hold")
                    pos.advice = self._simple_advice(pos)
                else:
                    pos.advice = self._simple_advice(pos)
            # Fund scores are set during _refresh_fund

        # Step 4: Portfolio-level evaluation
        if len(self._positions) >= 2:
            try:
                from quantsys.advisor.portfolio_evaluator import PortfolioEvaluator
                pf_positions = [
                    {"symbol": p.symbol, "quantity": int(p.quantity), "avg_cost": p.avg_cost}
                    for p in self._positions.values()
                    if p.asset_type in ("stock", "etf") and p.quantity > 0
                ]
                if pf_positions:
                    pe = PortfolioEvaluator()
                    pf_report = pe.evaluate(positions=pf_positions, cash=0, date=date_str)
                    snapshot.warnings = pf_report.warnings
                    snapshot.suggestions = pf_report.suggestions
                    snapshot.health = pf_report.health
            except Exception as e:
                logger.warning(f"Portfolio eval failed: {e}")

        # Step 5: Aggregate snapshot
        for pos in self._positions.values():
            snapshot.positions.append(pos)
            snapshot.total_cost += pos.avg_cost * pos.quantity
            snapshot.total_value += pos.market_value

        snapshot.total_pnl = snapshot.total_value - snapshot.total_cost
        snapshot.total_pnl_pct = (
            (snapshot.total_pnl / snapshot.total_cost * 100)
            if snapshot.total_cost > 0 else 0
        )

        if snapshot.positions and snapshot.total_value > 0:
            day_changes = [
                p.day_change_pct * p.market_value / 100
                for p in snapshot.positions if p.market_value > 0
            ]
            snapshot.day_change = sum(day_changes) / snapshot.total_value * 100

        # Health
        if snapshot.health == "unknown":
            if snapshot.total_pnl_pct < -10:
                snapshot.health = "critical"
                snapshot.warnings.append(f"组合整体亏损 {snapshot.total_pnl_pct:.1f}%，触发严重警告")
            elif snapshot.total_pnl_pct < -5:
                snapshot.health = "warning"
                snapshot.warnings.append(f"组合整体亏损 {snapshot.total_pnl_pct:.1f}%")
            else:
                snapshot.health = "healthy"

        if not snapshot.suggestions:
            self._generate_suggestions(snapshot)

        self._save()
        return snapshot

    # -- Price refresh methods ---------------------------------------------

    def _refresh_traded(self, pos: Position, date_str: str, force_api: bool):
        """Get latest price for stock/ETF. Fast path: local cache."""
        from quantsys.data.sources.cache import CacheManager
        cache = CacheManager(self._data_dir / "raw")

        current_price = 0.0
        prev_price = 0.0

        # 1. Try local stock_daily cache (instant)
        df = cache.get("stock_daily", symbol=pos.symbol)
        if df is not None and not df.empty and "close" in df.columns:
            df = df.sort_index()
            if len(df) >= 2:
                current_price = float(df["close"].iloc[-1])
                prev_price = float(df["close"].iloc[-2])

        # 2. Try cached NAV for ETFs
        if current_price == 0 and pos.asset_type == "etf":
            current_price, prev_price = self._load_cached_nav(pos.symbol, "etf")

        # 3. Only hit AKShare if force_api or no cached data
        if (current_price == 0 or force_api) and pos.asset_type == "etf":
            try:
                import akshare as ak
                import warnings
                with warnings.catch_warnings(), _suppress_stderr():
                    warnings.simplefilter("ignore")
                    nav_df = ak.fund_etf_fund_info_em(fund=pos.symbol)
                if nav_df is not None and not nav_df.empty and len(nav_df) >= 2:
                    current_price = float(nav_df["单位净值"].iloc[-1])
                    prev_price = float(nav_df["单位净值"].iloc[-2])
                    self._save_cached_nav(pos.symbol, "etf", nav_df)
            except Exception as e:
                logger.debug(f"ETF API failed for {pos.symbol}: {e}")

        # 4. Fallback
        if current_price == 0:
            current_price = pos.avg_cost

        pos.current_price = current_price
        pos.market_value = current_price * pos.quantity
        pos.pnl = pos.market_value - pos.avg_cost * pos.quantity
        pos.pnl_pct = (current_price / pos.avg_cost - 1) * 100 if pos.avg_cost > 0 else 0
        pos.day_change_pct = (current_price / prev_price - 1) * 100 if prev_price > 0 else 0
        pos.last_updated = date_str

    def _refresh_fund(self, pos: Position, date_str: str, force_api: bool):
        """Get latest NAV for mutual fund. Fast path: cached NAV."""
        current_nav = 0.0
        prev_nav = 0.0
        day_change = 0.0

        # 1. Try cached NAV (instant)
        if not force_api:
            current_nav, prev_nav = self._load_cached_nav(pos.symbol, "fund")

        # 2. Only hit AKShare if needed
        if current_nav == 0 or force_api:
            try:
                import akshare as ak
                import warnings
                with warnings.catch_warnings(), _suppress_stderr():
                    warnings.simplefilter("ignore")
                    df = ak.fund_open_fund_info_em(symbol=pos.symbol, indicator="单位净值走势")
                if df is not None and not df.empty and len(df) >= 2:
                    current_nav = float(df["单位净值"].iloc[-1])
                    prev_nav = float(df["单位净值"].iloc[-2])
                    day_change = float(df["日增长率"].iloc[-1]) if "日增长率" in df.columns else 0
                    self._save_cached_nav(pos.symbol, "fund", df)

                    # Score the fund
                    pos.score = self._score_fund(df)
                    pos.action = "buy" if pos.score >= 65 else ("sell" if pos.score <= 35 else "hold")
                    pos.advice = self._fund_advice(pos, df)
            except Exception as e:
                logger.debug(f"Fund API failed for {pos.symbol}: {e}")

        if current_nav == 0:
            current_nav = pos.avg_cost

        pos.current_price = current_nav
        pos.market_value = current_nav * pos.quantity
        pos.pnl = pos.market_value - pos.avg_cost * pos.quantity
        pos.pnl_pct = (current_nav / pos.avg_cost - 1) * 100 if pos.avg_cost > 0 else 0
        pos.day_change_pct = day_change if day_change != 0 else (
            (current_nav / prev_nav - 1) * 100 if prev_nav > 0 else 0
        )
        pos.last_updated = date_str

        # Score from cached data if not already set
        if pos.score == 50.0 and pos.advice == "":
            pos.advice = self._simple_advice(pos)

    # -- NAV cache ---------------------------------------------------------

    def _nav_cache_path(self, symbol: str, asset_type: str) -> Path:
        return self._nav_cache_dir / f"{asset_type}_{symbol}.parquet"

    def _load_cached_nav(self, symbol: str, asset_type: str) -> tuple[float, float]:
        """Load NAV from local cache. Returns (current, previous) or (0, 0)."""
        cache_path = self._nav_cache_path(symbol, asset_type)
        if not cache_path.exists():
            return 0.0, 0.0
        try:
            df = pd.read_parquet(cache_path)
            if df.empty or len(df) < 2:
                return 0.0, 0.0

            col = "单位净值" if "单位净值" in df.columns else (
                "close" if "close" in df.columns else df.columns[0]
            )
            # Check if data is stale (> 2 days)
            if "净值日期" in df.columns:
                last_date = pd.Timestamp(df["净值日期"].iloc[-1])
                if (datetime.now() - last_date).days > 2:
                    return 0.0, 0.0  # Stale, force refresh

            vals = df[col].astype(float)
            return float(vals.iloc[-1]), float(vals.iloc[-2])
        except Exception:
            return 0.0, 0.0

    def _save_cached_nav(self, symbol: str, asset_type: str, df: pd.DataFrame):
        """Save NAV data to local cache."""
        cache_path = self._nav_cache_path(symbol, asset_type)
        try:
            df.to_parquet(cache_path, index=False)
        except Exception:
            pass

    # -- Scoring -----------------------------------------------------------

    def _score_from_nav(self, symbol: str, asset_type: str) -> float:
        """Score an ETF from cached NAV data (fallback when no stock_daily data)."""
        cache_path = self._nav_cache_path(symbol, asset_type)
        if not cache_path.exists():
            return 50.0
        try:
            df = pd.read_parquet(cache_path)
            return self._score_fund(df)
        except Exception:
            return 50.0

    def _score_fund(self, df: pd.DataFrame) -> float:
        try:
            nav = df["单位净值"].astype(float)
            if len(nav) < 20:
                return 50.0
            current = nav.iloc[-1]

            ret_20d = (current / nav.iloc[-20] - 1) * 100 if len(nav) >= 20 else 0
            ret_60d = (current / nav.iloc[-60] - 1) * 100 if len(nav) >= 60 else 0
            ma20 = nav.rolling(20).mean().iloc[-1]
            ma_dev = (current / ma20 - 1) * 100

            high = nav.tail(252).max() if len(nav) >= 252 else nav.max()
            dd = (current / high - 1) * 100 if high > 0 else 0

            score = 50.0
            if ret_20d > 5: score += 20
            elif ret_20d > 0: score += 10
            elif ret_20d < -10: score -= 20
            elif ret_20d < -5: score -= 10
            if ret_60d > 10: score += 10
            elif ret_60d < -15: score -= 10
            if ma_dev > 0: score += 8
            else: score -= 5
            if dd < -20: score += 15
            elif dd < -10: score += 8
            elif dd > 0: score -= 5
            if len(nav) >= 5:
                ret_5d = (current / nav.iloc[-5] - 1) * 100
                if ret_5d > 3: score += 5
                elif ret_5d < -5: score -= 5

            return max(5.0, min(95.0, score))
        except Exception:
            return 50.0

    def _format_advice(self, pos: Position, eval_result) -> str:
        r = eval_result
        action_map = {
            "strong_buy": "强烈推荐持有/加仓",
            "buy": "建议持有，可逢低加仓",
            "hold": "暂时观望，维持现有仓位",
            "sell": "建议减仓或清仓",
            "strong_sell": "强烈建议清仓",
            "avoid": "建议规避",
        }
        base = action_map.get(r.action.value, "观望")
        extras = []
        if r.reasons:
            extras.append(r.reasons[0])
        if pos.pnl_pct < -5:
            extras.append(f"已亏损 {pos.pnl_pct:.1f}%，接近止损线")
        if pos.pnl_pct > 10:
            extras.append(f"已盈利 {pos.pnl_pct:.1f}%，可考虑止盈")
        return f"{base}。{'；'.join(extras)}" if extras else base

    def _simple_advice(self, pos: Position) -> str:
        if pos.pnl_pct <= -5:
            return f"已亏损 {pos.pnl_pct:.1f}%，建议止损"
        elif pos.pnl_pct >= 15:
            return f"已盈利 {pos.pnl_pct:.1f}%，建议分批止盈"
        elif pos.pnl_pct >= 5:
            return "小幅盈利，继续持有观察"
        elif pos.pnl_pct >= 0:
            return "持平，继续持有"
        else:
            return "小幅亏损，关注是否触及止损"

    def _fund_advice(self, pos: Position, df: pd.DataFrame) -> str:
        score = pos.score
        pnl = pos.pnl_pct
        if pnl <= -8:
            return f"基金已亏损 {pnl:.1f}%，考虑止损或转换。评分: {score:.0f}"
        elif pnl <= -3:
            return f"基金小幅亏损 {pnl:.1f}%。评分: {score:.0f}，{'可继续定投' if score >= 50 else '观察是否持续下跌'}"
        elif pnl >= 15:
            return f"基金盈利 {pnl:.1f}%，考虑分批止盈。评分: {score:.0f}"
        elif pnl >= 5:
            return f"基金盈利 {pnl:.1f}%，运行良好。评分: {score:.0f}"
        if score >= 65:
            return f"基金评分较高 ({score:.0f})，建议继续持有或加仓"
        elif score >= 35:
            return f"基金评分中性 ({score:.0f})，建议继续持有观察"
        else:
            return f"基金评分偏低 ({score:.0f})，建议关注或减仓"

    def _generate_suggestions(self, snapshot: PortfolioSnapshot):
        losing = [p for p in snapshot.positions if p.pnl_pct < -5]
        if losing:
            snapshot.suggestions.append(
                f"⚠️ {len(losing)} 只持仓亏损超5%: {', '.join(p.symbol for p in losing)}，关注止损"
            )
        if snapshot.positions and snapshot.total_value > 0:
            largest = max(snapshot.positions, key=lambda p: p.market_value)
            pct = largest.market_value / snapshot.total_value * 100
            if pct > 60:
                snapshot.suggestions.append(f"⚠️ 单只持仓 {largest.symbol} 占比 {pct:.0f}%，建议分散风险")
        buy_signals = [p for p in snapshot.positions if p.action in ("buy", "strong_buy")]
        if buy_signals:
            snapshot.suggestions.append(f"✅ {len(buy_signals)} 只持仓评分看多: {', '.join(p.symbol for p in buy_signals)}")
        sell_signals = [p for p in snapshot.positions if p.action in ("sell", "strong_sell")]
        if sell_signals:
            snapshot.suggestions.append(f"❌ {len(sell_signals)} 只持仓评分看空: {', '.join(p.symbol for p in sell_signals)}，考虑减仓")
        if not snapshot.suggestions:
            snapshot.suggestions.append("持仓状态正常，按策略信号操作即可")

    # -- Helpers -----------------------------------------------------------

    def _detect_type(self, symbol: str) -> str:
        """Detect asset type by code pattern and cached data availability.

        Priority: unambiguous patterns > stock cache lookup > ETF patterns > fund default.
        """
        code = symbol.strip()

        # 1. Unambiguous ETF patterns (5-digit, or 6-digit ETF-specific prefixes)
        if len(code) == 5 and code.startswith(("51", "56", "58", "59", "15", "16", "18")):
            return "etf"
        if len(code) == 6 and code.startswith(("159", "510", "511", "512", "513",
                                                  "515", "516", "517", "518", "560",
                                                  "561", "562", "563", "588", "589")):
            return "etf"

        # 2. Unambiguous stock patterns — always stock regardless of cache
        if code.startswith(("600", "601", "603", "605", "688", "689", "300", "301")):
            return "stock"

        # 3. Ambiguous 6-digit codes (000xxx/001xxx/002xxx/003xxx could be stock or fund)
        if len(code) == 6 and code.startswith(("000", "001", "002", "003")):
            stock_dir = self._data_dir / "raw" / "stock_daily"
            if stock_dir.exists():
                stock_file = stock_dir / f"{code}.parquet"
                if stock_file.exists():
                    return "stock"
            return "fund"

        # 4. Other 6-digit codes not matching any stock prefix → fund
        if len(code) == 6:
            return "fund"

        return "stock"

    def _load(self):
        if self._positions_file.exists():
            try:
                data = json.loads(self._positions_file.read_text(encoding="utf-8"))
                for item in data:
                    pos = Position(**item)
                    self._positions[pos.symbol] = pos
            except Exception as e:
                logger.warning(f"Failed to load positions: {e}")

    def _save(self):
        try:
            items = []
            for pos in self._positions.values():
                items.append({
                    "symbol": pos.symbol, "name": pos.name,
                    "asset_type": pos.asset_type,
                    "quantity": pos.quantity, "avg_cost": pos.avg_cost,
                    "added_date": pos.added_date,
                })
            self._positions_file.parent.mkdir(parents=True, exist_ok=True)
            self._positions_file.write_text(
                json.dumps(items, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Failed to save positions: {e}")
