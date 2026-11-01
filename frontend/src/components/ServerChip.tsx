import { useEffect, useState } from 'react'
import { useServerStore } from '@/store/serverStore'

export function ServerChip() {
  const status = useServerStore((s) => s.status)
  const check = useServerStore((s) => s.check)
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    void check()
  }, [check])

  useEffect(() => {
    if (status !== 'checking') return
    setSeconds(0)
    const id = window.setInterval(() => setSeconds((n) => n + 1), 1000)
    return () => window.clearInterval(id)
  }, [status])

  if (status === 'ready') return null
  const label =
    status === 'checking' ? `Waking server… ${seconds}s` : 'Server unreachable. Recorded runs only.'
  return (
    <span
      role="status"
      className="chip chip-warn max-w-[220px] truncate"
    >
      {label}
    </span>
  )
}
