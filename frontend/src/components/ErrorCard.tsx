import { TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'

interface Props {
  title?: string
  message: string
  onRetry?: () => void
  children?: ReactNode
}

/** Friendly failure card with a retry; never shows raw JSON or stack traces. */
export function ErrorCard({ title = 'Something went wrong', message, onRetry, children }: Props) {
  return (
    <div
      role="alert"
      className="rise mx-auto max-w-md rounded-xl border border-[var(--mc-line)] bg-[var(--mc-surface)] p-6 text-center"
    >
      <TriangleAlert className="mx-auto mb-3 h-6 w-6 text-[var(--mc-advisory)]" aria-hidden />
      <h2 className="mb-1 text-base font-semibold">{title}</h2>
      <p className="mb-4 text-sm text-[var(--mc-muted)]">{message}</p>
      <div className="flex flex-wrap justify-center gap-2">
        {onRetry && (
          <button
            onClick={onRetry}
            className="rounded-md bg-[var(--mc-accent)] px-4 py-2 text-sm font-medium text-white hover:brightness-110"
          >
            Try again
          </button>
        )}
        {children}
      </div>
    </div>
  )
}
