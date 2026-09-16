import { useEffect, useState } from 'react'
import { History, Loader2, NotebookPen, Trash2 } from 'lucide-react'
import type { Position } from '@/types/dashboard'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'

interface Trade {
  id: string
  date: string
  symbol: string
  name: string
  asset_type: string
  side: 'buy' | 'sell'
  quantity: number
  price: number
  note: string
}

const SIDE_LABEL: Record<string, { label: string; cls: string }> = {
  buy: { label: '买入', cls: 'bg-emerald-500/15 text-emerald-300' },
  sell: { label: '卖出', cls: 'bg-rose-500/15 text-rose-300' },
}

const inputCls =
  'h-8 rounded-md border border-zinc-700 bg-zinc-900 px-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-emerald-500 focus:outline-none'

const emptyForm = () => ({
  date: new Date().toISOString().slice(0, 10),
  symbol: '',
  name: '',
  asset_type: 'etf',
  side: 'buy' as 'buy' | 'sell',
  quantity: '' as string | number,
  price: '' as string | number,
  note: '',
})

interface TradeJournalProps {
  positions: Position[]
  /** called after any change so the parent reloads dashboard.json */
  onSaved: () => void
}

export function TradeJournal({ positions, onSaved }: TradeJournalProps) {
  const [open, setOpen] = useState(false)
  const [trades, setTrades] = useState<Trade[]>([])
  const [form, setForm] = useState(emptyForm)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      fetch('/api/trades')
        .then((r) => (r.ok ? r.json() : []))
        .then(setTrades)
        .catch(() => setTrades([]))
      setForm(emptyForm())
      setError(null)
    }
  }, [open])

  // 代码输入后自动带出已有标的的名称与类型
  const fillFromPositions = (symbol: string) => {
    const hit = positions.find((p) => p.symbol === symbol)
    setForm((f) => ({
      ...f,
      symbol,
      name: hit ? hit.name : f.name,
      asset_type: hit ? hit.asset_type : f.asset_type,
    }))
  }

  const submit = async () => {
    setSaving(true)
    setError(null)
    try {
      const res = await fetch('/api/trades', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : `记录失败（HTTP ${res.status}）`)
      }
      setTrades((prev) => [data.trade, ...prev])
      setForm(emptyForm())
      onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const remove = async (id: string) => {
    setSaving(true)
    setError(null)
    try {
      const res = await fetch(`/api/trades/${id}`, { method: 'DELETE' })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : `删除失败（HTTP ${res.status}）`)
      }
      setTrades((prev) => prev.filter((t) => t.id !== id))
      onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <History className="h-3.5 w-3.5" />
        交易记录
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-4xl border-zinc-800 bg-zinc-950 text-zinc-100 sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle>交易记录</DialogTitle>
            <p className="text-xs text-zinc-500">
              每记一笔买入/卖出，持仓数量与成本价（移动加权平均）自动重算并即时生效。
            </p>
          </DialogHeader>

          {/* 记一笔 */}
          <div className="flex flex-wrap items-end gap-2 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
            <label className="text-[11px] text-zinc-500">
              日期
              <Input type="date" className={`${inputCls} mt-1 w-36`} value={form.date}
                onChange={(e) => setForm({ ...form, date: e.target.value })} />
            </label>
            <label className="text-[11px] text-zinc-500">
              代码
              <Input className={`${inputCls} mt-1 w-24 font-mono`} value={form.symbol} placeholder="511220"
                onChange={(e) => fillFromPositions(e.target.value.trim())} />
            </label>
            <label className="text-[11px] text-zinc-500">
              名称
              <Input className={`${inputCls} mt-1 w-40`} value={form.name} placeholder="自动带出"
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="text-[11px] text-zinc-500">
              方向
              <select className={`${inputCls} mt-1 w-24`} value={form.side}
                onChange={(e) => setForm({ ...form, side: e.target.value as 'buy' | 'sell' })}>
                <option value="buy" className="bg-zinc-900">买入</option>
                <option value="sell" className="bg-zinc-900">卖出</option>
              </select>
            </label>
            <label className="text-[11px] text-zinc-500">
              数量
              <Input type="number" min="0" step="any" className={`${inputCls} mt-1 w-24 text-right tabular-nums`}
                value={String(form.quantity)}
                onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
            </label>
            <label className="text-[11px] text-zinc-500">
              价格
              <Input type="number" min="0" step="any" className={`${inputCls} mt-1 w-24 text-right tabular-nums`}
                value={String(form.price)}
                onChange={(e) => setForm({ ...form, price: e.target.value })} />
            </label>
            <label className="text-[11px] text-zinc-500">
              备注
              <Input className={`${inputCls} mt-1 w-36`} value={form.note} placeholder="可选"
                onChange={(e) => setForm({ ...form, note: e.target.value })} />
            </label>
            <Button size="sm" onClick={submit} disabled={saving || !form.symbol || !form.quantity || !form.price}>
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <NotebookPen className="h-3.5 w-3.5" />}
              记一笔
            </Button>
          </div>

          {error && (
            <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
              {error}
            </p>
          )}

          {/* 历史记录 */}
          <div className="max-h-[40vh] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-zinc-950 text-[11px] uppercase tracking-wider text-zinc-500">
                <tr>
                  <th className="px-2 py-2 text-left font-medium">日期</th>
                  <th className="px-2 py-2 text-left font-medium">标的</th>
                  <th className="px-2 py-2 text-right font-medium">方向</th>
                  <th className="px-2 py-2 text-right font-medium">数量</th>
                  <th className="px-2 py-2 text-right font-medium">价格</th>
                  <th className="px-2 py-2 text-right font-medium">金额</th>
                  <th className="px-2 py-2 text-left font-medium">备注</th>
                  <th className="px-2 py-2" />
                </tr>
              </thead>
              <tbody>
                {trades.map((t) => {
                  const side = SIDE_LABEL[t.side] ?? SIDE_LABEL.buy
                  return (
                    <tr key={t.id} className="border-t border-zinc-800/60">
                      <td className="px-2 py-1.5 tabular-nums text-zinc-400">{t.date}</td>
                      <td className="px-2 py-1.5">
                        <span className="font-medium text-zinc-200">{t.name || t.symbol}</span>
                        <span className="ml-1.5 font-mono text-xs text-zinc-500">{t.symbol}</span>
                      </td>
                      <td className="px-2 py-1.5 text-right">
                        <span className={`rounded-md px-1.5 py-0.5 text-xs ${side.cls}`}>{side.label}</span>
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums text-zinc-300">{t.quantity}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums text-zinc-300">{t.price}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums text-zinc-400">
                        {(t.quantity * t.price).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}
                      </td>
                      <td className="max-w-32 truncate px-2 py-1.5 text-xs text-zinc-500">{t.note}</td>
                      <td className="px-2 py-1.5 text-right">
                        <button onClick={() => remove(t.id)} disabled={saving}
                          className="rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-red-500/10 hover:text-red-400 disabled:opacity-40"
                          title="删除该记录（持仓会自动重算）">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  )
                })}
                {trades.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-2 py-6 text-center text-sm text-zinc-500">
                      暂无交易记录，在上方记一笔吧
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <DialogFooter>
            <p className="mr-auto text-xs text-zinc-600">
              删除记录后持仓按剩余记录自动重建
            </p>
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>关闭</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
