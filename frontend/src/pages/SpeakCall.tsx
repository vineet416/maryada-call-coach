import { LoaderCircle, Mic, Square, Volume2, VolumeX } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AnsweredBySelector } from '@/components/AnsweredBySelector'
import { CoachCard } from '@/components/CoachCard'
import { DetailDrawer } from '@/components/DetailDrawer'
import { ErrorCard } from '@/components/ErrorCard'
import { FindingList } from '@/components/FindingChip'
import { MicMeter, useMicLevel } from '@/components/MicMeter'
import { ReconnectBanner } from '@/components/ReconnectBanner'
import { RiskMeter } from '@/components/RiskMeter'
import { StageLine } from '@/components/StageLine'
import { TranscriptPanel } from '@/components/TranscriptPanel'
import { getRules, type Rule } from '@/lib/api'
import { audio } from '@/lib/audioEngine'
import { CallClient } from '@/lib/callClient'
import type { Finding } from '@/lib/events'
import { MIC_CALL_LIMIT_S } from '@/lib/limits'
import { MIC_PROBLEM_TEXT, MicError, acquireMic, releaseMicSoon, type MicCapture } from '@/lib/micCapture'
import { usePageTitle } from '@/lib/usePageTitle'
import { useSessionStore } from '@/store/sessionStore'
import { useSpeakStore } from '@/store/speakStore'

const WARN_AT_S = 30 // the timer warns this long before the limit
const BARGE_LEVEL = 0.05 // microphone level (RMS, 0 to 1) that counts as the visitor speaking over the coach voice
const BARGE_FRAMES = 4 // this many frames in a row (about 0.25 s) above BARGE_LEVEL stop the clip
const SLOW_END_MS = 40_000 // "Finishing…" is called slow after this long

