#!/usr/bin/env python3
"""Generate daily/weekly trading review reports and write to Obsidian vault.

Usage:
    python scripts/run_review.py daily [--date YYYY-MM-DD]
    python scripts/run_review.py weekly [--week-ending YYYY-MM-DD]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from quantsys.review.db_writer import TradeJournalDB
from quantsys.review.report_generator import ReportGenerator
from quantsys.advisor.index_analyzer import IndexAnalyzer


def cmd_daily(args):
    """Generate a daily review report."""
    db = TradeJournalDB()
    analyzer = IndexAnalyzer()
    gen = ReportGenerator(db=db, analyzer=analyzer)

    date = args.date
    path = gen.generate_daily_report(date)
    print(f"日报已生成: {path}")

    # Show a quick summary
    dash = analyzer.dashboard(date)
    print(f"\n市场概况 ({date or 'today'}):")
    print(f"  宽度: {dash.market_breadth}")
    print(f"  状态: {dash.dominant_regime}")
    print(f"  波动: {dash.volatility_regime}")
    if dash.signals:
        print(f"  信号: {'; '.join(dash.signals)}")

    db.close()


def cmd_weekly(args):
    """Generate a weekly review report."""
    db = TradeJournalDB()
    analyzer = IndexAnalyzer()
    gen = ReportGenerator(db=db, analyzer=analyzer)

    week_ending = args.week_ending
    path = gen.generate_weekly_report(week_ending)
    print(f"周报已生成: {path}")

    dash = analyzer.dashboard(week_ending)
    print(f"\n周末市场概况 ({week_ending or 'last Friday'}):")
    print(f"  宽度: {dash.market_breadth}")
    print(f"  状态: {dash.dominant_regime}")
    print(f"  波动: {dash.volatility_regime}")

    # Trade summary for the week
    trades = db.get_trades(days=7)
    buys = sum(1 for t in trades if t["direction"] == "BUY")
    sells = sum(1 for t in trades if t["direction"] == "SELL")
    print(f"\n本周交易: {len(trades)} 笔 (买{buys}/卖{sells})")

    db.close()


def main():
    parser = argparse.ArgumentParser(
        description="生成日/周交易复盘报告并写入 Obsidian vault"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_daily = sub.add_parser("daily", help="生成日报")
    p_daily.add_argument("--date", default=None, help="日期 YYYY-MM-DD (默认今天)")

    p_weekly = sub.add_parser("weekly", help="生成周报")
    p_weekly.add_argument("--week-ending", default=None,
                           help="周五日期 YYYY-MM-DD (默认最近周五)")

    args = parser.parse_args()

    if args.command == "daily":
        cmd_daily(args)
    elif args.command == "weekly":
        cmd_weekly(args)


if __name__ == "__main__":
    main()
