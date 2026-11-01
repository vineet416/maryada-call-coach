/**
 * WebSocket client for one call. Reconnects by itself (3 tries, 1/2/4 s) and resumes with the last
 * applied seq, so the server replays only what the screen has not seen. Events that arrive late as
 * catch-up are applied silently (no reveal animation, no audio) so a reconnect never looks like a glitch.
 */
import { audio } from '@/lib/audioEngine'
import { wsUrl } from '@/lib/api'
import type { Envelope } from '@/lib/events'
import { useSessionStore } from '@/store/sessionStore'

const RETRY_MS = [1000, 2000, 4000]
const STALE_AFTER_MS = 1500
const COACH_GAP_MS = 300

export class CallClient {
  private ws: WebSocket | null = null
  private attempt = 0
  private timer: number | undefined
  private finished = false
  private opened = false
  private anchor: { t: number; at: number } | null = null

  private path: string
  private hold: boolean // the "pause for the coach" choice made at start; the server uses the same one
  private played = new Set<number>()

  constructor(path: string, hold = false) {
    this.path = path
    this.hold = hold
  }

  open() {
    this.finished = false
    this.connect()
  }

  /** Stop the call from the user's side. */
  stop() {
    this.send({ type: 'stop' })
  }

  close() {
    this.finished = true
    window.clearTimeout(this.timer)
    const ws = this.ws
    this.ws = null
    if (ws) {
      ws.onopen = ws.onmessage = ws.onclose = ws.onerror = null
      ws.close()
    }
    audio.stopAll()
  }

  private send(msg: object) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg))
  }

  private connect() {
    const store = useSessionStore.getState()
    const ws = new WebSocket(wsUrl(this.path))
    this.ws = ws
    ws.onopen = () => {
      const last = useSessionStore.getState().lastSeq
      this.send(this.opened ? { type: 'resume', last_seq: last } : { type: 'start' })
      this.opened = true
      useSessionStore.getState().setConn('open')
    }
    ws.onmessage = (m) => {
      let env: Envelope
      try {
        env = JSON.parse(m.data as string) as Envelope
      } catch {
        return
      }
      this.attempt = 0 // data is flowing again: a later drop gets a fresh set of tries
      this.handle(env)
    }
    ws.onclose = () => this.onDrop()
    ws.onerror = () => undefined // onclose follows and handles it
    if (store.conn === 'idle') store.setConn('open')
  }

  private onDrop() {
    if (this.finished) return
    const st = useSessionStore.getState()
    if (st.status === 'ended' || st.status === 'error') return
    if (this.attempt >= RETRY_MS.length) {
      st.setFailed('The connection to the server was lost.')
      audio.stopAll()
      return
    }
    const wait = RETRY_MS[this.attempt]
    this.attempt += 1
    st.setConn('reconnecting', this.attempt)
    this.timer = window.setTimeout(() => this.connect(), wait)
  }

  private handle(env: Envelope) {
    const st = useSessionStore.getState()
    if (env.seq <= st.lastSeq) return // duplicate after a resume
    const now = performance.now()
    const est = this.anchor ? this.anchor.t + (now - this.anchor.at) : env.t_ms
    const stale = env.t_ms < est - STALE_AFTER_MS
    if (!stale) this.anchor = { t: env.t_ms, at: now }

    st.apply(env, stale)
    if (!stale) this.sideEffects(env)
    if (env.type === 'session.ended') {
      this.finished = true
      audio.stopTurn()
      this.ws?.close()
    }
  }

  private sideEffects(env: Envelope) {
    const st = useSessionStore.getState()
    switch (env.type) {
      case 'turn.started':
        // a turn re-sent by the recorded fallback must not restart audio that already played
        if (this.played.has(env.data.turn_idx)) break
        this.played.add(env.data.turn_idx)
        audio.playTurn(env.data.audio_url, env.data.turn_idx, env.data.speaker)
        break
      case 'coach.speak': {
        // The clip plays on top of the call at its event time (the call is lowered a little while it plays; it is never
        // paused) unless the user chose
        // "Pause the call while the coach speaks" (the server then also moves the later turns by the clip length).
        st.setNudgeSpeaking(true)
        if (this.hold) {
          st.setCoachHold(true)
          audio.pauseTurn()
          // the server moves later turns by the clip length plus the gap, even if the voice is muted meanwhile
          window.setTimeout(() => {
            useSessionStore.getState().setCoachHold(false)
            audio.resumeTurn()
          }, (env.data.duration_ms ?? 0) + COACH_GAP_MS)
        }
        audio.playCoach(env.data.audio_url, () => useSessionStore.getState().setNudgeSpeaking(false), !this.hold)
        break
      }
      case 'coach.nudge':
        if (env.data.audio_url) audio.preload([env.data.audio_url])
        break
    }
  }
}
