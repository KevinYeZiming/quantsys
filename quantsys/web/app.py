"""Quantsys Desktop — 量化评估辅助系统

A self-contained desktop-like web application with 2026 modern aesthetic.
Launch by double-clicking launch.command or running:

    python quantsys/web/app.py
"""

import sys
import json
import webbrowser
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

# =====================================================================
# HTML Template — 2026 Glassmorphism Design
# =====================================================================

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Quantsys · Quant Evaluation</title>
<style>
  :root {
    --bg: #0a0a0c;
    --surface: rgba(255,255,255,0.03);
    --surface-hover: rgba(255,255,255,0.06);
    --border: rgba(255,255,255,0.06);
    --text: #e4e4e7;
    --text-dim: #71717a;
    --accent: #6366f1;
    --accent-glow: rgba(99,102,241,0.15);
    --green: #22c55e;
    --red: #ef4444;
    --amber: #f59e0b;
    --radius: 16px;
    --radius-sm: 10px;
    --font: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif;
    --mono: "SF Mono", "JetBrains Mono", monospace;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: var(--font);
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    overflow: hidden;
    -webkit-font-smoothing: antialiased;
  }

  /* ── Sidebar ───────────────────── */
  .sidebar {
    width: 220px;
    min-width: 220px;
    background: rgba(255,255,255,0.015);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    padding: 28px 18px;
    gap: 6px;
    backdrop-filter: blur(20px);
  }

  .logo {
    font-size: 20px;
    font-weight: 700;
    letter-spacing: -0.5px;
    margin-bottom: 28px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .logo .dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 12px var(--accent-glow);
  }

  .nav-item {
    padding: 10px 14px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-size: 14px;
    font-weight: 450;
    color: var(--text-dim);
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 10px;
    border: 1px solid transparent;
    user-select: none;
  }
  .nav-item:hover { color: var(--text); background: var(--surface-hover); }
  .nav-item.active {
    color: var(--text);
    background: var(--accent-glow);
    border-color: rgba(99,102,241,0.2);
  }
  .nav-item .icon { font-size: 17px; width: 22px; text-align: center; }

  .sidebar-footer {
    margin-top: auto;
    font-size: 11px;
    color: var(--text-dim);
    padding: 10px 14px;
    border-top: 1px solid var(--border);
    padding-top: 16px;
  }
  .status-dot {
    display: inline-block;
    width: 6px; height: 6px;
    border-radius: 50%;
    margin-right: 6px;
  }
  .status-dot.online { background: var(--green); box-shadow: 0 0 6px rgba(34,197,94,0.5); }

  /* ── Main Content ──────────────── */
  .main {
    flex: 1;
    overflow-y: scroll;
    overflow-x: hidden;
    padding: 32px 40px;
    display: flex;
    flex-direction: column;
    gap: 28px;
    height: 100vh;
    -webkit-overflow-scrolling: touch;
    scrollbar-color: rgba(255,255,255,0.4) rgba(255,255,255,0.05);
    scrollbar-width: auto;
  }

  /* ── Custom Scrollbar ──────────── */
  .main::-webkit-scrollbar { width: 10px; display: block; }
  .main::-webkit-scrollbar-track { background: rgba(255,255,255,0.05); border-radius: 5px; margin: 4px 0; }
  .main::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.4); border-radius: 5px; min-height: 60px; }
  .main::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.6); }
  .main::-webkit-scrollbar-thumb:active { background: rgba(255,255,255,0.7); }

  /* textarea / pre / table scrollbar */
  textarea::-webkit-scrollbar, pre::-webkit-scrollbar, .table-wrap::-webkit-scrollbar { width: 6px; height: 6px; }
  textarea::-webkit-scrollbar-track, pre::-webkit-scrollbar-track, .table-wrap::-webkit-scrollbar-track { background: rgba(255,255,255,0.03); border-radius: 3px; }
  textarea::-webkit-scrollbar-thumb, pre::-webkit-scrollbar-thumb, .table-wrap::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.3); border-radius: 3px; }
  textarea::-webkit-scrollbar-thumb:hover, pre::-webkit-scrollbar-thumb:hover, .table-wrap::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.5); }

  .page { display: none; flex-direction: column; gap: 24px; }
  .page.active { display: flex; }

  h2 {
    font-size: 22px;
    font-weight: 650;
    letter-spacing: -0.3px;
  }
  .subtitle { font-size: 13px; color: var(--text-dim); margin-top: 2px; }

  /* ── Cards ─────────────────────── */
  .card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 16px;
  }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 22px 24px;
    transition: all 0.3s ease;
    backdrop-filter: blur(12px);
  }
  .card:hover {
    background: var(--surface-hover);
    border-color: rgba(255,255,255,0.1);
  }
  .card .label { font-size: 12px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 8px; }
  .card .value { font-size: 28px; font-weight: 650; letter-spacing: -0.5px; }
  .card .change { font-size: 12px; margin-top: 4px; }
  .card .change.up { color: var(--green); }
  .card .change.down { color: var(--red); }

  .card.wide { grid-column: 1 / -1; }

  /* ── Signal card ───────────────── */
  .signal-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px;
    display: flex;
    gap: 20px;
    align-items: flex-start;
    transition: all 0.3s ease;
  }
  .signal-card:hover { border-color: rgba(255,255,255,0.12); }

  .signal-badge {
    width: 48px; height: 48px;
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    font-weight: 700;
    flex-shrink: 0;
  }
  .signal-badge.buy { background: rgba(34,197,94,0.12); color: var(--green); }
  .signal-badge.sell { background: rgba(239,68,68,0.12); color: var(--red); }
  .signal-badge.hold { background: rgba(245,158,11,0.12); color: var(--amber); }

  .signal-info { flex: 1; }
  .signal-info .symbol { font-size: 18px; font-weight: 650; }
  .signal-info .reason { font-size: 13px; color: var(--text-dim); margin-top: 4px; }

  .signal-prices {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    margin-top: 14px;
  }
  .signal-prices .price-item .plabel { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.6px; }
  .signal-prices .price-item .pval { font-size: 17px; font-weight: 550; font-family: var(--mono); margin-top: 2px; }

  /* ── Table ─────────────────────── */
  .table-wrap {
    border-radius: var(--radius);
    border: 1px solid var(--border);
    overflow: hidden;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  th {
    text-align: left;
    padding: 12px 16px;
    font-weight: 500;
    color: var(--text-dim);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    background: rgba(255,255,255,0.02);
    border-bottom: 1px solid var(--border);
  }
  td {
    padding: 12px 16px;
    border-bottom: 1px solid rgba(255,255,255,0.03);
    font-family: var(--mono);
    font-size: 13px;
  }
  tr:hover td { background: var(--surface-hover); }

  .tag {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 500;
    font-family: var(--font);
  }
  .tag.buy { background: rgba(34,197,94,0.12); color: var(--green); }
  .tag.hold { background: rgba(245,158,11,0.12); color: var(--amber); }
  .tag.sell { background: rgba(239,68,68,0.12); color: var(--red); }
  .tag.strong_buy { background: rgba(34,197,94,0.18); color: #4ade80; }

  /* ── Controls ──────────────────── */
  .controls {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    align-items: center;
  }
  input, select {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 10px 14px;
    border-radius: var(--radius-sm);
    font-family: var(--font);
    font-size: 13px;
    outline: none;
    transition: border-color 0.2s;
  }
  input:focus, select:focus { border-color: rgba(99,102,241,0.4); }
  input { width: 160px; }
  select { width: 180px; }

  .btn {
    padding: 10px 20px;
    border-radius: var(--radius-sm);
    font-family: var(--font);
    font-size: 13px;
    font-weight: 550;
    cursor: pointer;
    border: 1px solid transparent;
    transition: all 0.2s ease;
  }
  .btn-primary {
    background: var(--accent);
    color: white;
    border-color: var(--accent);
  }
  .btn-primary:hover { background: #5558e6; box-shadow: 0 0 16px var(--accent-glow); }
  .btn-secondary {
    background: var(--surface);
    color: var(--text);
    border-color: var(--border);
  }
  .btn-secondary:hover { background: var(--surface-hover); }

  /* ── Toast ─────────────────────── */
  .toast {
    position: fixed;
    bottom: 28px;
    right: 28px;
    padding: 14px 22px;
    border-radius: var(--radius-sm);
    font-size: 13px;
    font-weight: 500;
    z-index: 999;
    animation: slideIn 0.3s ease;
    backdrop-filter: blur(16px);
    border: 1px solid var(--border);
    display: none;
  }
  .toast.success { background: rgba(34,197,94,0.12); color: var(--green); display: block; }
  .toast.error { background: rgba(239,68,68,0.12); color: var(--red); display: block; }
  @keyframes slideIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

  /* ── Empty state ──────────────── */
  .empty {
    text-align: center;
    padding: 60px 20px;
    color: var(--text-dim);
  }
  .empty .icon { font-size: 40px; margin-bottom: 12px; }

  /* ── Responsive ───────────────── */
  @media (max-width: 768px) {
    .sidebar { display: none; }
    .main { padding: 20px; }
    .signal-prices { grid-template-columns: 1fr 1fr 1fr; }
  }

  /* ── Market Context Bar (sticky) ── */
  .market-bar {
    position: sticky; top: 0; z-index: 50;
    background: rgba(10,10,12,0.88); backdrop-filter: blur(20px);
    border-bottom: 1px solid var(--border);
    padding: 8px 0; margin: -32px -40px 0 -40px;
    padding-left: 40px; padding-right: 40px;
    display: flex; gap: 20px; align-items: center;
    font-size: 12px; flex-wrap: wrap;
  }
  .market-bar .idx-item { display: flex; align-items: center; gap: 6px; font-family: var(--mono); }
  .market-bar .idx-name { color: var(--text-dim); font-family: var(--font); font-size: 11px; }
  .market-bar .idx-chg.up { color: var(--green); }
  .market-bar .idx-chg.down { color: var(--red); }
  .breadth-badge {
    padding: 2px 8px; border-radius: 4px; font-size: 10px;
    font-family: var(--font); font-weight: 500;
  }
  .breadth-badge.bullish { background: rgba(34,197,94,0.15); color: var(--green); }
  .breadth-badge.bearish { background: rgba(239,68,68,0.15); color: var(--red); }
  .breadth-badge.mixed { background: rgba(245,158,11,0.15); color: var(--amber); }

  /* ── Index Dashboard Cards ─────── */
  .idx-trend-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 20px; transition: all 0.3s ease;
  }
  .idx-trend-card:hover { border-color: rgba(255,255,255,0.12); }
  .idx-trend-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
  .idx-trend-name { font-size: 16px; font-weight: 650; }
  .idx-trend-price { font-size: 20px; font-weight: 650; font-family: var(--mono); }
  .idx-trend-change { font-size: 14px; font-family: var(--mono); margin-top: 2px; }
  .idx-trend-stats {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;
    margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border);
  }

  /* ── Regime Badge ──────────────── */
  .regime-badge {
    display: inline-block; padding: 4px 12px; border-radius: 20px;
    font-size: 11px; font-weight: 550; font-family: var(--font);
  }
  .regime-badge.trending-up { background: rgba(34,197,94,0.12); color: var(--green); }
  .regime-badge.trending-down { background: rgba(239,68,68,0.12); color: var(--red); }
  .regime-badge.ranging { background: rgba(245,158,11,0.12); color: var(--amber); }
  .regime-badge.volatile { background: rgba(239,68,68,0.08); color: var(--red); }

  /* ── Scroll-to-top ─────────────── */
  .scroll-top {
    position: fixed; bottom: 28px; left: 240px;
    width: 40px; height: 40px; border-radius: 50%;
    background: var(--surface); border: 1px solid var(--border);
    color: var(--text-dim); cursor: pointer;
    display: none; align-items: center; justify-content: center;
    font-size: 18px; z-index: 40; transition: all 0.2s;
  }
  .scroll-top:hover { background: var(--surface-hover); color: var(--text); }
  .scroll-top.visible { display: flex; }

  /* ── Skeleton loading ──────────── */
  .skeleton {
    background: linear-gradient(90deg, var(--surface) 25%, var(--surface-hover) 50%, var(--surface) 75%);
    background-size: 200% 100%; animation: shimmer 1.5s infinite; border-radius: 8px;
  }
  @keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }

  /* Glossary */
  .glossary-section { margin-bottom: 32px; }
  .glossary-cat {
    font-size: 13px; font-weight: 600; color: var(--accent); text-transform: uppercase;
    letter-spacing: 0.08em; margin: 0 0 14px 0; padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }
  .glossary-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 12px; }
  .glossary-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm);
    padding: 16px 18px; transition: border-color 0.2s, background 0.2s;
  }
  .glossary-card:hover { border-color: rgba(255,255,255,0.12); background: var(--surface-hover); }
  .glossary-card.hidden { display: none; }
  .glossary-term {
    font-size: 14px; font-weight: 600; color: var(--text); margin-bottom: 8px;
    display: flex; align-items: center; gap: 8px;
  }
  .glossary-weight {
    font-size: 10px; font-weight: 500; color: var(--accent); background: var(--accent-glow);
    padding: 2px 8px; border-radius: 10px;
  }
  .glossary-def { font-size: 12px; line-height: 1.7; color: var(--text-dim); }
  .glossary-def code { background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px; font-size: 11px; }
  .glossary-def strong { color: var(--text); }
</style>
</head>
<body>

<!-- Sidebar -->
<aside class="sidebar">
  <div class="logo">
    <span class="dot"></span> Quantsys
  </div>
  <div class="nav-item active" data-page="briefing">
    <span class="icon">📋</span> 每日简报
  </div>
  <div class="nav-item" data-page="evaluate">
    <span class="icon">🔬</span> 股票评估
  </div>
  <div class="nav-item" data-page="health">
    <span class="icon">💓</span> 健康检查
  </div>
  <div class="nav-item" data-page="positions">
    <span class="icon">💼</span> 我的持仓
  </div>
  <div class="nav-item" data-page="portfolio">
    <span class="icon">🎯</span> 组合分析
  </div>
  <div class="nav-item" data-page="history">
    <span class="icon">📈</span> 信号历史
  </div>
  <div class="nav-item" data-page="review">
    <span class="icon">📝</span> 交易复盘
  </div>
  <div class="nav-item" data-page="index">
    <span class="icon">🏛️</span> 指数看板
  </div>
  <div class="nav-item" data-page="glossary">
    <span class="icon">📖</span> 术语说明
  </div>
  <div class="sidebar-footer">
    <span class="status-dot online"></span> 系统就绪
    <br><span style="opacity:0.5">v0.4 · 量化投顾</span>
  </div>
