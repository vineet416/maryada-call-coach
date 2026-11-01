import { useEffect, useState } from 'react'
import { getHealth } from '@/lib/api'

const POLL_MS = 2000
const GIVE_UP_HINT_S = 75
const EXPECTED_S = 60

interface Props {
  onReady: () => void
  onRecorded?: () => void
}

const clock = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`

/** Full-screen "waking the server" state: polls /health every 2 s, continues by itself when it answers. */
export function ColdStartScreen({ onReady, onRecorded }: Props) {
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    const t0 = Date.now()
    const tick = window.setInterval(() => setSeconds(Math.floor((Date.now() - t0) / 1000)), 500)
    let stop = false
    const poll = async () => {
      while (!stop) {
        try {
          const ctl = new AbortController()
          const kill = window.setTimeout(() => ctl.abort(), 6000)
          await getHealth(ctl.signal)
          window.clearTimeout(kill)
          if (!stop) onReady()
          return
        } catch {
          await new Promise((r) => window.setTimeout(r, POLL_MS))
        }
      }
    }
    void poll()
    return () => {
      stop = true
      window.clearInterval(tick)
    }
  }, [onReady])

  return (
    <div role="status" aria-live="polite" className="card rise mx-auto mt-6 flex max-w-lg flex-col items-center gap-3.5 p-8 text-center sm:mt-10">
      <div className="spinner h-11 w-11" aria-hidden />
      <h2 className="text-lg font-semibold tracking-tight">Waking up the server</h2>
      <p className="max-w-[320px] text-[13.5px] leading-relaxed text-[var(--mc-muted)]">
        This demo runs on a free server that sleeps when idle. The first request can take up to a minute.
      </p>
      <div className="h-1.5 w-[260px] max-w-full overflow-hidden rounded-full bg-[#eaecf0]" aria-hidden>
        <div className="h-full rounded-full bg-[var(--mc-accent)] transition-[width] duration-500" style={{ width: `${Math.min(100, (seconds / EXPECTED_S) * 100)}%` }} />
      </div>
      <p className="mono text-xs text-[var(--mc-muted)]">{clock(seconds)} elapsed. Checking every 2 seconds; the call starts by itself.</p>
      {seconds >= GIVE_UP_HINT_S && onRecorded && (
        <div className="mt-2 w-full border-t border-[var(--mc-line)] pt-4">
          <p className="mb-3 text-sm">Still waking… you can keep waiting or play the recorded run.</p>
          <button onClick={onRecorded} className="btn btn-primary">
            Try recorded run
          </button>
        </div>
      )}
    </div>
  )
}
