import { create } from 'zustand'
import type { Band, Envelope, Finding, Speaker, Token } from '@/lib/events'

export type SessionStatus = 'idle' | 'connecting' | 'live' | 'ended' | 'error'
export type Mode = 'live' | 'replay'
export type Conn = 'idle' | 'open' | 'reconnecting' | 'failed'

export interface TokenView extends Token {
  /** Position inside its segment, drives the word-by-word reveal delay */
  d: number
  /** Number of words in its segment */
  n: number
}

export interface TurnView {
  idx: number
  speaker: Speaker
  audioUrl: string
  durationMs: number
  tokens: TokenView[]
  analysing: boolean
  ended: boolean
  /** True when the turn arrived as catch-up after a reconnect: no reveal animation */
  instant: boolean
  startedAt: number
}

export interface Nudge {
  findingId: string | null
  ruleId: string
  text: string
  audioUrl: string
  speaking: boolean
  latencyMs: number | null
}

export interface Risk {
  score: number
  band: Band
  delta: number
  reasonRule: string | null
}

export interface Summary {
  risk_peak: number
  findings_count: number
  by_rule: Record<string, number>
  stopped?: boolean
}

export interface Stage {
  stage: string
  text: string
  turnIdx: number
  since: number
}

export interface SessionState {
  status: SessionStatus
  mode: Mode
  sessionId: string | null
  conn: Conn
  attempt: number
  lastSeq: number
  turns: TurnView[]
  findings: Finding[]
  risk: Risk
  riskPeak: number
  stage: Stage | null
  banner: { kind: string; message: string } | null
  nudge: Nudge | null
  coachHold: boolean
  summary: Summary | null
  error: string | null
  langs: string[]
  latencyMs: number | null
  simulatedStart: string | null
  /** Speak live: who the visitor says they are speaking with (the server's value; 'unknown' until chosen) */
  answeredBy: string
  callStart: number | null
  reset: (mode: Mode) => void
  setStatus: (s: SessionStatus) => void
  setMode: (m: Mode) => void
  setSessionId: (id: string) => void
  setConn: (c: Conn, attempt?: number) => void
  setFailed: (message: string) => void
  setNudgeSpeaking: (v: boolean) => void
  setCoachHold: (v: boolean) => void
  apply: (env: Envelope, stale: boolean) => void
}

const ZERO_RISK: Risk = { score: 0, band: 'low', delta: 0, reasonRule: null }

const initial = {
  status: 'idle' as SessionStatus,
  mode: 'live' as Mode,
  sessionId: null,
  conn: 'idle' as Conn,
  attempt: 0,
  lastSeq: 0,
  turns: [] as TurnView[],
  findings: [] as Finding[],
  risk: ZERO_RISK,
  riskPeak: 0,
  stage: null,
  banner: null,
  nudge: null,
  coachHold: false,
  summary: null,
  error: null,
  langs: [] as string[],
  latencyMs: null,
  simulatedStart: null,
  answeredBy: 'unknown',
  callStart: null,
}

const LANG_CODE: Record<string, string> = { hi: 'Hindi', mr: 'Marathi', en: 'English' }