</aside>

<!-- Main Content -->
<main class="main">

  <!-- Market Context Bar -->
  <div class="market-bar" id="market-bar">
    <span style="font-size:11px;color:var(--text-dim);margin-right:4px">市场</span>
    <div id="market-indices" style="display:flex;gap:16px;align-items:center">
      <div class="skeleton" style="width:360px;height:18px"></div>
    </div>
    <span style="flex:1"></span>
    <span id="market-breadth"></span>
  </div>

  <!-- Page: Daily Brief -->
  <div class="page active" id="page-briefing">
    <div>
      <h2>每日交易简报</h2>
      <p class="subtitle">盘后评估 → 生成指令 → 次日条件单</p>
    </div>

    <div class="controls">
      <input type="date" id="briefing-date">
      <select id="briefing-mode">
        <option value="momentum">A: 周度动量轮动</option>
        <option value="mean_rev">B: 均值回归/网格</option>
        <option value="event">C: 事件驱动</option>
      </select>
      <select id="briefing-trades">
        <option value="0">本月0笔交易</option>
        <option value="1">本月1笔交易</option>
        <option value="2">本月2笔交易</option>
        <option value="3">本月3笔交易</option>
        <option value="4">本月4笔交易</option>
      </select>
      <button class="btn btn-primary" onclick="generateBriefing()">生成简报</button>
      <button class="btn btn-secondary" onclick="fillFromPositions('briefing')" title="加载持仓数据以生成卖出/止损信号">💼 使用我的持仓</button>
      <span id="briefing-pos-hint" style="font-size:11px;color:var(--accent);display:none">✓ 持仓数据已加载</span>
    </div>

    <div id="briefing-result">
      <div class="empty">
        <div class="icon">📊</div>
        <p>选择策略参数，点击"生成简报"</p>
      </div>
    </div>
  </div>

  <!-- Page: Stock Evaluation -->
  <div class="page" id="page-evaluate">
    <div>
      <h2>股票量化评估</h2>
      <p class="subtitle">动量 + 趋势 + 估值 + 流动性 + 因子 · 五维评分</p>
    </div>

    <div class="controls">
      <input type="text" id="eval-symbols" placeholder="600519, 000858, 601318" style="width:300px">
      <input type="date" id="eval-date">
      <button class="btn btn-primary" onclick="evaluateStocks()">开始评估</button>
      <button class="btn btn-secondary" onclick="fillFromPositions('evaluate')" title="加载持仓代码">💼 使用我的持仓</button>
    </div>

    <div id="eval-result">
      <div class="empty">
        <div class="icon">🔍</div>
        <p>输入股票代码，点击开始评估</p>
      </div>
    </div>
  </div>

  <!-- Page: Health Check -->
  <div class="page" id="page-health">
    <div>
      <h2>持仓健康检查</h2>
      <p class="subtitle">止损预警 · 回撤监控 · 交易频率 · 黑名单</p>
    </div>

    <div class="controls">
      <input type="text" id="health-symbol" placeholder="代码 (例如 600519)" style="width:160px">
      <input type="number" id="health-qty" placeholder="数量" style="width:100px" value="100" step="100">
      <input type="number" id="health-cost" placeholder="成本价" style="width:120px" step="0.01">
      <input type="number" id="health-cash" placeholder="现金" style="width:120px" value="0" step="100">
      <button class="btn btn-primary" onclick="checkHealth()">检查健康</button>
      <button class="btn btn-secondary" onclick="fillFromPositions('health')" title="加载全部持仓数据">💼 使用我的持仓</button>
      <span id="health-pos-count" style="display:none;font-size:11px;color:var(--accent)"></span>
    </div>

    <div id="health-result">
      <div class="empty">
        <div class="icon">💓</div>
        <p>输入当前持仓信息，点击检查健康</p>
      </div>
    </div>
  </div>

  <!-- Page: My Positions -->
  <div class="page" id="page-positions">
    <div>
      <h2>我的持仓</h2>
      <p class="subtitle">股票 · ETF · 基金 · 一键刷新每日盈亏</p>
    </div>

    <div class="controls" style="justify-content:space-between">
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        <button class="btn btn-primary" onclick="refreshPositions()">🔄 刷新盈亏</button>
        <button class="btn btn-secondary" onclick="showAddForm()">＋ 添加持仓</button>
      </div>
      <span id="positions-time" style="font-size:11px;color:var(--text-dim)"></span>
    </div>

    <!-- Add position form (hidden by default) -->
    <div id="add-form" class="card wide" style="display:none">
      <div class="label">添加新持仓</div>
      <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin-top:12px">
        <div>
          <div style="font-size:11px;color:var(--text-dim);margin-bottom:4px">类型</div>
          <select id="add-type" style="width:80px;padding:9px 8px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:13px">
            <option value="auto">自动</option>
            <option value="stock">股票</option>
            <option value="etf">ETF</option>
            <option value="fund">基金</option>
          </select>
        </div>
        <div>
          <div style="font-size:11px;color:var(--text-dim);margin-bottom:4px">代码</div>
          <input type="text" id="add-symbol" placeholder="600519 / 512710 / 017103" style="width:140px">
        </div>
        <div>
          <div style="font-size:11px;color:var(--text-dim);margin-bottom:4px">名称</div>
          <input type="text" id="add-name" placeholder="贵州茅台" style="width:160px">
        </div>
        <div>
          <div style="font-size:11px;color:var(--text-dim);margin-bottom:4px">数量</div>
          <input type="number" id="add-qty" placeholder="股数/份数" style="width:100px" step="any">
        </div>
        <div>
          <div style="font-size:11px;color:var(--text-dim);margin-bottom:4px">成本</div>
          <input type="number" id="add-cost" placeholder="均价" style="width:110px" step="0.001">
        </div>
        <button class="btn btn-primary" onclick="addPosition()">添加</button>
        <button class="btn btn-secondary" onclick="hideAddForm()">取消</button>
      </div>
      <div style="font-size:11px;color:var(--text-dim);margin-top:8px">
        自动识别: 60xxxx=上海股 | 00xxxx/30xxxx/68xxxx=深圳股 | 51xxxx/159xxx=ETF | 其余6位=基金
      </div>
    </div>

    <!-- Positions summary -->
    <div id="positions-summary" style="display:none">
      <div class="card-grid" id="positions-cards"></div>
    </div>

    <!-- Positions list -->
    <div id="positions-list">
      <div class="empty">
        <div class="icon">💼</div>
        <p>暂无持仓</p>
        <p style="font-size:11px;margin-top:8px">点击"添加持仓"追踪股票、ETF或基金，然后刷新获取每日盈亏和建议</p>
      </div>
    </div>
  </div>

  <!-- Page: Portfolio -->
  <div class="page" id="page-portfolio">
    <div>
      <h2>组合评估</h2>
      <p class="subtitle">风险分解 · 相关性矩阵 · 有效前沿 · 归因分析</p>
    </div>

    <div class="controls">
      <input type="text" id="pf-symbols" placeholder="代码 (逗号分隔, 例如 600519,000858)" style="width:350px">
      <input type="text" id="pf-qty" placeholder="数量 (逗号分隔, 例如 100,100)" style="width:250px">
      <input type="text" id="pf-cost" placeholder="成本 (逗号分隔, 例如 1700,160)" style="width:250px">
      <input type="number" id="pf-cash" placeholder="现金" style="width:140px" value="0" step="100">
      <input type="date" id="pf-date">
      <button class="btn btn-primary" onclick="evaluatePortfolio()">评估组合</button>
      <button class="btn btn-secondary" onclick="fillFromPositions('portfolio')" title="加载持仓数据">💼 使用我的持仓</button>
    </div>

    <div id="pf-result">
      <div class="empty">
        <div class="icon">🎯</div>
        <p>输入持仓详情，点击评估组合</p>
        <p style="font-size:11px;margin-top:8px">支持批量评估：风险分解、相关性矩阵、有效前沿、权重优化</p>
      </div>
    </div>
  </div>

  <!-- Page: Index Board -->
  <div class="page" id="page-index">
    <div>
      <h2>指数看板</h2>
      <p class="subtitle">五大指数 · 市场状态检测 · 趋势信号</p>
    </div>

    <div class="controls">
      <input type="date" id="index-date">
      <button class="btn btn-primary" onclick="loadIndexDashboard()">刷新</button>
    </div>

    <div class="card wide" id="index-summary" style="border-color:rgba(99,102,241,0.2);background:rgba(99,102,241,0.04)">
      <div class="skeleton" style="width:100%;height:60px"></div>
    </div>

    <div class="card-grid" id="index-cards">
      <div class="skeleton" style="height:160px"></div>
      <div class="skeleton" style="height:160px"></div>
      <div class="skeleton" style="height:160px"></div>
      <div class="skeleton" style="height:160px"></div>
      <div class="skeleton" style="height:160px"></div>
    </div>

    <div class="card-grid" id="index-regime">
      <div class="card">
        <div class="label">市场宽度</div>
        <div id="breadth-detail"></div>
      </div>
      <div class="card">
        <div class="label">主导状态</div>
        <div id="regime-detail"></div>
      </div>
      <div class="card">
        <div class="label">波动率环境</div>
        <div id="vol-regime"></div>
      </div>
      <div class="card">
        <div class="label">指数信号</div>
        <div id="index-signals"></div>
      </div>
    </div>

    <div class="card wide">
      <div class="label">52周位置 · 温度计</div>
      <div id="position-bars" style="display:flex;flex-direction:column;gap:12px;margin-top:12px"></div>
    </div>

    <div id="returns-table"></div>
  </div>

  <!-- Page: Glossary -->
  <div class="page" id="page-glossary">
    <div>
      <h2>术语说明</h2>
      <p class="subtitle">量化评估与组合分析中的关键概念解释</p>
    </div>

    <div class="controls" style="margin-bottom:20px">
      <input type="text" id="glossary-search" placeholder="搜索概念..." style="width:320px" oninput="filterGlossary()">
    </div>

    <div id="glossary-content">

      <!-- Scoring -->
      <div class="glossary-section">
        <h3 class="glossary-cat">股票评分体系</h3>
        <div class="glossary-grid">

          <div class="glossary-card" data-keywords="momentum score return">
            <div class="glossary-term">动量得分 <span class="glossary-weight">25%</span></div>
            <div class="glossary-def">
              衡量最近多时间周期的价格表现（5日、10日、20日、60日）。
              近期收益强劲的股票得分更高。基于与全市场股票的横截面百分位排名
              —— 处于20日收益第90百分位的股票将获得高动量得分。
            </div>
          </div>

          <div class="glossary-card" data-keywords="trend score moving average ma">
            <div class="glossary-term">趋势得分 <span class="glossary-weight">25%</span></div>
            <div class="glossary-def">
              评估短、中、长期均线（MA5/MA10/MA20/MA60/MA120）的排列对齐情况。
              多头排列（短期均线在长期均线之上）得分更高。同时考虑价格与关键均线的位置关系
              以及20日均线的斜率方向。
            </div>
          </div>

          <div class="glossary-card" data-keywords="valuation pe pb dividend yield cheap expensive">
            <div class="glossary-term">估值得分 <span class="glossary-weight">20%</span></div>
            <div class="glossary-def">
              使用市盈率（PE）、市净率（PB）和股息率评估股票的贵贱程度。
              与市场整体相比，较低的PE/PB和较高的股息率产生更高的估值得分。
              也可能包含行业相对比较。
            </div>
          </div>

          <div class="glossary-card" data-keywords="liquidity volume turnover trading">
            <div class="glossary-term">流动性得分 <span class="glossary-weight">15%</span></div>
            <div class="glossary-def">
              通过换手率、量比（当前成交量 vs. 20日均量）和买卖价差指标衡量交易活跃度。
              高流动性可降低滑点和执行成本，有助于进出仓位。
            </div>
          </div>

          <div class="glossary-card" data-keywords="factor composite multi-factor quality growth">
            <div class="glossary-term">因子复合 <span class="glossary-weight">15%</span></div>
            <div class="glossary-def">
              汇总多个风格因子，包括质量（ROE、盈利稳定性）、成长（营收/盈利增长率）
              和波动率（低波动优先）。每个子因子进行百分位排名，加权平均后得出最终复合得分。
            </div>
          </div>

        </div>
      </div>

      <!-- Risk Metrics -->
      <div class="glossary-section">
        <h3 class="glossary-cat">风险与收益指标</h3>
        <div class="glossary-grid">

          <div class="glossary-card" data-keywords="sharpe ratio risk-adjusted return">
            <div class="glossary-term">夏普比率 (Sharpe Ratio)</div>
            <div class="glossary-def">
              风险调整收益指标：<code>(组合收益 - 无风险利率) / 组合波动率</code>。
              衡量每单位总风险所带来的超额收益。夏普比率高于1.0为良好，高于2.0为优秀。
              负值表示组合表现不及无风险利率。
            </div>
          </div>

          <div class="glossary-card" data-keywords="sortino ratio downside risk">
            <div class="glossary-term">索提诺比率 (Sortino Ratio)</div>
            <div class="glossary-def">
              与夏普比率类似，但仅惩罚下行波动率（负收益）。
              <code>(组合收益 - 无风险利率) / 下行标准差</code>。
              更适合不在意上行波动的投资者。索提诺比率越高，说明在聚焦避险的情况下，
              风险调整后收益越好。
            </div>
          </div>

          <div class="glossary-card" data-keywords="calmar ratio max drawdown return">
            <div class="glossary-term">卡尔玛比率 (Calmar Ratio)</div>
            <div class="glossary-def">
              <code>年化收益 / 最大回撤</code>（取绝对值）。
              衡量收益与最差峰谷跌幅之间的关系。卡尔玛比率越高，说明策略能在产生
              强劲收益的同时避免严重回撤。高于1.0为理想水平。
            </div>
          </div>

          <div class="glossary-card" data-keywords="volatility standard deviation annualized risk">
            <div class="glossary-term">年化波动率</div>
            <div class="glossary-def">
              日收益率标准差乘以√252换算为年化值，以百分比表示。A股市场20-30%属正常，
              低于15%为低波动，高于40%为极端波动。代表年度收益波动的预期范围。
            </div>
          </div>

          <div class="glossary-card" data-keywords="max drawdown mdd peak trough worst loss">
            <div class="glossary-term">最大回撤 (MDD)</div>
            <div class="glossary-def">
              评估期内组合价值从峰值到谷底的最大跌幅。20%的MDD意味着组合从最高点
              损失了20%后才恢复。对评估最坏情况和心理承受能力至关重要。
            </div>
          </div>

          <div class="glossary-card" data-keywords="var value at risk tail loss percentile">
            <div class="glossary-term">VaR (风险价值)</div>
            <div class="glossary-def">
              在给定置信水平下特定时间范围内的最大预期损失。95%的1日VaR为-2%
              意味着单日亏损超过2%的概率仅为5%。常用置信水平：95%和99%。
              使用历史模拟法或参数法计算。
            </div>
          </div>

          <div class="glossary-card" data-keywords="cvar conditional var expected shortfall tail">
            <div class="glossary-term">CVaR (条件风险价值)</div>
            <div class="glossary-def">
              也称预期亏损（Expected Shortfall），即<em>超过</em>VaR阈值部分的平均亏损。
              如果95%VaR是-2%，CVaR回答的是："当情况真的非常糟糕时（最差的5%交易日），
              平均亏损是多少？"始终比VaR更严重，为监管机构所偏好。
            </div>
          </div>

          <div class="glossary-card" data-keywords="excess return benchmark relative outperformance">
            <div class="glossary-term">超额收益</div>
            <div class="glossary-def">
              <code>组合收益 - 基准收益</code>（如相对沪深300）。
              正的超额收益表示组合跑赢了基准。可年化处理用于多期评估。
              是计算Alpha的基础。
            </div>
          </div>

        </div>
      </div>

      <!-- Portfolio Theory -->
      <div class="glossary-section">
        <h3 class="glossary-cat">组合理论与优化</h3>
        <div class="glossary-grid">

          <div class="glossary-card" data-keywords="beta market sensitivity systematic risk correlation">
            <div class="glossary-term">Beta (β) 贝塔系数</div>
            <div class="glossary-def">
              衡量组合对市场波动的敏感度。β=1表示与市场同步波动。β>1表示比市场波动更大（进攻型），
              β<1表示比市场波动更小（防御型）。β=1.5意味着市场波动1%时，组合预期同向波动1.5%。
            </div>
          </div>

          <div class="glossary-card" data-keywords="alpha jensen excess risk-adjusted outperformance skill">
            <div class="glossary-term">Alpha (α) 阿尔法</div>
            <div class="glossary-def">
              不能被Beta解释的超额收益部分，代表管理人或策略的超额能力。正Alpha意味着组合
              在风险调整后跑赢了市场。计算公式：
              <code>α = 组合收益 - [无风险利率 + β × (市场收益 - 无风险利率)]</code>。
            </div>
          </div>

          <div class="glossary-card" data-keywords="tracking error deviation benchmark relative active">
            <div class="glossary-term">跟踪误差</div>
            <div class="glossary-def">
              超额收益（组合收益-基准收益）的标准差。衡量组合与基准的贴合程度。
              低跟踪误差（<3%）意味着被动/准指数策略；高跟踪误差（>10%）
              表示主动管理与基准偏离显著。
            </div>
          </div>

          <div class="glossary-card" data-keywords="information ratio ir active return consistency">
            <div class="glossary-term">信息比率 (IR)</div>
            <div class="glossary-def">
              <code>超额收益 / 跟踪误差</code>。衡量相对于基准的超额收益的稳定性。
              IR高于0.5通常被认为是好的，高于1.0为优秀。它回答的问题是：
              "Alpha是持续性的，还是仅靠运气？"
            </div>
          </div>

          <div class="glossary-card" data-keywords="efficient frontier markowitz optimization optimal portfolio">
            <div class="glossary-term">有效前沿</div>
            <div class="glossary-def">
              在每一风险水平下提供最高预期收益（或在每一收益水平下提供最低风险）的组合集合。
              基于马科维茨现代组合理论。位于前沿下方的组合是次优的。系统使用蒙特卡洛模拟
              逼近有效前沿并寻找最大夏普比率（切线）组合。
            </div>
          </div>

          <div class="glossary-card" data-keywords="hhi herfindahl concentration diversification">
            <div class="glossary-term">HHI (赫芬达尔指数)</div>
            <div class="glossary-def">
              衡量持仓集中度：<code>HHI = Σ(权重_i)²</code>。范围从接近0（完全等权重）
              到10,000（100%集中在一个持仓）。HHI低于1,000表示分散良好；
              高于2,500意味着集中风险较高。
            </div>
          </div>

          <div class="glossary-card" data-keywords="correlation matrix diversification benefit">
            <div class="glossary-term">相关性矩阵</div>
            <div class="glossary-def">
              展示组合中各持仓两两之间的收益相关性。范围从-1（完全相反）到+1（完全同步）。
              资产之间的低相关性或负相关性可提升分散效果。无论持仓数量多少，
              相关性普遍较高（均>0.8）的组合几乎没有分散化效益。
            </div>
          </div>

          <div class="glossary-card" data-keywords="risk-free rate rfr treasury yield benchmark">
            <div class="glossary-term">无风险利率 (RFR)</div>
            <div class="glossary-def">
              理论上零风险投资的收益率。实践中使用中国10年期国债收益率
              或1年期存款利率（约1.5-3%）。作为夏普比率、Alpha等风险调整指标的计算基准。
            </div>
          </div>

        </div>
      </div>

      <!-- Market Analysis -->
      <div class="glossary-section">
        <h3 class="glossary-cat">市场分析与状态识别</h3>
        <div class="glossary-grid">

          <div class="glossary-card" data-keywords="market breadth broad up down mixed indices">
            <div class="glossary-term">市场宽度</div>
            <div class="glossary-def">
              衡量主要指数中处于上升趋势与下降趋势的比例。"普涨"表示60%以上指数
              呈多头趋势。"普跌"表示60%以上呈空头趋势。"分化"表示涨跌互现。
              高宽度确认强势行情；低宽度警示潜在反转或板块轮动。
            </div>
          </div>

          <div class="glossary-card" data-keywords="regime trending up down ranging volatile market state">
            <div class="glossary-term">市场状态</div>
            <div class="glossary-def">
              将当前市场环境分为4种状态：
              <strong>上升趋势</strong>——价格在均线上方，强势正动量，适合趋势跟踪；
              <strong>下降趋势</strong>——价格在均线下方，负动量，建议防御性配置；
              <strong>区间震荡</strong>——价格围绕均线波动，方向性偏弱，适合网格/均值回归；
              <strong>波动加剧</strong>——高波动率（年化>30%），振幅大，假突破风险较高。
            </div>
          </div>

          <div class="glossary-card" data-keywords="52 week position percentile range high low">
            <div class="glossary-term">52周位置</div>
            <div class="glossary-def">
              当前价格在52周区间内的位置：<code>(价格 - 52周低点) / (52周高点 - 52周低点) × 100</code>。
              90表示指数接近年内高点；10表示接近年内低点。有助于判断市场是过热
              还是存在潜在买入机会。
            </div>
          </div>

          <div class="glossary-card" data-keywords="volume ratio trading activity surge">
            <div class="glossary-term">量比</div>
            <div class="glossary-def">
              <code>当日成交量 / 20日均量</code>。大于1.5表示交易异常活跃（潜在突破或恐慌）。
              低于0.5表示交投清淡。成交量确认可为价格变动增加可靠性。
            </div>
          </div>

          <div class="glossary-card" data-keywords="moving average ma golden cross dead cross signal">
            <div class="glossary-term">均线信号</div>
            <div class="glossary-def">
              <strong>金叉</strong>——短期均线（如MA20）上穿长期均线（如MA60），看涨信号。
              <strong>死叉</strong>——短期均线下穿长期均线，看跌信号。
              <strong>均线排列</strong>——当均线有序排列（短在上长在下=多头，短在下长在上=空头），
              确认趋势强度。系统跟踪MA5/10/20/60/120。
            </div>
          </div>

          <div class="glossary-card" data-keywords="style rotation large cap small cap growth value divergence">
            <div class="glossary-term">风格轮动</div>
            <div class="glossary-def">
              市场在大盘（沪深300）与小盘（中证500）之间，或成长（创业板、科创50）与价值之间
              的偏好切换。通过比较指数趋势来识别。"大盘占优"表示沪深300更强；
              "成长偏好"表示创业板/科创板表现更佳。理解风格轮动有助于板块和因子配置决策。
            </div>
          </div>

        </div>
      </div>

      <!-- ETF & Data -->
      <div class="glossary-section">
        <h3 class="glossary-cat">ETF评分与数据</h3>
        <div class="glossary-grid">

          <div class="glossary-card" data-keywords="etf nav fund scoring fallback">
            <div class="glossary-term">ETF净值评分</div>
            <div class="glossary-def">
              当标的实际为ETF（无stock_daily OHLCV数据）时，系统回退到使用缓存的净值（NAV）数据
              进行评分。ETF评分使用净值趋势（基金NAV的均线排列）、近期收益动量和
              相对市场价格的折溢价分析。这使得ETF即使没有传统股票因子数据也能获得有意义的评分。
            </div>
          </div>

          <div class="glossary-card" data-keywords="nav net asset value cache parquet stale refresh">
            <div class="glossary-term">净值缓存</div>
            <div class="glossary-def">
              ETF净值数据从AKShare（fund_etf_fund_info_em）获取并以Parquet文件缓存到本地。
              缓存过期检查使用2天阈值——如果最近缓存日期在2天内，直接使用缓存数据（亚秒级加载）。
              否则获取新数据。这样在首次获取后刷新时间保持在约0.1秒。
            </div>
          </div>

          <div class="glossary-card" data-keywords="cross-sectional percentile ranking z-score normalization">
            <div class="glossary-term">横截面排名</div>
            <div class="glossary-def">
              大多数评分使用当前股票池内的百分位排名而非绝对阈值。将股票的原始指标（如PE）
              与同日所有其他股票值比较，转换为0-100的百分位。这自动适应市场整体估值变化，
              确保评分分布在不同的市场环境中保持稳定。
            </div>
          </div>

          <div class="glossary-card" data-keywords="ohlcv open high low close volume data cache">
            <div class="glossary-term">OHLCV数据</div>
            <div class="glossary-def">
              开盘价、最高价、最低价、收盘价、成交量——标准日线数据。按标的缓存于
              <code>data/raw/stock_daily/</code>（股票）和<code>data/raw/index_daily/</code>（指数）。
              数据源自AKShare并通过每日数据管道更新。所有技术指标（均线、波动率、收益率、因子）
              均由此衍生计算。
            </div>
          </div>

        </div>
      </div>

    </div>
  </div>

  <!-- Page: Signal History -->
  <div class="page" id="page-review">
    <div>
      <h2>交易复盘</h2>
      <p class="subtitle">交易日志记录、日/周报告生成与AI复盘分析</p>
    </div>

    <!-- Report Generation -->
    <div class="card-grid">
      <div class="card">
        <div class="label">日报生成</div>
        <input type="date" id="review-date" style="margin:10px 0;padding:8px 12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text);width:100%">
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary" onclick="generateDailyReview()" style="flex:1">📋 生成日报</button>
        </div>
        <div class="subtitle" id="daily-report-link" style="margin-top:8px"></div>
      </div>
      <div class="card">
        <div class="label">周报生成</div>
        <input type="date" id="review-week-end" style="margin:10px 0;padding:8px 12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text);width:100%">
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary" onclick="generateWeeklyReview()" style="flex:1">📊 生成周报</button>
        </div>
        <div class="subtitle" id="weekly-report-link" style="margin-top:8px"></div>
      </div>
    </div>

    <!-- Trade Log Form -->
    <div class="card">
      <div class="label" style="font-size:16px;font-weight:600;margin-bottom:12px">📝 记录交易</div>
      <div style="display:flex;gap:10px;align-items:center;margin-bottom:12px">
        <span class="subtitle" style="white-space:nowrap">快速选择持仓:</span>
        <select id="trade-quick-select" onchange="onQuickTradeSelect()" style="flex:1;padding:8px 12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text)">
          <option value="">-- 选择持仓 --</option>
        </select>
        <button class="btn btn-secondary" onclick="populateTradeQuickSelect()" style="white-space:nowrap" title="刷新持仓列表">🔄</button>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr;gap:10px;align-items:end">
        <div>
          <div class="subtitle">代码</div>
          <input id="trade-symbol" placeholder="000001" style="width:100%;padding:8px 12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text)">
        </div>
        <div>
          <div class="subtitle">名称(可选)</div>
          <input id="trade-name" placeholder="平安银行" style="width:100%;padding:8px 12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text)">
        </div>
        <div>
          <div class="subtitle">方向</div>
          <select id="trade-direction" style="width:100%;padding:8px 12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text)">
            <option value="BUY">买入</option>
            <option value="SELL">卖出</option>
          </select>
        </div>
        <div>
          <div class="subtitle">价格</div>
          <input id="trade-price" type="number" step="0.01" placeholder="12.50" style="width:100%;padding:8px 12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text)">
        </div>
        <div>
          <div class="subtitle">数量(股)</div>
          <input id="trade-qty" type="number" placeholder="1000" style="width:100%;padding:8px 12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text)">
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px">
        <div>
          <div class="subtitle">策略</div>
          <input id="trade-strategy" placeholder="趋势跟踪" style="width:100%;padding:8px 12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text)">
        </div>
        <div>
          <div class="subtitle">理由</div>
          <input id="trade-reason" placeholder="突破买入信号" style="width:100%;padding:8px 12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text)">
        </div>
      </div>
      <button class="btn btn-secondary" onclick="logTrade()" style="margin-top:12px">记录交易</button>
    </div>

    <!-- Recent Trades -->
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <div class="label" style="font-size:16px;font-weight:600">📋 最近交易记录</div>
        <button class="btn btn-secondary" onclick="loadTradeHistory()">刷新</button>
      </div>
      <div id="trade-history-table">
        <div class="empty"><div class="icon">📭</div><p>暂无交易记录</p></div>
      </div>
    </div>
  </div>

  <div class="page" id="page-history">
    <div>
      <h2>信号历史</h2>
      <p class="subtitle">最近生成的交易信号</p>
    </div>

    <div class="controls">
      <select id="history-strategy">
        <option value="">全部策略</option>
        <option value="momentum">动量轮动</option>
        <option value="mean_rev">均值回归</option>
        <option value="event">事件驱动</option>
      </select>
      <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;white-space:nowrap">
        <input type="checkbox" id="history-positions-only" onchange="loadHistory()">
        仅显示持仓相关
      </label>
      <button class="btn btn-secondary" onclick="loadHistory()">刷新</button>
    </div>

    <div id="history-result">
      <div class="empty">
        <div class="icon">📈</div>
        <p>暂无信号记录，请先生成简报。</p>
      </div>
    </div>
  </div>

