import { Clock, KeyRound, Play, Square, Volume2, VolumeX } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { CoachCard } from '@/components/CoachCard'
import { ColdStartScreen } from '@/components/ColdStartScreen'
import { DetailDrawer } from '@/components/DetailDrawer'
import { ErrorCard } from '@/components/ErrorCard'
import { FindingList } from '@/components/FindingChip'
import { ModeBadge } from '@/components/ModeBadge'
import { ReconnectBanner } from '@/components/ReconnectBanner'
import { RiskMeter } from '@/components/RiskMeter'
import { StageLine } from '@/components/StageLine'
import { SummaryModal } from '@/components/SummaryModal'
import { TranscriptPanel } from '@/components/TranscriptPanel'
import { WaveformBar } from '@/components/WaveformBar'
import {
  ApiError,
  createSession,
  getHealth,
  getRules,
  getScenario,
  type Rule,
  type ScenarioDetail,
} from '@/lib/api'
import { audio } from '@/lib/audioEngine'
import { LIVE_CALLS_ENABLED } from '@/lib/features'
import { CallClient } from '@/lib/callClient'
import { usePageTitle } from '@/lib/usePageTitle'
import type { Finding } from '@/lib/events'
import { keysComplete, useHasKeys, useKeysStore } from '@/store/keysStore'
import { useServerStore } from '@/store/serverStore'
import { useSessionStore, type Mode } from '@/store/sessionStore'

type Phase = 'loading' | 'ready' | 'waking' | 'starting' | 'running' | 'error'

