import { useEffect, useRef, useState } from 'react'
import WaveSurfer from 'wavesurfer.js'
import { audioUrl, type ScenarioDetail } from '@/lib/api'
import { audio } from '@/lib/audioEngine'
import type { Finding } from '@/lib/events'
import { KIND_COLOR } from '@/lib/findings'

interface Props {
  scenario: ScenarioDetail
  findings: Finding[]
  /** Called every frame with the playhead in ms */
  onTime: (ms: number) => void
  running: boolean
}

/** Waveform of the whole call. The playhead follows the turn audio that is actually playing. */
export function WaveformBar({ scenario, findings, onTime, running }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const ws = useRef<WaveSurfer | null>(null)
  const head = useRef(0)
  const [failed, setFailed] = useState(false)
  const total = scenario.duration_ms ?? 1

  useEffect(() => {
    if (!box.current || !scenario.call_audio_url) return
    const s = WaveSurfer.create({
      container: box.current,
      url: audioUrl(scenario.call_audio_url),
      height: 52,
      waveColor: '#33465c',
      progressColor: '#4f8cff',
      cursorColor: '#e6edf3',
      cursorWidth: 2,
      barWidth: 2,
      barGap: 2,
      barRadius: 2,
      normalize: true,
      interact: false,
      hideScrollbar: true,
    })
    s.setMuted(true)
    s.on('error', () => setFailed(true))
    ws.current = s
    return () => {
      s.destroy()
      ws.current = null
    }
  }, [scenario.call_audio_url])

  useEffect(() => {
    if (!running) return
    let raf = 0
    const offsets = new Map(scenario.turns.map((t) => [t.idx, t]))
    const loop = () => {
      const cur = audio.currentTurnIdx
      const t = cur !== null ? offsets.get(cur) : undefined
      const pos = audio.turnTimeMs()
      if (t && pos !== null) {
        head.current = Math.min(t.offset_ms + pos, total)
        ws.current?.setTime(head.current / 1000)
        onTime(head.current)
      }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [running, scenario.turns, total, onTime])

  const marks = findings.filter((f) => f.kind !== 'good_practice')
  return (
    <div className="relative">
      {failed ? (
        <div className="h-[52px] rounded-md bg-[var(--mc-line)]/50" aria-hidden />
      ) : (
        <div ref={box} aria-hidden className="h-[52px]" />
      )}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-1.5">
        {marks.map((f) => {
          const t = scenario.turns.find((x) => x.idx === f.turn_idx)
          if (!t) return null
          return (
            <span
              key={f.id}
              className="absolute bottom-0 h-1.5 w-1.5 -translate-x-1/2 rounded-full"
              style={{ left: `${(t.offset_ms / total) * 100}%`, background: KIND_COLOR[f.kind] }}
            />
          )
        })}
      </div>
    </div>
  )
}
