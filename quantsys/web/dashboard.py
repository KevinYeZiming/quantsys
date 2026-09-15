"""Quantsys 量化评估辅助系统 — Streamlit Dashboard.

盘后量化评估 → 生成交易指令 → 次日手动/条件单执行的闭环。

Launch::

    streamlit run quantsys/web/dashboard.py
    → http://localhost:8501
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Quantsys - 量化评估辅助",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -- Sidebar ----------------------------------------------------------
st.sidebar.title("📊 Quantsys")
st.sidebar.caption("量化评估辅助系统 — 1万元小资金版")

page = st.sidebar.radio(
    "导航",
    ["🏠 账本概览", "📋 每日简报", "🔬 股票评估",
     "🎯 投资组合", "⚙️ 策略设置", "📡 数据管理", "📝 交易日志"],
)

st.sidebar.markdown("---")
st.sidebar.markdown("""
**设计理念**
- 算法评估 → 人工执行
- 低频高置信度 (≤4次/月)
- 止损-5% / 回撤-10%
- 银河APP条件单执行
""")


# =====================================================================
# Helpers
# =====================================================================

@st.cache_resource
def get_engine():
    from quantsys.advisor.recommendation import RecommendationEngine
    return RecommendationEngine()


@st.cache_resource
def get_evaluator():
    from quantsys.advisor.evaluator import StockEvaluator
    return StockEvaluator()


@st.cache_resource
def get_health_checker():
    from quantsys.advisor.portfolio_health import PortfolioHealthChecker
    return PortfolioHealthChecker()


@st.cache_resource
def get_portfolio_evaluator():
    from quantsys.advisor.portfolio_evaluator import PortfolioEvaluator
    return PortfolioEvaluator()


# =====================================================================
# Page: 账本概览
# =====================================================================

if page == "🏠 账本概览":
    st.title("账本概览")
    st.caption("量化评估辅助系统 · 盘后脚本 → 次日条件单 · 1万元小资金")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("💰 账户")
        capital = st.number_input("本金 (元)", value=10000, step=1000, key="capital")
        cash = st.number_input("可用资金", value=float(capital), step=100.0, key="cash")
        has_pos = st.checkbox("当前有持仓", key="has_pos")

    with col2:
        st.subheader("📦 持仓")
        pos_symbol = ""
        pos_qty = 0
        pos_cost = 0.0
        if has_pos:
            pos_symbol = st.text_input("股票代码", "600519", key="pos_symbol")
            pos_qty = st.number_input("数量 (股)", 100, step=100, key="pos_qty")
            pos_cost = st.number_input("成本价", 0.01, step=0.01, key="pos_cost")

    with col3:
        st.subheader("📊 状态")
        trade_count = st.number_input("本月已交易次数", 0, 4, 0, key="trade_count")

    st.markdown("---")

    if st.button("🔍 运行健康检查", type="primary", use_container_width=True):
        with st.spinner("检查中..."):
            checker = get_health_checker()
            positions = []
            if has_pos and pos_symbol:
                positions.append({
                    "symbol": pos_symbol, "quantity": pos_qty, "avg_cost": pos_cost,
                })

            report = checker.check(
                date=datetime.now().strftime("%Y-%m-%d"),
                positions=positions,
                cash=cash,
                initial_capital=capital,
            )

            # Display health
            colors = {"healthy": "green", "warning": "orange", "critical": "red", "unknown": "gray"}
            color = colors.get(report.overall_health, "gray")
            st.markdown(f"### 健康状态: :{color}[{report.overall_health.upper()}]")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("总资产", f"¥{report.total_value:,.0f}")
            c2.metric("回撤", f"{report.current_drawdown:.2%}")
            c3.metric("本月剩余", f"{report.trades_remaining}次")
            c4.metric("持仓数", str(len(report.positions)))

            if report.warnings:
                st.warning("⚠️ 风险警告")
                for w in report.warnings:
                    st.text(f"• {w}")

            if report.actions:
                st.error("🔴 需要执行的操作")
                for a in report.actions:
                    st.text(f"→ {a}")

            if report.positions:
                st.subheader("持仓明细")
                st.dataframe(pd.DataFrame(report.positions), use_container_width=True, hide_index=True)


# =====================================================================
# Page: 每日简报
# =====================================================================

elif page == "📋 每日简报":
    st.title("每日交易简报")
    st.caption("盘后运行 → 查看信号 → 次日银河APP设条件单")

    col1, col2, col3 = st.columns(3)
    with col1:
        eval_date = st.date_input("评估日期", datetime.now())
    with col2:
        from quantsys.advisor.recommendation import StrategyMode
        strategy_mode = st.selectbox(
            "策略模式",
            ["momentum", "mean_rev", "event"],
            format_func=lambda x: {
                "momentum": "A: 周频动量轮动",
                "mean_rev": "B: 均值回归/网格",
                "event": "C: 事件驱动",
            }.get(x, x),
        )
    with col3:
        monthly_trades = st.number_input("本月已交易", 0, 4, 0)

    st.markdown("---")

    if st.button("🚀 生成今日简报", type="primary", use_container_width=True):
        with st.spinner("计算中... (扫描全市场标的)"):
            engine = get_engine()
            mode = StrategyMode(strategy_mode)

            # Current position
            current_pos = None
            if st.session_state.get("has_pos"):
                current_pos = {
                    "symbol": st.session_state.get("pos_symbol", ""),
                    "quantity": st.session_state.get("pos_qty", 0),
                    "cost": st.session_state.get("pos_cost", 0),
                }

            briefing = engine.generate_briefing(
                date=str(eval_date),
                mode=mode,
                current_position=current_pos,
                monthly_trades=monthly_trades,
            )

            # Display results
            st.markdown(f"**生成时间**: {briefing.generated_at}")
            st.markdown(f"**账户状态**: {briefing.account_status}")
            st.markdown(f"**风险等级**: {briefing.risk_level.upper()}")

            if briefing.risk_warnings:
                st.warning("\n".join(f"• {w}" for w in briefing.risk_warnings))

            st.markdown("---")

            # Signals
            if briefing.signals:
                st.subheader("📊 交易信号")

                for sig in briefing.signals:
                    action_color = {
                        "buy": "🟢", "sell": "🔴", "hold": "🟡", "empty": "⚪"
                    }
                    icon = action_color.get(sig.action, "⚪")

                    st.markdown(f"### {icon} {sig.action.value.upper()} — {sig.symbol}")

                    cols = st.columns(4)
                    cols[0].metric("触发价", f"¥{sig.trigger_price:.2f}")
                    cols[1].metric("限价", f"¥{sig.limit_price:.2f}")
                    cols[2].metric("止损", f"¥{sig.stop_loss:.2f}" if sig.stop_loss > 0 else "—")
                    cols[3].metric("止盈", f"¥{sig.take_profit:.2f}" if sig.take_profit > 0 else "—")

                    st.info(f"**理由**: {sig.reason}")
                    st.caption(f"数量: {sig.quantity}股 | 仓位: {sig.position_pct:.0%} | 置信度: {sig.confidence:.0%}")

            else:
                st.info("今日无交易信号")

            # Todo list
            st.markdown("---")
            st.subheader("📝 操作清单")
            for item in briefing.todo:
                st.text(item)

            # Condition orders
            if briefing.condition_orders:
                st.markdown("---")
                st.subheader("📱 银河APP条件单设置指引")
                for i, order in enumerate(briefing.condition_orders):
                    with st.expander(f"{order['type']}: {order['symbol']} {order['side']}", expanded=(i == 0)):
                        st.markdown(f"**触发条件**: {order['trigger']}")
                        st.markdown(f"**委托指令**: {order['order']}")
                        st.caption(f"路径: {order['app_path']}")


# =====================================================================
# Page: 股票评估
# =====================================================================

elif page == "🔬 股票评估":
    st.title("个股量化评估")
    st.caption("5维横截面打分: 动量 + 趋势 + 估值 + 流动性 + 因子复合")

    col1, col2 = st.columns(2)
    with col1:
        eval_symbols = st.text_input("股票代码 (逗号分隔)", "600519,000858,601318,600036,000001")
    with col2:
        eval_date2 = st.date_input("评估日期", datetime.now(), key="eval_date2")

    if st.button("评估股票", type="primary"):
        symbols = [s.strip() for s in eval_symbols.split(",") if s.strip()]
        evaluator = get_evaluator()
        results = evaluator.evaluate_universe(symbols, str(eval_date2), top_n=0)

        if results:
            rows = []
            for r in results:
                rows.append({
                    "代码": r.symbol,
                    "综合得分": f"{r.total_score:.0f}",
                    "建议": r.action.value,
                    "动量": f"{r.momentum_score:.0f}",
                    "趋势": f"{r.trend_score:.0f}",
                    "估值": f"{r.valuation_score:.0f}",
                    "流动性": f"{r.liquidity_score:.0f}",
                    "因子复合": f"{r.factor_score:.0f}",
                    "置信度": f"{r.confidence:.0%}",
                    "权重": f"{r.target_weight:.2%}",
                    "风险": ", ".join(r.risk_flags) if r.risk_flags else "无",
                })

            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Score bar chart
            chart_data = pd.DataFrame([
                {"代码": r.symbol, "得分": r.total_score}
                for r in results
            ]).set_index("代码")
            st.bar_chart(chart_data)

            # Detail for each stock
            st.markdown("---")
            st.subheader("评估详情")
            for r in results:
                with st.expander(f"{r.symbol} — {r.action.value} (得分: {r.total_score:.0f})"):
                    st.text("\n".join(r.reasons))
                    if r.technical_signals:
                        st.json(r.technical_signals)
        else:
            st.warning("无有效评估结果 — 检查数据完整性")

# =====================================================================
# Page: 投资组合
# =====================================================================

elif page == "🎯 投资组合":
    st.title("投资组合评估")
    st.caption("风险分解 · 相关性矩阵 · 有效前沿 · 权重优化")

    col1, col2, col3 = st.columns(3)
    with col1:
        pf_symbols = st.text_input("持仓代码 (逗号分隔)", "600519,000858,601318", key="pf_symbols")
    with col2:
        pf_qtys = st.text_input("数量 (逗号分隔)", "100,100,100", key="pf_qtys")
    with col3:
        pf_costs = st.text_input("成本价 (逗号分隔)", "1700,160,50", key="pf_costs")

    col4, col5 = st.columns(2)
    with col4:
        pf_cash = st.number_input("可用资金", 0, value=2000, step=100, key="pf_cash")
    with col5:
        pf_date = st.date_input("评估日期", datetime.now(), key="pf_date")

    if st.button("📊 评估组合", type="primary", use_container_width=True):
        with st.spinner("计算组合风险指标..."):
            symbols = [s.strip() for s in pf_symbols.split(",") if s.strip()]
            qtys = [int(q.strip()) for q in pf_qtys.split(",") if q.strip()]
            costs = [float(c.strip()) for c in pf_costs.split(",") if c.strip()]

            positions = []
            for i, sym in enumerate(symbols):
                qty = qtys[i] if i < len(qtys) else 0
                cost = costs[i] if i < len(costs) else 0
                if qty > 0 and cost > 0:
                    positions.append({"symbol": sym, "quantity": qty, "avg_cost": cost})

            evaluator = get_portfolio_evaluator()
            report = evaluator.evaluate(
                positions=positions, cash=pf_cash, date=str(pf_date)
            )

            # Health
            colors = {"healthy": "green", "warning": "orange", "critical": "red"}
            color = colors.get(report.health, "gray")
            st.markdown(f"### 组合健康: :{color}[{report.health.upper()}]")

            # Risk dashboard
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("组合价值", f"¥{report.total_value:,.0f}")
            c2.metric("年化波动率", f"{report.portfolio_volatility:.1f}%")
            c3.metric("最大回撤", f"{report.max_drawdown:.1f}%")
            c4.metric("集中度 HHI", f"{report.concentration_hhi:.2f}")

            c5, c6, c7, c8 = st.columns(4)
            c5.metric("Sharpe", f"{report.sharpe_ratio:.2f}")
            c6.metric("Sortino", f"{report.sortino_ratio:.2f}")
            c7.metric("Calmar", f"{report.calmar_ratio:.2f}")
            c8.metric("VaR (95%)", f"{report.portfolio_var_95:.1f}%")

            # Warnings & suggestions
            if report.warnings:
                st.warning("⚠️ 风险警告")
                for w in report.warnings:
                    st.text(f"• {w}")
            if report.suggestions:
                st.info("💡 优化建议")
                for s in report.suggestions:
                    st.text(f"→ {s}")

            st.markdown("---")

            # Holdings
            if report.holdings:
                st.subheader("📦 持仓明细")
                st.dataframe(pd.DataFrame(report.holdings), use_container_width=True, hide_index=True)

            # Correlation matrix
            if report.corr_labels and len(report.corr_labels) > 1:
                st.subheader("📊 相关性矩阵")
                corr_df = pd.DataFrame(
                    report.correlation_matrix,
                    index=report.corr_labels,
                    columns=report.corr_labels,
                )
                st.dataframe(corr_df.style.background_gradient(
                    cmap="RdYlGn", vmin=-1, vmax=1
                ), use_container_width=True)
                st.caption(f"平均相关性: {report.avg_correlation:.2f} {'⚠️ 分散效果有限' if report.avg_correlation > 0.7 else ''}")

            # Weight optimization
            if report.optimal_weights:
                st.subheader("🎯 权重优化 (Max Sharpe)")
                opt_df = pd.DataFrame({
                    "最优权重 (%)": report.optimal_weights,
                    "最小波动权重 (%)": report.min_vol_weights,
                }).fillna(0)
                st.dataframe(opt_df, use_container_width=True)

            # Vol contribution
            if report.vol_contribution:
                st.subheader("📉 波动率分解")
                vol_df = pd.DataFrame.from_dict(
                    report.vol_contribution, orient="index", columns=["波动贡献 (%)"]
                )
                st.bar_chart(vol_df)


# =====================================================================
# Page: 策略设置
# =====================================================================

elif page == "⚙️ 策略设置":
    st.title("策略设置")
    st.caption("配置三类策略的参数和风控规则")

    tab1, tab2, tab3 = st.tabs(["A: 动量轮动", "B: 均值回归", "C: 事件驱动"])

    with tab1:
        st.markdown("""
        ### 周频动量轮动策略
        - **买入条件**: 20日动量排名 + 成交量放大 + RSI 40-70 + 流通市值>50亿
        - **仓位**: 全仓单吊 (1万元集中持仓)
        - **出场**: 硬止损-5% / 移动止盈 (回撤3%止盈) / 持有5交易日
        - **执行**: 周五收盘后跑脚本, 周一开盘前在银河APP设价格条件单
        """)
        st.number_input("动量周期 (交易日)", 10, 60, 20, key="mom_period")
        st.number_input("RSI下限", 20, 50, 40, key="mom_rsi_low")
        st.number_input("RSI上限", 50, 80, 70, key="mom_rsi_high")

    with tab2:
        st.markdown("""
        ### 均值回归/网格策略
        - **标的**: 主板高流动性大盘股 (600/000开头, 日均成交>1亿)
        - **买入**: 价格触及20日均线-2σ (布林下轨) + RSI<35
        - **网格**: 基础价=20日均线, 每跌2%买入一份, 每涨2%卖出一份
        - **执行**: 银河APP网格条件单, 分3层 (3000/3000/4000)
        """)
        st.number_input("均线周期", 5, 60, 20, key="mr_ma")
        st.number_input("标准差倍数", 1.0, 3.0, 2.0, key="mr_std")
        st.number_input("网格间距 %", 1.0, 5.0, 2.0, key="mr_grid")

    with tab3:
        st.markdown("""
        ### 事件驱动策略
        - **筛选**: 净利润同比>30% + 营收同比>20% + PE<行业均值
        - **持有**: 财报公告后5个交易日
        - **数据**: AKShare `stock_yjbb` 业绩报表
        """)
        st.number_input("净利润同比最低 %", 10, 100, 30, key="ev_profit")
        st.number_input("PE上限", 10, 100, 50, key="ev_pe")

    st.markdown("---")
    st.subheader("全局风控参数")
    c1, c2, c3 = st.columns(3)
    c1.number_input("单票止损 %", -10, 0, -5, key="risk_stop")
    c2.number_input("总回撤止损 %", -20, 0, -10, key="risk_dd")
    c3.number_input("月交易上限", 1, 10, 4, key="risk_trades")


# =====================================================================
# Page: 数据管理
# =====================================================================

elif page == "📡 数据管理":
    st.title("数据管理")
    st.caption("AKShare 数据更新 · Parquet 存储 · 支持增量/全量")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 增量更新数据", use_container_width=True):
            import subprocess
            with st.spinner("更新中... (1-2分钟)"):
                subprocess.run(
                    [sys.executable, str(_PROJECT_ROOT / "scripts" / "update_data.py")],
                    capture_output=True, timeout=300,
                )
            st.success("数据更新完成")

    with col2:
        if st.button("📦 全量历史下载", use_container_width=True):
            import subprocess
            with st.spinner("全量下载中... (较慢)"):
                subprocess.run(
                    [sys.executable, str(_PROJECT_ROOT / "scripts" / "update_data.py"), "--full"],
                    capture_output=True, timeout=600,
                )
            st.success("全量下载完成")

    st.markdown("---")
    st.subheader("数据状态")

    raw_dir = _PROJECT_ROOT / "data" / "raw"
    for dtype in ["stock_daily", "index_daily", "etf_daily", "trade_calendar",
                   "financials", "macro", "stock_basic"]:
        d = raw_dir / dtype
        count = len(list(d.glob("*.parquet"))) if d.exists() else 0
        icon = "✅" if count > 0 else "❌"
        st.text(f"{icon} {dtype}: {count} 文件")


# =====================================================================
# Page: 交易日志
# =====================================================================

elif page == "📝 交易日志":
    st.title("交易日志")
    st.caption("记录每笔实际成交, 对比信号质量, 持续迭代策略")

    st.markdown("""
    ### 建议字段 (Notion / 飞书 / SQLite)

    | 字段 | 说明 |
    |------|------|
    | 日期 | 成交日期 |
    | 信号来源 | momentum / mean_rev / event |
    | 股票代码 | 600519 |
    | 方向 | 买入 / 卖出 |
    | 信号价 | 策略给出的参考价 |
    | 成交价 | 实际成交价 |
    | 滑点 | (成交价-信号价)/信号价 |
    | 数量 | 股数 |
    | 手续费 | 佣金+印花税 |
    | 持仓天数 | 买入到卖出间隔 |
    | 盈亏 | 实际盈亏金额 |
    | 盈亏% | 实际收益率 |
    | 止盈/止损触发 | 是/否/手动 |
    | 情绪状态 | 执行时心态 (1-5) |
    | 备注 | 偏离信号的原因 |
    """)

    st.info("""
    **复盘节奏**:
    - 每日收盘后: 录入成交数据
    - 每周日: 计算周胜率、盈亏比
    - 每月底: 策略绩效归因 (是否跑赢了单纯的持有)
    """)
