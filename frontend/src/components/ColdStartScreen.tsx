import { useEffect, useState } from 'react'
import { getHealth } from '@/lib/api'

const POLL_MS = 2000
const GIVE_UP_HINT_S = 75

interface Props {
  onReady: () => void
  onRecorded: () => void
}

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
    <div
      role="status"
      aria-live="polite"
      className="rise mx-auto mt-10 max-w-lg rounded-2xl border border-[var(--mc-line)] bg-[var(--mc-surface)] p-8 text-center"
    >
      <div className="mx-auto mb-5 flex h-12 w-12 items-end justify-center gap-1" aria-hidden>
        {[0, 1, 2, 3, 4].map((i) => (
          <span
            key={i}
            className="wave w-1.5 rounded-full bg-[var(--mc-accent)]"
            style={{ height: `${20 + ((i * 17) % 26)}px`, animationDelay: `${i * 0.12}s` }}
          />
        ))}
      </div>
      <h2 className="mb-1 text-lg font-semibold">Waking up the server</h2>
      <p className="mb-4 text-sm text-[var(--mc-muted)]">
        Free hosting sleeps when idle. This can take up to a minute.
      </p>
      <p className="mono mb-1 text-3xl text-[var(--mc-text)]">{seconds}s</p>
      <p className="text-xs text-[var(--mc-muted)]">Checking every 2 seconds. The call starts by itself.</p>
      {seconds >= GIVE_UP_HINT_S && (
        <div className="mt-5 border-t border-[var(--mc-line)] pt-4">
          <p className="mb-3 text-sm">Still waking… you can keep waiting or play the recorded run.</p>
          <button
            onClick={onRecorded}
            className="rounded-md border border-[var(--mc-line)] px-4 py-2 text-sm hover:bg-[var(--mc-line)]"
          >
            Try recorded run
          </button>
        </div>
      )}
    </div>
  )
}
