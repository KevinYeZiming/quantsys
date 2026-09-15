import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/* ---------- visual constants ---------- */

export const GRADE_STYLE: Record<string, { badge: string; bar: string }> = {
  A: { badge: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30', bar: '#10b981' },
  B: { badge: 'bg-teal-500/15 text-teal-400 border-teal-500/30', bar: '#14b8a6' },
  C: { badge: 'bg-amber-500/15 text-amber-400 border-amber-500/30', bar: '#f59e0b' },
  D: { badge: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30', bar: '#71717a' },
}

export const ACTION_META: Record<string, { cn: string; label: string }> = {
  strong_buy: { cn: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30', label: '强烈买入' },
  buy: { cn: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20', label: '买入' },
  hold: { cn: 'bg-zinc-500/10 text-zinc-300 border-zinc-500/25', label: '持有' },
  sell: { cn: 'bg-rose-500/10 text-rose-300 border-rose-500/25', label: '卖出' },
  strong_sell: { cn: 'bg-rose-500/15 text-rose-400 border-rose-500/30', label: '强烈卖出' },
}

export const ASSET_LABEL: Record<string, string> = {
  stock: '个股',
  etf: 'ETF',
  fund: '基金',
  gold: '黄金',
}

/* ---------- small components ---------- */

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn('rounded-xl border border-zinc-800 bg-zinc-900/60 backdrop-blur', className)}>
      {children}
    </div>
  )
}

export function CardHeader({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-zinc-800/80 px-5 py-4">
      <div>
        <h3 className="text-sm font-semibold tracking-wide text-zinc-100">{title}</h3>
        {sub && <p className="mt-0.5 text-xs text-zinc-500">{sub}</p>}
      </div>
      {right}
    </div>
  )
}

export function GradeBadge({ grade }: { grade: string }) {
  const s = GRADE_STYLE[grade] ?? GRADE_STYLE.D
  return (
    <span className={cn('inline-flex h-6 w-6 items-center justify-center rounded-md border text-xs font-bold', s.badge)}>
      {grade}
    </span>
  )
}

export function ActionBadge({ action }: { action: string }) {
  const meta = ACTION_META[action] ?? ACTION_META.hold
  return (
    <span className={cn('inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium', meta.cn)}>
      {meta.label}
    </span>
  )
}

export function StatCard({ label, value, sub, accent }: {
  label: string; value: string; sub?: string; accent?: string
}) {
  return (
    <Card className="px-5 py-4">
      <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">{label}</p>
      <p className="mt-1.5 text-2xl font-bold tabular-nums text-zinc-50" style={accent ? { color: accent } : undefined}>
        {value}
      </p>
      {sub && <p className="mt-1 text-xs text-zinc-500">{sub}</p>}
    </Card>
  )
}

/** Radial score ring (0-100). */
export function ScoreRing({ score, size = 64, stroke = 6 }: { score: number; size?: number; stroke?: number }) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const frac = Math.max(0, Math.min(100, score)) / 100
  const color = score >= 60 ? '#10b981' : score >= 40 ? '#f59e0b' : '#f43f5e'
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#27272a" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - frac)}
          style={{ transition: 'stroke-dashoffset .6s ease' }}
        />
      </svg>
      <span className="absolute text-sm font-bold tabular-nums" style={{ color }}>{Math.round(score)}</span>
    </div>
  )
}

export function FmtPct({ v, digits = 1 }: { v: number | null | undefined; digits?: number }) {
  if (v == null) return <span className="text-zinc-600">—</span>
  return <span className={cn('tabular-nums', v > 0 ? 'text-emerald-400' : v < 0 ? 'text-rose-400' : 'text-zinc-400')}>{(v * 100).toFixed(digits)}%</span>
}

export function FmtNum({ v, digits = 3 }: { v: number | null | undefined; digits?: number }) {
  if (v == null) return <span className="text-zinc-600">—</span>
  return <span className="tabular-nums">{v.toFixed(digits)}</span>
}
