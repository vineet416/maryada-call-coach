import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Disclaimer } from '@/components/Disclaimer'
import { TopBar } from '@/components/TopBar'
import { Cases, Evaluation, HowItWorks, LiveCall, Manager, NotFound, Settings } from '@/pages/Pages'

/** The call page fits one laptop screen (see .shell-call); every other page scrolls normally. */
function Shell() {
  const onCall = useLocation().pathname.startsWith('/call/')
  return (
    <div className={`shell flex min-h-screen flex-col ${onCall ? 'shell-call' : ''}`}>
      <TopBar />
      <main className="mx-auto w-full max-w-[var(--page-w)] flex-1 px-4 py-6 sm:px-8 sm:py-8">
        <Routes>
          <Route path="/" element={<Cases />} />
          <Route path="/call/:id" element={<LiveCall />} />
          <Route path="/manager" element={<Manager />} />
          <Route path="/eval" element={<Evaluation />} />
          <Route path="/evaluation" element={<Navigate to="/eval" replace />} />
          <Route path="/how" element={<HowItWorks />} />
          <Route path="/how-it-works" element={<Navigate to="/how" replace />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <Disclaimer />
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  )
}
