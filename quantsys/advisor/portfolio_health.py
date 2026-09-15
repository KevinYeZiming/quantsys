"""Portfolio health diagnostics for small-capital trading.

Evaluates current holdings against risk rules:
    - Position concentration check
    - Stop-loss proximity warning
    - Drawdown monitoring
    - Trade frequency compliance
    - Blacklist management
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from quantsys.data.sources.cache import CacheManager

logger = logging.getLogger(__name__)


@dataclass
class HealthReport:
    """Portfolio health diagnostic report."""

    date: str
    overall_health: str = "unknown"       # healthy | warning | critical

    # Portfolio metrics
    total_value: float = 0.0
    cash: float = 0.0
    positions: list[dict] = field(default_factory=list)

    # Risk metrics
    current_drawdown: float = 0.0         # Peak-to-current drawdown
    max_drawdown: float = 0.0             # Historical max drawdown
    drawdown_halt: bool = False           # -10% drawdown halt active

    # Position checks
    position_concentration: float = 0.0   # % in single stock
    near_stop_loss: list[str] = field(default_factory=list)  # Symbols near -5%
    blacklist: list[str] = field(default_factory=list)       # Failed-twice stocks

    # Trade compliance
    trades_this_month: int = 0
    trades_remaining: int = 4
    monthly_limit_hit: bool = False

    # Recommendations
    warnings: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


class PortfolioHealthChecker:
    """Evaluate portfolio health and risk compliance for small capital."""

    # Risk thresholds (1万 capital tuned)
    STOP_LOSS_PCT = -0.05          # Single position stop loss
    DRAWDOWN_HALT = -0.10          # Portfolio drawdown halt
    MAX_POSITIONS = 2              # Max concurrent positions
    MONTHLY_TRADE_LIMIT = 4        # Max round trips per month

    def __init__(self, cache_dir: str | Path = None):
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / "data" / "raw"
        self._cache = CacheManager(Path(cache_dir))
        self._trade_log: list[dict] = []    # {date, symbol, action, price}
        self._blacklist: dict[str, str] = {}  # {symbol: reason}
        self._peak_value: float = 0.0

    def check(
        self,
        date: str,
        positions: list[dict] = None,
        cash: float = 0.0,
        initial_capital: float = 10000.0,
    ) -> HealthReport:
        """Run a full portfolio health check.

        Args:
            date: Reference date.
            positions: List of {symbol, name, quantity, avg_cost}.
            cash: Available cash.
            initial_capital: Starting capital (for drawdown calc).

        Returns:
            HealthReport with diagnostics and action items.
        """
        positions = positions or []
        report = HealthReport(date=date)
        report.cash = cash

        # Calculate position values
        total_mv = 0.0
        for pos in positions:
            symbol = pos.get("symbol", "")
            qty = pos.get("quantity", 0)
            cost = pos.get("avg_cost", 0)

            current_price = self._get_current_price(symbol, date)
            mv = current_price * qty
            pnl_pct = (current_price / cost - 1) if cost > 0 else 0

            report.positions.append({
                "symbol": symbol,
                "name": pos.get("name", ""),
                "quantity": qty,
                "avg_cost": cost,
                "current_price": current_price,
                "market_value": mv,
                "pnl_pct": round(pnl_pct * 100, 2),
                "near_stop": pnl_pct <= self.STOP_LOSS_PCT + 0.02,  # within 2% of stop
            })

            total_mv += mv

            # Near stop-loss warning
            if pnl_pct <= self.STOP_LOSS_PCT + 0.02 and pnl_pct > self.STOP_LOSS_PCT:
                report.near_stop_loss.append(symbol)

            # Stop-loss triggered
            if pnl_pct <= self.STOP_LOSS_PCT:
                report.warnings.append(f"{symbol} 触发止损线 ({pnl_pct:.1%})")
                report.actions.append(f"立即卖出 {symbol}")
                report.overall_health = "critical"

        report.total_value = cash + total_mv

        # Drawdown check
        if report.total_value > self._peak_value:
            self._peak_value = report.total_value
        report.current_drawdown = (
            (report.total_value / self._peak_value - 1)
            if self._peak_value > 0 else 0
        )
        report.max_drawdown = report.current_drawdown

        if report.current_drawdown <= self.DRAWDOWN_HALT:
            report.drawdown_halt = True
            report.warnings.append(
                f"账户回撤 {report.current_drawdown:.1%} 触发清仓线 ({self.DRAWDOWN_HALT:.0%})"
            )
            report.actions.append("清仓全部持仓，停手一周")
            report.overall_health = "critical"

        # Position concentration
        if len(positions) > self.MAX_POSITIONS:
            report.warnings.append(f"持仓数量 {len(positions)} 超过上限 {self.MAX_POSITIONS}")
            report.actions.append("减少持仓至最多2只")

        if positions and total_mv > 0:
            report.position_concentration = (
                max(p["market_value"] for p in report.positions) / total_mv
                if positions else 0
            )

        # Trade frequency
        report.trades_this_month = self._count_monthly_trades(date)
        report.trades_remaining = max(0, self.MONTHLY_TRADE_LIMIT - report.trades_this_month)
        report.monthly_limit_hit = report.trades_remaining == 0

        if report.trades_this_month >= 3:
            report.warnings.append(f"本月已交易 {report.trades_this_month} 次，剩余 {report.trades_remaining} 次")

        if report.monthly_limit_hit:
            report.warnings.append("本月交易次数已用完，暂停新开仓")
            report.overall_health = "warning"

        # Blacklist check
        for pos in positions:
            if pos["symbol"] in self._blacklist:
                report.warnings.append(
                    f"{pos['symbol']} 在黑名单中: {self._blacklist[pos['symbol']]}"
                )
                report.actions.append(f"清仓 {pos['symbol']} (黑名单)")

        # Overall health
        if report.overall_health == "unknown":
            if report.warnings:
                report.overall_health = "warning"
            else:
                report.overall_health = "healthy"

        return report

    def log_trade(self, date: str, symbol: str, action: str, price: float):
        """Record a trade for monthly counting and blacklist management."""
        self._trade_log.append({
            "date": date, "symbol": symbol, "action": action, "price": price,
        })

    def add_to_blacklist(self, symbol: str, reason: str):
        """Add a symbol to blacklist (e.g., after two consecutive stop losses)."""
        self._blacklist[symbol] = reason
        logger.info(f"Blacklisted {symbol}: {reason}")

    def get_blacklist(self) -> dict:
        return dict(self._blacklist)

    def _get_current_price(self, symbol: str, date: str) -> float:
        """Get latest available price for a symbol."""
        df = self._cache.get("stock_daily", symbol=symbol)
        if df is None or df.empty:
            return 0.0

        df = df.sort_index()
        target = pd.Timestamp(date)
        df = df[df.index <= target]

        if df.empty or "close" not in df.columns:
            return 0.0

        return float(df["close"].iloc[-1])

    def _count_monthly_trades(self, date: str) -> int:
        """Count completed trades (buy+sell pairs) in the current month."""
        date_dt = pd.Timestamp(date)
        month_start = date_dt.replace(day=1)

        month_trades = [
            t for t in self._trade_log
            if pd.Timestamp(t["date"]) >= month_start
        ]
        # Each buy-sell pair counts as 1 trade
        buys = sum(1 for t in month_trades if t["action"] == "buy")
        sells = sum(1 for t in month_trades if t["action"] == "sell")
        return max(buys, sells)  # Conservative: count completed round trips