</main>

<!-- Toast -->
<div class="toast" id="toast"></div>
<!-- Scroll-to-top -->
<div class="scroll-top" id="scroll-top" onclick="document.querySelector('.main').scrollTo({top:0,behavior:'smooth'})">↑</div>

<script>
// ── Navigation ──────────────────────
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    item.classList.add('active');
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById('page-' + item.dataset.page).classList.add('active');
  });
});

// ── Init dates ─────────────────────
const today = new Date().toISOString().split('T')[0];
document.getElementById('briefing-date').value = today;
document.getElementById('eval-date').value = today;
document.getElementById('pf-date').value = today;

// ── Shared: Position data cache ────
let _cachedPositions = null;
let _positionsLastFetch = 0;
const POSITIONS_CACHE_TTL = 30000;

async function getMyPositions(forceRefresh = false) {
  const now = Date.now();
  if (_cachedPositions && !forceRefresh && (now - _positionsLastFetch) < POSITIONS_CACHE_TTL) {
    return _cachedPositions;
  }
  try {
    const resp = await fetch('/api/positions/data');
    const data = await resp.json();
    _cachedPositions = data.positions || [];
    _positionsLastFetch = now;
    return _cachedPositions;
  } catch (e) {
    return [];
  }
}

async function fillFromPositions(targetId) {
  const positions = await getMyPositions(true);
  if (positions.length === 0) {
    showToast('暂无持仓数据，请先在"我的持仓"中添加', 'error');
    return false;
  }

  if (targetId === 'health') {
    // Leave form fields empty so checkHealth() uses multi-position mode
    document.getElementById('health-symbol').value = '';
    document.getElementById('health-qty').value = '';
    document.getElementById('health-cost').value = '';
    document.getElementById('health-pos-count').textContent = `已加载 ${positions.length} 个持仓`;
    document.getElementById('health-pos-count').style.display = 'inline';
    showToast(`已加载 ${positions.length} 个持仓到健康检查`, 'success');
  } else if (targetId === 'portfolio') {
    document.getElementById('pf-symbols').value = positions.map(p => p.symbol).join(',');
    document.getElementById('pf-qty').value = positions.map(p => Math.round(p.quantity)).join(',');
    document.getElementById('pf-cost').value = positions.map(p => p.avg_cost.toFixed(3)).join(',');
    showToast(`已加载 ${positions.length} 个持仓到组合分析`, 'success');
  } else if (targetId === 'evaluate') {
    document.getElementById('eval-symbols').value = positions.map(p => p.symbol).join(',');
    showToast(`已加载 ${positions.length} 个持仓到评估`, 'success');
  } else if (targetId === 'briefing') {
    showToast(`已加载 ${positions.length} 个持仓，生成时将包含持仓信号`, 'success');
  }
  return true;
}

