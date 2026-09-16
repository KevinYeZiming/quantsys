import { useCallback, useEffect, useState } from 'react'
import { Activity, FlaskConical, LayoutDashboard, Wallet } from 'lucide-react'
import type { DashboardData } from '@/types/dashboard'
import { Overview } from '@/sections/Overview'
import { FactorLab } from '@/sections/FactorLab'
import { Signals } from '@/sections/Signals'
import { Holdings } from '@/sections/Holdings'
import { UpdateButton } from '@/components/UpdateButton'
import { cn } from '@/lib/utils'

type Tab = 'overview' | 'factors' | 'signals' | 'holdings'

const TABS: { key: Tab; label: string; icon: typeof LayoutDashboard }[] = [
  { key: 'overview', label: '总览', icon: LayoutDashboard },
  { key: 'factors', label: '因子实验室', icon: FlaskConical },
  { key: 'signals', label: '买卖信号', icon: Activity },
  { key: 'holdings', label: '持仓', icon: Wallet },
]

export default function Home() {
  const [tab, setTab] = useState<Tab>(() => {
    const h = window.location.hash.replace('#', '')
    return (TABS.some((t) => t.key === h) ? h : 'overview') as Tab
  })
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await fetch('data/dashboard.json', { cache: 'no-store' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setData((await res.json()) as DashboardData)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // keep URL hash in sync so views are deep-linkable (and headlessly testable)
  useEffect(() => {
    window.location.hash = tab
  }, [tab])

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 antialiased">
      {/* Header */}
      <header className="sticky top-0 z-40 border-b border-zinc-800/80 bg-zinc-950/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4 sm:px-6">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-400">
              <Activity className="h-4.5 w-4.5" />
            </div>
            <div className="leading-tight">
              <p className="text-sm font-bold tracking-wide">Quantsys <span className="text-emerald-400">量化仪表盘</span></p>
              <p className="text-[10px] text-zinc-500">A股 · 基金 · 黄金 · 因子研究</p>
            </div>
          </div>

          <nav className="ml-2 flex flex-1 items-center gap-1 overflow-x-auto">
            {TABS.map(({ key, label, icon: Icon }) => (
              <button key={key} onClick={() => setTab(key)}
                className={cn(
                  'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition-colors whitespace-nowrap',
                  tab === key
                    ? 'bg-emerald-500/15 font-medium text-emerald-300'
                    : 'text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200',
                )}>
                <Icon className="h-3.5 w-3.5" />
                {label}
              </button>
            ))}
          </nav>

          <UpdateButton onUpdated={load} />

          <div className="hidden text-right text-[11px] leading-tight text-zinc-500 sm:block">
            <p>数据生成于</p>
            <p className="tabular-nums text-zinc-400">{data?.generated_at ?? '—'}</p>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        {error && (
          <div className="mb-6 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
            无法加载数据文件 data/dashboard.json（{error}）。
            请先运行 python3 scripts/export_dashboard_data.py 生成数据。
          </div>
        )}
        {!data && !error && (
          <div className="flex h-64 items-center justify-center text-sm text-zinc-500">
            正在加载数据…
          </div>
        )}
        {data && tab === 'overview' && (
          <Overview data={data}
            onGoFactors={() => setTab('factors')}
            onGoSignals={() => setTab('signals')} />
        )}
        {data && tab === 'factors' && <FactorLab data={data} />}
        {data && tab === 'signals' && <Signals data={data} />}
        {data && tab === 'holdings' && <Holdings data={data} onPositionsChanged={load} />}
      </main>

      <footer className="border-t border-zinc-800/60 py-6 text-center text-xs text-zinc-600">
        Quantsys · 本仪表盘为研究工具输出，不构成投资建议 ·
        点击右上角「一键更新」抓取最新行情并重新评估
      </footer>
    </div>
  )
}
