# 因子库文档

## 因子列表

### 价值因子 (Value)

| 因子 | 类名 | 公式 | 方向 | 参考 |
|------|------|------|------|------|
| ROE(TTM) | ROEFactor | 净利润(TTM) / 平均净资产 | + | Fama-French, Zhu 2025 |
| ROA(TTM) | ROAFactor | 净利润(TTM) / 平均总资产 | + | Piotroski |
| E/P | EPFactor | 1 / PE(TTM) | + | Fama-French |
| B/P | BPFactor | 1 / PB | + | Fama-French, Zhu 2025 |
| CF/P | CFPFactor | 经营现金流 / 总市值 | + | Lakonishok |

### 动量/反转因子 (Momentum)

| 因子 | 类名 | 公式 | 方向 | 参考 |
|------|------|------|------|------|
| 12-1月动量 | Momentum12M1M | 过去12个月（跳过最近1月）累计收益 | + | Jegadeesh & Titman |
| 60日动量 | Momentum60D | 过去60个交易日收益 | + | QuantsPlaybook |
| 短期反转 | ShortTermReversal | -5日收益 | + | Lehmann |

### 波动率因子 (Volatility)

| 因子 | 类名 | 公式 | 方向 | 参考 |
|------|------|------|------|------|
| 特质波动率 | IdioVolatility | -Std(CAPM残差) | 低波动异象 | Ang et al., Zhu 2025 |
| 收益率偏度 | VolatilitySkew | -日收益偏度 | 负偏度溢价 | QuantsPlaybook |
| 振幅 | Amplitude20D | -Avg((高-低)/收) | 低振幅溢价 | 券商研报 |

### 流动性因子 (Liquidity)

| 因子 | 类名 | 公式 | 方向 | 参考 |
|------|------|------|------|------|
| 换手率 | Turnover20D | -Avg(20日换手率) | 低换手溢价 | QuantsPlaybook |
| 量价相关性 | VolumeCorrelation | Corr(成交量变化, 收益) | + | QuantsPlaybook |
| Amihud非流动 | AmihudIlliq | Avg(|r|/成交额) | 流动性溢价 | Amihud 2002 |

### 技术因子 (Technical)

| 因子 | 类名 | 公式 | 方向 | 参考 |
|------|------|------|------|------|
| RSI | RSIFactor | -14日RSI | 反转信号 | Wilder |
| MACD背离 | MACDDivergence | (MACD-信号线)/价格 | + | QuantsPlaybook |
| 均线偏离 | MADeviation | (收-MA60)/MA60 | + | 券商研报 |

### 另类因子 (Alternative)

| 因子 | 类名 | 公式 | 方向 | 参考 |
|------|------|------|------|------|
| 聪明钱 | SmartMoneyFlow | 大单资金流/成交额 | + | QuantsPlaybook |
| STR | SalienceTheory | -|zscore(收益)| | 负向 | Bordalo et al., Zhu 2025 |
| 最大值效应 | MaxEffect | -Max(20日收益) | 负向 | Bali et al. |

## 因子处理流程

```
原始因子值
  │
  ▼
去极值 (Winsorize 1%/99%分位数)
  │
  ▼
缺值填充 (截面中位数)
  │
  ▼
中性化 (行业+市值回归取残差)
  │
  ▼
标准化 (截面Z-score)
  │
  ▼
IC-IR加权合成
```

## IC分析

IC (Information Coefficient): 因子值与未来收益的截面相关系数。

- Pearson IC: 正态IC
- Spearman IC (RankIC): 排序IC，更稳健

IR (Information Ratio) = mean(IC) / std(IC)，衡量因子稳定性。
