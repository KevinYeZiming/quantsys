# 系统评估与修订报告

> 评估对象：`/Volumes/ZimingYe/量化交易`（Quantsys · 中国 A 股量化交易系统）
> 评估日期：2026-09-15
> 对照基准：聚宽（JoinQuant）/ 米筐（RiceQuant）研究范式、Alphalens 因子分析框架、Qlib 因子流水线、券商金工研报方法论（东方证券《因子选股系列》、光大证券单因子测试体系）

---

## 一、总体结论

系统架构清晰、工程完成度高，作为"数据 → 因子 → 策略 → 回测 → 复盘"的闭环框架已经合格；但**距离主流量化研究平台有三个结构性缺口**：

1. **因子层"重计算、轻评估"** —— 20 个因子只做了预处理（去极值/标准化/中性化），没有任何 IC / RankIC / ICIR / 分层回测 / 换手率 / 衰减分析，无法回答"这个因子到底有没有 alpha、多久衰减、该不该进组合"。`multifactor` 策略配置了 `factor_weights: "ic_ir"`，实际代码 fallback 为等权——**IC-IR 加权是名不副实的**。
2. **资产覆盖不全** —— 只有 A 股个股 + ETF。场外基金（申赎型）数据只在持仓追踪器里零散获取，黄金只有轮动池里的一只 518880 ETF，**均没有体系化的数据保存与独立评估**。
3. **买卖评估单一** —— 评估器只面向"1 万元、主板、最多 2 只"的小资金股票场景，基金与黄金没有打分与买卖信号。

本次修订针对这三个缺口实施（见第三部分），其余优点保留不动。

---

## 二、优点与缺点详评

### 2.1 优点（值得保留）

| # | 优点 | 证据 |
|---|------|------|
| 1 | 分层架构规范：data / factors / strategies / backtest / portfolio / risk / advisor / review 职责清晰 | `quantsys/` 目录结构、`docs/architecture.md` |
| 2 | 因子库覆盖六大类 20 因子，预处理流水线（MAD 去极值、横截面中位数填充、行业/市值中性化）符合券商金工规范 | `factors/processor.py`、`factors/neutralizer.py`、`config/factors.yaml` |
| 3 | A 股交易制度适配完整：T+1、印花税 0.05%、涨跌停、ST/新股/停牌过滤、节假日交易日历 | `README.md`、`config/backtest.yaml`、`data/calendar.py` |
| 4 | 数据层有 Parquet 缓存 + 增量更新 + 限流重试，工程化程度高 | `data/sources/cache.py`、`scripts/update_data.py` |
| 5 | advisor 层采用横截面百分位打分（而非绝对阈值），方法论正确 | `advisor/evaluator.py` |
| 6 | 复盘体系：SQLite 交易日志 + 报告生成，形成闭环 | `review/trade_logger.py`、`data/trade_journal.db` |
| 7 | 有 Streamlit Dashboard 和 FastAPI，具备人机交互界面 | `web/`、`api/server.py` |
| 8 | 指标库含 IC、夏普、卡玛、索提诺、最大回撤等基础指标 | `utils/metrics.py` |

### 2.2 缺点（对照主流标准）

