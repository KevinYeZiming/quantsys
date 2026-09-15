import { useEffect, useRef, useState } from 'react'
import { Check, Loader2, RefreshCw, X } from 'lucide-react'
import { cn } from '@/lib/utils'

type StepStatus = 'pending' | 'running' | 'ok' | 'failed'

interface Step {
  id: string
  label: string
  status: StepStatus
  note?: string
  logTail?: string[]
}

interface UpdateButtonProps {
  /** called when the pipeline finished so the parent reloads dashboard.json */
  onUpdated: () => void
}

export function UpdateButton({ onUpdated }: UpdateButtonProps) {
  const [open, setOpen] = useState(false)
  const [running, setRunning] = useState(false)
  const [steps, setSteps] = useState<Step[]>([])
  const [finishedAt, setFinishedAt] = useState<string | null>(null)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => () => esRef.current?.close(), [])

  const patchStep = (id: string, patch: Partial<Step>) =>
    setSteps((prev) => prev.map((s) => (s.id === id ? { ...s, ...patch } : s)))

  const start = () => {
    if (running) return
    esRef.current?.close()
    setSteps([])
    setFinishedAt(null)
    setRunning(true)
    setOpen(true)

    const es = new EventSource('/api/update')
    esRef.current = es

    es.addEventListener('step', (ev) => {
      const msg = JSON.parse((ev as MessageEvent).data)
      setSteps((prev) =>
        prev.some((s) => s.id === msg.id)
          ? prev.map((s) => (s.id === msg.id ? { ...s, ...msg } : s))
          : [...prev, { status: 'pending', ...msg }],
      )
      if (msg.status === 'running') patchStep(msg.id, { status: 'running' })
    })
    es.addEventListener('done', () => {
      es.close()
      setRunning(false)
      setFinishedAt(new Date().toLocaleTimeString())
      onUpdated()
    })
    es.addEventListener('error', (ev) => {
      es.close()
      setRunning(false)
      if (ev instanceof MessageEvent) {
        try {
          const msg = JSON.parse(ev.data)
          setSteps((prev) => [
            ...prev,
            { id: '_error', label: msg.message ?? '更新失败', status: 'failed' },
          ])
        } catch {
          /* malformed payload — ignore */
        }
      }
    })
  }

  return (
    <div className="relative">
      <button
        onClick={() => (open && !running ? setOpen(false) : start())}
        disabled={running}
        className={cn(
          'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition-colors',
          running
            ? 'cursor-wait bg-emerald-500/10 text-emerald-300'
            : 'bg-zinc-800/70 text-zinc-300 hover:bg-zinc-700/70 hover:text-zinc-100',
        )}
        title="一键更新：抓取最新行情并重新评估"
      >
        {running ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <RefreshCw className="h-3.5 w-3.5" />
        )}
        <span className="hidden sm:inline">{running ? '更新中…' : '一键更新'}</span>
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 rounded-xl border border-zinc-800 bg-zinc-900/95 p-4 shadow-xl backdrop-blur">
          <p className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
            数据更新流水线
          </p>
          {steps.length === 0 && (
            <p className="text-sm text-zinc-400">正在启动…</p>
          )}
          <ul className="space-y-2">
            {steps.map((s) => (
              <li key={s.id}>
                <div className="flex items-start gap-2">
                  <span
                    className={cn(
                      'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full',
                      s.status === 'ok' && 'bg-emerald-500/20 text-emerald-400',
                      s.status === 'failed' && 'bg-red-500/20 text-red-400',
                      s.status === 'running' && 'bg-amber-500/20 text-amber-400',
                      s.status === 'pending' && 'bg-zinc-700/40 text-zinc-500',
                    )}
                  >
                    {s.status === 'running' ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : s.status === 'ok' ? (
                      <Check className="h-3 w-3" />
                    ) : s.status === 'failed' ? (
                      <X className="h-3 w-3" />
                    ) : (
                      <span className="h-1 w-1 rounded-full bg-current" />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p
                      className={cn(
                        'text-sm leading-tight',
                        s.status === 'failed'
                          ? 'text-red-300'
                          : s.status === 'ok'
                            ? 'text-zinc-200'
                            : 'text-zinc-300',
                      )}
                    >
                      {s.label}
                      {s.note && (
                        <span className="ml-1.5 text-xs text-zinc-500">{s.note}</span>
                      )}
                    </p>
                    {s.logTail && s.logTail.length > 0 && (
                      <pre className="mt-1 max-h-24 overflow-y-auto whitespace-pre-wrap break-all rounded bg-zinc-950/70 p-1.5 text-[10px] leading-relaxed text-zinc-500">
                        {s.logTail.join('\n')}
                      </pre>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
          {finishedAt && (
            <p className="mt-3 border-t border-zinc-800 pt-2 text-xs text-emerald-400">
              更新完成 · 数据已刷新（{finishedAt}）
            </p>
          )}
        </div>
      )}
    </div>
  )
}
