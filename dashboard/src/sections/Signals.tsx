import { Radar, RadarChart, PolarGrid, PolarAngleAxis, ResponsiveContainer, Tooltip } from 'recharts'
import { AlertTriangle } from 'lucide-react'
import type { DashboardData } from '@/types/dashboard'
import { ActionBadge, ASSET_LABEL, Card, FmtPct, ScoreRing } from '@/components/bits'

const tooltipStyle = {
  background: '#18181b', border: '1px solid #27272a', borderRadius: 8,
  fontSize: 12, color: '#e4e4e7', boxShadow: '0 8px 24px rgba(0,0,0,.5)',
}

export function Signals({ data }: { data: DashboardData }) {
  const evals = data.evaluations
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {evals.map((e) => {
          const radar = [
            { dim: '动量', v: e.momentum_score ?? 50 },
            { dim: '趋势', v: e.trend_score ?? 50 },
            { dim: '风险', v: e.risk_score ?? 50 },
            { dim: '位置', v: e.position_score ?? 50 },
          ]
          return (
            <Card key={e.symbol} className="overflow-hidden">
              <div className="flex items-center justify-between border-b border-zinc-800/80 px-5 py-4">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-zinc-100">{e.name || e.symbol}</p>
                  <p className="mt-0.5 text-xs text-zinc-500">
                    {e.symbol} · {ASSET_LABEL[e.asset_type] ?? e.asset_type} · 数据截至 {e.m_as_of ?? e.date}
                  </p>
                </div>
                <ActionBadge action={e.action} />
              </div>

              <div className="flex items-center gap-4 px-5 py-4">
                <ScoreRing score={e.total_score ?? 50} size={72} />
                <div className="h-28 flex-1">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart data={radar} outerRadius="72%">
                      <PolarGrid stroke="#27272a" />
                      <PolarAngleAxis dataKey="dim" tick={{ fill: '#a1a1aa', fontSize: 11 }} />
                      <Tooltip contentStyle={tooltipStyle} />
                      <Radar dataKey="v" stroke="#10b981" fill="#10b981" fillOpacity={0.25} isAnimationActive={false} />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 border-t border-zinc-800/80 px-5 py-3 text-center text-xs">
                <div>
                  <p className="text-zinc-500">现价</p>
                  <p className="mt-0.5 font-bold tabular-nums text-zinc-100">{e.price ?? '—'}</p>
                </div>
                <div>
                  <p className="text-zinc-500">止损参考</p>
                  <p className="mt-0.5 font-bold tabular-nums text-rose-400">{e.stop_loss ?? '—'}</p>
                </div>
                <div>
                  <p className="text-zinc-500">止盈参考</p>
                  <p className="mt-0.5 font-bold tabular-nums text-emerald-400">{e.take_profit ?? '—'}</p>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 border-t border-zinc-800/80 px-5 py-3 text-center text-xs">
                <div>
                  <p className="text-zinc-500">20日涨跌</p>
                  <p className="mt-0.5"><FmtPct v={e.m_ret_20d} /></p>
                </div>
                <div>
                  <p className="text-zinc-500">RSI(14)</p>
                  <p className="mt-0.5 font-bold tabular-nums text-zinc-100">{(e.m_rsi ?? 0).toFixed(0)}</p>
                </div>
                <div>
                  <p className="text-zinc-500">距52周高点</p>
                  <p className="mt-0.5"><FmtPct v={e.m_dd_from_high} /></p>
                </div>
              </div>

              <div className="space-y-1.5 border-t border-zinc-800/80 px-5 py-4 text-xs leading-relaxed">
                {e.reasons.map((r, i) => (
                  <p key={i} className="text-zinc-400">· {r}</p>
                ))}
                {e.risk_flags.map((f, i) => (
                  <p key={`f${i}`} className="flex items-start gap-1.5 text-rose-400">
                    <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> {f}
                  </p>
                ))}
                <p className="pt-1 text-zinc-600">
                  置信度 {((e.confidence ?? 0) * 100).toFixed(0)}% · 建议仓位 {(e.target_weight ?? 0) > 0
                    ? `${((e.target_weight ?? 0) * 100).toFixed(0)}%` : '0（清仓）'}
                </p>
              </div>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
