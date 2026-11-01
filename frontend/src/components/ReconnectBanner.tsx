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
    <div role="status" className="fixed inset-x-0 top-0 z-50">
      <div className="flex items-center gap-2.5 border-b border-[var(--mc-advisory-edge)] bg-[var(--mc-advisory-tint)] px-5 py-3 text-[13px] font-medium text-[#93370d]">
        <span className="spinner h-4 w-4 flex-none !border-[2.5px] !border-[var(--mc-advisory-edge)] !border-t-[var(--mc-advisory-ink)]" aria-hidden />
        Connection lost. Reconnecting, your call is safe… (attempt {attempt}/3)
      </div>
    </div>
  )
}
