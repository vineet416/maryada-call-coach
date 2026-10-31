/** Plays the call-turn MP3s and the coach voice. Started by the user's click (browsers block autoplay). */
import { audioUrl } from '@/lib/api'

const COACH_KEY = 'maryada.coachVoice'
const MUTE_KEY = 'maryada.muted'

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
  currentTurnIdx: number | null = null
  coachVoice = readFlag(COACH_KEY, true)
  muted = readFlag(MUTE_KEY, false)

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

  playTurn(url: string, idx: number) {
    this.stopTurn()
    const a = this.get(url)
    a.currentTime = 0
    a.muted = this.muted
    this.turn = a
    this.currentTurnIdx = idx
    void a.play().catch(() => undefined)
  }

  stopTurn() {
    this.turn?.pause()
    this.turn = null
    this.currentTurnIdx = null
  }

  /** Position inside the current turn audio in ms (null when nothing plays). */
  turnTimeMs(): number | null {
    return this.turn && !this.turn.paused ? this.turn.currentTime * 1000 : null
  }

  playCoach(url: string, onEnd: () => void) {
    this.stopCoach()
    if (!this.coachVoice || this.muted) {
      onEnd()
      return
    }
    const a = this.get(url)
    a.currentTime = 0
    a.volume = 1
    this.coach = a
    this.onCoachEnd = onEnd
    a.onended = () => this.finishCoach()
    a.onerror = () => this.finishCoach()
    void a.play().catch(() => this.finishCoach())
  }

  private finishCoach() {
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

  setCoachVoice(v: boolean) {
    this.coachVoice = v
    writeFlag(COACH_KEY, v)
    if (!v) this.stopCoach()
  }
}

export const audio = new AudioEngine()
