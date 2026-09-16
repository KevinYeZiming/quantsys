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

const MAX_LOG_LINES = 30

interface UpdateButtonProps {
  /** called when the pipeline finished so the parent reloads dashboard.json */
  onUpdated: () => void
}

export function UpdateButton({ onUpdated }: UpdateButtonProps) {
  const [open, setOpen] = useState(false)
  const [running, setRunning] = useState(false)
  const [steps, setSteps] = useState<Step[]>([])
  const [finishedAt, setFinishedAt] = useState<string | null>(null)
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [now, setNow] = useState<number>(Date.now())
  const [interrupted, setInterrupted] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const hbRef = useRef<number | null>(null)

  useEffect(
    () => () => {
      esRef.current?.close()
      if (hbRef.current != null) clearInterval(hbRef.current)
    },
    [],
  )

  // 运行中每秒刷新一次计时
  useEffect(() => {
    if (!running) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [running])

  const elapsed = () => {
    if (startedAt == null) return ''
    const s = Math.floor((now - startedAt) / 1000)
    return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
  }

  const start = () => {
    if (running) return
    esRef.current?.close()
    setSteps([])
    setFinishedAt(null)
    setInterrupted(false)
    setRunning(true)
    setOpen(true)
    setStartedAt(Date.now())

    // 心跳：运行期间每 10 秒告知后端页面仍在，失联超 30 秒后端自动终止更新
    const beat = () => fetch('/api/heartbeat', { method: 'POST' }).catch(() => {})
    beat()
    const hb = setInterval(beat, 10000)
    hbRef.current = hb

    const es = new EventSource('/api/update')
    esRef.current = es

    const stopHb = () => {
      clearInterval(hb)
      hbRef.current = null
    }

    es.addEventListener('step', (ev) => {
      const msg = JSON.parse((ev as MessageEvent).data)
      setSteps((prev) =>
        prev.some((s) => s.id === msg.id)
          ? prev.map((s) => (s.id === msg.id ? { ...s, ...msg } : s))
          : [...prev, { status: 'pending', ...msg }],
      )
    })
    // 实时追加子进程输出，让用户看到逐只股票的进度
    es.addEventListener('log', (ev) => {
      const msg = JSON.parse((ev as MessageEvent).data)
      setSteps((prev) =>
        prev.map((s) =>
          s.id === msg.id
            ? { ...s, logTail: [...(s.logTail ?? []), msg.line].slice(-MAX_LOG_LINES) }
            : s,
        ),
      )
    })
    es.addEventListener('done', () => {
      es.close()
      stopHb()
      setRunning(false)
      setFinishedAt(new Date().toLocaleTimeString())
      onUpdated()
    })
    es.addEventListener('error', (ev) => {
      es.close()
      stopHb()
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
      } else {
        // 连接中断（关页面/合盖休眠/服务重启）
        setInterrupted(true)
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
        <span className="hidden sm:inline">
          {running ? `更新中 ${elapsed()}` : '一键更新'}
        </span>
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-96 max-w-[90vw] rounded-xl border border-zinc-800 bg-zinc-900/95 p-4 shadow-xl backdrop-blur">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
              数据更新流水线
            </p>
            {running && (
              <p className="text-xs tabular-nums text-amber-400">{elapsed()}</p>
            )}
          </div>
          {steps.length === 0 && (
            <p className="text-sm text-zinc-400">正在启动…</p>
          )}
          <ul className="max-h-96 space-y-2 overflow-y-auto">
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
                      <pre className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap break-all rounded bg-zinc-950/70 p-1.5 text-[10px] leading-relaxed text-zinc-500">
                        {s.logTail.join('\n')}
                      </pre>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
          {interrupted && (
            <p className="mt-3 border-t border-zinc-800 pt-2 text-xs text-amber-400">
              连接已中断（页面关闭、合盖休眠或服务重启）。可重新点击「一键更新」继续。
            </p>
          )}
          {finishedAt && !interrupted && (
            <p className="mt-3 border-t border-zinc-800 pt-2 text-xs text-emerald-400">
              更新完成 · 数据已刷新（{finishedAt}）
            </p>
          )}
        </div>
      )}
    </div>
  )
}