const mmss = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`

export function SpeakCall() {
  usePageTitle('Speak live · Maryada')
  const navigate = useNavigate()
  const session = useSpeakStore((s) => s.session)
  const clock = useSpeakStore((s) => s.clock)
  const st = useSessionStore()
  const [rules, setRules] = useState<Rule[]>([])
  const [open, setOpen] = useState<Finding | null>(null)
  const [mic, setMic] = useState<MicCapture | null>(null)
  const [micProblem, setMicProblem] = useState<string | null>(null)
  const [voiceOn, setVoiceOn] = useState(audio.coachVoice)
  const [ending, setEnding] = useState(false)
  const [slowEnd, setSlowEnd] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const client = useRef<CallClient | null>(null)
  const finished = useRef(false) // the call ended and the page is moving on to the report
  const level = useMicLevel(mic)

  // no session (reload, or a direct visit): back to the set-up page
  useEffect(() => {
    if (!session && !finished.current) navigate('/speak', { replace: true }) // a finished call is on its way to the report
  }, [session, navigate])

  useEffect(() => {
    const ctl = new AbortController()
    getRules(ctl.signal).then(setRules).catch(() => undefined) // the rule names are a nicety: the call goes on without them
    return () => ctl.abort()
  }, [])

  // open the call: the socket first, then the microphone feeds it
  useEffect(() => {
    if (!session) return
    const store = useSessionStore.getState()
    store.reset('live')
    store.setSessionId(session.id)
    store.setStatus('connecting')
    const c = new CallClient(session.wsUrl, false, true)
    client.current = c
    c.open()
    let mine: MicCapture | null = null
    let off: (() => void) | null = null
    let gone = false
    acquireMic()
      .then((m) => {
        if (gone) return
        mine = m
        m.setSink((f) => c.sendFrame(f))
        off = m.onEnded(() => setMicProblem('Your microphone stopped. End the call to see your report.'))
        setMic(m)
      })
      .catch((e) => setMicProblem(e instanceof MicError ? MIC_PROBLEM_TEXT[e.problem] : MIC_PROBLEM_TEXT.error))
    return () => {
      gone = true
      off?.()
      mine?.setSink(null)
      c.close()
      client.current = null
      releaseMicSoon()
    }
  }, [session])

  // timer: from the server's start of the call
  useEffect(() => {
    if (!st.callStart) return
    const tick = () => setElapsed(Math.floor((Date.now() - (st.callStart ?? Date.now())) / 1000))
    tick()
    const t = window.setInterval(tick, 250)
    return () => window.clearInterval(t)
  }, [st.callStart])

  // the visitor speaks over the coach voice: stop the clip and tell the server
  const speaking = !!st.nudge?.speaking
  useEffect(() => {
    if (!mic || !speaking) return
    let run = 0
    return mic.onLevel((l) => {
      run = l > BARGE_LEVEL ? run + 1 : 0
      if (run >= BARGE_FRAMES) {
        run = 0
        client.current?.control({ type: 'barge_in' })
        audio.stopCoach()
      }
    })
  }, [mic, speaking])

  // the call is over (End call, the time limit, or a failure the server reported): on to the report
  useEffect(() => {
    if (st.status !== 'ended' || !session || st.sessionId !== session.id) return // sessionId: ignore the previous call's ended state
    const notice = useSessionStore.getState().error
    finished.current = true
    useSpeakStore.getState().setSession(null)
    navigate(`/speak/report/${session.id}`, { replace: true, state: notice ? { notice } : null })
  }, [st.status, st.sessionId, session, navigate])

  useEffect(() => {
    if (!ending) return
    const t = window.setTimeout(() => setSlowEnd(true), SLOW_END_MS)
    return () => window.clearTimeout(t)
  }, [ending])

  const end = () => {
    setEnding(true)
    mic?.setSink(null)
    client.current?.control({ type: 'end' })
  }
  const choose = (value: string) => client.current?.control({ type: 'set_answered_by', value })
  const closeDrawer = useCallback(() => setOpen(null), [])

  if (!session) return null
  const failed = st.status === 'error' || st.conn === 'failed'
  if (failed && st.status !== 'ended')
    return (
      <ErrorCard title="The call could not continue" message={st.error ?? 'The connection to the server was lost.'}>
        <Link to="/speak" className="btn btn-primary" onClick={() => useSpeakStore.getState().setSession(null)}>Back to set-up</Link>
      </ErrorCard>
    )

  const left = Math.max(0, MIC_CALL_LIMIT_S - elapsed)
  const warn = !!st.callStart && left <= WARN_AT_S
  return (
    <div className="call-fit flex flex-col gap-3 sm:gap-4">
      <ReconnectBanner />

      <header className="card flex flex-none flex-wrap items-center justify-between gap-x-4 gap-y-2.5 p-3 sm:px-5 sm:py-3">
        <h1 className="text-lg font-semibold leading-tight tracking-tight sm:text-xl">Speak live</h1>
        <div className="flex flex-wrap items-center gap-2">
          <span className="chip chip-ok">
            <span className={`h-[7px] w-[7px] rounded-full bg-[var(--mc-good-practice)] ${ending ? '' : 'pulse-dot'}`} aria-hidden />
            {ending ? 'Finishing…' : micProblem ? 'Microphone off' : st.status === 'live' ? 'Listening to you' : 'Connecting…'}
          </span>
          {clock && <span className="chip chip-warn">Clock set to {clock} (test)</span>}
          <span className={`chip mono text-[13px] font-semibold ${warn ? 'chip-advisory' : 'text-[var(--mc-text)]'}`} aria-label="Call timer">
            {mmss(Math.min(elapsed, MIC_CALL_LIMIT_S))} / {mmss(MIC_CALL_LIMIT_S)}
          </span>
          {warn && !ending && <span role="status" className="text-xs font-semibold text-[var(--mc-advisory-ink)]">Less than 30 seconds left</span>}
          <span className="inline-flex items-center gap-1.5" title="Microphone level">
            <Mic className="h-4 w-4 text-[var(--mc-muted)]" aria-hidden />
            <MicMeter level={level} compact />
          </span>
          <button
            type="button"
            aria-pressed={!voiceOn}
            onClick={() => {
              audio.setCoachVoice(!voiceOn)
              setVoiceOn(!voiceOn)
            }}
            className="btn btn-sm"
          >
            {voiceOn ? <Volume2 className="h-4 w-4" aria-hidden /> : <VolumeX className="h-4 w-4" aria-hidden />}
            {voiceOn ? 'Mute coach voice' : 'Coach voice muted'}
          </button>
          <button type="button" onClick={end} disabled={ending} aria-busy={ending} className="btn btn-sm btn-primary">
            {ending ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Square className="h-2.5 w-2.5 fill-current" aria-hidden />}
            {ending ? 'Finishing…' : 'End call'}
          </button>
        </div>
      </header>

      {micProblem && <p role="alert" className="banner banner-warn">{micProblem}</p>}
      {slowEnd && <p role="status" className="banner banner-warn">Finishing is taking longer than usual. The checks are still running.</p>}
      {st.banner && <p role="status" className="banner banner-warn">{st.banner.message}</p>}

      <AnsweredBySelector value={st.answeredBy} onChoose={choose} disabled={ending} />

      <div className="call-grid grid grid-cols-[minmax(0,1fr)] gap-3 sm:gap-4 lg:grid-cols-[minmax(0,1fr)_380px] lg:grid-rows-[auto_auto_minmax(0,1fr)] lg:items-start">
        <div className="call-tx order-3 min-w-0 lg:order-none lg:col-start-1 lg:row-span-3 lg:row-start-1">
          <TranscriptPanel
            turns={st.turns}
            findings={st.findings}
            scenario={null}
            onOpen={setOpen}
            you
            offsetOf={(t) => (st.callStart ? Math.max(0, t.startedAt - st.callStart) : 0)}
          >
            <StageLine />
          </TranscriptPanel>
        </div>
        <div className="order-1 min-w-0 lg:order-none lg:col-start-2 lg:row-start-1">
          <CoachCard rules={rules} voiceOn={voiceOn} onVoice={setVoiceOn} reminder={st.answeredBy === 'unknown'} />
        </div>
        <div className="order-2 min-w-0 lg:order-none lg:col-start-2 lg:row-start-2">
          <RiskMeter />
        </div>
        <div className="call-find order-4 min-h-0 min-w-0 lg:order-none lg:col-start-2 lg:row-start-3">
          <FindingList findings={st.findings} rules={rules} onOpen={setOpen} callTime={st.simulatedStart} />
        </div>
      </div>

      <DetailDrawer finding={open} rule={rules.find((r) => r.id === open?.rule_id)} onClose={closeDrawer} callTime={st.simulatedStart} />
    </div>
  )
}