// ── Toast ──────────────────────────
let _toastTimer = null;
function showToast(msg, type) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast ' + type;
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { t.className = 'toast'; }, 3000);
}

// ── Briefing ───────────────────────
async function generateBriefing() {
  const date = document.getElementById('briefing-date').value;
  const mode = document.getElementById('briefing-mode').value;
  const trades = document.getElementById('briefing-trades').value;
  const div = document.getElementById('briefing-result');

  div.innerHTML = '<div class="empty"><div class="icon">⏳</div><p>计算中...</p></div>';

  try {
    // Auto-load positions for context-aware signals
    const positions = await getMyPositions();
    let url = `/api/briefing?date=${date}&mode=${mode}&trades=${trades}`;
    if (positions.length > 0) {
      const p = positions[0];
      url += `&pos_symbol=${encodeURIComponent(p.symbol)}&pos_qty=${p.quantity}&pos_cost=${p.avg_cost}`;
      const hint = document.getElementById('briefing-pos-hint');
      if (hint) hint.style.display = 'inline';
    }
    const resp = await fetch(url);
    const data = await resp.json();

    if (data.error) {
      div.innerHTML = `<div class="empty"><div class="icon">⚠️</div><p>${data.error}</p></div>`;
      return;
    }

    let html = '';

    // Summary cards
    html += `<div class="card-grid">
      <div class="card">
        <div class="label">账户状态</div>
        <div class="value">${data.account_status || '空仓'}</div>
      </div>
      <div class="card">
        <div class="label">风险等级</div>
        <div class="value" style="color:${data.risk_level==='critical'?'var(--red)':data.risk_level==='warning'?'var(--amber)':'var(--green)'}">${(data.risk_level||'normal').toUpperCase()}</div>
      </div>
      <div class="card">
        <div class="label">剩余交易次数</div>
        <div class="value">${4 - (data.monthly_trades_used||0)} / 4</div>
      </div>
    </div>`;

    // Warnings
    if (data.risk_warnings && data.risk_warnings.length) {
      html += '<div class="card wide" style="border-color:rgba(245,158,11,0.3);background:rgba(245,158,11,0.04)">';
      html += data.risk_warnings.map(w => `<span style="color:var(--amber);font-size:13px">⚠️ ${w}</span>`).join('<br>');
      html += '</div>';
    }

    // Signals
    if (data.signals && data.signals.length) {
      for (const s of data.signals) {
        const isBuy = s.action === 'buy';
        const badgeClass = isBuy ? 'buy' : (s.action === 'sell' ? 'sell' : 'hold');
        const badgeText = isBuy ? '买入' : (s.action === 'sell' ? '卖出' : '持有');
        html += `<div class="signal-card">
          <div class="signal-badge ${badgeClass}">${badgeText}</div>
          <div class="signal-info">
            <div class="symbol">${s.symbol} <span style="font-size:12px;color:var(--text-dim);font-weight:400">${s.strategy || ''}</span></div>
            <div class="reason">${s.reason || ''}</div>
            <div class="signal-prices">
              <div class="price-item"><div class="plabel">触发价</div><div class="pval">¥${(s.trigger_price||0).toFixed(2)}</div></div>
              <div class="price-item"><div class="plabel">限价</div><div class="pval">¥${(s.limit_price||0).toFixed(2)}</div></div>
              <div class="price-item"><div class="plabel">数量</div><div class="pval">${s.quantity||0} 股</div></div>
              <div class="price-item"><div class="plabel">止损</div><div class="pval" style="color:var(--red)">¥${(s.stop_loss||0).toFixed(2)}</div></div>
              <div class="price-item"><div class="plabel">止盈</div><div class="pval" style="color:var(--green)">¥${(s.take_profit||0).toFixed(2)}</div></div>
              <div class="price-item"><div class="plabel">置信度</div><div class="pval">${((s.confidence||0)*100).toFixed(0)}%</div></div>
            </div>
          </div>
        </div>`;
      }
    } else {
      html += '<div class="empty"><div class="icon">✅</div><p>今日无交易信号</p></div>';
    }

    // Todo
    if (data.todo && data.todo.length) {
      html += '<div class="card wide"><div class="label">待办事项</div>';
      html += data.todo.map(t => `<div style="font-size:13px;padding:4px 0">→ ${t}</div>`).join('');
      html += '</div>';
    }

    // Condition orders
    if (data.condition_orders && data.condition_orders.length) {
      html += '<div class="card wide"><div class="label">📱 条件单</div>';
      html += data.condition_orders.map(o =>
        `<div style="font-size:12px;padding:6px 0;border-bottom:1px solid var(--border);color:var(--text-dim)">
          <span style="color:var(--text)">${o.type}</span> · ${o.symbol} ${o.side} → ${o.trigger}
        </div>`
      ).join('');
      html += '</div>';
    }

    div.innerHTML = html;
    showToast('简报已生成', 'success');

  } catch (e) {
    div.innerHTML = `<div class="empty"><div class="icon">❌</div><p>请求失败: ${escHtml(e.message)}</p></div>`;
    showToast('请求失败，请检查后端', 'error');
  }
}

// ── Evaluate ───────────────────────
async function evaluateStocks() {
  let symbols = document.getElementById('eval-symbols').value.trim();
  const date = document.getElementById('eval-date').value;
  const div = document.getElementById('eval-result');

  // Auto-load positions if no manual input
  if (!symbols) {
    const positions = await getMyPositions();
    if (positions.length === 0) {
      showToast('请先输入股票代码，或在"我的持仓"中添加数据', 'error');
      return;
    }
    symbols = positions.map(p => p.symbol).join(',');
    document.getElementById('eval-symbols').value = symbols;
  }

  div.innerHTML = '<div class="empty"><div class="icon">⏳</div><p>评估中...</p></div>';

  try {
    const resp = await fetch(`/api/evaluate?symbols=${encodeURIComponent(symbols)}&date=${date}`);
    const data = await resp.json();

    if (!data.results || !data.results.length) {
      div.innerHTML = '<div class="empty"><div class="icon">⚠️</div><p>无有效评估结果</p></div>';
      return;
    }

    let html = '<div class="table-wrap"><table><thead><tr>';
    html += '<th>代码</th><th>评分</th><th>操作</th><th>动量</th><th>趋势</th><th>估值</th><th>流动性</th><th>因子</th><th>风险</th>';
    html += '</tr></thead><tbody>';

    for (const r of data.results) {
      const tagClass = r.action && r.action.includes('buy') ? 'buy' : (r.action && r.action.includes('sell') ? 'sell' : 'hold');
      html += `<tr>
        <td style="font-weight:600">${r.symbol}</td>
        <td style="font-weight:650;font-size:15px">${(r.total_score||0).toFixed(0)}</td>
        <td><span class="tag ${tagClass}">${r.action || '-'}</span></td>
        <td>${(r.momentum_score||0).toFixed(0)}</td>
        <td>${(r.trend_score||0).toFixed(0)}</td>
        <td>${(r.valuation_score||0).toFixed(0)}</td>
        <td>${(r.liquidity_score||0).toFixed(0)}</td>
        <td>${(r.factor_score||0).toFixed(0)}</td>
        <td style="font-size:11px;color:var(--text-dim)">${(r.risk_flags||[]).join(', ') || 'None'}</td>
      </tr>`;
    }
    html += '</tbody></table></div>';

    // Detail cards
    for (const r of data.results.slice(0, 3)) {
      if (r.reasons && r.reasons.length) {
        html += `<div class="card" style="margin-top:12px">
          <div style="font-weight:600;margin-bottom:6px">${r.symbol} · Evaluation Details</div>
          <div style="font-size:12px;color:var(--text-dim)">${r.reasons.join('  ·  ')}</div>
        </div>`;
      }
    }

    div.innerHTML = html;
    showToast(`评估完成: ${data.results.length} 只股票`, 'success');

  } catch (e) {
    div.innerHTML = `<div class="empty"><div class="icon">❌</div><p>${escHtml(e.message)}</p></div>`;
  }
}

// ── Health Check ───────────────────
async function checkHealth() {
  let symbol = document.getElementById('health-symbol').value.trim();
  const qty = document.getElementById('health-qty').value;
  const cost = document.getElementById('health-cost').value;
  const cash = document.getElementById('health-cash').value;
  const div = document.getElementById('health-result');

  // Auto-load all positions if no manual symbol entered
  let positionsParam = '';
  if (!symbol) {
    const positions = await getMyPositions();
    if (positions.length === 0) {
      showToast('请先输入持仓代码，或在"我的持仓"中添加数据', 'error');
      return;
    }
    positionsParam = positions.map(p => `${p.symbol},${p.quantity},${p.avg_cost}`).join('|');
    symbol = positions[0].symbol;
  }

  div.innerHTML = '<div class="empty"><div class="icon">⏳</div><p>检查中...</p></div>';

  try {
    let url = `/api/health?symbol=${symbol}&qty=${qty}&cost=${cost}&cash=${cash}`;
    if (positionsParam) url += `&positions=${encodeURIComponent(positionsParam)}`;
    const resp = await fetch(url);
    const data = await resp.json();

    const color = data.overall_health === 'healthy' ? 'var(--green)' :
                  data.overall_health === 'critical' ? 'var(--red)' : 'var(--amber)';

    let html = `<div class="card-grid">
      <div class="card">
        <div class="label">健康状态</div>
        <div class="value" style="color:${color}">${(data.overall_health||'unknown').toUpperCase()}</div>
      </div>
      <div class="card">
        <div class="label">总资产</div>
        <div class="value">¥${(data.total_value||0).toLocaleString()}</div>
      </div>
      <div class="card">
        <div class="label">当前回撤</div>
        <div class="value" style="color:${(data.current_drawdown||0)<-0.05?'var(--red)':'var(--text)'}">${((data.current_drawdown||0)*100).toFixed(1)}%</div>
      </div>
      <div class="card">
        <div class="label">剩余交易次数</div>
        <div class="value">${data.trades_remaining||0}</div>
      </div>
    </div>`;

    if (data.positions && data.positions.length) {
      html += '<div class="table-wrap"><table><thead><tr><th>代码</th><th>数量</th><th>成本</th><th>现价</th><th>市值</th><th>盈亏</th><th>接近止损</th></tr></thead><tbody>';
      for (const p of data.positions) {
        const pnlColor = (p.pnl_pct||0) >= 0 ? 'var(--green)' : 'var(--red)';
        html += `<tr>
          <td style="font-weight:600">${p.symbol}</td>
          <td>${p.quantity}</td><td>¥${(p.avg_cost||0).toFixed(2)}</td>
          <td>¥${(p.current_price||0).toFixed(2)}</td>
          <td>¥${(p.market_value||0).toLocaleString()}</td>
          <td style="color:${pnlColor}">${(p.pnl_pct||0).toFixed(1)}%</td>
          <td>${p.near_stop ? '⚠️ Near' : '-'}</td>
        </tr>`;
      }
      html += '</tbody></table></div>';
    }

    if (data.warnings && data.warnings.length) {
      html += '<div class="card wide" style="border-color:rgba(245,158,11,0.3)">';
      html += data.warnings.map(w => `<div style="color:var(--amber);font-size:13px">⚠️ ${w}</div>`).join('');
      html += '</div>';
    }
    if (data.actions && data.actions.length) {
      html += '<div class="card wide" style="border-color:rgba(239,68,68,0.3)">';
      html += data.actions.map(a => `<div style="color:var(--red);font-size:13px">→ ${a}</div>`).join('');
      html += '</div>';
    }

    div.innerHTML = html;
    showToast('健康检查完成', 'success');

  } catch (e) {
    div.innerHTML = `<div class="empty"><div class="icon">❌</div><p>${escHtml(e.message)}</p></div>`;
  }
}

