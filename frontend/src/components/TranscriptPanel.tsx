import { ArrowDown } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { Finding } from '@/lib/events'
import type { ScenarioDetail } from '@/lib/api'
import type { TurnView } from '@/store/sessionStore'
import { Bubble } from '@/components/Bubble'

interface Props {
  turns: TurnView[]
  findings: Finding[]
  scenario: ScenarioDetail | null
  onOpen: (f: Finding) => void
}

/** Chat-style transcript. Follows the call; if the viewer scrolls up, a "jump to latest" pill appears. */
export function TranscriptPanel({ turns, findings, scenario, onOpen }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)
  const [away, setAway] = useState(false)

  const toBottom = useCallback((smooth = true) => {
    const el = box.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  }, [])

  const onScroll = () => {
    const el = box.current
    if (!el) return
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    pinned.current = near
    setAway(!near)
  }

  const tokenCount = turns.reduce((n, t) => n + t.tokens.length, 0)
  useEffect(() => {
    if (pinned.current) toBottom()
  }, [turns.length, tokenCount, findings.length, toBottom])

  const offset = (idx: number) => scenario?.turns.find((t) => t.idx === idx)?.offset_ms ?? 0

  return (
    <div className="relative">
      <div
        ref={box}
        onScroll={onScroll}
        className="h-[min(62vh,640px)] space-y-3 overflow-y-auto rounded-2xl border border-[var(--mc-line)] bg-[var(--mc-bg)]/60 p-3 sm:p-4"
        aria-live="polite"
        aria-label="Call transcript"
      >
        {turns.length === 0 && <p className="py-10 text-center text-sm text-[var(--mc-muted)]">Waiting for the first words…</p>}
        {turns.map((t) => (
          <Bubble key={t.idx} turn={t} offsetMs={offset(t.idx)} findings={findings} onOpen={onOpen} />
        ))}
      </div>
      {away && (
        <button
          onClick={() => {
            pinned.current = true
            setAway(false)
            toBottom()
          }}
          className="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-full bg-[var(--mc-accent)] px-3 py-1.5 text-xs font-medium text-white shadow-lg"
        >
          <ArrowDown className="h-3.5 w-3.5" aria-hidden /> Jump to latest
        </button>
      )}
    </div>
  )
}
