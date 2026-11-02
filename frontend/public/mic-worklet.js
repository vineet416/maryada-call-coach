/* Speak live: turns the microphone signal (native rate, any channel count) into 8 kHz mono PCM16 frames of 1024 bytes
   (512 samples, 64 ms) and posts each frame with its level (RMS, 0 to 1). Plain JavaScript: it is loaded as is by the browser. */
const OUT_RATE = 8000
const FRAME_SAMPLES = 512

class Downsampler extends AudioWorkletProcessor {
  constructor() {
    super()
    this.ratio = sampleRate / OUT_RATE // input samples per output sample (5.5125 at 44.1 kHz, 6 at 48 kHz)
    this.phase = 0
    this.sum = 0
    this.count = 0
    this.out = new Int16Array(FRAME_SAMPLES)
    this.n = 0
    this.energy = 0
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0]
    if (!ch) return true
    for (let i = 0; i < ch.length; i++) {
      // averaging the input samples of one output sample is a cheap low-pass before the decimation
      this.sum += ch[i]
      this.count += 1
      this.phase += 1
      if (this.phase < this.ratio) continue
      this.phase -= this.ratio
      const v = Math.max(-1, Math.min(1, this.sum / this.count))
      this.sum = 0
      this.count = 0
      this.out[this.n++] = Math.round(v * 32767)
      this.energy += v * v
      if (this.n === FRAME_SAMPLES) {
        const level = Math.sqrt(this.energy / FRAME_SAMPLES)
        this.port.postMessage({ pcm: this.out.buffer, level }, [this.out.buffer])
        this.out = new Int16Array(FRAME_SAMPLES)
        this.n = 0
        this.energy = 0
      }
    }
    return true
  }
}

registerProcessor('maryada-downsampler', Downsampler)