// ── Positions Management ───────────
async function refreshPositions() {
  const div = document.getElementById('positions-list');
  const summary = document.getElementById('positions-summary');
  const timeEl = document.getElementById('positions-time');
  div.innerHTML = '<div class="empty"><div class="icon">⏳</div><p>刷新中...</p></div>';

  try {
    const resp = await fetch('/api/positions/refresh');
    const data = await resp.json();

    if (data.error) {
      div.innerHTML = `<div class="empty"><div class="icon">⚠️</div><p>${data.error}</p></div>`;
      return;
    }

    timeEl.textContent = '更新于 ' + (data.generated_at || '');

    if (!data.positions || data.positions.length === 0) {
      summary.style.display = 'none';
      div.innerHTML = '<div class="empty"><div class="icon">💼</div><p>暂无持仓</p><p style="font-size:11px;margin-top:8px">点击"添加持仓"追踪股票、ETF或基金</p></div>';
      return;
    }

    // Summary cards
    const healthColor = data.health==='critical'?'var(--red)':data.health==='warning'?'var(--amber)':'var(--green)';
    document.getElementById('positions-cards').innerHTML = `
      <div class="card">
        <div class="label">总市值</div>
        <div class="value">¥${(data.total_value||0).toLocaleString()}</div>
      </div>
      <div class="card">
        <div class="label">总成本</div>
        <div class="value">¥${(data.total_cost||0).toLocaleString()}</div>
      </div>
      <div class="card">
        <div class="label">总盈亏</div>
        <div class="value" style="color:${(data.total_pnl||0)>=0?'var(--green)':'var(--red)'}">${(data.total_pnl_pct||0)>=0?'+':''}${(data.total_pnl_pct||0).toFixed(2)}%</div>
        <div class="change ${(data.total_pnl||0)>=0?'up':'down'}">¥${(data.total_pnl||0).toLocaleString()}</div>
      </div>
      <div class="card">
        <div class="label">今日变动</div>
        <div class="value" style="color:${(data.day_change||0)>=0?'var(--green)':'var(--red)'}">${(data.day_change||0)>=0?'+':''}${(data.day_change||0).toFixed(2)}%</div>
      </div>
      <div class="card">
        <div class="label">健康度</div>
        <div class="value" style="color:${healthColor}">${(data.health||'unknown').toUpperCase()}</div>
      </div>
    `;
    summary.style.display = 'block';

    // Position cards
    let html = '';
    for (const p of data.positions) {
      const pnlColor = p.pnl_pct >= 0 ? 'var(--green)' : 'var(--red)';
      const actionClass = (p.action||'').includes('buy') ? 'buy' : ((p.action||'').includes('sell') ? 'sell' : 'hold');
      const typeLabel = p.asset_type === 'fund' ? '基金' : (p.asset_type === 'etf' ? 'ETF' : '股票');
      const typeColor = p.asset_type === 'fund' ? 'var(--accent)' : (p.asset_type === 'etf' ? '#8b5cf6' : 'var(--amber)');

      html += `<div class="signal-card" style="position:relative">
        <div class="signal-badge ${actionClass}">${actionClass === 'buy' ? '买' : (actionClass === 'sell' ? '卖' : '观')}</div>
        <div class="signal-info">
          <div style="display:flex;justify-content:space-between;align-items:start">
            <div>
              <span class="symbol">${p.symbol}</span>
              <span style="font-size:11px;color:${typeColor};margin-left:8px;padding:2px 6px;border-radius:4px;background:${typeColor}15">${typeLabel}</span>
              ${p.name ? `<span style="font-size:12px;color:var(--text-dim);margin-left:6px">${p.name}</span>` : ''}
            </div>
            <button class="btn btn-secondary" style="padding:4px 10px;font-size:11px" onclick="removePosition('${p.symbol}')">✕</button>
          </div>
          <div class="signal-prices" style="margin-top:10px">
            <div class="price-item"><div class="plabel">Price</div><div class="pval">¥${(p.current_price||0).toFixed(p.asset_type==='fund'?4:2)}</div></div>
            <div class="price-item"><div class="plabel">Cost</div><div class="pval">¥${(p.avg_cost||0).toFixed(p.asset_type==='fund'?4:2)}</div></div>
            <div class="price-item"><div class="plabel">Qty</div><div class="pval">${p.quantity||0}</div></div>
            <div class="price-item"><div class="plabel">Mkt Val</div><div class="pval">¥${(p.market_value||0).toLocaleString()}</div></div>
            <div class="price-item"><div class="plabel">P&L</div><div class="pval" style="color:${pnlColor}">${(p.pnl_pct||0)>=0?'+':''}${(p.pnl_pct||0).toFixed(2)}%</div></div>
            <div class="price-item"><div class="plabel">Today</div><div class="pval" style="color:${p.day_change_pct>=0?'var(--green)':'var(--red)'}">${p.day_change_pct>=0?'+':''}${(p.day_change_pct||0).toFixed(2)}%</div></div>
          </div>
          <div style="margin-top:10px;padding:8px 12px;border-radius:8px;background:var(--surface);font-size:12px;color:var(--text-dim)">
            <span style="color:var(--text);font-weight:500">Advice:</span> ${p.advice||'No advice yet'}
            ${p.score ? `<span style="margin-left:8px;font-size:11px;color:var(--accent)">Score ${p.score.toFixed(0)}</span>` : ''}
          </div>
        </div>
      </div>`;
    }

    // Suggestions
    if (data.suggestions && data.suggestions.length) {
      html += '<div class="card wide" style="margin-top:12px;border-color:rgba(99,102,241,0.2)"><div class="label">💡 组合建议</div>';
      html += data.suggestions.map(s => `<div style="font-size:13px;padding:2px 0">→ ${s}</div>`).join('');
      html += '</div>';
    }
    if (data.warnings && data.warnings.length) {
      html += '<div class="card wide" style="border-color:rgba(245,158,11,0.3)">';
      html += data.warnings.map(w => `<div style="font-size:13px;color:var(--amber)">⚠️ ${w}</div>`).join('');
      html += '</div>';
    }

    div.innerHTML = html;
    showToast('持仓已刷新', 'success');

  } catch (e) {
    div.innerHTML = `<div class="empty"><div class="icon">❌</div><p>${escHtml(e.message)}</p></div>`;
  }
}

function showAddForm() {
  document.getElementById('add-form').style.display = 'block';
}
function hideAddForm() {
  document.getElementById('add-form').style.display = 'none';
  document.getElementById('add-symbol').value = '';
  document.getElementById('add-name').value = '';
  document.getElementById('add-qty').value = '';
  document.getElementById('add-cost').value = '';
  const typeEl = document.getElementById('add-type');
  if (typeEl) typeEl.value = 'auto';
}

async function addPosition() {
  const symbol = document.getElementById('add-symbol').value.trim();
  const name = document.getElementById('add-name').value.trim();
  const qty = document.getElementById('add-qty').value;
  const cost = document.getElementById('add-cost').value;
  const typeEl = document.getElementById('add-type');
  const type = typeEl ? typeEl.value : 'auto';

  if (!symbol) { showToast('请输入代码', 'error'); return; }
  if (!qty || qty <= 0) { showToast('请输入有效数量', 'error'); return; }
  if (!cost || cost <= 0) { showToast('请输入有效成本', 'error'); return; }

  try {
    const params = new URLSearchParams({ symbol, name, qty, cost });
    if (type && type !== 'auto') params.append('type', type);
    const resp = await fetch('/api/positions/add?' + params.toString());
    const data = await resp.json();
    if (data.error) { showToast(data.error, 'error'); return; }

    hideAddForm();
    showToast(`已添加 ${symbol} (${data.asset_type||'unknown'})`, 'success');
    refreshPositions();
  } catch (e) {
    showToast('添加失败: ' + e.message, 'error');
  }
}

async function removePosition(symbol) {
  if (!confirm(`确认删除 ${symbol}？`)) return;
  try {
    const resp = await fetch(`/api/positions/remove?symbol=${symbol}`);
    const data = await resp.json();
    if (data.error) { showToast(data.error, 'error'); return; }
    showToast(`已删除 ${symbol}`, 'success');
    refreshPositions();
  } catch (e) {
    showToast('删除失败', 'error');
  }
}

// Auto-refresh positions on page load
const origNavClick = document.querySelector('.nav-item[data-page="positions"]')?.onclick;
document.querySelector('.nav-item[data-page="positions"]')?.addEventListener('click', () => {
  setTimeout(refreshPositions, 100);
});

// ── Portfolio Evaluation ───────────
async function evaluatePortfolio() {
  let symbols = document.getElementById('pf-symbols').value.trim();
  let qtys = document.getElementById('pf-qty').value.trim();
  let costs = document.getElementById('pf-cost').value.trim();
  const cash = document.getElementById('pf-cash').value || '0';
  const date = document.getElementById('pf-date').value;
  const div = document.getElementById('pf-result');

  // Auto-load positions if no manual input
  if (!symbols) {
    const positions = await getMyPositions();
    if (positions.length === 0) {
      showToast('请先输入持仓代码，或在"我的持仓"中添加数据', 'error');
      return;
    }
    symbols = positions.map(p => p.symbol).join(',');
    qtys = positions.map(p => Math.round(p.quantity)).join(',');
    costs = positions.map(p => p.avg_cost.toFixed(3)).join(',');
    document.getElementById('pf-symbols').value = symbols;
    document.getElementById('pf-qty').value = qtys;
    document.getElementById('pf-cost').value = costs;
  }

  div.innerHTML = '<div class="empty"><div class="icon">⏳</div><p>评估中...</p></div>';

  try {
    const resp = await fetch(`/api/portfolio?symbols=${encodeURIComponent(symbols)}&qtys=${encodeURIComponent(qtys)}&costs=${encodeURIComponent(costs)}&cash=${cash}&date=${date}&benchmark=000300`);
    const data = await resp.json();

    if (data.error) {
      div.innerHTML = `<div class="empty"><div class="icon">⚠️</div><p>${data.error}</p></div>`;
      return;
    }

    let html = '';

    // Risk Dashboard
    html += `<div class="card-grid">
      <div class="card">
        <div class="label">组合价值</div>
        <div class="value">¥${(data.total_value||0).toLocaleString()}</div>
      </div>
      <div class="card">
        <div class="label">年化波动率</div>
        <div class="value" style="color:${(data.portfolio_volatility||0)>35?'var(--red)':(data.portfolio_volatility||0)>20?'var(--amber)':'var(--green)'}">${(data.portfolio_volatility||0).toFixed(1)}%</div>
      </div>
      <div class="card">
        <div class="label">最大回撤</div>
        <div class="value" style="color:${(data.max_drawdown||0)<-15?'var(--red)':(data.max_drawdown||0)<-8?'var(--amber)':'var(--green)'}">${(data.max_drawdown||0).toFixed(1)}%</div>
      </div>
      <div class="card">
        <div class="label">夏普比率</div>
        <div class="value" style="color:${(data.sharpe_ratio||0)>1?'var(--green)':(data.sharpe_ratio||0)>0?'var(--amber)':'var(--red)'}">${(data.sharpe_ratio||0).toFixed(2)}</div>
      </div>
      <div class="card">
        <div class="label">索提诺比率</div>
        <div class="value">${(data.sortino_ratio||0).toFixed(2)}</div>
      </div>
      <div class="card">
        <div class="label">卡尔玛比率</div>
        <div class="value">${(data.calmar_ratio||0).toFixed(2)}</div>
      </div>
      <div class="card">
        <div class="label">VaR (95%)</div>
        <div class="value" style="color:var(--red)">${(data.portfolio_var_95||0).toFixed(2)}%</div>
      </div>
      <div class="card">
        <div class="label">集中度 HHI</div>
        <div class="value" style="color:${(data.concentration_hhi||0)>0.5?'var(--red)':'var(--green)'}">${(data.concentration_hhi||0).toFixed(2)}</div>
      </div>
    </div>`;

    // Benchmark metrics (if available)
    if (data.benchmark_code) {
      html += `<div class="card-grid" style="margin-top:0">
        <div class="card">
          <div class="label">Beta (相对${data.benchmark_name})</div>
          <div class="value" style="color:${(data.beta||0)>1.2?'var(--amber)':(data.beta||0)<0?'var(--red)':'var(--text)'}">${(data.beta||0).toFixed(2)}</div>
        </div>
        <div class="card">
          <div class="label">Alpha (年化)</div>
          <div class="value" style="color:${(data.alpha||0)>=0?'var(--green)':'var(--red)'}">${(data.alpha||0)>=0?'+':''}${(data.alpha||0).toFixed(1)}%</div>
        </div>
        <div class="card">
          <div class="label">超额收益</div>
          <div class="value" style="color:${(data.excess_return||0)>=0?'var(--green)':'var(--red)'}">${(data.excess_return||0)>=0?'+':''}${(data.excess_return||0).toFixed(1)}%</div>
        </div>
        <div class="card">
          <div class="label">信息比率</div>
          <div class="value" style="color:${(data.information_ratio||0)>=0?'var(--green)':'var(--red)'}">${(data.information_ratio||0).toFixed(2)}</div>
        </div>
        <div class="card">
          <div class="label">${data.benchmark_name}收益</div>
          <div class="value" style="color:${(data.benchmark_return||0)>=0?'var(--green)':'var(--red)'}">${(data.benchmark_return||0)>=0?'+':''}${(data.benchmark_return||0).toFixed(1)}%</div>
        </div>
        <div class="card">
          <div class="label">跟踪误差</div>
          <div class="value">${(data.tracking_error||0).toFixed(1)}%</div>
        </div>
      </div>`;
    }

    // Warnings & suggestions
    if (data.warnings && data.warnings.length) {
      html += '<div class="card wide" style="border-color:rgba(245,158,11,0.3)">';
      html += '<div class="label">⚠️ 风险警告</div>';
      html += data.warnings.map(w => `<div style="font-size:13px;color:var(--amber);padding:2px 0">• ${w}</div>`).join('');
      html += '</div>';
    }
    if (data.suggestions && data.suggestions.length) {
      html += '<div class="card wide" style="border-color:rgba(99,102,241,0.2)">';
      html += '<div class="label">💡 优化建议</div>';
      html += data.suggestions.map(s => `<div style="font-size:13px;color:var(--text);padding:2px 0">→ ${s}</div>`).join('');
      html += '</div>';
    }

    // Holdings table
    if (data.holdings && data.holdings.length) {
      html += '<div class="table-wrap"><table><thead><tr><th>代码</th><th>数量</th><th>成本</th><th>现价</th><th>市值</th><th>权重</th><th>盈亏</th><th>波动贡献</th></tr></thead><tbody>';
      for (const h of data.holdings) {
        const pnlColor = h.pnl_pct >= 0 ? 'var(--green)' : 'var(--red)';
        html += `<tr>
          <td style="font-weight:600">${h.symbol}</td>
          <td>${h.quantity}</td><td>¥${h.avg_cost.toFixed(2)}</td>
          <td>¥${h.current_price.toFixed(2)}</td>
          <td>¥${h.market_value.toLocaleString()}</td>
          <td>${h.weight}%</td>
          <td style="color:${pnlColor}">${h.pnl_pct.toFixed(1)}%</td>
          <td>${data.vol_contribution&&data.vol_contribution[h.symbol]?data.vol_contribution[h.symbol]+'%':'-'}</td>
        </tr>`;
      }
      html += '</tbody></table></div>';
    }

    // Correlation matrix
    if (data.correlation_matrix && data.corr_labels && data.corr_labels.length > 1) {
      html += '<div class="card wide"><div class="label">📊 相关性矩阵</div>';
      html += '<div style="overflow-x:auto"><table><thead><tr><th></th>';
      for (const l of data.corr_labels) html += `<th>${l}</th>`;
      html += '</tr></thead><tbody>';
      for (let i = 0; i < data.corr_labels.length; i++) {
        html += `<tr><td style="font-weight:600">${data.corr_labels[i]}</td>`;
        for (let j = 0; j < data.corr_labels.length; j++) {
          const val = data.correlation_matrix[i][j];
          const bg = i===j ? 'transparent' : val>0.7 ? 'rgba(239,68,68,0.2)' : val>0.4 ? 'rgba(245,158,11,0.15)' : 'rgba(34,197,94,0.1)';
          html += `<td style="background:${bg};font-weight:${i===j?400:500}">${val.toFixed(2)}</td>`;
        }
        html += '</tr>';
      }
      html += '</tbody></table></div>';
      html += `<div style="font-size:11px;color:var(--text-dim);margin-top:8px">平均相关性: ${(data.avg_correlation||0).toFixed(2)} ${(data.avg_correlation||0)>0.7?'⚠️ 分散化收益有限':''}</div>`;
      html += '</div>';
    }

    // Efficient Frontier weights
    if (data.optimal_weights && Object.keys(data.optimal_weights).length) {
      html += '<div class="card wide"><div class="label">🎯 权重优化 (最大夏普)</div>';
      html += '<div style="display:flex;gap:24px;flex-wrap:wrap">';
      for (const [sym, w] of Object.entries(data.optimal_weights)) {
        const minW = data.min_vol_weights ? data.min_vol_weights[sym] || 0 : 0;
        html += `<div style="text-align:center">
          <div style="font-weight:600;font-size:15px">${sym}</div>
          <div style="font-size:11px;color:var(--text-dim);margin-top:2px">最优</div>
          <div style="font-size:22px;font-weight:650;margin-top:4px;color:var(--accent)">${w}%</div>
          <div style="font-size:10px;color:var(--text-dim)">最小波动: ${minW}%</div>
        </div>`;
      }
      html += '</div></div>';
    }

    div.innerHTML = html;
    showToast('组合评估完成', 'success');
  } catch (e) {
    div.innerHTML = `<div class="empty"><div class="icon">❌</div><p>${escHtml(e.message)}</p></div>`;
  }
}

