/** The footer. Speak live pages say the call is the visitor's own; every other page keeps the synthetic-calls wording. */
export function Disclaimer({ speak = false }: { speak?: boolean }) {
  return (
    <footer className="border-t border-[var(--mc-line)] bg-white px-4 py-4 text-center text-xs text-[var(--mc-muted)]">
      {speak ? 'Demo: you speak this call yourself' : 'Demo with synthetic calls'} · not legal advice · based on RBI/2026-27/223 (effective 1 Jan 2027)
    </footer>
  )
}
