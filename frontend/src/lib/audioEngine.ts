/** Plays the call-turn MP3s and the coach voice. Started by the user's click (browsers block autoplay). */
import { audioUrl } from '@/lib/api'

const COACH_KEY = 'maryada.coachVoice'
const MUTE_KEY = 'maryada.muted'
const PAUSE_KEY = 'maryada.pauseForCoach'
const VOLUME_KEY = 'maryada.coachVolume'

/**
 * Browser gains. The library already mixes the voices at agent -22, borrower -24, third party -25 and coach -27 LUFS.
 * The coach clip plays on top of the call, so it gets a further -1.5 dB (0.84), and the call is lowered by DUCK_DB while
 * the clip plays: the coach ends up about 3 dB under the borrower (-28.5 against -25.5 LUFS) and 5 dB under the agent. The call voices play at full
 * level. (iOS ignores element volume, so there only the library levels apply.)
 */
const CALL_GAIN = { agent: 1, borrower: 1, third_party: 1 }
export const COACH_GAIN = 0.84
/** The volume slider (0 to 100) is the element volume in percent: 100 is the clip at its own level, which peaks well under full scale, so it never clips. Untouched, it equals COACH_GAIN. */
export const DEFAULT_COACH_VOLUME = Math.round(COACH_GAIN * 100)
/** The call audio is lowered by this much while the coach clip plays (0 turns ducking off). */
export const DUCK_DB = -1.5

/** Tuning by ear in the dev server only: ?coach=<gain 0.1-1>&duck=<dB 0-6>. Missing or invalid values are ignored. */
function override(name: string, lo: number, hi: number): number | null {
  if (!import.meta.env.DEV) return null
  const raw = new URLSearchParams(window.location.search).get(name)
  const v = raw === null || raw.trim() === '' ? NaN : Number(raw)
  return Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : null
}
const duckDb = () => (override('duck', 0, 6) !== null ? -(override('duck', 0, 6) as number) : DUCK_DB)
const FADE_MS = 150

function readVolume(): number {
  try {
    const raw = localStorage.getItem(VOLUME_KEY)
    const v = raw === null ? NaN : Number(raw)
    return Number.isFinite(v) ? Math.min(100, Math.max(0, Math.round(v))) : DEFAULT_COACH_VOLUME
  } catch {
    return DEFAULT_COACH_VOLUME
  }
}

function readFlag(key: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(key)
    return v === null ? fallback : v === '1'
  } catch {
    return fallback
  }
}
function writeFlag(key: string, v: boolean) {
  try {
    localStorage.setItem(key, v ? '1' : '0')
  } catch {
    /* storage may be blocked */
  }
}

class AudioEngine {
  private turn: HTMLAudioElement | null = null
  private coach: HTMLAudioElement | null = null
  private cache = new Map<string, HTMLAudioElement>()
  private onCoachEnd: (() => void) | null = null
  private turnGain = 1
  private duckLevel = 1 // current multiplier on the call audio (1 = not ducked)
  private duckTarget = 1
  private duckTimer: number | undefined
  currentTurnIdx: number | null = null
  private turnStartT = 0 // call time (server clock, ms) at which the current turn's audio starts
  private turnPlayedAt = 0 // performance.now() when it was started here
  private frozenInto = 0 // ms into the turn while the call is held
  private held = false // the call is paused for the coach (the pause option); a finished clip also reports paused
  coachVoice = readFlag(COACH_KEY, true)
  /** 0 to 100, kept in this browser; applies to the next coach clip (and to the one playing). */
  coachVolume = readVolume()
  muted = readFlag(MUTE_KEY, false)
  /** Option: the call pauses only while the coach clip plays. Default off (the coach plays over the call). */
  pauseForCoach = readFlag(PAUSE_KEY, false)

  private get(url: string): HTMLAudioElement {
    let a = this.cache.get(url)
    if (!a) {
      a = new Audio(audioUrl(url))
      a.preload = 'auto'
      this.cache.set(url, a)
    }
    return a
  }

  preload(urls: string[]) {
    urls.forEach((u) => this.get(u))
  }

  /** Called inside the Start click so later programmatic play() calls are allowed. */
  unlock() {
    const a = new Audio()
    a.muted = true
    void a.play().catch(() => undefined)
  }

  playTurn(url: string, idx: number, speaker: keyof typeof CALL_GAIN = 'agent', startT = 0) {
    this.stopTurn()
    const a = this.get(url)
    a.currentTime = 0
    a.muted = this.muted
    this.turnGain = CALL_GAIN[speaker]
    a.volume = this.turnGain * this.duckLevel
    this.turn = a
    this.currentTurnIdx = idx
    this.turnStartT = startT
    this.turnPlayedAt = performance.now()
    this.frozenInto = 0
    this.held = false
    void a.play().catch(() => undefined)
  }

