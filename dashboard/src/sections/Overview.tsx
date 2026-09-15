import { useMemo } from 'react'
import {
  Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import type { DashboardData } from '@/types/dashboard'
import { ActionBadge, Card, CardHeader, StatCard, GRADE_STYLE } from '@/components/bits'

const tooltipStyle = {
  background: '#18181b', border: '1px solid #27272a', borderRadius: 8,
  fontSize: 12, color: '#e4e4e7', boxShadow: '0 8px 24px rgba(0,0,0,.5)',
}

export function Overview({ data, onGoFactors, onGoSignals }: {
  data: DashboardData
  onGoFactors: () => void
  onGoSignals: () => void
}) {
  const factors = data.factor_summary
  const evals = data.evaluations

  const grades = useMemo(() => {
    const g: Record<string, number> = { A: 0, B: 0, C: 0, D: 0 }
    factors.forEach((f) => { g[f.grade] = (g[f.grade] ?? 0) + 1 })
    return (['A', 'B', 'C', 'D'] as const)
      .filter((k) => g[k] > 0)
      .map((k) => ({ name: `${k} 级`, value: g[k], fill: GRADE_STYLE[k].bar }))
  }, [factors])

  const topFactors = useMemo(
    () => [...factors].sort((a, b) => (b.score ?? 0) - (a.score ?? 0)).slice(0, 8),
    [factors],
  )

  const actionDist = useMemo(() => {
    const m = new Map<string, number>()
    evals.forEach((e) => m.set(e.action, (m.get(e.action) ?? 0) + 1))
    const colors: Record<string, string> = {
      strong_buy: '#059669', buy: '#10b981', hold: '#71717a',
      sell: '#f43f5e', strong_sell: '#be123c',
    }
    return [...m.entries()].map(([k, v]) => ({ name: k, value: v, fill: colors[k] ?? '#71717a' }))
  }, [evals])

  const buys = evals.filter((e) => e.action === 'buy' || e.action === 'strong_buy').length
  const sells = evals.filter((e) => e.action === 'sell' || e.action === 'strong_sell').length

  return (
    <div className="space-y-6">
      {/* KPI row */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="评估因子数" value={String(factors.length)}
          sub={`${factors.filter((f) => f.grade === 'A' || f.grade === 'B').length} 个 A/B 级有效因子`} />
        <StatCard label="持仓/标的评估" value={String(evals.length)}
          sub={`买入信号 ${buys} · 卖出信号 ${sells}`}
          accent={sells > buys ? '#f43f5e' : '#10b981'} />
        <StatCard label="最优因子 RankIC" value={(topFactors[0]?.rank_ic_mean ?? 0).toFixed(3)}
          sub={topFactors[0]?.factor ?? '—'} accent="#10b981" />
        <StatCard label="数据生成时间" value={data.generated_at.slice(5, 16)}
          sub="scripts/export_dashboard_data.py" />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Top factors */}
        <Card className="lg:col-span-2">
          <CardHeader title="因子得分榜 TOP 8" sub="综合评级分数（IC强度·稳定性·一致性·单调性）"
            right={<button onClick={onGoFactors}
              className="text-xs text-emerald-400 hover:text-emerald-300">进入因子实验室 →</button>} />
          <div className="h-72 px-2 py-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={topFactors} layout="vertical" margin={{ left: 16, right: 24 }}>
                <XAxis type="number" domain={[0, 100]} tick={{ fill: '#71717a', fontSize: 11 }} axisLine={{ stroke: '#27272a' }} tickLine={false} />
                <YAxis type="category" dataKey="factor" width={130}
                  tick={{ fill: '#a1a1aa', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'rgba(255,255,255,.03)' }}
                  formatter={(v: number, name: string) => [v?.toFixed(1), name === 'score' ? '得分' : name]} />
                <Bar dataKey="score" radius={[0, 4, 4, 0]} isAnimationActive={false} label={{ position: 'right', fill: '#71717a', fontSize: 10 }}>
                  {topFactors.map((f) => (
                    <Cell key={f.factor} fill={GRADE_STYLE[f.grade]?.bar ?? '#71717a'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Grade donut + action donut */}
        <Card>
          <CardHeader title="因子评级分布" sub="A 强 alpha · D 无效/反向" />
          <div className="flex h-40 items-center justify-center">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={grades} dataKey="value" isAnimationActive={false} innerRadius={44} outerRadius={66}
                  paddingAngle={3} strokeWidth={0}>
                  {grades.map((g) => <Cell key={g.name} fill={g.fill} />)}
                </Pie>
                <Tooltip contentStyle={tooltipStyle} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex justify-center gap-4 pb-4 text-xs text-zinc-400">
            {grades.map((g) => (
              <span key={g.name} className="flex items-center gap-1.5">
                <i className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: g.fill }} />
                {g.name} × {g.value}
              </span>
            ))}
          </div>
          <div className="border-t border-zinc-800/80 px-5 py-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">当前信号分布</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {actionDist.map((a) => (
                <span key={a.name} className="flex items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1 text-xs text-zinc-300">
                  <i className="inline-block h-2 w-2 rounded-full" style={{ background: a.fill }} />
                  <ActionBadge action={a.name} /> {a.value}
                </span>
              ))}
            </div>
          </div>
        </Card>
      </div>

      {/* Latest signals strip */}
      <Card>
        <CardHeader title="最新买卖评估" sub={`${evals[0]?.date ?? '—'} · 股/基/金统一四维打分（动量·趋势·风险·位置）`}
          right={<button onClick={onGoSignals}
            className="text-xs text-emerald-400 hover:text-emerald-300">查看全部 →</button>} />
        <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
          {evals.slice(0, 6).map((e) => {
            const Icon = e.action.includes('buy') ? ArrowUpRight
              : e.action.includes('sell') ? ArrowDownRight : Minus
            return (
              <div key={e.symbol} className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/80 px-4 py-3">
                <Icon className="h-4 w-4 shrink-0"
                  color={e.action.includes('buy') ? '#10b981' : e.action.includes('sell') ? '#f43f5e' : '#71717a'} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-zinc-100">{e.name || e.symbol}</p>
                  <p className="text-xs text-zinc-500">{e.symbol} · {e.asset_type}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-bold tabular-nums text-zinc-100">{(e.total_score ?? 0).toFixed(0)}<span className="text-[10px] text-zinc-500">分</span></p>
                  <ActionBadge action={e.action} />
                </div>
              </div>
            )
          })}
        </div>
      </Card>
    </div>
  )
}
