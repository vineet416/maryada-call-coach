import { ArrowDown } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import type { Finding } from '@/lib/events'
import type { ScenarioDetail } from '@/lib/api'
import type { TurnView } from '@/store/sessionStore'
import { Bubble } from '@/components/Bubble'
import { KIND_LABEL } from '@/lib/events'

interface Props {
  turns: TurnView[]
  findings: Finding[]
  scenario: ScenarioDetail | null
  onOpen: (f: Finding) => void
  children?: ReactNode
}

const LEGEND = ['violation', 'advisory', 'needs_review', 'good_practice'] as const

/** Chat-style transcript. Follows the call; if the viewer scrolls up, a "jump to latest" pill appears. */
export function TranscriptPanel({ turns, findings, scenario, onOpen, children }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)
  const [away, setAway] = useState(false)

  const toBottom = useCallback((smooth = true) => {
    const el = box.current
    const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth && !calm ? 'smooth' : 'auto' })
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
    <section className="card relative flex min-w-0 flex-col" aria-labelledby="transcript-h">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#eaecf0] px-4 py-4 sm:px-6">
        <h2 id="transcript-h" className="text-[15px] font-semibold">Live transcript</h2>
        <ul className="hidden gap-3.5 text-xs text-[#475467] sm:flex" aria-label="Legend">
          {LEGEND.map((k) => (
            <li key={k}>
              <span className={`tok tok-${k}`}>{KIND_LABEL[k]}</span>
            </li>
          ))}
        </ul>
      </div>
      <div
        ref={box}
        id="call-transcript"
        onScroll={onScroll}
        className="flex h-[min(62vh,640px)] flex-col gap-[18px] overflow-y-auto px-4 py-5 sm:px-6"
        aria-live="polite"
        aria-label="Call transcript"
        tabIndex={0}
      >
        {turns.length === 0 && <p className="py-10 text-center text-sm text-[var(--mc-muted)]">Waiting for the first words…</p>}
        {turns.map((t) => (
          <Bubble key={t.idx} turn={t} offsetMs={offset(t.idx)} findings={findings} onOpen={onOpen} />
        ))}
      </div>
      {children}
      {away && (
        <button
          onClick={() => {
            pinned.current = true
            setAway(false)
            toBottom()
          }}
          className="btn btn-sm btn-primary absolute bottom-20 left-1/2 -translate-x-1/2 shadow-lg"
        >
          <ArrowDown className="h-3.5 w-3.5" aria-hidden /> Jump to latest
        </button>
      )}
    </section>
  )
}
