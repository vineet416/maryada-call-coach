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
      height: 32,
      waveColor: '#d0d5dd',
      progressColor: '#4338ca',
      cursorColor: '#0f172a',
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
    const turns = scenario.turns
    const loop = () => {
      const cur = audio.currentTurnIdx
      const i = cur !== null ? turns.findIndex((t) => t.idx === cur) : -1
      const into = audio.turnIntoMs()
      const call = audio.callTimeMs()
      if (i >= 0 && into !== null && call !== null) {
        // The file's cursor moves with real time but never past where the next turn starts in the file, so it holds
        // during the agent's extra wait and stays on the sound that is playing.
        const limit = i + 1 < turns.length ? turns[i + 1].offset_ms : total
        head.current = Math.min(turns[i].offset_ms + into, limit, total)
        ws.current?.setTime(head.current / 1000)
        onTime(call)
      }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [running, scenario.turns, total, onTime])

  // One marker per agent turn that has flags, labelled with its rule ids
  const marks = new Map<number, { ids: string[]; kind: Finding['kind'] }>()
  for (const f of findings) {
    if (f.kind === 'good_practice') continue
    const m = marks.get(f.turn_idx) ?? { ids: [], kind: f.kind }
    if (!m.ids.includes(f.rule_id)) m.ids.push(f.rule_id)
    if (f.kind === 'violation') m.kind = 'violation'
    marks.set(f.turn_idx, m)
  }
  return (
    <div className="relative pb-[18px] pt-1">
      {failed ? (
        <div className="h-8 rounded-md bg-[var(--mc-line)]/50" aria-hidden />
      ) : (
        <div ref={box} aria-hidden className="h-8" />
      )}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-4">
        {[...marks].map(([idx, m]) => {
          const t = scenario.turns.find((x) => x.idx === idx)
          if (!t) return null
          return (
            <span
              key={idx}
              className="absolute bottom-0 flex -translate-x-1/2 flex-col items-center gap-0.5"
              style={{ left: `${(t.offset_ms / total) * 100}%` }}
            >
              <span className="h-[9px] w-[9px] rounded-full" style={{ background: KIND_COLOR[m.kind] }} />
              <span className="text-[10px] leading-none text-[var(--mc-muted)]">{m.ids.join(' · ')}</span>
            </span>
          )
        })}
      </div>
    </div>
  )
}
