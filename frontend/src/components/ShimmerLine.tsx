export function ShimmerLine({ label }: { label: string }) {
  return (
    <div className="mt-2 flex items-center gap-2" role="status" aria-label={label}>
      <div className="shimmer h-[3px] flex-1" />
      <span className="text-[11px] text-[var(--mc-muted)]">{label}…</span>
    </div>
  )
}
