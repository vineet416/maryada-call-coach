import { usePageTitle } from '@/lib/usePageTitle'
import { Link } from 'react-router-dom'
import { Hourglass } from 'lucide-react'

interface Props {
  title: string
  intro: string
  /** What the page will show once its data exists */
  items: { name: string; text: string }[]
  note: string
}

/** Empty state for a page whose data does not exist yet. It shows no numbers, only what will appear. */
export function ComingSoon({ title, intro, items, note }: Props) {
  usePageTitle(`${title} · Maryada`)
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-bold tracking-[-0.025em]">{title}</h1>
          <p className="mt-0.5 max-w-[700px] text-sm text-[var(--mc-muted)]">{intro}</p>
        </div>
        <span className="chip chip-accent">
          <Hourglass className="h-3.5 w-3.5" aria-hidden /> Coming soon
        </span>
      </div>

      <section className="card flex flex-col items-start gap-3 border-[var(--mc-accent-ring)] bg-[#f8f8ff] p-6" aria-labelledby="soon-h">
        <h2 id="soon-h" className="text-[17px] font-semibold tracking-tight text-[var(--mc-accent-dark)]">Nothing to show yet</h2>
        <p className="max-w-[720px] text-[13.5px] leading-relaxed text-[var(--mc-text-2)]">{note}</p>
        <Link to="/" className="link text-[13.5px]">Browse the sample calls →</Link>
      </section>

      <section aria-labelledby="will-h" className="flex flex-col gap-3.5">
        <h2 id="will-h" className="text-lg font-semibold tracking-tight">What will appear here</h2>
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((i) => (
            <li key={i.name} className="card flex flex-col gap-2 p-5">
              <h3 className="text-[15px] font-semibold">{i.name}</h3>
              <p className="text-[13px] leading-normal text-[var(--mc-muted)]">{i.text}</p>
              <div className="mt-1 space-y-2" aria-hidden>
                <div className="h-2 w-4/5 rounded-full bg-[#eaecf0]" />
                <div className="h-2 w-3/5 rounded-full bg-[#eaecf0]" />
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
