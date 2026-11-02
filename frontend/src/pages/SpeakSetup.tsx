import { LoaderCircle, Mic } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { MicMeter, useMicLevel } from '@/components/MicMeter'
import { Switch } from '@/components/Switch'
import { ApiError, createSpeakSession, testGnani, testLlm, type TestResult } from '@/lib/api'
import { audio } from '@/lib/audioEngine'
import { MIC_PROBLEM_TEXT, MicError, acquireMic, releaseMicSoon, type MicCapture } from '@/lib/micCapture'
import { usePageTitle } from '@/lib/usePageTitle'
import { keysComplete, useKeysStore } from '@/store/keysStore'
import { useSpeakStore } from '@/store/speakStore'

type Mic = { kind: 'idle' } | { kind: 'asking' } | { kind: 'ready'; mic: MicCapture } | { kind: 'problem'; text: string }
type Test = null | 'busy' | TestResult

const EXAMPLES = [
  { label: 'Polite', text: 'Good evening, I am calling from [your company] about your personal loan. This call is recorded.' },
  { label: 'Rule-breaking', text: 'If you do not pay today I will send the police to your house.' },
  { label: 'Third party', text: 'Are you his wife? Then tell her he owes us 50,000 rupees on his loan.' },
]

export function SpeakSetup() {
  usePageTitle('Speak live as the agent · Maryada')
  const navigate = useNavigate()
  const keys = useKeysStore((s) => s.keys)
  const [mic, setMic] = useState<Mic>({ kind: 'idle' })
  const [voiceOn, setVoiceOn] = useState(audio.coachVoice)
  const [gnaniTest, setGnaniTest] = useState<Test>(null)
  const [llmTest, setLlmTest] = useState<Test>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const level = useMicLevel(mic.kind === 'ready' ? mic.mic : null)

  // ?clock=HH:MM is read once, here, and kept in the set-up store
  useEffect(() => {
    useSpeakStore.getState().setClockFromAddress(new URLSearchParams(window.location.search).get('clock'))
  }, [])

  // leaving this page lets go of the microphone unless the call page takes it over within a second
  useEffect(() => () => releaseMicSoon(), [])

  const gnaniSet = keys.gnaniKey.trim() !== ''
  const llmSet = !!(keys.baseUrl.trim() && keys.llmKey.trim() && keys.model.trim())
  const ready = keysComplete(keys) && mic.kind === 'ready'

  const testMic = async () => {
    setMic({ kind: 'asking' })
    try {
      setMic({ kind: 'ready', mic: await acquireMic() })
    } catch (e) {
      setMic({ kind: 'problem', text: e instanceof MicError ? MIC_PROBLEM_TEXT[e.problem] : MIC_PROBLEM_TEXT.error })
    }
  }

  const run = async (kind: 'gnani' | 'llm') => {
    const set = kind === 'gnani' ? setGnaniTest : setLlmTest
    set('busy')
    try {
      set(kind === 'gnani' ? await testGnani(keys.gnaniKey.trim()) : await testLlm(keys.baseUrl.trim(), keys.llmKey.trim(), keys.model.trim()))
    } catch (e) {
      set({ ok: false, message_user: e instanceof Error ? e.message : 'The check failed.' })
    }
  }

  const start = async () => {
    if (!ready) return
    audio.unlock() // the click allows the coach voice to play later
    setStarting(true)
    setError(null)
    try {
      const creds = {
        gnani: { api_key: keys.gnaniKey.trim() },
        llm: { base_url: keys.baseUrl.trim(), api_key: keys.llmKey.trim(), model: keys.model.trim() },
      }
      const s = await createSpeakSession(creds, useSpeakStore.getState().clock)
      useSpeakStore.getState().setSession({ id: s.session_id, wsUrl: s.ws_url })
      navigate('/speak/call')
    } catch (e) {
      setError(e instanceof ApiError || e instanceof Error ? e.message : 'Could not start the call.')
      setStarting(false)
    }
  }

  const why = !keysComplete(keys) ? 'Add both keys in Settings to start.' : mic.kind !== 'ready' ? 'Test your microphone to start.' : ''

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5 sm:gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-[28px] font-bold tracking-[-0.025em]">Speak live as the agent</h1>
        <p className="text-[14.5px] leading-relaxed text-[var(--mc-text-2)]">
          You play the loan-recovery agent. Maryada checks only what you say, underlines rule breaks and coaches you. Nothing to configure: the
          time comes from the real clock, the language is detected, and you tell Maryada who you are speaking with during the call.
        </p>
      </div>

      <section aria-labelledby="mic-h" className="card flex flex-col gap-3 p-4 sm:p-6">
        <h2 id="mic-h" className="text-[15px] font-semibold">Microphone</h2>
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" onClick={() => void testMic()} disabled={mic.kind === 'asking'} className="btn">
            {mic.kind === 'asking' ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : <Mic className="h-4 w-4" aria-hidden />}
            {mic.kind === 'ready' ? 'Test again' : 'Test microphone'}
          </button>
          {mic.kind === 'ready' && <MicMeter level={level} />}
        </div>
        <p role="status" className={`text-[13px] ${mic.kind === 'problem' ? 'font-medium text-[var(--mc-violation-ink)]' : 'text-[var(--mc-muted)]'}`}>
          {mic.kind === 'idle' && 'Allow the microphone, then say a few words. The bar should move.'}
          {mic.kind === 'asking' && 'Waiting for the browser to allow the microphone…'}
          {mic.kind === 'ready' && 'Microphone ready. If the bar does not move when you speak, check your input device.'}
          {mic.kind === 'problem' && mic.text}
        </p>
      </section>

      <section aria-labelledby="voice-h" className="card flex flex-col gap-2 p-4 sm:p-6">
        <div className="flex items-center justify-between gap-3">
          <h2 id="voice-h" className="text-[15px] font-semibold">Coach voice</h2>
          <Switch
            label="Coach voice"
            checked={voiceOn}
            onChange={(v) => {
              audio.setCoachVoice(v)
              setVoiceOn(v)
            }}
          />
        </div>
        <p className="text-[13px] text-[var(--mc-muted)]">Wear headphones, or the voice is picked up by your microphone. The card always shows.</p>
      </section>

      <section aria-labelledby="keys-h" className="card flex flex-col gap-3 p-4 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="keys-h" className="text-[15px] font-semibold">Your keys</h2>
          <Link to="/settings" className="link">Open Settings</Link>
        </div>
        <KeyRow name="Gnani key" set={gnaniSet} test={gnaniTest} onTest={() => void run('gnani')} />
        <KeyRow name="Language model" set={llmSet} test={llmTest} onTest={() => void run('llm')} />
        <p className="text-xs text-[var(--mc-muted)]">The keys stay in your browser. Your speech goes only to your own Gnani and language-model accounts, and nothing is stored on our server.</p>
      </section>

      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" onClick={() => void start()} disabled={!ready || starting} aria-describedby={why ? 'start-why' : undefined} className="btn btn-lg btn-primary">
            {starting ? 'Starting…' : 'Start the call'}
          </button>
          {why && <span id="start-why" className="text-[13px] text-[var(--mc-muted)]">{why}</span>}
        </div>
        {error && <p role="alert" className="banner banner-warn">{error}</p>}
      </div>

      <section aria-labelledby="try-h" className="flex flex-col gap-3">
        <p className="text-[13.5px] font-medium text-[var(--mc-text-2)]">Use fictional details. Do not say real names, numbers or personal data.</p>
        <p className="text-[13.5px] text-[var(--mc-muted)]">R6 (sensitive occasions) is not checked in live mode because it relies on the borrower's words.</p>
        <h2 id="try-h" className="text-[15px] font-semibold">Lines to try</h2>
        <ul className="flex flex-col gap-2">
          {EXAMPLES.map((e) => (
            <li key={e.label} className="card flex flex-col gap-0.5 p-3.5 sm:px-5">
              <span className="lbl">{e.label}</span>
              <span className="text-[14px] leading-relaxed">“{e.text}”</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

function KeyRow({ name, set, test, onTest }: { name: string; set: boolean; test: Test; onTest: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <span className="w-32 text-[13.5px] font-medium">{name}</span>
      <span className={`chip ${set ? 'chip-ok' : 'chip-advisory'}`}>{set ? 'Set' : 'Missing'}</span>
      <button type="button" onClick={onTest} disabled={!set || test === 'busy'} className="btn btn-sm">
        {test === 'busy' ? 'Testing…' : 'Test'}
      </button>
      {test && test !== 'busy' && (
        <span role="status" className={`text-[12.5px] font-medium ${test.ok ? 'text-[var(--mc-good-practice-ink)]' : 'text-[var(--mc-violation-ink)]'}`}>
          {test.ok ? '✓ ' : '✗ '}
          {test.message_user}
        </span>
      )}
    </div>
  )
}
