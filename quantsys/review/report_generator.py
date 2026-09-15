"""Markdown report generator for daily/weekly trading review.

Writes structured reports directly to the Obsidian vault so they appear
in the user's knowledge base alongside research notes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from quantsys.advisor.index_analyzer import IndexAnalyzer, IndexDashboard
from quantsys.review.db_writer import TradeJournalDB

logger = logging.getLogger(__name__)

OBSIDIAN_VAULT = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents"
REVIEW_DIR = "交易复盘"
DAILY_DIR = "日报"
WEEKLY_DIR = "周报"
DECISION_DIR = "决策日志"


class ReportGenerator:
    """Generate Markdown trading review reports for Obsidian.

    Usage::

        gen = ReportGenerator()
        path = gen.generate_daily_report("2026-07-16")
        print(f"Report written to {path}")
    """

    def __init__(self, vault_path: str | Path = None,
                 db: TradeJournalDB = None,
                 analyzer: IndexAnalyzer = None):
        if vault_path is None:
            vault_path = OBSIDIAN_VAULT
        self._vault = Path(vault_path)
        self._db = db or TradeJournalDB()
        self._analyzer = analyzer or IndexAnalyzer()

        # Ensure target directories exist
        self._base = self._vault / REVIEW_DIR
        self._daily_dir = self._base / DAILY_DIR
        self._weekly_dir = self._base / WEEKLY_DIR
        self._decision_dir = self._base / DECISION_DIR
        for d in [self._daily_dir, self._weekly_dir, self._decision_dir]:
            d.mkdir(parents=True, exist_ok=True)

    # -- public API -----------------------------------------------------------

    def generate_daily_report(self, date: str = None) -> Path:
        """Generate a daily trading review report.

        Args:
            date: Target date (default: today).

        Returns:
            Path to the generated Markdown file.
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        target = pd.Timestamp(date)
        dash = self._analyzer.dashboard(date)
        trades = self._get_trades_for_date(date)
        snapshots = self._db.get_daily_snapshots(days=1)

        content = self._build_daily_report(date, dash, trades, snapshots)
        path = self._daily_dir / f"{date}.md"
        path.write_text(content, encoding="utf-8")
        logger.info(f"Daily report written: {path}")
        return path

    def generate_weekly_report(self, week_ending: str = None) -> Path:
        """Generate a weekly trading review report.

        Args:
            week_ending: Friday date (default: most recent Friday).

        Returns:
            Path to the generated Markdown file.
        """
        if week_ending is None:
            week_ending = self._last_friday()

        end_date = pd.Timestamp(week_ending)
        start_date = end_date - pd.Timedelta(days=7)
        week_range = f"{start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}"

        dash = self._analyzer.dashboard(week_ending)
        trades = self._db.get_trades(days=7)
        snapshots = self._db.get_daily_snapshots(days=7)

        content = self._build_weekly_report(week_range, end_date, dash, trades, snapshots)
        path = self._weekly_dir / f"{end_date.strftime('%Y-%m-%d')}.md"
        path.write_text(content, encoding="utf-8")
        logger.info(f"Weekly report written: {path}")
        return path

    def generate_decision_log(self, date: str = None,
                               decision_type: str = "daily_review",
                               summary: str = "",
                               reasoning: str = "",
                               action_items: list[str] = None) -> Path:
        """Generate a standalone decision log entry.

        Args:
            date: Decision date.
            decision_type: 'daily_review', 'weekly_review', or 'adjustment'.
            summary: One-line summary.
            reasoning: Detailed reasoning.
            action_items: Actionable next steps.

        Returns:
            Path to the generated Markdown file.
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        type_label = {"daily_review": "日", "weekly_review": "周", "adjustment": "调整"}

        content = f"""---
date: {date}
type: {decision_type}
---

# 决策日志: {date} ({type_label.get(decision_type, decision_type)})

## 摘要
{summary}

## 分析推理
{reasoning}

## 行动项
"""
        if action_items:
            for item in action_items:
                content += f"- [ ] {item}\n"
        else:
            content += "- [ ] 待补充\n"

        content += f"\n---\n*生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}*"

        path = self._decision_dir / f"{date}-{decision_type}.md"
        path.write_text(content, encoding="utf-8")
        logger.info(f"Decision log written: {path}")

        # Also persist to SQLite
        self._db.log_decision(
            date=date,
            decision_type=decision_type,
            summary=summary,
            reasoning=reasoning,
            action_items=action_items or [],
            report_path=str(path),
        )

        return path

    # -- report builders -----------------------------------------------------

    def _build_daily_report(self, date: str, dash: IndexDashboard,
                             trades: list[dict],
                             snapshots: list[dict]) -> str:
        """Construct daily report Markdown."""

        # Market overview
        idx_lines = ""
        for code, snap in dash.indices.items():
            direction = "+" if snap.change_1d >= 0 else ""
            idx_lines += (f"| {snap.name} ({code}) | {snap.close:.2f} | "
                          f"{direction}{snap.change_1d:.2f}% | "
                          f"{snap.trend} | {snap.regime} | "
                          f"{snap.position_52w:.0f}% |\n")

        # Trades table
        trade_lines = ""
        if trades:
            for t in trades:
                dir_badge = "买入" if t["direction"] == "BUY" else "卖出"
                trade_lines += (f"| {t['symbol']} | {dir_badge} | "
                                f"{t['price']:.2f} | {t['quantity']} | "
                                f"{t.get('reason', '')} |\n")
        else:
            trade_lines = "| — | — | — | — | 今日无交易 |\n"

        # Snapshot info
        snapshot_info = ""
        if snapshots:
            s = snapshots[0]
            snapshot_info = f"""## 持仓快照