  stopTurn() {
    this.turn?.pause()
    this.turn = null
    this.currentTurnIdx = null
  }

  /** Lower (or restore) the call audio with a short fade. */
  private setDuck(on: boolean) {
    this.duckTarget = on ? 10 ** (duckDb() / 20) : 1
    window.clearInterval(this.duckTimer)
    const step = ((1 - 10 ** (duckDb() / 20)) * 20) / FADE_MS || 1
    this.duckTimer = window.setInterval(() => {
      const d = this.duckTarget - this.duckLevel
      this.duckLevel = Math.abs(d) <= step ? this.duckTarget : this.duckLevel + Math.sign(d) * step
      if (this.turn) this.turn.volume = this.turnGain * this.duckLevel
      if (this.duckLevel === this.duckTarget) window.clearInterval(this.duckTimer)
    }, 20)
  }

  /** Hold the call audio where it is (only used by the "pause while the coach speaks" option). */
  pauseTurn() {
    this.frozenInto = this.turnIntoMs() ?? this.frozenInto
    this.held = true
    this.turn?.pause()
  }

  resumeTurn() {
    if (this.held && this.turn?.ended) this.turnPlayedAt = performance.now() - this.frozenInto
    this.held = false
    if (this.turn && !this.turn.ended) void this.turn.play().catch(() => undefined)
  }

  /**
   * Real time since this turn's audio started, in ms (null when no turn was started). It follows the audio while it plays
   * and the clock after it ended (the silence before the next turn, including the agent's wait for a nudge); it holds
   * only while the call is paused for the coach.
   */
  turnIntoMs(): number | null {
    if (!this.turn) return null
    if (this.held) return this.frozenInto
    const audioMs = this.turn.currentTime * 1000
    this.frozenInto = this.turn.ended ? Math.max(audioMs, performance.now() - this.turnPlayedAt) : audioMs
    return this.frozenInto
  }

  /** Call time in ms on the server clock: the start of the current turn plus the real time into it. */
  callTimeMs(): number | null {
    const into = this.turnIntoMs()
    return into === null ? null : this.turnStartT + into
  }

  private coachLevel() {
    return override('coach', 0.1, 1) ?? this.coachVolume / 100
  }

  playCoach(url: string, onEnd: () => void, duck = true, force = false) {
    this.stopCoach()
    if (!force && (!this.coachVoice || this.muted)) {
      onEnd()
      return
    }
    const a = this.get(url)
    a.currentTime = 0
    a.volume = this.coachLevel()
    this.coach = a
    this.onCoachEnd = onEnd
    if (duck) this.setDuck(true)
    a.onended = () => this.finishCoach()
    a.onerror = () => this.finishCoach()
    void a.play().catch(() => this.finishCoach())
  }

  private finishCoach() {
    this.setDuck(false)
    const cb = this.onCoachEnd
    this.onCoachEnd = null
    if (this.coach) this.coach.onended = null
    this.coach = null
    cb?.()
  }

  /** Settings: hear an existing coach clip at the chosen level (no call is playing, so nothing is ducked). */
  previewCoach(url: string, onEnd: () => void) {
    this.playCoach(url, onEnd, false, true)
  }

  setCoachVolume(v: number) {
    this.coachVolume = Math.min(100, Math.max(0, Math.round(v)))
    try {
      localStorage.setItem(VOLUME_KEY, String(this.coachVolume))
    } catch {
      /* storage may be blocked: the level then lasts until the page is closed */
    }
    if (this.coach) this.coach.volume = this.coachLevel()
  }

  stopCoach() {
    if (!this.coach) return
    this.coach.pause()
    this.finishCoach()
  }

  stopAll() {
    this.stopTurn()
    this.stopCoach()
  }

  setMuted(v: boolean) {
    this.muted = v
    writeFlag(MUTE_KEY, v)
    if (this.turn) this.turn.muted = v
    if (v) this.stopCoach()
  }

  setPauseForCoach(v: boolean) {
    this.pauseForCoach = v
    writeFlag(PAUSE_KEY, v)
  }

  /** What the server is told at start: pause only when the coach will really be heard. */
  get holdForCoach(): boolean {
    return this.pauseForCoach && this.coachVoice && !this.muted
  }

  setCoachVoice(v: boolean) {
    this.coachVoice = v
    writeFlag(COACH_KEY, v)
    if (!v) this.stopCoach()
  }
}

export const audio = new AudioEngine()
