import { useState } from 'react'
import { Loader2, Pencil, Plus, Trash2 } from 'lucide-react'
import type { Position } from '@/types/dashboard'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'

const ASSET_TYPES = [
  { value: 'etf', label: 'ETF' },
  { value: 'stock', label: '股票' },
  { value: 'fund', label: '场外基金' },
  { value: 'gold', label: '黄金' },
]

const inputCls =
  'h-8 rounded-md border border-zinc-700 bg-zinc-900 px-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-emerald-500 focus:outline-none'

interface PositionEditorProps {
  positions: Position[]
  /** called after a successful save so the parent reloads dashboard.json */
  onSaved: () => void
}

export function PositionEditor({ positions, onSaved }: PositionEditorProps) {
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState<Position[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const openEditor = () => {
    setRows(positions.map((p) => ({ ...p })))
    setError(null)
    setOpen(true)
  }

  const update = (i: number, patch: Partial<Position>) =>
    setRows((prev) => prev.map((r, j) => (j === i ? { ...r, ...patch } : r)))

  const remove = (i: number) => setRows((prev) => prev.filter((_, j) => j !== i))

  const add = () =>
    setRows((prev) => [
      ...prev,
      {
        symbol: '',
        name: '',
        asset_type: 'etf',
        quantity: 100,
        avg_cost: 1,
        added_date: new Date().toISOString().slice(0, 10),
      },
    ])

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const res = await fetch('/api/positions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(rows),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : `保存失败（HTTP ${res.status}）`)
      }
      setOpen(false)
      onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Button size="sm" variant="outline" onClick={openEditor}>
        <Pencil className="h-3.5 w-3.5" />
        编辑持仓
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-4xl border-zinc-800 bg-zinc-950 text-zinc-100 sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle>编辑持仓</DialogTitle>
            <p className="text-xs text-zinc-500">
              保存后立即重新生成仪表盘数据；点击「一键更新」可重新评估新持仓的买卖信号。
              股票/ETF 代码为 6 位数字，场外基金为天天基金 6 位代码，黄金填 Au99.99 等现货代码。
            </p>
          </DialogHeader>

          <div className="max-h-[55vh] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-zinc-950 text-[11px] uppercase tracking-wider text-zinc-500">
                <tr>
                  <th className="px-2 py-2 text-left font-medium">代码</th>
                  <th className="px-2 py-2 text-left font-medium">名称</th>
                  <th className="px-2 py-2 text-left font-medium">类型</th>
                  <th className="px-2 py-2 text-right font-medium">数量</th>
                  <th className="px-2 py-2 text-right font-medium">成本价</th>
                  <th className="px-2 py-2 text-left font-medium">买入日期</th>
                  <th className="px-2 py-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className="border-t border-zinc-800/60">
                    <td className="px-2 py-1.5">
                      <Input
                        className={`${inputCls} w-24 font-mono`}
                        value={r.symbol}
                        placeholder="511220"
                        onChange={(e) => update(i, { symbol: e.target.value.trim() })}
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <Input
                        className={`${inputCls} w-full min-w-36`}
                        value={r.name}
                        placeholder="标的名称"
                        onChange={(e) => update(i, { name: e.target.value })}
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <select
                        className={`${inputCls} w-28`}
                        value={r.asset_type}
                        onChange={(e) => update(i, { asset_type: e.target.value })}
                      >
                        {ASSET_TYPES.map((t) => (
                          <option key={t.value} value={t.value} className="bg-zinc-900">
                            {t.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-2 py-1.5">
                      <Input
                        type="number" min="0" step="any"
                        className={`${inputCls} w-24 text-right tabular-nums`}
                        value={String(r.quantity)}
                        onChange={(e) => update(i, { quantity: parseFloat(e.target.value) || 0 })}
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <Input
                        type="number" min="0" step="any"
                        className={`${inputCls} w-24 text-right tabular-nums`}
                        value={String(r.avg_cost)}
                        onChange={(e) => update(i, { avg_cost: parseFloat(e.target.value) || 0 })}
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <Input
                        type="date"
                        className={`${inputCls} w-36`}
                        value={r.added_date}
                        onChange={(e) => update(i, { added_date: e.target.value })}
                      />
                    </td>
                    <td className="px-2 py-1.5 text-right">
                      <button
                        onClick={() => remove(i)}
                        className="rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-red-500/10 hover:text-red-400"
                        title="删除该持仓"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-2 py-6 text-center text-sm text-zinc-500">
                      暂无持仓，点击下方「添加标的」
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {error && (
            <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
              {error}
            </p>
          )}

          <DialogFooter className="gap-2 sm:gap-2">
            <Button variant="outline" size="sm" onClick={add}>
              <Plus className="h-3.5 w-3.5" />
              添加标的
            </Button>
            <div className="flex-1" />
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button size="sm" onClick={save} disabled={saving}>
              {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
