import { Menu, ShieldCheck, X } from 'lucide-react'
import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { ServerChip } from '@/components/ServerChip'

const LINKS = [
  { to: '/', label: 'Cases' },
  { to: '/manager', label: 'Manager' },
  { to: '/eval', label: 'Evaluation' },
  { to: '/how', label: 'How it works' },
  { to: '/settings', label: 'Settings' },
]

export function TopBar() {
  const [open, setOpen] = useState(false)
  const links = LINKS.map(({ to, label }) => (
    <NavLink
      key={to}
      to={to}
      end={to === '/'}
      onClick={() => setOpen(false)}
      className={({ isActive }) => `nv ${isActive ? 'on' : ''}`}
    >
      {label}
    </NavLink>
  ))
  return (
    <header className="border-b border-[var(--mc-line)] bg-white">
      <div className="mx-auto flex min-h-16 max-w-[var(--page-w)] flex-wrap items-center gap-x-7 gap-y-2 px-4 sm:px-8">
        <Link to="/" className="flex items-center gap-2.5 rounded-lg" aria-label="Maryada, home">
          <span className="flex h-[30px] w-[30px] items-center justify-center rounded-lg bg-[var(--mc-accent)]">
            <ShieldCheck className="h-[18px] w-[18px] text-white" aria-hidden />
          </span>
          <span className="text-[17px] font-bold tracking-tight">Maryada</span>
        </Link>
        <nav aria-label="Main" className="hidden flex-1 gap-1 md:flex">
          {links}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <ServerChip />
          <span className="chip hidden bg-[#f9fafb] sm:inline-flex">Synthetic demo · not legal advice</span>
          <button
            type="button"
            className="flex h-10 w-10 items-center justify-center rounded-[10px] border border-[var(--mc-line)] bg-white md:hidden"
            aria-label={open ? 'Close menu' : 'Open menu'}
            aria-expanded={open}
            aria-controls="mobile-nav"
            onClick={() => setOpen(!open)}
          >
            {open ? <X className="h-[18px] w-[18px]" aria-hidden /> : <Menu className="h-[18px] w-[18px]" aria-hidden />}
          </button>
        </div>
        {open && (
          <nav id="mobile-nav" aria-label="Main" className="flex w-full flex-col gap-1 pb-3 md:hidden">
            {links}
          </nav>
        )}
      </div>
    </header>
  )
}
