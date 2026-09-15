# 系统架构

## 整体架构

```
┌─────────────────────────────────────────────────┐
│                  CLI / Claude Skills              │
│  /quant-data   /quant-backtest   /quant-signals  │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              策略引擎 (Strategy Engine)           │
│  MultiFactor  ETFRotation  TrendFollow  Industry │
└────────┬────────────────────────────┬───────────┘
         │                            │
┌────────▼──────────┐    ┌───────────▼───────────┐
│   因子库 (Factors) │    │  回测引擎 (Backtest)    │
│  20 factors       │    │  Backtrader + AShare   │
│  Registry         │    │  Broker / Reporter     │
│  Processor        │    └───────────────────────┘
│  Neutralizer      │
└────────┬──────────┘
         │
┌────────▼──────────┐
│   数据层 (Data)    │
│  AKShare Source   │
│  Cache (Parquet)  │
│  Calendar         │
│  Universe Builder │
└───────────────────┘
```

## 数据流

```
AKShare API → DataSource → CacheManager → Parquet/SQLite
                                              │
                    Factor Engine ←───────────┘
                         │
                    FactorRegistry.compute_all()
                         │
                    FactorProcessor (去极值/标准化)
                         │
                    FactorNeutralizer (行业/市值中性化)
                         │
                    Strategy.generate_signals()
                         │
                    BacktestEngine.run()
                         │
                    ReportGenerator → HTML Report
```

## 模块职责

### data/ — 数据层
- **sources/akshare.py**: AKShare API适配，获取A股/ETF/指数/财报数据
- **cache.py**: Parquet缓存，增量更新去重
- **fetcher.py**: 数据下载编排器
- **calendar.py**: A股交易日历（含中国节假日）
- **universe.py**: 构建可交易股票池（排除ST/新股/停牌）
- **cleaner.py**: 数据清洗（去极值/检测错误数据）

### factors/ — 因子库
- **base.py**: 抽象因子基类
- **registry.py**: 因子注册与自动发现
- **value.py/momentum.py/volatility.py/liquidity.py/technical.py/alternative.py**: 6类20因子
- **processor.py**: 因子预处理（去极值/标准化/缺值填充）
- **neutralizer.py**: 行业和市值中性化（截面回归残差法）

### strategies/ — 策略引擎
- **base.py**: 策略基类接口
- **multifactor.py**: IC加权多因子选股
- **etf_rotation.py**: 动量ETF轮动+风险平价
- **trend_following.py**: 双均线+海龟突破趋势跟踪
- **industry_rotation.py**: 行业资金流轮动

### backtest/ — 回测引擎
- **broker.py**: A股费率模型（T+1/印花税/佣金）
- **datafeed.py**: Backtrader数据源适配
- **engine.py**: Backtrader Cerebro封装
- **reporter.py**: HTML回测报告（权益曲线/回撤/月度收益）

### portfolio/ — 组合优化
- **risk_parity.py**: 风险平价（含HRP）
- **mean_variance.py**: 均值方差（to be added）
- **rebalance.py**: 调仓计划

### risk/ — 风险管理
- **position_sizer.py**: 仓位管理（等权/波动率目标/Kelly）
- **stop_loss.py**: 止损规则（跟踪/ATR/时间）