// ── History (stub) ─────────────────
async function loadHistory() {
  const div = document.getElementById('history-result');
  const strategy = document.getElementById('history-strategy').value;
  const positionsOnly = document.getElementById('history-positions-only').checked;

  try {
    let url = strategy ? `/api/history?strategy=${strategy}` : '/api/history';
    if (positionsOnly) {
      const positions = await getMyPositions();
      if (positions.length > 0) {
        url += `${strategy ? '&' : '?'}symbols=${encodeURIComponent(positions.map(p => p.symbol).join(','))}`;
      }
    }
    const resp = await fetch(url);
    const data = await resp.json();
    if (data.signals && data.signals.length) {
      let html = '<div class="table-wrap"><table><thead><tr><th>日期</th><th>策略</th><th>代码</th><th>方向</th><th>价格</th><th>理由</th></tr></thead><tbody>';
      for (const s of data.signals) {
        html += `<tr><td>${s.date||''}</td><td>${s.strategy||''}</td><td style="font-weight:600">${s.symbol}</td>
          <td><span class="tag ${s.action}">${s.action}</span></td>
          <td>¥${(s.limit_price||0).toFixed(2)}</td>
          <td style="font-size:12px;color:var(--text-dim)">${(s.reason||'').slice(0,50)}</td></tr>`;
      }
      html += '</tbody></table></div>';
      div.innerHTML = html;
    } else {
      div.innerHTML = '<div class="empty"><div class="icon">📈</div><p>No signal records yet</p></div>';
    }
  } catch (e) {
    div.innerHTML = `<div class="empty"><div class="icon">❌</div><p>${escHtml(e.message)}</p></div>`;
  }
}

// ── Market Context Bar ────────────
async function loadMarketBar() {
  try {
    const resp = await fetch('/api/market/context');
    const data = await resp.json();
    if (data.error) return;

    let html = '';
    const indices = data.indices || {};
    for (const [code, info] of Object.entries(indices)) {
      const cls = (info.change_1d || 0) >= 0 ? 'up' : 'down';
      const sign = info.change_1d >= 0 ? '+' : '';
      html += `<div class="idx-item">
        <span class="idx-name">${info.name}</span>
        <span style="font-size:12px">${(info.close||0).toLocaleString()}</span>
        <span class="idx-chg ${cls}">${sign}${(info.change_1d||0).toFixed(2)}%</span>
      </div>`;
    }
    document.getElementById('market-indices').innerHTML = html;

    const bc = data.breadth_class || 'mixed';
    const bl = data.market_breadth === 'broadly_up' ? '普涨' :
               data.market_breadth === 'broadly_down' ? '普跌' : '分化';
    document.getElementById('market-breadth').innerHTML =
      `<span class="breadth-badge ${bc}">${bl}</span>`;
  } catch(e) {
    document.getElementById('market-indices').innerHTML =
      '<span style="color:var(--text-dim);font-size:11px">加载市场数据...</span>';
  }
}

// ── Index Dashboard ───────────────
async function loadIndexDashboard() {
  const date = document.getElementById('index-date').value;
  const cardsDiv = document.getElementById('index-cards');
  cardsDiv.innerHTML = '<div class="empty"><div class="icon">⏳</div><p>加载指数数据...</p></div>';

  try {
    const resp = await fetch('/api/index/dashboard?date=' + date);
    const data = await resp.json();
    if (data.error) { cardsDiv.innerHTML = '<div class="empty"><p>' + data.error + '</p></div>'; return; }

    // Summary
    document.getElementById('index-summary').innerHTML =
      `<div style="font-size:16px;font-weight:600;margin-bottom:4px">${data.summary||''}</div>
      <div style="font-size:12px;color:var(--text-dim);display:flex;gap:16px;flex-wrap:wrap">
        <span>宽度: ${data.market_breadth||''}</span>
        <span>状态: ${data.dominant_regime||''}</span>
        <span>波动: ${data.volatility_regime||''}</span>
        ${(data.signals||[]).map(s => '<span style="color:var(--accent)">📡 '+s+'</span>').join('')}
      </div>`;

    // Index trend cards
    const indices = data.indices || {};
    let cardsHtml = '';
    const regimeReg = {
      'trending_up':'上升趋势','trending_down':'下降趋势','ranging':'区间震荡','volatile':'波动加剧'
    };
    for (const [code, idx] of Object.entries(indices)) {
      const chgCls = (idx.change_1d||0) >= 0 ? 'up' : 'down';
      const sign = (idx.change_1d||0) >= 0 ? '+' : '';
      const reg = regimeReg[idx.regime] || idx.regime;
      const regCls = idx.regime === 'trending_up' ? 'trending-up' :
                     idx.regime === 'trending_down' ? 'trending-down' :
                     idx.regime === 'volatile' ? 'volatile' : 'ranging';

      cardsHtml += `<div class="idx-trend-card">
        <div class="idx-trend-header">
          <span class="idx-trend-name">${idx.name}</span>
          <span class="regime-badge ${regCls}">${reg}</span>
        </div>
        <div class="idx-trend-price">${(idx.close||0).toLocaleString()}</div>
        <div class="idx-trend-change" style="color:${chgCls==='up'?'var(--green)':'var(--red)'}">
          ${sign}${(idx.change_1d||0).toFixed(2)}% 今日
        </div>
        <div class="idx-trend-stats">
          <div><div class="plabel">5日</div><div class="pval" style="color:${idx.change_5d>=0?'var(--green)':'var(--red)'}">${idx.change_5d>=0?'+':''}${idx.change_5d.toFixed(2)}%</div></div>
          <div><div class="plabel">20日</div><div class="pval" style="color:${idx.change_20d>=0?'var(--green)':'var(--red)'}">${idx.change_20d>=0?'+':''}${idx.change_20d.toFixed(2)}%</div></div>
          <div><div class="plabel">60日</div><div class="pval" style="color:${idx.change_60d>=0?'var(--green)':'var(--red)'}">${idx.change_60d>=0?'+':''}${idx.change_60d.toFixed(2)}%</div></div>
          <div><div class="plabel">波动率</div><div class="pval">${idx.volatility_20d.toFixed(1)}%</div></div>
          <div><div class="plabel">52周位置</div><div class="pval">${idx.position_52w.toFixed(0)}%</div></div>
          <div><div class="plabel">距高点</div><div class="pval" style="color:var(--red)">${idx.max_drawdown.toFixed(1)}%</div></div>
        </div>
      </div>`;
    }
    cardsDiv.innerHTML = cardsHtml;

    // 52-week position bars
    let barsHtml = '';
    for (const [code, idx] of Object.entries(indices)) {
      const pct = idx.position_52w || 50;
      const color = pct > 80 ? 'var(--red)' : pct < 20 ? 'var(--green)' : 'var(--accent)';
      barsHtml += `<div style="display:flex;align-items:center;gap:12px">
        <span style="width:70px;font-size:13px;font-weight:500">${idx.name}</span>
        <div style="flex:1;height:8px;background:rgba(255,255,255,0.05);border-radius:4px;position:relative">
          <div style="width:${Math.min(100,pct)}%;height:100%;background:${color};border-radius:4px;transition:width 0.5s ease"></div>
          <div style="position:absolute;left:${Math.min(100,pct)}%;top:-4px;width:8px;height:16px;background:${color};border-radius:4px;transform:translateX(-50%)"></div>
        </div>
        <span style="font-size:12px;font-family:var(--mono);width:40px;text-align:right">${pct.toFixed(0)}%</span>
      </div>`;
    }
    document.getElementById('position-bars').innerHTML = barsHtml;

    // Breadth & regime
    const nBull = Object.values(indices).filter(i => i.trend === 'bullish').length;
    const nTotal = Object.keys(indices).length;
    document.getElementById('breadth-detail').innerHTML =
      `<div style="margin-top:8px;font-size:24px;font-weight:650">${nBull}/${nTotal} 偏多</div>
      <div class="change" style="margin-top:4px">${data.market_breadth||''}</div>`;
    document.getElementById('regime-detail').innerHTML =
      `<div style="margin-top:8px;font-size:18px;font-weight:650">${data.dominant_regime||''}</div>`;
    document.getElementById('vol-regime').innerHTML =
      `<div style="margin-top:8px;font-size:18px;font-weight:650;text-transform:capitalize">${data.volatility_regime||''}</div>`;
    document.getElementById('index-signals').innerHTML =
      `<div style="margin-top:8px;font-size:13px">${(data.signals||[]).join('<br>') || 'No special signals'}</div>`;

    // Returns comparison table
    let thtml = '<table><thead><tr><th>Index</th><th>Close</th><th>1-Day</th><th>5-Day</th><th>20-Day</th><th>60-Day</th><th>Trend</th><th>Regime</th></tr></thead><tbody>';
    for (const [code, idx] of Object.entries(indices)) {
      const trendMap = {bullish:'Bull',bearish:'Bear',neutral:'Neutral'};
      thtml += `<tr>
        <td style="font-weight:600;font-family:var(--font)">${idx.name}</td>
        <td>${idx.close.toLocaleString()}</td>
        <td style="color:${idx.change_1d>=0?'var(--green)':'var(--red)'}">${idx.change_1d>=0?'+':''}${idx.change_1d.toFixed(2)}%</td>
        <td style="color:${idx.change_5d>=0?'var(--green)':'var(--red)'}">${idx.change_5d>=0?'+':''}${idx.change_5d.toFixed(2)}%</td>
        <td style="color:${idx.change_20d>=0?'var(--green)':'var(--red)'}">${idx.change_20d>=0?'+':''}${idx.change_20d.toFixed(2)}%</td>
        <td style="color:${idx.change_60d>=0?'var(--green)':'var(--red)'}">${idx.change_60d>=0?'+':''}${idx.change_60d.toFixed(2)}%</td>
        <td><span class="tag ${idx.trend==='bullish'?'buy':(idx.trend==='bearish'?'sell':'hold')}">${trendMap[idx.trend]}</span></td>
        <td><span class="regime-badge">${idx.regime}</span></td>
      </tr>`;
    }
    thtml += '</tbody></table>';
    document.getElementById('returns-table').innerHTML = '<div class="table-wrap">' + thtml + '</div>';

    showToast('Index board loaded', 'success');
  } catch(e) {
    cardsDiv.innerHTML = '<div class="empty"><div class="icon">❌</div><p></p></div>';
    cardsDiv.querySelector('p').textContent = e.message;
  }
}

// ── Scroll-to-top ─────────────────
// ── Glossary search ────────────────
function filterGlossary() {
  const q = document.getElementById('glossary-search').value.toLowerCase().trim();
  const cards = document.querySelectorAll('#page-glossary .glossary-card');
  const sections = document.querySelectorAll('#page-glossary .glossary-section');
  cards.forEach(card => {
    const keywords = (card.dataset.keywords || '') + ' ' + card.textContent.toLowerCase();
    card.classList.toggle('hidden', q && !keywords.includes(q));
  });
  sections.forEach(sec => {
    const visible = sec.querySelectorAll('.glossary-card:not(.hidden)').length > 0;
    sec.style.display = q && !visible ? 'none' : '';
  });
}

