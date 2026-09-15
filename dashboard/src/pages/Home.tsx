import { useEffect, useState } from 'react'
import { Activity, FlaskConical, LayoutDashboard, Wallet } from 'lucide-react'
import raw from '@/data/dashboard.json'
import type { DashboardData } from '@/types/dashboard'
import { Overview } from '@/sections/Overview'
import { FactorLab } from '@/sections/FactorLab'
import { Signals } from '@/sections/Signals'
import { Holdings } from '@/sections/Holdings'
import { cn } from '@/lib/utils'

const data = raw as unknown as DashboardData

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

          <div className="hidden text-right text-[11px] leading-tight text-zinc-500 sm:block">
            <p>数据生成于</p>
            <p className="tabular-nums text-zinc-400">{data.generated_at}</p>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        {tab === 'overview' && (
          <Overview data={data}
            onGoFactors={() => setTab('factors')}
            onGoSignals={() => setTab('signals')} />
        )}
        {tab === 'factors' && <FactorLab data={data} />}
        {tab === 'signals' && <Signals data={data} />}
        {tab === 'holdings' && <Holdings data={data} />}
      </main>

      <footer className="border-t border-zinc-800/60 py-6 text-center text-xs text-zinc-600">
        Quantsys · 本仪表盘为研究工具输出，不构成投资建议 ·
        刷新数据：evaluate_factors.py → evaluate_assets.py → export_dashboard_data.py
      </footer>
    </div>
  )
}
