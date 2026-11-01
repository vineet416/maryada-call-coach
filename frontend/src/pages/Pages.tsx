import { Link } from 'react-router-dom'
import { usePageTitle } from '@/lib/usePageTitle'
import { ComingSoon } from '@/components/ComingSoon'

export { Cases } from '@/pages/Cases'
export { LiveCall } from '@/pages/LiveCall'
export { HowItWorks } from '@/pages/HowItWorks'
export { Settings } from '@/pages/Settings'
export { Evaluation } from '@/pages/Evaluation'

export const Manager = () => (
  <ComingSoon
    title="Team compliance"
    intro="Where coaching is needed across a team, from every call Maryada analysed."
    note="The manager view is not built yet, so no numbers are shown here. When it is, it will read results from analysed calls only."
    items={[
      { name: 'Summary tiles', text: 'Calls analysed, agents, violations, violation rate, average risk and good-practice rate.' },
      { name: 'Agent leaderboard', text: 'Calls, violations, average risk, top rule, status and risk trend for each agent.' },
      { name: 'Violations by rule', text: 'How often each of the rules R1 to R6 was broken.' },
      { name: 'Agent by rule', text: 'Which agent breaks which rule, as a compact grid.' },
      { name: 'Violations per day and calls by hour', text: 'Trends over time, and calls placed outside permitted hours.' },
      { name: 'Needs attention', text: 'Agents who may need training, with a coaching suggestion and an example call.' },
    ]}
  />
)

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
