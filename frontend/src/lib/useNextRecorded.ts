import { useEffect, useState } from 'react'
import { getScenarios } from '@/lib/api'

/** Id of the next recorded run after this one in the Cases order (wrapping round); null when there is none. */
export function useNextRecorded(currentId: string): string | null {
  const [next, setNext] = useState<string | null>(null)
  useEffect(() => {
    const ctl = new AbortController()
    getScenarios(ctl.signal)
      .then((list) => {
        // same order as the Cases page: recorded runs first
        const all = [...list].sort((a, b) => Number(b.has_replay) - Number(a.has_replay))
        const at = all.findIndex((c) => c.id === currentId)
        const after = [...all.slice(at + 1), ...all.slice(0, Math.max(at, 0))]
        setNext(after.find((c) => c.has_replay && c.id !== currentId)?.id ?? null)
      })
      .catch(() => undefined) // the suggestion is optional
    return () => ctl.abort()
  }, [currentId])
  return next
}
