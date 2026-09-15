// Shared types for the bundled dashboard.json

export interface FactorRow {
  factor: string
  n_days: number | null
  ic_mean: number | null
  ic_std: number | null
  icir: number | null
  ic_tstat: number | null
  ic_pos_ratio: number | null
  rank_ic_mean: number | null
  rank_ic_std: number | null
  rank_icir: number | null
  rank_ic_pos_ratio: number | null
  long_short_ann: number | null
  monotonicity: number | null
  turnover: number | null
  coverage: number | null
  grade: string
  score: number | null
  rank_ic_1d: number | null
  rank_ic_3d: number | null
  rank_ic_5d: number | null
  rank_ic_10d: number | null
  rank_ic_20d: number | null
}

export interface FactorDetail {
  decay: Record<string, number | null>
  quantile_means: (number | null)[]
  ic_series: (number | null)[]
}

export interface Correlation {
  labels: string[]
  values: (number | null)[][]
}

export interface Evaluation {
  symbol: string
  asset_type: string
  date: string
  name: string
  price: number | null
  momentum_score: number | null
  trend_score: number | null
  risk_score: number | null
  position_score: number | null
  total_score: number | null
  action: string
  confidence: number | null
  target_weight: number | null
  stop_loss: number | null
  take_profit: number | null
  reasons: string[]
  risk_flags: string[]
  // flattened metrics (m_ prefix)
  m_ret_5d?: number | null
  m_ret_20d?: number | null
  m_ret_60d?: number | null
  m_rsi?: number | null
  m_ann_vol?: number | null
  m_dd_from_high?: number | null
  m_range_position?: number | null
  m_ma20?: number | null
  m_ma60?: number | null
  m_pnl_pct?: number | null
  m_avg_cost?: number | null
  m_as_of?: string
  [key: string]: unknown
}

export interface Position {
  symbol: string
  name: string
  asset_type: string
  quantity: number
  avg_cost: number
  added_date: string
}

export interface DashboardData {
  generated_at: string
  factor_summary: FactorRow[]
  factor_details: Record<string, FactorDetail>
  factor_correlation: Correlation | null
  evaluations: Evaluation[]
  positions: Position[]
}
