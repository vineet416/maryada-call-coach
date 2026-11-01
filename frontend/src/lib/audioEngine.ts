/** Plays the call-turn MP3s and the coach voice. Started by the user's click (browsers block autoplay). */
import { audioUrl } from '@/lib/api'

const COACH_KEY = 'maryada.coachVoice'
const MUTE_KEY = 'maryada.muted'
const PAUSE_KEY = 'maryada.pauseForCoach'

/**
 * Browser gains. The library already mixes the voices at agent -22, borrower -24, third party -25 and coach -27 LUFS;
 * the coach clip plays on top of the call, so it gets a further -1.9 dB (0.8): about 5 dB under the borrower and
 * 7 dB under the agent. The call voices play at full level. (iOS ignores element volume, so there the library levels
 * alone keep the order.)
 */
const GAIN = { agent: 1, borrower: 1, third_party: 1, coach: 0.8 }
/** The call audio is lowered by this much while the coach clip plays (3-4 dB; 0 turns ducking off). */
export const DUCK_DB = -3.5
const FADE_MS = 150

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
  coachVoice = readFlag(COACH_KEY, true)
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

  playTurn(url: string, idx: number, speaker: keyof typeof GAIN = 'agent') {
    this.stopTurn()
    const a = this.get(url)
    a.currentTime = 0
    a.muted = this.muted
    this.turnGain = GAIN[speaker]
    a.volume = this.turnGain * this.duckLevel
    this.turn = a
    this.currentTurnIdx = idx
    void a.play().catch(() => undefined)
  }

  stopTurn() {
    this.turn?.pause()
    this.turn = null
    this.currentTurnIdx = null
  }

  /** Lower (or restore) the call audio with a short fade. */
  private setDuck(on: boolean) {
    this.duckTarget = on ? 10 ** (DUCK_DB / 20) : 1
    window.clearInterval(this.duckTimer)
    const step = ((1 - 10 ** (DUCK_DB / 20)) * 20) / FADE_MS || 1
    this.duckTimer = window.setInterval(() => {
      const d = this.duckTarget - this.duckLevel
      this.duckLevel = Math.abs(d) <= step ? this.duckTarget : this.duckLevel + Math.sign(d) * step
      if (this.turn) this.turn.volume = this.turnGain * this.duckLevel
      if (this.duckLevel === this.duckTarget) window.clearInterval(this.duckTimer)
    }, 20)
  }

  /** Hold the call audio where it is (only used by the "pause while the coach speaks" option). */
  pauseTurn() {
    this.turn?.pause()
  }

  resumeTurn() {
    if (this.turn && !this.turn.ended) void this.turn.play().catch(() => undefined)
  }

  /** Position inside the current turn audio in ms (null when nothing plays). */
  turnTimeMs(): number | null {
    return this.turn && !this.turn.paused ? this.turn.currentTime * 1000 : null
  }

  playCoach(url: string, onEnd: () => void, duck = true) {
    this.stopCoach()
    if (!this.coachVoice || this.muted) {
      onEnd()
      return
    }
    const a = this.get(url)
    a.currentTime = 0
    a.volume = GAIN.coach
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