const fmt = (ms: number) => {
  const s = Math.floor(ms / 1000)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

export function LiveCall() {
  const { id = '' } = useParams()
  const [scenario, setScenario] = useState<ScenarioDetail | null>(null)
  const [rules, setRules] = useState<Rule[]>([])
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<string | null>(null)
  const [wanted, setWanted] = useState<Mode>('live')
  const [open, setOpen] = useState<Finding | null>(null)
  const [summaryOpen, setSummaryOpen] = useState(true)
  const [timeMs, setTimeMs] = useState(0)
  const [voiceOn, setVoiceOn] = useState(audio.coachVoice)
  const [muted, setMuted] = useState(audio.muted)
  const client = useRef<CallClient | null>(null)
  const navigate = useNavigate()

  const st = useSessionStore()
  usePageTitle(scenario ? `${scenario.id.toUpperCase()} ${scenario.title} · Maryada` : `${id.toUpperCase() || 'Call'} · Maryada`)

  const teardown = useCallback(() => {
    client.current?.close()
    client.current = null
  }, [])

  const load = useCallback(() => {
    setPhase('loading')
    setError(null)
    teardown()
    useSessionStore.getState().reset('live')
    setTimeMs(0)
    setSummaryOpen(true)
    const ctl = new AbortController()
    Promise.all([getScenario(id, ctl.signal), getRules(ctl.signal)])
      .then(([sc, rl]) => {
        setScenario(sc)
        setRules(rl)
        setPhase('ready')
      })
      .catch((e: Error) => {
        if (e.name === 'AbortError') return
        // A sleeping free-tier server also fails here: send the viewer to the waking screen
        setError(e.message)
        setPhase(e instanceof ApiError && !e.retryable ? 'error' : 'waking')
      })
    return () => ctl.abort()
  }, [id, teardown])

  useEffect(() => {
    const cancel = load()
    return () => {
      cancel()
      teardown()
      audio.stopAll()
    }
  }, [load, teardown])

  /** Create the session and open the socket. Called from the Start click, which also unlocks audio. */
  const begin = useCallback(
    async (requested: Mode) => {
      if (!scenario) return
      const mode: Mode = LIVE_CALLS_ENABLED ? requested : 'replay' // a keyed live run cannot start while it is switched off
      setWanted(mode)
      audio.unlock()
      setError(null)
      setPhase('starting')
      useSessionStore.getState().reset(mode)
      useSessionStore.getState().setStatus('connecting')
      try {
        await getHealth(AbortSignal.timeout(4000)) // quick probe: a sleeping server shows the waking screen
      } catch {
        setPhase('waking')
        return
      }
      try {
        const k = useKeysStore.getState().keys
        const creds =
          mode === 'live' && keysComplete(k)
            ? {
                gnani: { api_key: k.gnaniKey.trim() },
                llm: { base_url: k.baseUrl.trim(), api_key: k.llmKey.trim(), model: k.model.trim() },
              }
            : undefined
        const hold = audio.holdForCoach
        const s = await createSession(scenario.id, mode, creds, hold)
        const store = useSessionStore.getState()
        store.setSessionId(s.session_id)
        store.setMode(s.effective_mode === 'mic' ? 'live' : s.effective_mode)
        audio.preload(scenario.turns.map((t) => t.audio_url))
        client.current = new CallClient(s.ws_url, hold)
        client.current.open()
        setPhase('running')
      } catch (e) {
        useSessionStore.getState().setStatus('idle')
        setError(e instanceof Error ? e.message : 'Could not start the call.')
        setPhase('error')
      }
    },
    [scenario],
  )

  // A recorded run that played to its end opens its call report. A stopped call, a live call and a live call that
  // fell back to the recording keep the summary here: their events differ from the saved recording.
  const toReport = st.status === 'ended' && st.mode === 'replay' && st.banner?.kind !== 'replay' && !st.summary?.stopped
  useEffect(() => {
    if (toReport && scenario) navigate(`/call/${scenario.id}/report`)
  }, [toReport, scenario, navigate])

  const stop = () => client.current?.stop()
  const closeDrawer = useCallback(() => setOpen(null), [])
  const onTime = useCallback((ms: number) => setTimeMs(ms), [])
  const rule = (f: Finding | null) => rules.find((r) => r.id === f?.rule_id)

  if (phase === 'waking')
    return (
      <>
        <ColdStartScreen
          onReady={() => {
            useServerStore.setState({ status: 'ready' })
            if (!scenario) load()
            else void begin(wanted)
          }}
          onRecorded={
            scenario && !scenario.has_replay
              ? undefined
              : () => {
                  useServerStore.setState({ status: 'ready' })
                  if (!scenario) load()
                  else void begin('replay')
                }
          }
        />
      </>
    )

  if (phase === 'error')
    return (
      <ErrorCard title="Could not start the call" message={error ?? 'Please try again.'} onRetry={load}>
        <Link to="/" className="btn">
          Back to cases
        </Link>
      </ErrorCard>
    )

  if (phase === 'loading' || !scenario)
    return (
      <div aria-busy="true" aria-label="Loading call" className="space-y-5">
        <p role="status" className="text-sm font-medium text-[var(--mc-muted)]">Loading call… the server may take a few seconds to wake up.</p>
        <div className="skeleton h-40" />
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
          <div className="skeleton h-96" />
          <div className="skeleton h-96" />
        </div>
      </div>
    )

  const idle = phase === 'ready' || phase === 'starting'
  const running = st.status === 'live' || st.status === 'connecting'
  const failed = st.status === 'error' || st.conn === 'failed'
  const total = scenario.duration_ms ?? 0

  return (
    <div className="call-fit flex flex-col gap-3 sm:gap-4">
      <ReconnectBanner />

      {/* Top strip: one compact band, so the transcript gets the height */}
      <header className="card flex flex-none flex-col gap-1 p-3 sm:px-5 sm:py-3">
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <div className="flex min-w-0 flex-col gap-0.5 sm:min-w-[280px]">
            <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs text-[var(--mc-muted)]">
              <Link to="/" className="link !font-normal">Cases</Link>
              <span aria-hidden>/</span>
              <span>{scenario.id.toUpperCase()}</span>
            </nav>
            <h1 className="text-lg font-semibold leading-tight tracking-tight sm:text-xl">{scenario.title}</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <ModeBadge mode={st.mode} status={st.status} />
            <span className="chip mono text-[13px] font-semibold text-[var(--mc-text)]" aria-label="Call timer">
              {fmt(timeMs)} {total > 0 && <span className="font-medium text-[var(--mc-muted)]">/ {fmt(total)}</span>}
            </span>
            {/* These two slots keep their width while empty, so the band never jumps when a chip appears */}
            <span
              className={`chip mono ${st.latencyMs === null ? 'invisible' : ''}`}
              title="From the end of the agent words to the coach card"
              aria-hidden={st.latencyMs === null}
            >
              <Clock className="h-[13px] w-[13px]" aria-hidden />
              Flag in {((st.latencyMs ?? 0) / 1000).toFixed(1)} s{st.mode === 'replay' ? ' · recorded' : ''}
            </span>
            <span role="group" className="flex min-h-7 min-w-[132px] flex-wrap items-center gap-1.5" aria-label="Languages heard">
              {st.langs.map((l) => (
                <span key={l} className="chip">{l}</span>
              ))}
            </span>
            <button
              onClick={() => {
                audio.setMuted(!muted)
                setMuted(!muted)
              }}
              aria-label={muted ? 'Unmute call audio' : 'Mute call audio'}
              className="btn btn-sm !px-2.5"
            >
              {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
            </button>
            {running && st.status === 'live' && (
              <button onClick={stop} className="btn btn-sm">
                <Square className="h-2.5 w-2.5 fill-current" aria-hidden /> Stop
              </button>
            )}
          </div>
        </div>
        <WaveformBar scenario={scenario} findings={st.findings} onTime={onTime} running={!idle} />
      </header>

      {st.banner && (
        <p role="status" className="banner banner-warn">
          {st.banner.kind === 'replay' ? `Recorded run. ${st.banner.message}` : st.banner.message}
        </p>
      )}

      {failed && (
        <ErrorCard title="The connection was lost" message={st.error ?? 'The live connection could not be restored.'} onRetry={load}>
          {scenario?.has_replay && (
            <button
              onClick={() => {
                teardown()
                void begin('replay')
              }}
              className="btn"
            >
              Try recorded run
            </button>
          )}
        </ErrorCard>
      )}

      {idle && !failed ? (
        <StartCard scenario={scenario} busy={phase === 'starting'} onStart={(m) => void begin(m)} />
      ) : (
        <div className="call-grid grid grid-cols-[minmax(0,1fr)] gap-3 sm:gap-4 lg:grid-cols-[minmax(0,1fr)_380px] lg:grid-rows-[auto_auto_minmax(0,1fr)] lg:items-start">
          <div className="call-tx min-w-0 order-3 lg:order-none lg:col-start-1 lg:row-span-3 lg:row-start-1">
            <TranscriptPanel turns={st.turns} findings={st.findings} scenario={scenario} onOpen={setOpen}>
              <StageLine />
            </TranscriptPanel>
          </div>
          <div className="min-w-0 order-1 lg:order-none lg:col-start-2 lg:row-start-1">
            <CoachCard rules={rules} voiceOn={voiceOn} onVoice={setVoiceOn} />
          </div>
          <div className="min-w-0 order-2 lg:order-none lg:col-start-2 lg:row-start-2">
            <RiskMeter />
          </div>
          <div className="call-find min-h-0 min-w-0 order-4 lg:order-none lg:col-start-2 lg:row-start-3">
            <FindingList findings={st.findings} rules={rules} onOpen={setOpen} callTime={scenario.simulated_start_time} />
          </div>
        </div>
      )}

      <DetailDrawer finding={open} rule={rule(open)} onClose={closeDrawer} callTime={scenario.simulated_start_time} />
      {st.status === 'ended' && st.summary && summaryOpen && (
        <SummaryModal
          scenario={scenario}
          summary={st.summary}
          findings={st.findings}
          rules={rules}
          mode={st.mode}
          onRunAgain={() => load()}
          onClose={() => setSummaryOpen(false)}
        />
      )}
    </div>
  )
}

function StartCard({ scenario, busy, onStart }: { scenario: ScenarioDetail; busy: boolean; onStart: (m: Mode) => void }) {
  const hasKeys = useHasKeys()
  const [needKeys, setNeedKeys] = useState(false)
  if (LIVE_CALLS_ENABLED && needKeys && !hasKeys)
    return (
      <section className="card rise mx-auto flex w-full max-w-xl flex-col gap-3.5 p-6 sm:p-7" aria-labelledby="keys-h">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--mc-accent-tint)]">
          <KeyRound className="h-5 w-5 text-[var(--mc-accent)]" aria-hidden />
        </span>
        <h2 id="keys-h" className="text-[17px] font-semibold tracking-tight">Add your keys to start a live call</h2>
        <p className="text-[13.5px] leading-relaxed text-[var(--mc-muted)]">
          Live calls run on your own Gnani and language model keys. Nothing is stored.
          {scenario.has_replay ? ' Or play a recorded run with no keys at all.' : ' This call has no recorded run.'}
        </p>
        <div className="flex flex-wrap gap-2.5">
          <Link to="/settings" className="btn btn-primary">
            Open Settings
          </Link>
          {scenario.has_replay && (
            <button disabled={busy} onClick={() => onStart('replay')} className="btn">
              Play recorded run
            </button>
          )}
        </div>
      </section>
    )
  return (
    <section className="card rise mx-auto flex w-full max-w-xl flex-col gap-3.5 p-6 sm:p-7" aria-labelledby="ready-h">
      <span className="lbl">Ready</span>
      <h2 id="ready-h" className="text-xl font-semibold tracking-tight">{scenario.title}</h2>
      <p className="text-[13.5px] leading-relaxed text-[var(--mc-muted)]">{scenario.summary.replace(/^HERO\.\s*/, '')}</p>
      <div className="flex flex-wrap items-center gap-3">
        {scenario.has_replay && (
          <button disabled={busy} onClick={() => onStart('replay')} className="btn btn-lg btn-primary">
            <Play className="h-3.5 w-3.5 fill-current" aria-hidden /> {busy ? 'Starting…' : 'Play recorded run'}
          </button>
        )}
        {LIVE_CALLS_ENABLED && (
          <button
            disabled={busy}
            onClick={() => (hasKeys ? onStart('live') : setNeedKeys(true))}
            className={`btn btn-lg ${scenario.has_replay ? '' : 'btn-primary'}`}
          >
            Start live call
            {!hasKeys && !busy && <span className="chip chip-warn h-5 text-[11px]">Needs your keys</span>}
          </button>
        )}
        {!scenario.has_replay && !LIVE_CALLS_ENABLED && (
          <p role="status" className="text-[13.5px] text-[var(--mc-text-2)]">
            This call has no recorded run yet. Live modes are coming soon. <Link to="/" className="link">Choose a call with a recorded run</Link>
          </p>
        )}
      </div>
      <p className="text-xs text-[var(--mc-muted)]">
        Press start to allow sound. The coach card shows on screen; its voice is optional.
      </p>
    </section>
  )
}