| 指标 | 数值 |
|------|------|
| 总资产 | {s.get('total_asset', 0):,.0f} |
| 总成本 | {s.get('total_cost', 0):,.0f} |
| 总盈亏 | {s.get('total_pnl', 0):,.0f} |
| 当日盈亏 | {s.get('daily_pnl', 0):,.0f} |
| 现金 | {s.get('cash', 0):,.0f} |
"""
        else:
            snapshot_info = """## 持仓快照

> 暂无快照数据，请先刷新持仓。
"""

        return f"""---
date: {date}
type: daily_review
---

# 日报: {date}

## 市场概况

| 指数 | 收盘价 | 日涨跌 | 趋势 | 状态 | 52周位置 |
|------|--------|--------|------|------|----------|
{idx_lines}

- **市场宽度**: {dash.market_breadth}
- **主导状态**: {dash.dominant_regime}
- **波动率环境**: {dash.volatility_regime}
- **信号**: {"; ".join(dash.signals) if dash.signals else "无明显信号"}

## 今日交易

| 代码 | 方向 | 价格 | 数量 | 理由 |
|------|------|------|------|------|
{trade_lines}

{snapshot_info}
## AI 分析

<!-- Claude Agent 填充 -->

---

## 决策记录

- [ ] 复盘交易执行质量
- [ ] 检查是否偏离策略规则
- [ ] 更新止损/止盈位

---
*生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""

    def _build_weekly_report(self, week_range: str, end_date: pd.Timestamp,
                              dash: IndexDashboard, trades: list[dict],
                              snapshots: list[dict]) -> str:
        """Construct weekly report Markdown."""

        # Weekly index returns
        idx_lines = ""
        for code, snap in dash.indices.items():
            idx_lines += (f"| {snap.name} | {snap.close:.2f} | "
                          f"{snap.change_5d:+.2f}% | {snap.change_20d:+.2f}% | "
                          f"{snap.trend} | {snap.regime} |\n")

        # Weekly trade summary
        buy_count = sum(1 for t in trades if t["direction"] == "BUY")
        sell_count = sum(1 for t in trades if t["direction"] == "SELL")
        total_buy = sum(t["amount"] for t in trades if t["direction"] == "BUY")
        total_sell = sum(t["amount"] for t in trades if t["direction"] == "SELL")

        trade_lines = ""
        if trades:
            for t in trades:
                dir_badge = "买入" if t["direction"] == "BUY" else "卖出"
                trade_lines += (f"| {t['trade_date']} | {t['symbol']} | "
                                f"{dir_badge} | {t['price']:.2f} | "
                                f"{t['quantity']} | {t.get('reason', '')} |\n")
        else:
            trade_lines = "| — | — | — | — | — | 本周无交易 |\n"

        # PnL from snapshots
        pnl_summary = ""
        if snapshots:
            total_pnl = sum(s.get("total_pnl", 0) for s in snapshots)
            daily_pnls = [s.get("daily_pnl", 0) for s in snapshots if s.get("daily_pnl")]
            weekly_pnl = sum(daily_pnls)
            pnl_summary = f"""## 盈亏概览

| 指标 | 数值 |
|------|------|
| 累积盈亏 | {total_pnl:,.0f} |
| 本周盈亏 | {weekly_pnl:,.0f} |
| 交易笔数 | {len(trades)} (买{buy_count}/卖{sell_count}) |
| 买入金额 | {total_buy:,.0f} |
| 卖出金额 | {total_sell:,.0f} |
"""

        return f"""---
date: {end_date.strftime('%Y-%m-%d')}
type: weekly_review
week_range: "{week_range}"
---

# 周报: {week_range}

## 本周市场回顾

| 指数 | 收盘价 | 5日涨跌 | 20日涨跌 | 趋势 | 状态 |
|------|--------|---------|----------|------|------|
{idx_lines}

- **市场宽度**: {dash.market_breadth}
- **主导状态**: {dash.dominant_regime}
- **波动率环境**: {dash.volatility_regime}
- **信号**: {"; ".join(dash.signals) if dash.signals else "无明显信号"}

## 本周交易汇总

| 日期 | 代码 | 方向 | 价格 | 数量 | 理由 |
|------|------|------|------|------|------|
{trade_lines}

{pnl_summary}
## 下周展望

<!-- Claude Agent 填充 -->

---

## 待办

- [ ] 检查下周经济日历
- [ ] 调整持仓风险敞口
- [ ] 审查策略参数是否需要调整

---
*生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""

    # -- helpers -------------------------------------------------------------

    def _get_trades_for_date(self, date: str) -> list[dict]:
        """Get trades for a specific date from the journal."""
        import sqlite3
        try:
            rows = self._db._conn.execute(
                "SELECT * FROM trade_log WHERE trade_date = ? ORDER BY id DESC",
                (date,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    @staticmethod
    def _last_friday() -> str:
        """Return the most recent Friday as YYYY-MM-DD."""
        today = datetime.now()
        days_since_friday = (today.weekday() - 4) % 7
        friday = today - timedelta(days=days_since_friday)
        return friday.strftime("%Y-%m-%d")
