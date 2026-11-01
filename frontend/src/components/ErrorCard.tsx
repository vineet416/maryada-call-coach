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
    <div role="alert" className="card rise mx-auto flex max-w-lg flex-col gap-3.5 p-6 sm:p-7">
      <div className="flex items-start gap-3.5">
        <span className="flex h-10 w-10 flex-none items-center justify-center rounded-full bg-[var(--mc-violation-tint)]">
          <TriangleAlert className="h-5 w-5 text-[var(--mc-violation)]" aria-hidden />
        </span>
        <div>
          <h2 className="text-base font-semibold tracking-tight">{title}</h2>
          <p className="mt-1 text-[13.5px] leading-relaxed text-[var(--mc-muted)]">{message}</p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2.5">
        {onRetry && (
          <button onClick={onRetry} className="btn btn-primary">
            Try again
          </button>
        )}
        {children}
      </div>
    </div>
  )
}