| # | 缺口 | 严重度 | 说明 |
|---|------|--------|------|
| 1 | **无因子有效性评估** | ★★★★★ | 没有 IC/RankIC 时间序列、ICIR、IC>0 占比、分层十分位收益与多空价差、换手率、因子衰减（horizon）、因子相关性矩阵。`scripts/` 下没有任何 `evaluate_*` 脚本 |
| 2 | **IC-IR 加权名不副实** | ★★★★ | `strategies/multifactor.py:148-149` 注释写明 "Default to equal weight if IC data is not available"，即永远走等权分支 |
| 3 | **基本面因子实际不可用** | ★★★ | ROE/ROA/E/P/B/P/CF/P 依赖财务数据，但 `data/raw/financials/` 为空、抓取接口 `stock_financial_abstract_ths` 无缓存落盘逻辑 |
| 4 | **基金数据无体系** | ★★★★ | 场外基金 NAV 只在 `position_tracker.py` 内部临时抓取缓存，无独立数据源类、无批量保存、无净值以外的信息（累计净值/分红/规模/费率） |
| 5 | **黄金数据无体系** | ★★★★ | 黄金只有 ETF 轮动池的 518880；无上海金交所现货（AU9999 等）、无伦敦金代理、无黄金 ETF 篮子的统一保存 |
| 6 | **买卖评估只覆盖主板股票** | ★★★★ | `advisor/recommendation.py` 限 600/000/002、限股价 ≤100、限 1 万资金；基金/黄金无打分、无信号 |
| 7 | **因子冗余无处理** | ★★★ | 20 因子内相关性高（如 turnover/volume_corr/Amihud 同属流动性，momentum_12m/60d 同属动量），等权组合会重复暴露同一风险 |
| 8 | **无未来函数防护** | ★★★ | 因子计算直接在全 panel 上 rolling，虽然 rolling 本身安全，但无显式的 point-in-time 校验、无财报公告日对齐（PIT 数据库缺失） |
| 9 | **数据质量监控薄弱** | ★★ | 有 cleaner 但无缺失率/复权一致性/停牌完整性报告 |
| 10 | **ml 模块为空占位** | ★★ | `quantsys/ml/` 只有空 `__init__.py` |
| 11 | **测试覆盖薄** | ★★ | 仅 4 个测试文件，且均为数据层小测 |

---

## 三、本次修订内容

### 3.1 新增：主流因子评估框架（对应缺口 1、2、7）

| 文件 | 内容 |
|------|------|
| `quantsys/factors/evaluation.py` | `FactorEvaluator`：日度 Pearson IC / Spearman RankIC 序列、IC 均值/标准差/ICIR、IC>0 占比、t 统计量；十分位分层收益与多空价差（Q1-Q10）、分层单调性；因子换手率（排名稳定性）；IC 衰减（1/3/5/10/20 日前瞻）；因子相关性矩阵；综合评分表与 Markdown 报告 |
| `scripts/evaluate_factors.py` | CLI：跑全部启用因子 → 输出汇总 CSV + 逐因子明细 + `reports/factor_evaluation.md`；`--save-weights` 生成 IC-IR 权重文件供策略加载 |

**多因子策略接入真实权重**：`MultiFactorStrategy` 新增 `weights_path` 参数，存在权重文件时按 `mean_icir / Σ|mean_icir|` 加权，并对高相关因子簇做冗余降权；不存在时保持原等权行为（向后兼容）。

### 3.2 新增：基金数据获取与保存（对应缺口 4）

| 文件 | 内容 |
|------|------|
| `quantsys/data/sources/funds.py` | `FundSource`：场外基金单位净值/累计净值（`fund_open_fund_info_em`）、基金概况（类型/成立日/规模/费率，`fund_individual_basic_info_xq`），统一列名后存入 `fund_nav` / `fund_info` 缓存类型，支持增量更新 |
| `scripts/update_assets.py --type fund` | 批量更新 `config/assets.yaml` 中的基金列表 |

### 3.3 新增：黄金数据获取与保存（对应缺口 5）

| 文件 | 内容 |
|------|------|
| `quantsys/data/sources/gold.py` | `GoldSource`：上金所现货（AU9999 等，`spot_hist_sge`）、黄金 ETF 行情（复用 ETF 接口）、人民币汇率参考，存入 `gold_spot` / `gold_etf` 缓存类型，支持增量更新 |
| `scripts/update_assets.py --type gold` | 批量更新黄金标的 |

### 3.4 新增：股/基/金统一买卖评估器（对应缺口 6）