export const useSessionStore = create<SessionState>((set, get) => ({
  ...initial,
  reset: (mode) => set({ ...initial, mode }),
  setStatus: (status) => set({ status }),
  setMode: (mode) => set({ mode }),
  setSessionId: (sessionId) => set({ sessionId }),
  setConn: (conn, attempt = 0) => set({ conn, attempt }),
  setFailed: (message) => set({ status: 'error', conn: 'failed', error: message }),
  setNudgeSpeaking: (v) => set((s) => (s.nudge ? { nudge: { ...s.nudge, speaking: v } } : {})),
  setCoachHold: (coachHold) => set({ coachHold }),

  apply: (env, stale) => {
    // seq is monotonic per session: anything at or below the last applied seq is a duplicate
    if (env.seq <= get().lastSeq) return
    const d = env.data
    const patch: Partial<SessionState> = { lastSeq: env.seq }
    const s = get()

    switch (env.type) {
      case 'session.started':
        patch.status = 'live'
        patch.simulatedStart = d.simulated_start_time ?? null
        patch.callStart = Date.now()
        break

      case 'context.updated':
        patch.answeredBy = d.answered_by
        if (s.nudge?.ruleId === 'SELECT' && d.answered_by !== 'unknown') patch.nudge = null // the reminder has done its job
        break

      case 'stage.status':
        patch.stage = { stage: d.stage, text: d.text, turnIdx: d.turn_idx, since: Date.now() }
        break

      case 'turn.started': {
        // A repeated turn_idx (recorded fallback restarts a turn) replaces the earlier copy
        const rest = s.turns.filter((t) => t.idx !== d.turn_idx)
        const turn: TurnView = {
          idx: d.turn_idx,
          speaker: d.speaker,
          audioUrl: d.audio_url,
          durationMs: d.duration_ms,
          tokens: [],
          analysing: false,
          ended: false,
          instant: stale,
          startedAt: Date.now(),
        }
        patch.turns = [...rest, turn].sort((a, b) => a.idx - b.idx)
        patch.coachHold = false
        break
      }

      case 'transcript.final': {
        const raw: Token[] = d.tokens ?? []
        const first = raw.length ? raw[0].i : 0
        const add: TokenView[] = raw.map((t) => ({ ...t, d: t.i - first, n: raw.length }))
        const langs = new Set(s.langs)
        for (const t of raw) if (LANG_CODE[t.lang]) langs.add(LANG_CODE[t.lang])
        const turns = s.turns.map((t) =>
          t.idx === d.turn_idx && !t.tokens.some((x) => add.length && x.i === add[0].i)
            ? {
                ...t,
                tokens: [...t.tokens, ...add].sort((a, b) => a.i - b.i),
                // the words arrived after the audio had already played: show them at once
                instant: t.instant || Date.now() - t.startedAt > t.durationMs,
              }
            : t,
        )
        patch.turns = turns
        patch.langs = [...langs]
        break
      }

      case 'finding.pending':
        patch.turns = s.turns.map((t) => (t.idx === d.turn_idx ? { ...t, analysing: true } : t))
        break

      case 'finding.detected': {
        const f = d as unknown as Finding
        // Same finding id (early then deep result) replaces itself: never a duplicate chip
        const rest = s.findings.filter((x) => x.id !== f.id)
        patch.findings = [...rest, f]
        if (typeof f.latency?.total_ms === 'number' && f.kind !== 'good_practice') patch.latencyMs = f.latency.total_ms
        break
      }

      case 'coach.nudge':
        patch.nudge = {
          findingId: d.finding_id ?? null,
          ruleId: d.rule_id,
          text: d.text,
          audioUrl: d.audio_url,
          speaking: false,
          latencyMs: d.latency?.total_ms ?? null,
        }
        if (typeof d.latency?.total_ms === 'number') patch.latencyMs = d.latency.total_ms
        break

      case 'risk.update': {
        // The meter only ever follows risk.update events in order, so a resume cannot make it jump
        patch.risk = { score: d.score, band: d.band, delta: d.delta, reasonRule: d.reason_rule_id ?? null }
        patch.riskPeak = Math.max(s.riskPeak, d.score)
        break
      }

      case 'turn.ended':
        patch.turns = s.turns.map((t) => (t.idx === d.turn_idx ? { ...t, ended: true, analysing: false } : t))
        break

      case 'banner':
        patch.banner = { kind: d.kind, message: d.message }
        if (d.kind === 'replay') patch.mode = 'replay'
        break

      case 'session.ended':
        patch.status = 'ended'
        patch.summary = d.summary
        patch.stage = null
        patch.coachHold = false
        break

      case 'error':
        patch.error = d.message_user ?? 'Something went wrong.'
        if (!d.retryable) patch.status = 'error'
        break
    }
    set(patch)
  },
}))
