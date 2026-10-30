import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Disclaimer } from '@/components/Disclaimer'
import { TopBar } from '@/components/TopBar'
import { Cases, Evaluation, HowItWorks, LiveCall, Manager, NotFound, Settings } from '@/pages/Pages'

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex min-h-screen flex-col">
        <TopBar />
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
          <Routes>
            <Route path="/" element={<Cases />} />
            <Route path="/call/:id" element={<LiveCall />} />
            <Route path="/manager" element={<Manager />} />
            <Route path="/eval" element={<Evaluation />} />
            <Route path="/how" element={<HowItWorks />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </main>
        <Disclaimer />
      </div>
    </BrowserRouter>
  )
}
