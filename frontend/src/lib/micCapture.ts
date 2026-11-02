/**
 * Speak live: the visitor's microphone. getUserMedia (echo cancellation, noise suppression and auto gain on) feeds an
 * AudioWorklet (public/mic-worklet.js) that resamples to 8 kHz mono PCM16 and hands out frames of 1024 bytes with a level.
 * Nothing is recorded or kept here: a frame goes to the sink and is gone. One capture is shared by the set-up page (the
 * microphone test) and the call page, so the browser asks for permission once.
 */
export type MicProblem = 'insecure' | 'unsupported' | 'denied' | 'missing' | 'busy' | 'error'

export const MIC_PROBLEM_TEXT: Record<MicProblem, string> = {
  insecure: 'The microphone only works on a secure page (https, or localhost while testing). Open Maryada over https.',
  unsupported: 'This browser cannot capture the microphone. Use a current Chrome, Edge, Firefox or Safari.',
  denied: 'Microphone access is blocked. Allow it for this site in the browser address bar, then try again.',
  missing: 'No microphone was found. Plug one in or choose one in your system settings, then try again.',
  busy: 'The microphone is in use by another app or tab. Close it there, then try again.',
  error: 'The microphone could not be started. Reload the page and try again.',
}

export class MicError extends Error {
  problem: MicProblem
  constructor(problem: MicProblem) {
    super(MIC_PROBLEM_TEXT[problem])
    this.problem = problem
  }
}

function problemOf(e: unknown): MicProblem {
  const name = e instanceof DOMException ? e.name : ''
  if (name === 'NotAllowedError' || name === 'SecurityError') return 'denied'
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'missing'
  if (name === 'NotReadableError' || name === 'AbortError') return 'busy'
  return 'error'
}

export type FrameSink = (frame: ArrayBuffer) => void

export class MicCapture {
  private ctx: AudioContext
  private stream: MediaStream
  private node: AudioWorkletNode
  private sink: FrameSink | null = null
  private levelListeners = new Set<(level: number) => void>()
  private endListeners = new Set<() => void>()
  level = 0

  private constructor(ctx: AudioContext, stream: MediaStream, node: AudioWorkletNode) {
    this.ctx = ctx
    this.stream = stream
    this.node = node
    node.port.onmessage = (m: MessageEvent<{ pcm: ArrayBuffer; level: number }>) => {
      this.level = m.data.level
      this.levelListeners.forEach((f) => f(this.level))
      this.sink?.(m.data.pcm)
    }
    stream.getAudioTracks().forEach((t) => (t.onended = () => this.endListeners.forEach((f) => f())))
  }

  static async open(): Promise<MicCapture> {
    if (!window.isSecureContext) throw new MicError('insecure')
    if (!navigator.mediaDevices?.getUserMedia || typeof AudioWorkletNode === 'undefined') throw new MicError('unsupported')
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      })
    } catch (e) {
      throw new MicError(problemOf(e))
    }
    try {
      const ctx = new AudioContext() // the native rate: the worklet resamples to 8 kHz
      await ctx.audioWorklet.addModule(`${import.meta.env.BASE_URL}mic-worklet.js`)
      const node = new AudioWorkletNode(ctx, 'maryada-downsampler', { numberOfOutputs: 0 })
      ctx.createMediaStreamSource(stream).connect(node)
      await ctx.resume()
      return new MicCapture(ctx, stream, node)
    } catch {
      stream.getTracks().forEach((t) => t.stop())
      throw new MicError('error')
    }
  }

  setSink(sink: FrameSink | null) {
    this.sink = sink
  }

  onLevel(f: (level: number) => void) {
    this.levelListeners.add(f)
    return () => void this.levelListeners.delete(f)
  }

  /** Called when the microphone stops by itself (unplugged, or permission taken away). */
  onEnded(f: () => void) {
    this.endListeners.add(f)
    return () => void this.endListeners.delete(f)
  }

  get alive() {
    return this.stream.getAudioTracks().some((t) => t.readyState === 'live')
  }

  close() {
    this.sink = null
    this.node.port.onmessage = null
    this.stream.getTracks().forEach((t) => t.stop())
    void this.ctx.close().catch(() => undefined)
  }
}

let current: MicCapture | null = null
let opening: Promise<MicCapture> | null = null
let releaseTimer: number | undefined

/** The shared capture: reuses a live one, otherwise asks the browser. */
export async function acquireMic(): Promise<MicCapture> {
  window.clearTimeout(releaseTimer)
  if (current?.alive) return current
  opening ??= MicCapture.open()
    .then((c) => (current = c))
    .finally(() => (opening = null))
  return opening
}

/** Let go of the microphone shortly after the last page using it is gone (a quick remount keeps it). */
export function releaseMicSoon(delayMs = 1000) {
  window.clearTimeout(releaseTimer)
  releaseTimer = window.setTimeout(() => {
    current?.close()
    current = null
  }, delayMs)
}