(function() {
  const btn = document.getElementById('scroll-top');
  const main = document.querySelector('.main');
  if (main && btn) {
    main.addEventListener('scroll', () => {
      if (main.scrollTop > 400) btn.classList.add('visible');
      else btn.classList.remove('visible');
    });
  }
})();

// ── Trade Review ───────────────────
async function populateTradeQuickSelect() {
  const select = document.getElementById('trade-quick-select');
  const positions = await getMyPositions(true);
  select.innerHTML = '<option value="">-- 选择持仓 --</option>';
  for (const p of positions) {
    select.innerHTML += `<option value="${p.symbol}|${p.name}|${p.quantity}|${p.avg_cost}">${p.symbol} ${p.name} — ${Math.round(p.quantity)}股 @¥${p.avg_cost.toFixed(2)}</option>`;
  }
}

function onQuickTradeSelect() {
  const select = document.getElementById('trade-quick-select');
  const val = select.value;
  if (!val) return;
  const parts = val.split('|');
  document.getElementById('trade-symbol').value = parts[0];
  document.getElementById('trade-name').value = parts[1] || '';
  document.getElementById('trade-qty').value = parts[2] || '';
  document.getElementById('trade-direction').value = 'SELL';
  document.getElementById('trade-price').focus();
}

async function logTrade() {
  const symbol = document.getElementById('trade-symbol').value.trim();
  const name = document.getElementById('trade-name').value.trim();
  const direction = document.getElementById('trade-direction').value;
  const price = parseFloat(document.getElementById('trade-price').value);
  const qty = parseInt(document.getElementById('trade-qty').value);
  const strategy = document.getElementById('trade-strategy').value.trim();
  const reason = document.getElementById('trade-reason').value.trim();

  if (!symbol) { showToast('请输入代码', 'error'); return; }
  if (!price || price <= 0) { showToast('请输入有效价格', 'error'); return; }
  if (!qty || qty <= 0) { showToast('请输入有效数量', 'error'); return; }

  try {
    const params = new URLSearchParams({ symbol, name, direction, price, quantity: qty, strategy, reason });
    const resp = await fetch('/api/trades/log', { method: 'POST', body: params });
    const data = await resp.json();
    if (data.error) { showToast(data.error, 'error'); return; }
    showToast(data.message, 'success');
    // Check if selling all shares — prompt to remove position
    if (direction === 'SELL') {
      const positions = await getMyPositions(true);
      const pos = positions.find(p => p.symbol === symbol);
      if (pos && qty >= pos.quantity && confirm(`已卖出全部 ${symbol} 持仓，是否从持仓列表移除？`)) {
        try {
          const rmResp = await fetch(`/api/positions/remove?symbol=${encodeURIComponent(symbol)}`);
          const rmData = await rmResp.json();
          if (rmData.message) showToast(rmData.message, 'success');
        } catch (e) { /* ignore removal error */ }
      }
    }
    // Clear form
    document.getElementById('trade-symbol').value = '';
    document.getElementById('trade-name').value = '';
    document.getElementById('trade-price').value = '';
    document.getElementById('trade-qty').value = '';
    document.getElementById('trade-strategy').value = '';
    document.getElementById('trade-reason').value = '';
    document.getElementById('trade-quick-select').value = '';
    loadTradeHistory();
  } catch (e) {
    showToast('记录失败: ' + e.message, 'error');
  }
}

async function generateDailyReview() {
  const date = document.getElementById('review-date').value;
  const linkDiv = document.getElementById('daily-report-link');
  linkDiv.innerHTML = '<span style="color:var(--amber)">⏳ 生成中...</span>';
  try {
    const resp = await fetch(`/api/review/daily?date=${date}`);
    const data = await resp.json();
    if (data.error) { showToast(data.error, 'error'); linkDiv.innerHTML = ''; return; }
    showToast(data.message, 'success');
    linkDiv.innerHTML = `<span style="color:var(--green)">✅ 已生成</span> <a href="#" style="color:var(--accent);font-size:12px" onclick="showToast('报告已写入Obsidian vault: ${data.report_path.replace(/'/g,'')}','success')">查看路径</a>`;
  } catch (e) {
    showToast('日报生成失败: ' + e.message, 'error');
    linkDiv.innerHTML = '';
  }
}

async function generateWeeklyReview() {
  const date = document.getElementById('review-week-end').value;
  const linkDiv = document.getElementById('weekly-report-link');
  linkDiv.innerHTML = '<span style="color:var(--amber)">⏳ 生成中...</span>';
  try {
    const resp = await fetch(`/api/review/weekly?date=${date}`);
    const data = await resp.json();
    if (data.error) { showToast(data.error, 'error'); linkDiv.innerHTML = ''; return; }
    showToast(data.message, 'success');
    linkDiv.innerHTML = `<span style="color:var(--green)">✅ 已生成</span> <a href="#" style="color:var(--accent);font-size:12px" onclick="showToast('报告已写入Obsidian vault: ${data.report_path.replace(/'/g,'')}','success')">查看路径</a>`;
  } catch (e) {
    showToast('周报生成失败: ' + e.message, 'error');
    linkDiv.innerHTML = '';
  }
}

async function loadTradeHistory() {
  const div = document.getElementById('trade-history-table');
  try {
    const resp = await fetch('/api/trades/history?days=30');
    const data = await resp.json();
    if (!data.trades || data.trades.length === 0) {
      div.innerHTML = '<div class="empty"><div class="icon">📭</div><p>暂无交易记录</p></div>';
      return;
    }
    let html = '<div class="table-wrap"><table><thead><tr><th>日期</th><th>代码</th><th>方向</th><th>价格</th><th>数量</th><th>金额</th><th>策略</th><th>理由</th></tr></thead><tbody>';
    for (const t of data.trades) {
      const dirClass = t.direction === 'BUY' ? 'style="color:var(--green)"' : 'style="color:var(--red)"';
      const dirText = t.direction === 'BUY' ? '买入' : '卖出';
      html += `<tr>
        <td>${t.trade_date}</td>
        <td>${t.symbol} ${t.name||''}</td>
        <td ${dirClass}>${dirText}</td>
        <td>${t.price.toFixed(2)}</td>
        <td>${t.quantity}</td>
        <td>¥${t.amount.toLocaleString()}</td>
        <td>${t.strategy||'-'}</td>
        <td>${t.reason||'-'}</td>
      </tr>`;
    }
    html += '</tbody></table></div>';
    html += `<div style="margin-top:12px;font-size:13px;color:var(--text-dim)">共 ${data.count} 笔交易</div>`;
    div.innerHTML = html;
  } catch (e) {
    div.innerHTML = `<div class="empty"><div class="icon">⚠️</div><p>加载失败: ${e.message}</p></div>`;
  }
}

// ── HTML escape helper ────────────
function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ── Auto-load & index page init ───
document.addEventListener('DOMContentLoaded', () => {
  loadMarketBar();
  setInterval(loadMarketBar, 300000);
  const todayStr = new Date().toISOString().split('T')[0];
  const idxDate = document.getElementById('index-date');
  const revDate = document.getElementById('review-date');
  const evalDate = document.getElementById('eval-date');
  const pfDate = document.getElementById('pf-date');
  const briefingDate = document.getElementById('briefing-date');
  if (idxDate) idxDate.value = todayStr;
  if (revDate) revDate.value = todayStr;
  if (evalDate) evalDate.value = todayStr;
  if (pfDate) pfDate.value = todayStr;
  if (briefingDate) briefingDate.value = todayStr;
  document.querySelector('.nav-item[data-page="index"]')?.addEventListener('click', () => {
    setTimeout(loadIndexDashboard, 100);
  });
  document.querySelector('.nav-item[data-page="review"]')?.addEventListener('click', () => {
    setTimeout(loadTradeHistory, 100);
    setTimeout(populateTradeQuickSelect, 150);
  });
});

// ── Keyboard shortcut ──────────────
document.addEventListener('keydown', (e) => {
  if (e.metaKey && e.key === 'Enter') {
    const activePage = document.querySelector('.page.active');
    if (activePage && activePage.id === 'page-briefing') generateBriefing();
    if (activePage && activePage.id === 'page-evaluate') evaluateStocks();
    if (activePage && activePage.id === 'page-health') checkHealth();
    if (activePage && activePage.id === 'page-portfolio') evaluatePortfolio();
    if (activePage && activePage.id === 'page-review') { loadTradeHistory(); populateTradeQuickSelect(); }
    if (activePage && activePage.id === 'page-positions') refreshPositions();
  }
});
</script>
</body>
</html>"""


# =====================================================================
# API Routes
# =====================================================================

_signal_history: list[dict] = []


def _get_engine():
    from quantsys.advisor.recommendation import RecommendationEngine
    return RecommendationEngine()


def _get_evaluator():
    from quantsys.advisor.evaluator import StockEvaluator
    return StockEvaluator()


def _get_checker():
    from quantsys.advisor.portfolio_health import PortfolioHealthChecker
    return PortfolioHealthChecker()


@app.after_request
def _no_cache(response):
    """Disable browser caching so code updates take effect immediately."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/")
def index():
    return render_template_string(TEMPLATE)


