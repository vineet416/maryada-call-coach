import { NavLink } from 'react-router-dom'
import { ServerChip } from '@/components/ServerChip'

const LINKS = [
  { to: '/', label: 'Cases' },
  { to: '/manager', label: 'Manager' },
  { to: '/eval', label: 'Evaluation' },
  { to: '/how', label: 'How it works' },
  { to: '/settings', label: 'Settings' },
]

export function TopBar() {
  return (
    <header className="border-b border-[var(--mc-line)] bg-[var(--mc-surface)]">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
        <span className="text-lg font-semibold">Maryada</span>
        <nav aria-label="Main" className="flex flex-wrap gap-4 text-sm">
          {LINKS.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                isActive ? 'text-[var(--mc-text)] underline underline-offset-4' : 'text-[var(--mc-muted)]'
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <ServerChip />
          <span className="rounded-full border border-[var(--mc-line)] px-2 py-0.5 text-xs text-[var(--mc-muted)]">
            Synthetic demo · not legal advice
          </span>
        </div>
      </div>
    </header>
  )
}
