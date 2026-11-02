import { Link } from 'react-router-dom'
import { usePageTitle } from '@/lib/usePageTitle'

export { Cases } from '@/pages/Cases'
export { LiveCall } from '@/pages/LiveCall'
export { HowItWorks } from '@/pages/HowItWorks'
export { Settings } from '@/pages/Settings'
export { Evaluation } from '@/pages/Evaluation'
export { Manager } from '@/pages/Manager'
export { ManagerAgent } from '@/pages/ManagerAgent'

export function NotFound() {
  usePageTitle('Page not found · Maryada')
  return (
    <section className="card mx-auto flex max-w-sm flex-col items-center gap-2.5 p-8 text-center">
      <span className="lbl">Page not found</span>
      <div className="text-[64px] font-bold leading-none tracking-[-0.04em] text-[#6366f1]" aria-hidden>404</div>
      <h1 className="text-[17px] font-semibold tracking-tight">This page does not exist</h1>
      <p className="max-w-[280px] text-[13.5px] leading-relaxed text-[var(--mc-muted)]">
        The link may be old or mistyped. Start again from the sample calls.
      </p>
      <Link to="/" className="btn btn-primary mt-1.5">Back to cases</Link>
    </section>
  )
}