@app.route("/api/briefing")
def api_briefing():
    """Generate daily trading briefing."""
    try:
        from quantsys.advisor.recommendation import StrategyMode

        date = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
        mode_str = request.args.get("mode", "momentum")
        trades = int(request.args.get("trades", 0))

        mode_map = {
            "momentum": StrategyMode.MOMENTUM,
            "mean_rev": StrategyMode.MEAN_REVERSION,
            "event": StrategyMode.EVENT_DRIVEN,
        }
        mode = mode_map.get(mode_str, StrategyMode.MOMENTUM)

        # Build current_position from query params if provided
        pos_symbol = request.args.get("pos_symbol", "").strip()
        pos_qty = float(request.args.get("pos_qty", 0) or 0)
        pos_cost = float(request.args.get("pos_cost", 0) or 0)
        current_position = None
        if pos_symbol and pos_qty > 0 and pos_cost > 0:
            current_position = {
                "symbol": pos_symbol, "quantity": pos_qty, "cost": pos_cost,
            }

        engine = _get_engine()
        briefing = engine.generate_briefing(
            date=date, mode=mode,
            current_position=current_position,
            monthly_trades=trades,
        )

        signals_data = []
        for s in briefing.signals:
            sig = {
                "symbol": s.symbol,
                "action": s.action.value,
                "strategy": s.strategy,
                "quantity": s.quantity,
                "trigger_price": s.trigger_price,
                "limit_price": s.limit_price,
                "stop_loss": s.stop_loss,
                "take_profit": s.take_profit,
                "confidence": s.confidence,
                "reason": s.reason,
            }
            signals_data.append(sig)
            _signal_history.append({"date": date, **sig})

        return jsonify({
            "date": date,
            "account_status": briefing.account_status,
            "risk_level": briefing.risk_level,
            "risk_warnings": briefing.risk_warnings,
            "monthly_trades_used": briefing.monthly_trades_used,
            "signals": signals_data,
            "todo": briefing.todo,
            "condition_orders": briefing.condition_orders,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/evaluate")
def api_evaluate():
    """Evaluate stocks with cross-sectional ranking against full cached universe."""
    try:
        symbols_str = request.args.get("symbols", "")
        date = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
        symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]

        if not symbols:
            return jsonify({"error": "请输入股票代码"}), 400

        evaluator = _get_evaluator()

        # Auto-expand to full cache universe for meaningful cross-sectional
        # ranking when user provides fewer than 3 symbols (otherwise all
        # scores default to 50.0 — useless).
        if len(symbols) < 3 and _CACHED_STOCK_SYMBOLS:
            all_symbols = list(dict.fromkeys(symbols + _CACHED_STOCK_SYMBOLS))
            results = evaluator.evaluate_universe(all_symbols, date, top_n=0)
            # Return only the user's requested symbols
            requested = set(symbols)
            results = [r for r in results if r.symbol in requested]
        else:
            results = evaluator.evaluate_universe(symbols, date, top_n=0)

        return jsonify({
            "date": date,
            "count": len(results),
            "results": [
                {
                    "symbol": r.symbol,
                    "total_score": r.total_score,
                    "momentum_score": r.momentum_score,
                    "trend_score": r.trend_score,
                    "valuation_score": r.valuation_score,
                    "liquidity_score": r.liquidity_score,
                    "factor_score": r.factor_score,
                    "action": r.action.value,
                    "confidence": r.confidence,
                    "reasons": r.reasons,
                    "risk_flags": r.risk_flags,
                }
                for r in results
            ],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/health")
def api_health():
    """Portfolio health check — supports single or multi-position via `positions`
    param (pipe-delimited: SYM,QTY,COST|SYM,QTY,COST)."""
    try:
        symbol = request.args.get("symbol", "")
        qty = int(request.args.get("qty", 0))
        cost = float(request.args.get("cost", 0))
        cash = float(request.args.get("cash", 0))
        positions_param = request.args.get("positions", "")

        positions = []
        if positions_param:
            for part in positions_param.split("|"):
                parts = part.split(",")
                if len(parts) >= 3:
                    positions.append({
                        "symbol": parts[0].strip(),
                        "quantity": int(parts[1].strip()),
                        "avg_cost": float(parts[2].strip()),
                    })
        elif symbol and qty > 0 and cost > 0:
            positions.append({"symbol": symbol, "quantity": qty, "avg_cost": cost})

        checker = _get_checker()
        report = checker.check(
            date=datetime.now().strftime("%Y-%m-%d"),
            positions=positions,
            cash=cash,
            initial_capital=10000.0,
        )

        return jsonify({
            "overall_health": report.overall_health,
            "total_value": report.total_value,
            "current_drawdown": report.current_drawdown,
            "trades_remaining": report.trades_remaining,
            "positions": report.positions,
            "warnings": report.warnings,
            "actions": report.actions,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/portfolio")
def api_portfolio():
    """Portfolio-level evaluation."""
    try:
        from quantsys.advisor.portfolio_evaluator import PortfolioEvaluator

        symbols_str = request.args.get("symbols", "")
        qtys_str = request.args.get("qtys", "")
        costs_str = request.args.get("costs", "")
        cash = float(request.args.get("cash", 0))
        date = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
        benchmark = request.args.get("benchmark", "")

        symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]
        qtys = [int(q.strip()) for q in qtys_str.split(",") if q.strip()]
        costs = [float(c.strip()) for c in costs_str.split(",") if c.strip()]

        if not symbols:
            return jsonify({"error": "请输入持仓代码"}), 400

        # Build positions
        positions = []
        for i, sym in enumerate(symbols):
            qty = qtys[i] if i < len(qtys) else 0
            cost = costs[i] if i < len(costs) else 0
            if qty > 0 and cost > 0:
                positions.append({"symbol": sym, "quantity": qty, "avg_cost": cost})

        evaluator = PortfolioEvaluator()
        report = evaluator.evaluate(positions=positions, cash=cash, date=date, benchmark=benchmark or None)

        return jsonify({
            "date": report.date,
            "total_value": report.total_value,
            "cash": report.cash,
            "n_positions": report.n_positions,
            "health": report.health,
            "portfolio_volatility": report.portfolio_volatility,
            "portfolio_var_95": report.portfolio_var_95,
            "portfolio_cvar_95": report.portfolio_cvar_95,
            "max_drawdown": report.max_drawdown,
            "current_drawdown": report.current_drawdown,
            "sharpe_ratio": report.sharpe_ratio,
            "sortino_ratio": report.sortino_ratio,
            "calmar_ratio": report.calmar_ratio,
            "avg_correlation": report.avg_correlation,
            "concentration_hhi": report.concentration_hhi,
            "largest_position_pct": report.largest_position_pct,
            "correlation_matrix": report.correlation_matrix,
            "corr_labels": report.corr_labels,
            "optimal_weights": report.optimal_weights,
            "min_vol_weights": report.min_vol_weights,
            "vol_contribution": report.vol_contribution,
            "frontier_points": report.frontier_points[:50],
            "holdings": report.holdings,
            "warnings": report.warnings,
            "suggestions": report.suggestions,
            # Benchmark metrics
            "beta": report.beta,
            "alpha": report.alpha,
            "excess_return": report.excess_return,
            "tracking_error": report.tracking_error,
            "information_ratio": report.information_ratio,
            "benchmark_code": report.benchmark_code,
            "benchmark_name": report.benchmark_name,
            "benchmark_return": report.benchmark_return,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -- Position tracker --------------------------------------------------

def _get_tracker():
    from quantsys.advisor.position_tracker import PositionTracker
    return PositionTracker()


@app.route("/api/positions/refresh")
def api_positions_refresh():
    """Refresh all positions with latest prices and advice."""
    try:
        tracker = _get_tracker()
        snapshot = tracker.refresh()

        return jsonify({
            "date": snapshot.date,
            "generated_at": snapshot.generated_at,
            "total_cost": snapshot.total_cost,
            "total_value": snapshot.total_value,
            "total_pnl": snapshot.total_pnl,
            "total_pnl_pct": snapshot.total_pnl_pct,
            "day_change": snapshot.day_change,
            "health": snapshot.health,
            "positions": [
                {
                    "symbol": p.symbol,
                    "name": p.name,
                    "asset_type": p.asset_type,
                    "quantity": p.quantity,
                    "avg_cost": p.avg_cost,
                    "current_price": p.current_price,
                    "market_value": p.market_value,
                    "pnl": p.pnl,
                    "pnl_pct": p.pnl_pct,
                    "day_change_pct": p.day_change_pct,
                    "score": p.score,
                    "action": p.action,
                    "advice": p.advice,
                    "risk_flags": p.risk_flags,
                    "last_updated": p.last_updated,
                }
                for p in snapshot.positions
            ],
            "suggestions": snapshot.suggestions,
            "warnings": snapshot.warnings,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/positions/add")
def api_positions_add():
    """Add a new position."""
    try:
        symbol = request.args.get("symbol", "").strip()
        name = request.args.get("name", "").strip()
        qty = float(request.args.get("qty", 0))
        cost = float(request.args.get("cost", 0))
        asset_type = request.args.get("type", "").strip()

        if not symbol:
            return jsonify({"error": "请输入代码"}), 400
        if qty <= 0 or cost <= 0:
            return jsonify({"error": "数量和成本必须大于零"}), 400

        tracker = _get_tracker()
        pos = tracker.add(symbol, name, qty, cost, asset_type=asset_type or "")

        return jsonify({
            "symbol": pos.symbol,
            "name": pos.name,
            "asset_type": pos.asset_type,
            "quantity": pos.quantity,
            "avg_cost": pos.avg_cost,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/positions/remove")
def api_positions_remove():
    """Remove a position."""
    try:
        symbol = request.args.get("symbol", "").strip()
        if not symbol:
            return jsonify({"error": "请输入代码"}), 400

        tracker = _get_tracker()
        ok = tracker.remove(symbol)
        return jsonify({"removed": ok, "symbol": symbol})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/positions/data")
def api_positions_data():
    """Return raw position static data (symbol, name, qty, cost).
    No price refresh, no API calls — reads from in-memory JSON. ~1ms."""
    try:
        tracker = _get_tracker()
        positions = [{
            "symbol": p.symbol,
            "name": p.name,
            "asset_type": p.asset_type,
            "quantity": p.quantity,
            "avg_cost": p.avg_cost,
        } for p in tracker.positions]
        return jsonify({"count": len(positions), "positions": positions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -- Index analysis endpoints -------------------------------------------

@app.route("/api/index/dashboard")
def api_index_dashboard():
    """Index dashboard with all major index metrics."""
    try:
        date = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
        indices_str = request.args.get("indices", "")

        from quantsys.advisor.index_analyzer import IndexAnalyzer
        analyzer = IndexAnalyzer()
        codes = [c.strip() for c in indices_str.split(",") if c.strip()] or None
        dashboard = analyzer.dashboard(date, codes=codes)

        regime_trans = {
            "trending_up": "上升趋势", "trending_down": "下降趋势",
            "ranging": "区间震荡", "volatile": "波动加剧",
        }
        breadth_trans = {
            "broadly_up": "普涨", "mixed": "分化", "broadly_down": "普跌",
        }

        return jsonify({
            "date": dashboard.date,
            "market_breadth": breadth_trans.get(dashboard.market_breadth, dashboard.market_breadth),
            "dominant_regime": regime_trans.get(dashboard.dominant_regime, dashboard.dominant_regime),
            "volatility_regime": dashboard.volatility_regime,
            "summary": dashboard.summary,
            "signals": dashboard.signals,
            "indices": {
                code: {
                    "code": snap.code,
                    "name": snap.name,
                    "close": snap.close,
                    "change_1d": snap.change_1d,
                    "change_5d": snap.change_5d,
                    "change_20d": snap.change_20d,
                    "change_60d": snap.change_60d,
                    "volatility_20d": snap.volatility_20d,
                    "high_52w": snap.high_52w,
                    "low_52w": snap.low_52w,
                    "position_52w": snap.position_52w,
                    "ma20": snap.ma20,
                    "ma60": snap.ma60,
                    "ma120": snap.ma120,
                    "trend": snap.trend,
                    "regime": snap.regime,
                    "volume_ratio": snap.volume_ratio,
                    "max_drawdown": snap.max_drawdown,
                }
                for code, snap in dashboard.indices.items()
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/market/context")
def api_market_context():
    """Lightweight market context for sticky bar on all pages."""
    try:
        date = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))

        from quantsys.advisor.index_analyzer import IndexAnalyzer
        analyzer = IndexAnalyzer()
        dashboard = analyzer.dashboard(date)

        breadth_trans = {
            "broadly_up": "bullish", "mixed": "mixed", "broadly_down": "bearish",
        }

        return jsonify({
            "date": dashboard.date,
            "market_breadth": dashboard.market_breadth,
            "breadth_class": breadth_trans.get(dashboard.market_breadth, "mixed"),
            "dominant_regime": dashboard.dominant_regime,
            "volatility_regime": dashboard.volatility_regime,
            "indices": {
                code: {
                    "name": snap.name,
                    "close": snap.close,
                    "change_1d": snap.change_1d,
                    "trend": snap.trend,
                }
                for code, snap in dashboard.indices.items()
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/index/snapshot")
def api_index_snapshot():
    """Single index detailed metrics."""
    try:
        code = request.args.get("code", "000300")
        date = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))

        from quantsys.advisor.index_analyzer import IndexAnalyzer
        analyzer = IndexAnalyzer()
        snap = analyzer.snapshot(code, date)

        if snap is None:
            return jsonify({"error": f"Index {code} data not found"}), 404

        return jsonify({
            "code": snap.code,
            "name": snap.name,
            "date": snap.date,
            "close": snap.close,
            "change_1d": snap.change_1d,
            "change_5d": snap.change_5d,
            "change_20d": snap.change_20d,
            "change_60d": snap.change_60d,
            "volatility_20d": snap.volatility_20d,
            "high_52w": snap.high_52w,
            "low_52w": snap.low_52w,
            "position_52w": snap.position_52w,
            "ma20": snap.ma20,
            "ma60": snap.ma60,
            "ma120": snap.ma120,
            "trend": snap.trend,
            "regime": snap.regime,
            "volume_ratio": snap.volume_ratio,
            "max_drawdown": snap.max_drawdown,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history")
def api_history():
    """Get signal history — optional filter by strategy and/or symbols."""
    strategy_filter = request.args.get("strategy", "")
    symbols_filter = request.args.get("symbols", "")
    signals = _signal_history
    if strategy_filter:
        signals = [s for s in signals if s.get("strategy") == strategy_filter]
    if symbols_filter:
        symbol_set = set(s.strip() for s in symbols_filter.split(",") if s.strip())
        signals = [s for s in signals if s.get("symbol") in symbol_set]
    return jsonify({"signals": signals[-50:]})  # Last 50


# =====================================================================
# Trade Review API Routes
# =====================================================================

def _get_review_db():
    """Lazy-load TradeJournalDB singleton."""
    if not hasattr(_get_review_db, "_db"):
        from quantsys.review.db_writer import TradeJournalDB
        _get_review_db._db = TradeJournalDB()
    return _get_review_db._db


@app.route("/api/trades/log", methods=["POST"])
def api_log_trade():
    """Log a manual trade."""
    symbol = (request.form.get("symbol") or request.args.get("symbol", "")).strip()
    direction = (request.form.get("direction") or request.args.get("direction", "BUY")).strip()
    price = float(request.form.get("price") or request.args.get("price", 0))
    quantity = int(request.form.get("quantity") or request.args.get("quantity", 0))
    reason = (request.form.get("reason") or request.args.get("reason", "")).strip()
    strategy = (request.form.get("strategy") or request.args.get("strategy", "")).strip()
    name = (request.form.get("name") or request.args.get("name", "")).strip()

    if not symbol:
        return jsonify({"error": "请输入代码"}), 400
    if not direction or direction not in ("BUY", "SELL"):
        return jsonify({"error": "方向必须为BUY或SELL"}), 400
    if price <= 0 or quantity <= 0:
        return jsonify({"error": "价格和数量必须大于零"}), 400

    db = _get_review_db()
    tid = db.log_trade(
        symbol=symbol, name=name, direction=direction,
        price=price, quantity=quantity, reason=reason, strategy=strategy,
    )
    return jsonify({"id": tid, "message": f"交易已记录: {direction} {symbol} {quantity}@{price}"})


@app.route("/api/trades/history")
def api_trades_history():
    """Get trade history."""
    days = int(request.args.get("days", 30))
    symbol = request.args.get("symbol", "").strip() or None
    db = _get_review_db()
    trades = db.get_trades(days=days, symbol=symbol)
    return jsonify({"trades": trades, "count": len(trades)})


@app.route("/api/review/daily")
def api_review_daily():
    """Generate daily review report."""
    date = request.args.get("date", "").strip() or None
    try:
        from quantsys.review.report_generator import ReportGenerator
        gen = ReportGenerator(db=_get_review_db())
        path = gen.generate_daily_report(date)
        return jsonify({"report_path": str(path), "message": "日报已生成"})
    except Exception as e:
        return jsonify({"error": f"生成日报失败: {e}"}), 500


@app.route("/api/review/weekly")
def api_review_weekly():
    """Generate weekly review report."""
    week_ending = request.args.get("date", "").strip() or None
    try:
        from quantsys.review.report_generator import ReportGenerator
        gen = ReportGenerator(db=_get_review_db())
        path = gen.generate_weekly_report(week_ending)
        return jsonify({"report_path": str(path), "message": "周报已生成"})
    except Exception as e:
        return jsonify({"error": f"生成周报失败: {e}"}), 500


# =====================================================================
# Pre-computed data (safe filesystem-only ops, no native libs)
# =====================================================================

_CACHED_STOCK_SYMBOLS = []  # filled from stock_daily/ parquet files
_stock_dir = _PROJECT_ROOT / "data" / "raw" / "stock_daily"
if _stock_dir.exists():
    _CACHED_STOCK_SYMBOLS = sorted([
        p.stem for p in _stock_dir.glob("*.parquet")
        if not p.name.startswith("._")
    ])


# =====================================================================
# Launcher
# =====================================================================

def _preload():
    """Eagerly import and warm up all heavy modules to avoid segfault from lazy
    native library initialization during the first Flask request.

    The native libs (pandas/numpy/pyarrow) must be fully initialized BEFORE
    Werkzeug's request loop starts accepting connections.  Lazy imports
    inside a request handler cause SIGSEGV (exit 139).
    """
    print("  预加载核心组件...")
    from quantsys.advisor.recommendation import RecommendationEngine  # noqa
    from quantsys.advisor.index_analyzer import IndexAnalyzer  # noqa
    from quantsys.advisor.position_tracker import PositionTracker  # noqa
    from quantsys.advisor.evaluator import StockEvaluator  # noqa
    from quantsys.advisor.portfolio_health import PortfolioHealthChecker  # noqa
    from quantsys.review.db_writer import TradeJournalDB  # noqa
    from quantsys.review.report_generator import ReportGenerator  # noqa
    TradeJournalDB().close()


def main():
    """Launch the desktop application."""
    port = 8520
    url = f"http://127.0.0.1:{port}"

    # Pre-load all native-heavy modules BEFORE starting the server
    # to prevent segfault from lazy imports during request handling
    _preload()

    # Auto-open browser after a short delay
    def open_browser():
        time.sleep(0.8)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()

    print(f"\n  📊 Quantsys Desktop · 量化评估辅助系统")
    print(f"  → {url}")
    print(f"  按 Ctrl+C 退出\n")

    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
