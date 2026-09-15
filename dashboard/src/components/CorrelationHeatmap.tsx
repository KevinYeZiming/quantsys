import { Fragment, useMemo, useState } from 'react'
import type { Correlation } from '@/types/dashboard'

/** Diverging blue-white-red heatmap for the factor correlation matrix. */
export function CorrelationHeatmap({ corr }: { corr: Correlation }) {
  const [hover, setHover] = useState<{ i: number; j: number } | null>(null)

  const { labels, values } = corr
  const cell = 34

  const color = (v: number | null): string => {
    if (v == null) return '#18181b'
    const a = Math.min(Math.abs(v), 1)
    if (v >= 0) return `rgba(16, 185, 129, ${0.12 + a * 0.75})`
    return `rgba(244, 63, 94, ${0.12 + a * 0.75})`
  }

  const strongPairs = useMemo(() => {
    const out: { a: string; b: string; v: number }[] = []
    for (let i = 0; i < labels.length; i++)
      for (let j = i + 1; j < labels.length; j++) {
        const v = values[i]?.[j]
        if (v != null && Math.abs(v) > 0.7) out.push({ a: labels[i], b: labels[j], v })
      }
    return out.sort((x, y) => Math.abs(y.v) - Math.abs(x.v))
  }, [labels, values])

  return (
    <div className="flex flex-col gap-6 lg:flex-row">
      <div className="overflow-x-auto">
        <div
          className="grid"
          style={{ gridTemplateColumns: `auto repeat(${labels.length}, ${cell}px)` }}
        >
          {/* corner + column headers */}
          <div />
          {labels.map((l, j) => (
            <div key={j} className="flex items-end justify-center pb-1">
              <span className="origin-bottom-left rotate-45 whitespace-nowrap text-[10px] text-zinc-500" style={{ transform: 'translateY(-2px) rotate(-45deg)' }}>
                {l.length > 10 ? l.slice(0, 10) + '…' : l}
              </span>
            </div>
          ))}
          {labels.map((li, i) => (
            <Fragment key={`r${i}`}>
              <div className="flex items-center pr-2 text-right text-[10px] text-zinc-500"
                style={{ height: cell, maxWidth: 140, overflow: 'hidden' }}>
                {li.length > 14 ? li.slice(0, 14) + '…' : li}
              </div>
              {labels.map((_, j) => {
                const v = values[i]?.[j]
                const active = hover && (hover.i === i || hover.j === j)
                return (
                  <div
                    key={`${i}-${j}`}
                    onMouseEnter={() => setHover({ i, j })}
                    onMouseLeave={() => setHover(null)}
                    className="m-[1px] flex items-center justify-center rounded-[3px] text-[9px] tabular-nums text-zinc-200"
                    style={{
                      width: cell - 2, height: cell - 2,
                      background: color(v),
                      opacity: hover ? (active ? 1 : 0.35) : 1,
                      cursor: 'default',
                    }}
                    title={`${li} × ${labels[j]} = ${v == null ? '—' : v.toFixed(3)}`}
                  >
                    {v != null && Math.abs(v) >= 0.85 ? v.toFixed(2) : ''}
                  </div>
                )
              })}
            </Fragment>
          ))}
        </div>
      </div>

      <div className="min-w-52 flex-1">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
          高相关因子对（|ρ| &gt; 0.7）
        </h4>
        {strongPairs.length === 0 ? (
          <p className="mt-3 text-sm text-zinc-500">未发现冗余因子对，等权组合暴露分散。</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {strongPairs.slice(0, 8).map((p, k) => (
              <li key={k} className="flex items-center justify-between gap-3 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs">
                <span className="text-zinc-300">{p.a} × {p.b}</span>
                <span className={p.v > 0 ? 'font-bold text-emerald-400' : 'font-bold text-rose-400'}>
                  {p.v.toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-4 text-[11px] leading-relaxed text-zinc-600">
          日均横截面 Spearman 相关。|ρ| 越接近 1，两个因子重复暴露越多；
          建议保留 RankICIR 更高的一只，或对高相关簇做正交化后再合成。
        </p>
      </div>
    </div>
  )
}
