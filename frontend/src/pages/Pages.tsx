import { Link } from 'react-router-dom'
import { PageStub } from '@/components/PageStub'

export { Cases } from '@/pages/Cases'
export { LiveCall } from '@/pages/LiveCall'

export const Manager = () => (
  <PageStub title="Team compliance" note="The manager dashboard will appear here." />
)
export const Evaluation = () => <PageStub title="Evaluation" note="Evaluation results will appear here." />
export const HowItWorks = () => <PageStub title="How it works" note="The pipeline and rulebook will appear here." />
export const Settings = () => <PageStub title="Settings" note="Bring-your-own-key settings will appear here." />

export const NotFound = () => (
  <section>
    <h1 className="mb-2 text-2xl font-semibold">Page not found</h1>
    <Link to="/" className="text-[var(--mc-accent)] underline">
      Back to cases
    </Link>
  </section>
)
