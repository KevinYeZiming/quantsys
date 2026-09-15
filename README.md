# 中国A股量化交易系统

Chinese A-Share & ETF Quantitative Trading System

基于《2024/25中国量化投资白皮书》、朱一峰《股票量化投资策略》（2025）等权威来源，从零搭建的实战量化交易框架。

## 核心策略

| 策略 | 描述 | 参考来源 |
|------|------|----------|
| **多因子选股** | 20因子IC-IR加权，行业/市值中性化，CSI 300/500选股 | 朱一峰(2025), QuantsPlaybook |
| **ETF轮动** | 动量排序+风险平价，核心-卫星结构，20只ETF标的池 | Pomelo-ETF, 中信证券 |
| **趋势跟踪** | 双均线+海龟突破，ATR仓位管理 | 经典CTA策略A股适配 |
| **行业轮动** | 申万行业+资金流+动量多维打分 | 国金证券, 广发证券 |

## 因子体系（20因子）

- **价值**：ROE, ROA, E/P, B/P, CF/P
- **动量**：12-1月动量, 60日动量, 短期反转
- **波动率**：特质波动率, 偏度, 振幅
- **流动性**：换手率, 量价相关性, Amihud非流动性
- **技术**：RSI, MACD背离, 均线偏离
- **另类**：聪明钱, 凸显理论(STR), 最大值效应

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 验证环境

```bash
python3 scripts/validate_setup.py
```

### 3. 获取数据

```bash
# 增量更新（推荐日常使用）
python3 scripts/update_data.py --incremental

# 全量历史数据下载
python3 scripts/update_data.py --full --start 20150101
```

### 4. 计算因子

```bash
python3 scripts/calc_factors.py
```

### 5. 运行回测

```bash
# 多因子选股回测
python3 scripts/run_backtest.py --strategy multifactor --start 2018-01-01 --end 2023-12-31

# ETF轮动回测
python3 scripts/run_backtest.py --strategy etf_rotation

# 趋势跟踪回测
python3 scripts/run_backtest.py --strategy trend_following --universe csi500
```

### 6. 生成交易信号

```bash
python3 scripts/generate_signals.py
```

## 因子有效性评估（主流单因子测试）

对标券商金工研究范式与 Alphalens 分析流水线：

```bash
# 全量评估：IC / RankIC / ICIR / IC衰减 / 十分位分层 / 换手率 / 相关性矩阵
python3 scripts/evaluate_factors.py --start 2022-01-01 --save-weights
```

- 报告输出：`reports/factor_evaluation.md`（总表+逐因子明细+相关性矩阵）
- `--save-weights` 生成 `data/factor_weights.csv`，多因子策略自动加载实现**真实 IC-IR 加权**（文件不存在时回退等权）

单项主流门槛：|RankIC| > 0.02，|ICIR| > 0.3，IC>0 占比 > 0.55，分层单调性 > 0.5。

## 基金 / 黄金数据与统一买卖评估

```bash
# 1. 更新基金（场外）与黄金（上金所现货+黄金ETF）数据，本地 Parquet 持久化
python3 scripts/update_assets.py --type fund     # 基金池见 config/assets.yaml
python3 scripts/update_assets.py --type gold

# 2. 统一买卖评估（股/基/金一致输出：动作+置信度+建议仓位+止损止盈）
python3 scripts/evaluate_assets.py --positions                  # 评估当前持仓
python3 scripts/evaluate_assets.py --symbols 600519,000858      # 个股
python3 scripts/evaluate_assets.py --fund 017103,110022         # 基金
python3 scripts/evaluate_assets.py --gold 518880,Au99.99        # 黄金
```

- 打分模型：动量 / 趋势 / 风险 / 位置 四维，各取**自身历史分位**（横截面缺失时单标的也可评估），权重与阈值见 `config/assets.yaml`
- 结果落盘：`data/evaluations/eval_*.parquet` + Markdown 报告

## Claude Code 技能

| 命令 | 功能 |
|------|------|
| `/quant-data` | 更新数据+计算因子 |
| `/quant-backtest <策略名>` | 运行回测+生成报告 |
| `/quant-signals` | 生成今日交易信号 |

## 可视化仪表盘

React + TypeScript + Tailwind 深色主题仪表盘（`dashboard/` 目录），可视化因子评估与买卖信号，可打包部署 GitHub Pages：

```bash
cd dashboard && npm install && npm run dev   # http://localhost:3000
```

数据链路：`evaluate_factors.py` → `evaluate_assets.py` → `export_dashboard_data.py` → `dashboard/src/data/dashboard.json`（已随仓库提交示例数据，clone 即见真实结果）。详见 [dashboard/README.md](dashboard/README.md)。

## A股适配特性

- **T+1交收**：当日买入次日才能卖出
- **印花税**：卖方0.05%（2023年8月起减半）
- **涨跌停限制**：主板±10%，科创/创业±20%
- **ST/新股/停牌过滤**：自动排除不适合交易的标的
- **交易日历**：含中国节假日（春节等）调整

## 项目结构

```
量化交易/
├── config/          # YAML配置（策略参数/因子定义/回测设置/风控/assets 资产池）
├── quantsys/        # 核心Python包
│   ├── data/        # 数据层（AKShare适配/缓存/日历/股票池/sources: funds·gold）
│   ├── factors/     # 因子库（20因子+注册/处理/中性化/evaluation 有效性评估）
│   ├── strategies/  # 策略引擎（4个策略，multifactor 支持真实 IC-IR 加权）
│   ├── backtest/    # 回测引擎（Backtrader封装）
│   ├── portfolio/   # 组合优化（风险平价/均值方差）
│   ├── risk/        # 风险管理（仓位/止损）
│   └── advisor/     # 决策层（个股横截面打分/asset_evaluator 股基金统一评估）
├── scripts/         # CLI脚本（含 evaluate_factors / update_assets / evaluate_assets）
├── notebooks/       # Jupyter研究笔记本
├── tests/           # 测试套件
└── docs/            # 文档（含 ASSESSMENT_AND_REVISION 评估修订报告）
```

## 数据源

使用 [AKShare](https://akshare.akfamily.xyz/) — 免费、开源、无需注册的金融数据接口。

数据以Parquet格式存储在 `data/raw/` 目录下，元数据存储在 SQLite (`data/metadata.db`)。

## 回测配置

默认回测设置（可在 `config/backtest.yaml` 中调整）：
- 初始资金：100万元
- 佣金：0.025%
- 印花税：0.05%（卖方）
- 无风险利率：1.5%（1年期Shibor）

## License

MIT
