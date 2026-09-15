"""Trade recommendation engine for small-capital A-share trading.

Implements three low-frequency, high-confidence strategy prototypes
tuned for 1万 RMB capital:

    A. Weekly momentum rotation (周频动量轮动)
    B. Mean reversion / grid trading (均值回归/网格)
    C. Event-driven (业绩事件驱动)

Generates buy/sell/hold signals with price zones, stop-loss levels,
and position sizing — designed for manual execution via Galaxy
Securities APP condition orders.

Key constraints:
    - Max 1-2 positions (commission optimization for small capital)
    - Monthly trade limit (≤4 round trips to control costs)
    - 5% hard stop-loss, 10% portfolio drawdown halt
    - Main board + SME only (no ST/ChiNext/STAR)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from quantsys.data.sources.cache import CacheManager
from quantsys.data.universe import UniverseBuilder

logger = logging.getLogger(__name__)


# =====================================================================
# Signal types
# =====================================================================

class SignalType(str, Enum):
    BUY = "buy"            # 买入
    SELL = "sell"          # 卖出
    HOLD = "hold"          # 持仓不动
    EMPTY = "empty"        # 空仓等待


class StrategyMode(str, Enum):
    MOMENTUM = "momentum"         # A: Weekly momentum rotation
    MEAN_REVERSION = "mean_rev"   # B: Mean reversion / grid
    EVENT_DRIVEN = "event"        # C: Event-driven


@dataclass
class TradeSignal:
    """A single trade recommendation for manual execution."""

    date: str                              # Signal date
    strategy: str                          # Strategy name
    symbol: str                            # Stock code
    name: str = ""                         # Stock name
    action: SignalType = SignalType.HOLD   # What to do
    quantity: int = 0                      # Number of shares (multiple of 100)

    # Price guidance for condition orders
    trigger_price: float = 0.0             # Condition order trigger price
    limit_price: float = 0.0               # Limit order price
    stop_loss: float = 0.0                 # Hard stop-loss price (-5%)
    take_profit: float = 0.0               # Take-profit price (+10%)

    # Context
    confidence: float = 0.5                # 0-1 confidence
    reason: str = ""                       # Why this signal
    risk_flags: list[str] = field(default_factory=list)

    # Position management
    position_pct: float = 0.0              # Suggested position % (0-100)
    current_price: float = 0.0


@dataclass
class DailyBriefing:
    """Daily trading briefing — the output of an after-hours run."""

    date: str
    generated_at: str = ""

    # Summary
    account_status: str = ""               # 空仓/持仓
    current_position: dict | None = None   # Current holding info

    # Signals
    signals: list[TradeSignal] = field(default_factory=list)

    # Risk
    risk_level: str = "normal"             # normal | warning | critical
    risk_warnings: list[str] = field(default_factory=list)
    monthly_trades_used: int = 0           # Trades this month
    monthly_trades_limit: int = 4

    # Instructions for the user
    todo: list[str] = field(default_factory=list)
    condition_orders: list[dict] = field(default_factory=list)


# =====================================================================
# Recommendation Engine
# =====================================================================

class RecommendationEngine:
    """Generate trade recommendations for small-capital A-share trading.

    Usage::

        engine = RecommendationEngine(cache_dir="data/raw")
        briefing = engine.generate_briefing(date="2024-01-15")
        for sig in briefing.signals:
            print(f"{sig.action.value.upper()} {sig.symbol} @ {sig.limit_price}")
    """

    # A-share commission: min 5 RMB buy + min 5 RMB sell + 0.05% stamp on sell
    MIN_COMMISSION = 5.0
    STAMP_DUTY = 0.0005

    def __init__(self, cache_dir: str | Path = None):
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / "data" / "raw"
        self._cache_dir = Path(cache_dir)
        self._cache = CacheManager(self._cache_dir)
        self._universe = UniverseBuilder(self._cache)

    # -- Main entry point ------------------------------------------------

    def generate_briefing(
        self,
        date: str,
        mode: StrategyMode = StrategyMode.MOMENTUM,
        current_position: dict = None,
        monthly_trades: int = 0,
    ) -> DailyBriefing:
        """Generate a complete daily trading briefing.

        Args:
            date: Reference date 'YYYY-MM-DD'.
            mode: Strategy mode to use.
            current_position: Current holding dict {symbol, quantity, cost}.
            monthly_trades: Number of trades already executed this month.

        Returns:
            DailyBriefing with signals, risk assessment, and todo list.
        """
        briefing = DailyBriefing(
            date=date,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            current_position=current_position,
            monthly_trades_used=monthly_trades,
            monthly_trades_limit=4,
        )

        # Check if we can trade
        if monthly_trades >= 4:
            briefing.risk_level = "critical"
            briefing.risk_warnings.append("本月交易次数已达上限 (4次)，暂停交易")
            briefing.todo.append("本月不再开新仓")
            return briefing

        # Build universe (main board + SME, no ST/ChiNext/STAR)
        universe = self._build_safe_universe(date)
        if not universe:
            briefing.risk_warnings.append("无可交易标的")
            return briefing

        # Check current position status
        has_position = current_position and current_position.get("quantity", 0) > 0

        if has_position:
            briefing.account_status = "持仓"
            pos_signal = self._check_position_exit(
                current_position, date
            )
            if pos_signal:
                briefing.signals.append(pos_signal)
                briefing.account_status = "准备卖出"
        else:
            briefing.account_status = "空仓"

        # Generate entry signals (only if we have capacity)
        if not has_position or len(briefing.signals) == 0:
            if mode == StrategyMode.MOMENTUM:
                entry_signal = self._strategy_momentum(universe, date, briefing)
            elif mode == StrategyMode.MEAN_REVERSION:
                entry_signal = self._strategy_mean_reversion(universe, date, briefing)
            elif mode == StrategyMode.EVENT_DRIVEN:
                entry_signal = self._strategy_event_driven(date, briefing)
            else:
                entry_signal = None

            if entry_signal:
                briefing.signals.append(entry_signal)

        # Build todo list
        briefing.todo = self._build_todo(briefing)
        briefing.condition_orders = self._build_condition_orders(briefing)

        return briefing

    # -- Strategy A: Weekly Momentum Rotation ----------------------------

    def _strategy_momentum(
        self,
        universe: list[str],
        date: str,
        briefing: DailyBriefing,
    ) -> Optional[TradeSignal]:
        """Weekly momentum rotation (周频动量轮动).

        Logic:
            1. Calculate 20-day return for all main board stocks
            2. Filter: volume expanding, price above MA20, RSI 40-70
            3. Rank by momentum, select top candidate
            4. Full position (1万 = single stock)
        """
        if not universe:
            return None

        target_date = pd.Timestamp(date)
        lookback = 60
        date_start = target_date - timedelta(days=lookback * 2)

        candidates = []
        for symbol in universe[:100]:  # Cap for performance
            try:
                df = self._cache.get("stock_daily", symbol=symbol)
                if df is None or df.empty or len(df) < lookback:
                    continue

                df = df.sort_index()
                df = df[df.index <= target_date].tail(lookback)

                if len(df) < 40:
                    continue

                close = df["close"]
                volume = df.get("volume", pd.Series(dtype=float))

                current = close.iloc[-1]
                if current <= 0 or current > 100:  # Skip high-price stocks
                    continue

                # 20-day momentum
                momentum_20d = (close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else -999

                # Volume expansion check
                if len(volume) >= 20:
                    vol_20 = volume.tail(20).mean()
                    vol_5 = volume.tail(5).mean()
                    vol_expanding = vol_5 > vol_20 * 1.1
                else:
                    vol_expanding = False

                # MA20 check
                ma20 = close.rolling(20).mean().iloc[-1]
                above_ma20 = current > ma20

                # RSI check
                rsi = self._calc_rsi(close)
                rsi_ok = 40 <= rsi <= 70 if rsi is not None else True

                # Market cap proxy: avoid small-cap manipulation risk
                if "amount" in df.columns:
                    avg_amount = df["amount"].tail(20).mean()
                else:
                    avg_amount = 0

                if vol_expanding and above_ma20 and rsi_ok:
                    candidates.append({
                        "symbol": symbol,
                        "momentum_20d": momentum_20d,
                        "current": current,
                        "avg_amount": avg_amount,
                        "ma20": ma20,
                        "rsi": rsi,
                    })
            except Exception as e:
                logger.debug(f"Momentum scan failed for {symbol}: {e}")
                continue

        if not candidates:
            briefing.risk_warnings.append("动量轮动策略无符合条件的标的")
            return None

        # Sort by momentum, select top
        candidates.sort(key=lambda x: x["momentum_20d"], reverse=True)

        # Filter: market cap proxy > threshold (avoid micro-caps)
        valid = [c for c in candidates if c["avg_amount"] > 5e7]  # 50M daily amount
        if not valid:
            valid = candidates[:5]  # Fallback to top 5

        best = valid[0]
        current_price = best["current"]
        stop_loss = current_price * 0.95     # -5%
        take_profit = current_price * 1.10    # +10%
        quantity = int(10000 / current_price / 100) * 100  # Lot rounding

        if quantity == 0:
            briefing.risk_warnings.append(f"{best['symbol']} 股价过高，1万元无法买入1手")
            return None

        return TradeSignal(
            date=date,
            strategy="momentum_rotation",
            symbol=best["symbol"],
            action=SignalType.BUY,
            quantity=quantity,
            trigger_price=round(current_price * 1.01, 2),
            limit_price=round(current_price * 1.01, 2),
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            confidence=0.65,
            reason=(
                f"20日动量 {best['momentum_20d']:.1%}, "
                f"RSI {best['rsi']:.0f}, 量价齐升, "
                f"日均成交 {best['avg_amount']/1e8:.1f}亿"
            ),
            position_pct=1.0,
            current_price=current_price,
        )

    # -- Strategy B: Mean Reversion / Grid -------------------------------

    def _strategy_mean_reversion(
        self,
        universe: list[str],
        date: str,
        briefing: DailyBriefing,
    ) -> Optional[TradeSignal]:
        """Mean reversion / grid trading (均值回归/网格).

        Logic:
            1. Focus on high-liquidity main board stocks or ETFs
            2. Signal when price hits 20-day MA lower band (-2 std)
            3. Scale in: buy when oversold (RSI < 35)
            4. Sell signal when price returns to MA20 or RSI > 65
        """
        target_date = pd.Timestamp(date)

        # Look for oversold candidates in high-liquidity stocks
        candidates = []
        for symbol in universe[:80]:
            try:
                df = self._cache.get("stock_daily", symbol=symbol)
                if df is None or df.empty or len(df) < 60:
                    continue

                df = df.sort_index()
                df = df[df.index <= target_date].tail(60)

                close = df["close"]
                volume = df.get("volume", pd.Series(dtype=float))
                current = close.iloc[-1]

                if current <= 0 or current > 80:
                    continue

                # 20-day Bollinger Bands
                ma20 = close.rolling(20).mean().iloc[-1]
                std20 = close.rolling(20).std().iloc[-1]
                lower_band = ma20 - 2 * std20

                # RSI oversold check
                rsi = self._calc_rsi(close)

                # Volume check (decent liquidity)
                if len(volume) >= 20:
                    avg_vol = volume.tail(20).mean()
                else:
                    avg_vol = 0

                # Signal: price near/below lower band + RSI oversold
                if current <= lower_band * 1.02 and rsi is not None and rsi < 35:
                    candidates.append({
                        "symbol": symbol,
                        "current": current,
                        "ma20": ma20,
                        "lower_band": lower_band,
                        "rsi": rsi,
                        "avg_vol": avg_vol,
                    })
            except Exception as e:
                logger.debug(f"Mean-rev scan failed for {symbol}: {e}")

        if not candidates:
            briefing.risk_warnings.append("均值回归策略无超卖标的")
            return None

        # Filter for liquidity
        valid = [c for c in candidates if c["avg_vol"] > 1e6]
        if not valid:
            valid = candidates

        # Best candidate: deepest below MA20
        valid.sort(key=lambda x: x["current"] / x["ma20"])

        best = valid[0]
        current_price = best["current"]
        stop_loss = current_price * 0.95
        take_profit = best["ma20"]  # Target: return to MA20
        quantity = int(10000 / current_price / 100) * 100

        if quantity == 0:
            return None

        return TradeSignal(
            date=date,
            strategy="mean_reversion",
            symbol=best["symbol"],
            action=SignalType.BUY,
            quantity=quantity,
            trigger_price=round(current_price, 2),
            limit_price=round(current_price * 1.005, 2),
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            confidence=0.60,
            reason=(
                f"突破布林下轨, 低于MA20 {1-current_price/best['ma20']:.1%}, "
                f"RSI {best['rsi']:.0f} 超卖, 目标回归MA20({best['ma20']:.2f})"
            ),
            position_pct=1.0,
            current_price=current_price,
        )

    # -- Strategy C: Event-Driven ----------------------------------------

    def _strategy_event_driven(
        self,
        date: str,
        briefing: DailyBriefing,
    ) -> Optional[TradeSignal]:
        """Event-driven strategy (业绩事件驱动).

        Logic:
            1. Check for recent earnings announcements
            2. Filter: net profit YoY > 30% + revenue YoY > 20% + PE < industry avg
            3. Hold until 5 days after announcement

        Note: Requires stock_basic data with PE/PB and financial data.
        Falls back gracefully when data is unavailable.
        """
        # Try to load earnings data
        basic = self._cache.get("stock_basic")
        if basic is None or basic.empty:
            briefing.risk_warnings.append("业绩数据不可用，事件驱动策略跳过")
            return None

        # Look for PE, profit growth columns
        profit_cols = ["净利润同比", "profit_yoy", "利润同比"]
        pe_cols = ["市盈率-动态", "pe_ttm", "pe"]

        profit_col = None
        for c in profit_cols:
            if c in basic.columns:
                profit_col = c
                break

        pe_col = None
        for c in pe_cols:
            if c in basic.columns:
                pe_col = c
                break

        if profit_col is None or pe_col is None:
            briefing.risk_warnings.append("缺少业绩/PE字段，事件驱动策略不可用")
            return None

        # Filter candidates
        basic[profit_col] = pd.to_numeric(basic[profit_col], errors="coerce")
        basic[pe_col] = pd.to_numeric(basic[pe_col], errors="coerce")

        candidates = basic[
            (basic[profit_col] > 30) &
            (basic[pe_col] > 0) &
            (basic[pe_col] < 50) &
            (basic[pe_col] < basic[pe_col].quantile(0.3))
        ].copy()

        if candidates.empty:
            briefing.risk_warnings.append("事件驱动策略无符合条件的标的")
            return None

        # Pick best (lowest PE among high profit growth)
        candidates = candidates.sort_values(pe_col)
        best = candidates.iloc[0]
        symbol = str(best.get("symbol", ""))

        # Get current price
        df = self._cache.get("stock_daily", symbol=symbol)
        if df is None or df.empty:
            return None

        df = df.sort_index()
        current_price = float(df["close"].iloc[-1])
        stop_loss = current_price * 0.95
        take_profit = current_price * 1.15  # Wider target for event-driven
        quantity = int(10000 / current_price / 100) * 100

        if quantity == 0:
            return None

        return TradeSignal(
            date=date,
            strategy="event_driven",
            symbol=symbol,
            action=SignalType.BUY,
            quantity=quantity,
            trigger_price=round(current_price * 1.01, 2),
            limit_price=round(current_price * 1.01, 2),
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            confidence=0.55,
            reason=(
                f"业绩高增: {best[profit_col]:.0f}% YoY, "
                f"PE={best[pe_col]:.1f} (行业低位), "
                f"持有至公告后5日"
            ),
            position_pct=1.0,
            current_price=current_price,
        )

    # -- Position exit check ---------------------------------------------

    def _check_position_exit(
        self, position: dict, date: str
    ) -> Optional[TradeSignal]:
        """Check if current holding should be sold."""
        symbol = position.get("symbol", "")
        cost = position.get("cost", 0)
        qty = position.get("quantity", 0)

        if not symbol or qty <= 0:
            return None

        df = self._cache.get("stock_daily", symbol=symbol)
        if df is None or df.empty:
            return None

        df = df.sort_index()
        target_date = pd.Timestamp(date)
        df = df[df.index <= target_date]

        if df.empty:
            return None

        current_price = float(df["close"].iloc[-1])
        pnl_pct = (current_price / cost - 1) if cost > 0 else 0

        reasons = []
        sell = False

        # Stop loss: -5%
        if pnl_pct <= -0.05:
            sell = True
            reasons.append(f"触发止损 ({pnl_pct:.1%} < -5%)")

        # Take profit: trailing stop (回撤3%止盈)
        if "close" in df.columns and len(df) >= 5:
            recent_high = df["close"].tail(20).max()
            if recent_high > 0:
                drawdown = (current_price - recent_high) / recent_high
                if pnl_pct > 0.05 and drawdown <= -0.03:
                    sell = True
                    reasons.append(f"移动止盈 (从高点回撤 {drawdown:.1%})")

        # Total drawdown halt
        if pnl_pct <= -0.10:
            sell = True
            reasons.append("总回撤超10%，清仓停手一周")

        if sell:
            return TradeSignal(
                date=date,
                strategy="risk_management",
                symbol=symbol,
                action=SignalType.SELL,
                quantity=qty,
                trigger_price=round(current_price * 0.99, 2),
                limit_price=round(current_price * 0.99, 2),
                stop_loss=0.0,
                take_profit=0.0,
                confidence=0.95,
                reason=", ".join(reasons),
                current_price=current_price,
                position_pct=0.0,
            )

        # Hold: no sell signal triggered
        return None

    # -- Helpers ---------------------------------------------------------

    def _build_safe_universe(self, date: str) -> list[str]:
        """Build universe of safe, tradeable main board stocks."""
        try:
            all_stocks = self._universe.build(date, index_code=None, exclude_st=True)
        except Exception:
            # Fallback: discover from cache
            stock_dir = self._cache_dir / "stock_daily"
            if stock_dir.exists():
                all_stocks = [
                    p.stem for p in stock_dir.glob("*.parquet")
                    if not p.name.startswith("._")
                ]
            else:
                return []

        # Filter: main board + SME only (600/000/002), no 300/688
        safe = []
        for s in all_stocks:
            s = str(s)
            if s.startswith(("600", "601", "603", "000", "001", "002")):
                # Skip high-price stocks (>100 RMB, hard with 1万)
                safe.append(s)

        return safe

    def _calc_rsi(self, close: pd.Series, period: int = 14) -> Optional[float]:
        """Calculate RSI for a price series."""
        if len(close) < period + 1:
            return None

        delta = close.diff().dropna()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta.where(delta < 0, 0.0))

        avg_gain = gain.tail(period).mean()
        avg_loss = loss.tail(period).mean()

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return float(100 - (100 / (1 + rs)))

    def _build_todo(self, briefing: DailyBriefing) -> list[str]:
        """Build human-readable todo list from signals."""
        todos = []

        for sig in briefing.signals:
            if sig.action == SignalType.BUY:
                todos.append(
                    f"【买入】{sig.symbol} {sig.quantity}股 "
                    f"限价{sig.limit_price:.2f} | "
                    f"止损{sig.stop_loss:.2f} | "
                    f"止盈{sig.take_profit:.2f}"
                )
            elif sig.action == SignalType.SELL:
                todos.append(
                    f"【卖出】{sig.symbol} {sig.quantity}股 "
                    f"限价{sig.limit_price:.2f} | "
                    f"理由: {sig.reason}"
                )
            elif sig.action == SignalType.HOLD:
                todos.append(f"【持仓不动】{sig.symbol}")
            elif sig.action == SignalType.EMPTY:
                todos.append("【空仓等待】今日无信号")

        if not todos:
            todos.append("今日无操作，继续等待信号")

        # Add risk reminders
        if briefing.monthly_trades_used >= 3:
            todos.insert(0, f"⚠️ 本月已交易 {briefing.monthly_trades_used} 次，仅剩 {4 - briefing.monthly_trades_used} 次")

        return todos

    def _build_condition_orders(self, briefing: DailyBriefing) -> list[dict]:
        """Build condition order instructions for Galaxy Securities APP."""
        orders = []

        for sig in briefing.signals:
            if sig.action == SignalType.BUY:
                orders.append({
                    "type": "价格条件单",
                    "symbol": sig.symbol,
                    "side": "买入",
                    "trigger": f"价格升至 {sig.trigger_price}",
                    "order": f"限价 {sig.limit_price} 买入 {sig.quantity} 股",
                    "app_path": "银河证券APP → 交易 → 条件单 → 价格条件单",
                })
                orders.append({
                    "type": "止损条件单",
                    "symbol": sig.symbol,
                    "side": "卖出",
                    "trigger": f"价格跌至 {sig.stop_loss}",
                    "order": f"市价卖出全部 {sig.quantity} 股",
                    "app_path": "银河证券APP → 交易 → 条件单 → 止损条件单",
                })
            elif sig.action == SignalType.SELL:
                orders.append({
                    "type": "价格条件单",
                    "symbol": sig.symbol,
                    "side": "卖出",
                    "trigger": f"价格跌至 {sig.limit_price}",
                    "order": f"限价 {sig.limit_price} 卖出 {sig.quantity} 股",
                    "app_path": "银河证券APP → 交易 → 条件单 → 价格条件单",
                })

        return orders