| 文件 | 内容 |
|------|------|
| `quantsys/advisor/asset_evaluator.py` | `AssetEvaluator`：对 stock / fund / gold 三类资产统一执行 趋势-动量-波动-位置 四维打分（横截面 + 时序双模式），输出 strong_buy/buy/hold/sell/strong_sell、建议仓位、止损止盈参考、理由；评估结果落盘 `data/evaluations/` 与 `reports/asset_evaluation.md` |
| `scripts/evaluate_assets.py` | CLI：评估持仓（`data/positions.json`）或任意标的列表 |

### 3.5 配置与测试

- `config/assets.yaml`：基金自选池、黄金标的池、评估参数（权重/阈值/止损）
- `tests/test_factor_evaluation.py`、`tests/test_asset_evaluator.py`：合成数据测试，不依赖网络
- `requirements.txt`：无新增硬依赖（沿用 akshare/pandas/scipy）

---

## 四、修订后的使用方式

```bash
# 1. 更新数据（股票/ETF 原有流程不变）
python3 scripts/update_data.py --incremental

# 2. 新增：更新基金与黄金数据
python3 scripts/update_assets.py --type fund
python3 scripts/update_assets.py --type gold

# 3. 新增：因子有效性评估（输出 IC/ICIR/分层/换手/衰减报告）
python3 scripts/evaluate_factors.py --start 2022-01-01 --save-weights

# 4. 多因子选股（自动加载上一步生成的 IC-IR 权重）
python3 scripts/run_backtest.py --strategy multifactor --start 2022-01-01

# 5. 新增：持仓/自选标的买卖评估（股/基/金统一）
python3 scripts/evaluate_assets.py --positions
python3 scripts/evaluate_assets.py --symbols 600519,518880,017103
```

---

## 五、遗留建议（超出本次范围）

1. **PIT 财务数据库**：基本面因子要真正可用，需要搭建 point-in-time 财报库（公告日对齐），建议接入 Tushare Pro 或 CSMAR。
2. **组合归因**：回测层补 Brinson 归因与风格暴露分析（对标聚宽/绩效分析报告）。
3. **ML 模块**：`quantsys/ml/` 目前为空，可引入 LightGBM 因子合成与特征重要性分析（对标 Qlib 的 Alpha158 + LGBM 流水线）。
4. **实盘对接**：`broker/galaxy_qmt.py` 建议补模拟盘 paper-trading 模式做上线前验证。

---

## 六、修订验证记录（2026-09-15 在本工作区副本执行）

| 验证项 | 命令 | 结果 |
|--------|------|------|
| 全部测试（18 个原有 + 18 个新增） | `pytest tests/ -q` | **36 passed** |
| 因子评估全流程（20 只真实缓存股票，2022-01 起） | `scripts/evaluate_factors.py --start 2022-01-01 --min-cross-section 10 --save-weights` | 20 因子全部出分；`reports/factor_evaluation.md`、`factor_evaluation_summary.csv`、`factor_correlation.csv`、`data/factor_weights.csv` 均生成 |
| IC-IR 权重接入与回退 | 构造 `MultiFactorStrategy(weights_path=...)` | 权重正确归一化并剔除负 IR 因子；文件缺失时回退等权并告警 |
| 持仓买卖评估（6 只真实 ETF 持仓） | `scripts/evaluate_assets.py --positions` | 输出动作/置信度/仓位/止损止盈；落盘 `data/evaluations/eval_20260915_192138.parquet/.md/.json` |

**真实数据下的初步发现**（20 只股票小样本，仅供参考）：凸显理论（STR）与最大值效应因子 RankIC≈0.06、单调性≈0.9 为最优；RSI 与 60 日动量呈显著反向（A 股反转特征），应在组合中反向使用或剔除；5 个价值因子因无财务数据全部空值——与评估报告缺口 #3 一致，建议优先补 PIT 财务库。

**未验证项**：`scripts/update_assets.py` 的实盘网络抓取（本环境无 akshare/网络），其列名归一化与增量更新逻辑已由 mock 测试覆盖（`test_fund_nav_normalization`、`test_fund_info_transpose`、`test_gold_spot_normalization`）。
