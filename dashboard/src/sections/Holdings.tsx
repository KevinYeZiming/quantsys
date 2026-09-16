import type { DashboardData } from '@/types/dashboard'
import { ActionBadge, ASSET_LABEL, Card, CardHeader, FmtPct } from '@/components/bits'
import { PositionEditor } from '@/components/PositionEditor'
import { TradeJournal } from '@/components/TradeJournal'

export function Holdings({ data, onPositionsChanged }: { data: DashboardData; onPositionsChanged: () => void }) {
  const evalBySymbol = new Map(data.evaluations.map((e) => [e.symbol, e]))
  const rows = data.positions.map((p) => ({ pos: p, ev: evalBySymbol.get(p.symbol) }))

  const totalCost = rows.reduce((s, r) => s + r.pos.quantity * r.pos.avg_cost, 0)
  const totalValue = rows.reduce((s, r) => s + r.pos.quantity * (r.ev?.price ?? r.pos.avg_cost), 0)
  const totalPnl = totalValue - totalCost

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-5 py-4">
          <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">持仓数量</p>
          <p className="mt-1.5 text-2xl font-bold tabular-nums text-zinc-50">{rows.length}</p>
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-5 py-4">
          <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">总成本</p>
          <p className="mt-1.5 text-2xl font-bold tabular-nums text-zinc-50">¥{totalCost.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</p>
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-5 py-4">
          <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">总市值（按评估价）</p>
          <p className="mt-1.5 text-2xl font-bold tabular-nums text-zinc-50">¥{totalValue.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</p>
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-5 py-4">
          <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">总盈亏</p>
          <p className={`mt-1.5 text-2xl font-bold tabular-nums ${totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {totalPnl >= 0 ? '+' : ''}¥{totalPnl.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}
            <span className="ml-1 text-sm font-medium">
              ({totalCost > 0 ? `${((totalPnl / totalCost) * 100).toFixed(1)}%` : '—'})
            </span>
          </p>
        </div>
      </div>

      <Card className="overflow-hidden">
        <CardHeader
          title="持仓明细"
          sub="现价与信号来自最近一次统一买卖评估（evaluate_assets）"
          right={
            <div className="flex gap-2">
              <TradeJournal positions={data.positions} onSaved={onPositionsChanged} />
              <PositionEditor positions={data.positions} onSaved={onPositionsChanged} />
            </div>
          }
        />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-zinc-800 text-[11px] uppercase tracking-wider text-zinc-500">
              <tr>
                <th className="px-5 py-3 text-left font-medium">标的</th>
                <th className="px-3 py-3 text-right font-medium">类型</th>
                <th className="px-3 py-3 text-right font-medium">数量</th>
                <th className="px-3 py-3 text-right font-medium">成本价</th>
                <th className="px-3 py-3 text-right font-medium">现价/净值</th>
                <th className="px-3 py-3 text-right font-medium">浮动盈亏</th>
                <th className="px-3 py-3 text-right font-medium">评估总分</th>
                <th className="px-3 py-3 text-right font-medium">信号</th>
                <th className="px-3 py-3 text-right font-medium">建议仓位</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ pos, ev }) => {
                const pnl = ev?.price != null ? (ev.price / pos.avg_cost - 1) : null
                return (
                  <tr key={pos.symbol} className="border-b border-zinc-800/50 last:border-0 hover:bg-zinc-800/30">
                    <td className="px-5 py-3">
                      <p className="font-medium text-zinc-100">{pos.name || pos.symbol}</p>
                      <p className="text-xs text-zinc-500">{pos.symbol} · 建仓 {pos.added_date}</p>
                    </td>
                    <td className="px-3 py-3 text-right text-xs text-zinc-400">{ASSET_LABEL[pos.asset_type] ?? pos.asset_type}</td>
                    <td className="px-3 py-3 text-right tabular-nums text-zinc-300">{pos.quantity.toLocaleString()}</td>
                    <td className="px-3 py-3 text-right tabular-nums text-zinc-300">{pos.avg_cost}</td>
                    <td className="px-3 py-3 text-right tabular-nums text-zinc-100">{ev?.price ?? '—'}</td>
                    <td className="px-3 py-3 text-right"><FmtPct v={pnl} /></td>
                    <td className="px-3 py-3 text-right">
                      <span className={`font-bold tabular-nums ${
                        (ev?.total_score ?? 50) >= 60 ? 'text-emerald-400'
                        : (ev?.total_score ?? 50) <= 40 ? 'text-rose-400' : 'text-zinc-200'
                      }`}>{ev?.total_score?.toFixed(0) ?? '—'}</span>
                    </td>
                    <td className="px-3 py-3 text-right">{ev ? <ActionBadge action={ev.action} /> : <span className="text-xs text-zinc-600">未评估</span>}</td>
                    <td className="px-3 py-3 text-right tabular-nums text-xs text-zinc-300">
                      {ev?.target_weight != null ? `${(ev.target_weight * 100).toFixed(0)}%` : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <p className="text-xs leading-relaxed text-zinc-600">
        说明：评估基于「动量 / 趋势 / 风险 / 位置」四维历史分位打分模型（详见
        quantsys/advisor/asset_evaluator.py），仅供参考，不构成投资建议。
        更新数据后重新运行 scripts/evaluate_assets.py 与 export_dashboard_data.py 即可刷新本页。
      </p>
    </div>
  )
}
