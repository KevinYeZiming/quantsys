import { useMemo, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis, ScatterChart, Scatter, ZAxis, Cell,
} from 'recharts'
import type { DashboardData, FactorRow } from '@/types/dashboard'
import { CorrelationHeatmap } from '@/components/CorrelationHeatmap'
import { Card, CardHeader, GradeBadge } from '@/components/bits'

const tooltipStyle = {
  background: '#18181b', border: '1px solid #27272a', borderRadius: 8,
  fontSize: 12, color: '#e4e4e7', boxShadow: '0 8px 24px rgba(0,0,0,.5)',
}

const GREEN = '#10b981'
const RED = '#f43f5e'

export function FactorLab({ data }: { data: DashboardData }) {
  const factors = data.factor_summary
  const [selected, setSelected] = useState<string>(factors[0]?.factor ?? '')

  const row = useMemo(() => factors.find((f) => f.factor === selected), [factors, selected])
  const detail = data.factor_details[selected]

  const decayData = useMemo(() => {
    if (!detail) return []
    return Object.entries(detail.decay).map(([h, v]) => ({ h: `${h}日`, v }))
  }, [detail])

  const quantileData = useMemo(() => {
    if (!detail) return []
    const n = detail.quantile_means.length
    return detail.quantile_means.map((v, i) => ({
      q: `Q${i + 1}${i === 0 ? '·低' : i === n - 1 ? '·高' : ''}`, v,
    }))
  }, [detail])

  const icSeries = useMemo(() => {
    if (!detail) return []
    return detail.ic_series.map((v, i) => ({ i, v }))
  }, [detail])

  // scatter: rank_ic_mean (x) vs rank_icir (y), bubble = score
  const scatterData = useMemo(() => factors
    .filter((f) => f.rank_ic_mean != null && f.rank_icir != null)
    .map((f) => ({
      name: f.factor, x: f.rank_ic_mean, y: f.rank_icir,
      z: Math.max(f.score ?? 10, 8), grade: f.grade,
    })), [factors])

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-5">
        {/* Factor table */}
        <Card className="overflow-hidden lg:col-span-2">
          <CardHeader title="因子总表" sub="按综合得分降序 · 点击行查看明细" />
          <div className="max-h-[560px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-zinc-900 text-[11px] uppercase tracking-wider text-zinc-500">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">因子</th>
                  <th className="px-2 py-2 text-right font-medium">RankIC</th>
                  <th className="px-2 py-2 text-right font-medium">ICIR</th>
                  <th className="px-2 py-2 text-right font-medium">单调</th>
                  <th className="px-3 py-2 text-right font-medium">级</th>
                </tr>
              </thead>
              <tbody>
                {factors.map((f: FactorRow) => (
                  <tr key={f.factor}
                    onClick={() => setSelected(f.factor)}
                    className={`cursor-pointer border-t border-zinc-800/60 transition-colors ${
                      selected === f.factor ? 'bg-emerald-500/10' : 'hover:bg-zinc-800/40'
                    }`}>
                    <td className="px-4 py-2 font-mono text-xs text-zinc-200">{f.factor}</td>
                    <td className={`px-2 py-2 text-right tabular-nums text-xs ${
                      (f.rank_ic_mean ?? 0) > 0.02 ? 'text-emerald-400' : (f.rank_ic_mean ?? 0) < -0.02 ? 'text-rose-400' : 'text-zinc-400'
                    }`}>{f.rank_ic_mean == null ? '—' : f.rank_ic_mean.toFixed(3)}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-xs text-zinc-300">{f.rank_icir == null ? '—' : f.rank_icir.toFixed(2)}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-xs text-zinc-300">{f.monotonicity == null ? '—' : f.monotonicity.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right"><GradeBadge grade={f.grade} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Detail panel */}
        <div className="space-y-6 lg:col-span-3">
          <Card>
            <CardHeader title={`${selected} · 明细`}
              sub="RankIC 时序 / IC 衰减 / 十分位分层收益"
              right={row && <GradeBadge grade={row.grade} />} />
            <div className="grid gap-6 p-5 md:grid-cols-3">
              <div className="md:col-span-3">
                <p className="mb-2 text-xs font-medium text-zinc-500">日度 RankIC 序列（抽样）</p>
                <div className="h-28">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={icSeries}>
                      <CartesianGrid stroke="#27272a" strokeDasharray="3 3" vertical={false} />
                      <XAxis hide dataKey="i" />
                      <YAxis tick={{ fill: '#71717a', fontSize: 10 }} width={40} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [v?.toFixed(4), 'RankIC']} labelFormatter={() => ''} />
                      <ReferenceLine y={0} stroke="#3f3f46" />
                      <Line type="monotone" dataKey="v" stroke={GREEN} dot={false} strokeWidth={1.5}
                        connectNulls isAnimationActive={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
              <div className="md:col-span-1">
                <p className="mb-2 text-xs font-medium text-zinc-500">IC 衰减（前瞻 1-20 日）</p>
                <div className="h-40">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={decayData}>
                      <CartesianGrid stroke="#27272a" strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="h" tick={{ fill: '#71717a', fontSize: 10 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fill: '#71717a', fontSize: 10 }} width={36} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [v?.toFixed(4), 'RankIC']} />
                      <Bar dataKey="v" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                        {decayData.map((d, i) => <Cell key={i} fill={(d.v ?? 0) >= 0 ? GREEN : RED} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
              <div className="md:col-span-2">
                <p className="mb-2 text-xs font-medium text-zinc-500">
                  十分位分层平均前瞻收益（单调性 {(row?.monotonicity ?? 0).toFixed(2)}）
                </p>
                <div className="h-40">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={quantileData}>
                      <CartesianGrid stroke="#27272a" strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="q" tick={{ fill: '#71717a', fontSize: 10 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fill: '#71717a', fontSize: 10 }} width={44} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [v == null ? '—' : `${(v * 100).toFixed(3)}%`, '收益']} />
                      <ReferenceLine y={0} stroke="#3f3f46" />
                      <Bar dataKey="v" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                        {quantileData.map((d, i) => <Cell key={i} fill={(d.v ?? 0) >= 0 ? GREEN : RED} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
            {/* metric chips */}
            <div className="flex flex-wrap gap-2 border-t border-zinc-800/80 px-5 py-3 text-xs">
              {[
                ['IC 均值', row?.ic_mean], ['IC 标准差', row?.ic_std], ['ICIR', row?.rank_icir],
                ['t 统计', row?.ic_tstat], ['IC>0 占比', row?.ic_pos_ratio, true],
                ['多空年化', row?.long_short_ann, true], ['换手率', row?.turnover, true],
                ['覆盖率', row?.coverage, true],
              ].map(([label, v, isPct]) => (
                <span key={label as string} className="rounded-md border border-zinc-800 bg-zinc-900 px-2.5 py-1 text-zinc-400">
                  {label as string}{' '}
                  <b className="tabular-nums text-zinc-100">
                    {v == null ? '—' : isPct ? `${((v as number) * 100).toFixed(1)}%` : (v as number).toFixed(3)}
                  </b>
                </span>
              ))}
            </div>
          </Card>

          {/* IC-IR scatter */}
          <Card>
            <CardHeader title="因子全景散点" sub="横轴 RankIC · 纵轴 ICIR · 气泡大小 = 综合得分 · 主流门槛 |IC|>0.02, |ICIR|>0.3" />
            <div className="h-64 px-2 py-4">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ left: 8, right: 16, bottom: 8 }}>
                  <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
                  <XAxis type="number" dataKey="x" domain={[-0.06, 0.08]}
                    tick={{ fill: '#71717a', fontSize: 10 }} name="RankIC" />
                  <YAxis type="number" dataKey="y" domain={[-0.25, 0.3]}
                    tick={{ fill: '#71717a', fontSize: 10 }} name="ICIR" />
                  <ZAxis type="number" dataKey="z" range={[60, 420]} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ strokeDasharray: '3 3' }}
                    formatter={(v: number, name: string) => [v?.toFixed(3), name]}
                    labelFormatter={(_, payload) => payload?.[0]?.payload?.name ?? ''} />
                  <ReferenceLine x={0} stroke="#3f3f46" />
                  <ReferenceLine y={0} stroke="#3f3f46" />
                  <ReferenceLine x={0.02} stroke="#065f46" strokeDasharray="4 4" />
                  <ReferenceLine y={0.3} stroke="#065f46" strokeDasharray="4 4" />
                  <Scatter data={scatterData} fill={GREEN} isAnimationActive={false}>
                    {scatterData.map((d) => (
                      <Cell key={d.name}
                        fill={d.grade === 'A' ? '#10b981' : d.grade === 'B' ? '#14b8a6' : d.grade === 'C' ? '#f59e0b' : '#52525b'} />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      </div>

      {/* Correlation heatmap */}
      <Card>
        <CardHeader title="因子相关性矩阵" sub="日均横截面 Spearman 相关 · 悬停查看数值" />
        <div className="p-5">
          {data.factor_correlation ? (
            <CorrelationHeatmap corr={data.factor_correlation} />
          ) : (
            <p className="text-sm text-zinc-500">无相关性数据</p>
          )}
        </div>
      </Card>
    </div>
  )
}
