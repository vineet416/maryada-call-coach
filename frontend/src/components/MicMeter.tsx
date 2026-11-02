import { useEffect, useState } from 'react'
import type { MicCapture } from '@/lib/micCapture'

/** The microphone level (0 to 1) of a capture, refreshed with every frame. */
export function useMicLevel(mic: MicCapture | null): number {
  const [level, setLevel] = useState(0)
  useEffect(() => {
    if (!mic) {
      setLevel(0)
      return
    }
    return mic.onLevel(setLevel)
  }, [mic])
  return level
}

const LOUD = 0.02 // above this the meter reads "hearing you"

/** A level bar with a word beside it, so the state is never shown by the bar alone. */
export function MicMeter({ level, label = 'Microphone level', compact = false }: { level: number; label?: string; compact?: boolean }) {
  const pct = Math.min(100, Math.round(level * 400))
  const hearing = level > LOUD
  return (
    <div className="flex items-center gap-2.5">
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        className={`relative overflow-hidden rounded-full border border-[var(--mc-line)] bg-[#f2f4f7] ${compact ? 'h-2.5 w-20 sm:w-28' : 'h-3 w-full max-w-xs'}`}
      >
        <div className="absolute inset-y-0 left-0 rounded-full bg-[var(--mc-good-practice)]" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-[4.5rem] text-xs font-medium text-[var(--mc-text-2)]" aria-hidden>
        {hearing ? 'Hearing you' : 'Quiet'}
      </span>
    </div>
  )
}
