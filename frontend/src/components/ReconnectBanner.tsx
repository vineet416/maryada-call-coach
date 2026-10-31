import { useEffect, useState } from 'react'
import { useSessionStore } from '@/store/sessionStore'

const SHOW_AFTER_MS = 1500

/**
 * Floats above the page (no layout shift). It appears only if the connection stays down for 1.5 s,
 * so a quick resume by last_seq is invisible to the viewer.
 */
export function ReconnectBanner() {
  const conn = useSessionStore((s) => s.conn)
  const attempt = useSessionStore((s) => s.attempt)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (conn !== 'reconnecting') {
      setVisible(false)
      return
    }
    const t = window.setTimeout(() => setVisible(true), SHOW_AFTER_MS)
    return () => window.clearTimeout(t)
  }, [conn])

  if (!visible || conn !== 'reconnecting') return null
  return (
    <div
      role="status"
      className="fixed inset-x-0 top-0 z-50 flex justify-center px-4 pt-3"
    >
      <div className="rounded-full border border-[var(--mc-advisory)]/50 bg-[var(--mc-surface)] px-4 py-1.5 text-sm text-[var(--mc-advisory)] shadow-lg">
        Reconnecting… (attempt {attempt}/3)
      </div>
    </div>
  )
}
