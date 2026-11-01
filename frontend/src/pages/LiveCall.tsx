import { Play, Square, Volume2, VolumeX } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
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
import { CallClient } from '@/lib/callClient'
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

  const st = useSessionStore()

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
    async (mode: Mode) => {
      if (!scenario) return
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
        store.setMode(s.effective_mode)
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
          onRecorded={() => {
            useServerStore.setState({ status: 'ready' })
            if (!scenario) load()
            else void begin('replay')
          }}
        />
      </>
    )

  if (phase === 'error')
    return (
      <ErrorCard title="Could not start the call" message={error ?? 'Please try again.'} onRetry={load}>
        <Link to="/" className="rounded-md border border-[var(--mc-line)] px-4 py-2 text-sm hover:bg-[var(--mc-line)]">
          Back to cases
        </Link>
      </ErrorCard>
    )

  if (phase === 'loading' || !scenario)
    return (
      <div aria-busy="true" aria-label="Loading call" className="space-y-4">
        <div className="skeleton h-14" />
        <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
          <div className="skeleton h-96" />
          <div className="skeleton h-96" />
        </div>
      </div>
    )

  const idle = phase === 'ready' || phase === 'starting'
  const running = st.status === 'live' || st.status === 'connecting'
  const failed = st.status === 'error' || st.conn === 'failed'

  return (
    <div>
      <ReconnectBanner />

      {/* Top strip */}
      <header className="mb-4 rounded-2xl border border-[var(--mc-line)] bg-[var(--mc-surface)] p-3 sm:p-4">
        <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-2">
          <div className="min-w-0 flex-1">
            <p className="mono text-[11px] text-[var(--mc-muted)]">{scenario.id.toUpperCase()}</p>
            <h1 className="truncate text-base font-semibold sm:text-lg">{scenario.title}</h1>
          </div>
          <ModeBadge mode={st.mode} status={st.status} />
          <span className="mono rounded-md bg-[var(--mc-bg)] px-2 py-1 text-sm" aria-label="Call timer">
            {fmt(timeMs)}
          </span>
          {st.latencyMs !== null && (
            <span className="mono rounded-full border border-[var(--mc-line)] px-2.5 py-0.5 text-xs text-[var(--mc-muted)]" title="From the end of the agent's words to the coach card">
              Flag in {(st.latencyMs / 1000).toFixed(1)}s{st.mode === 'replay' ? ' · recorded' : ''}
            </span>
          )}
          {st.langs.map((l) => (
            <span key={l} className="rounded-full bg-[var(--mc-line)] px-2 py-0.5 text-[11px] text-[var(--mc-muted)]">
              {l}
            </span>
          ))}
          <button
            onClick={() => {
              audio.setMuted(!muted)
              setMuted(!muted)
            }}
            aria-label={muted ? 'Unmute call audio' : 'Mute call audio'}
            className="rounded-md p-2 hover:bg-[var(--mc-line)]"
          >
            {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
          </button>
          {running && st.status === 'live' && (
            <button onClick={stop} className="flex items-center gap-1.5 rounded-md border border-[var(--mc-line)] px-3 py-1.5 text-sm hover:bg-[var(--mc-line)]">
              <Square className="h-3.5 w-3.5 fill-current" aria-hidden /> Stop
            </button>
          )}
        </div>
        <WaveformBar scenario={scenario} findings={st.findings} onTime={onTime} running={!idle} />
      </header>

      {st.banner && st.banner.kind !== 'replay' && (
        <p role="status" className="mb-3 rounded-lg border border-[var(--mc-advisory)]/40 bg-[var(--mc-advisory)]/10 px-3 py-2 text-sm text-[var(--mc-advisory)]">
          {st.banner.message}
        </p>
      )}
      {st.banner?.kind === 'replay' && (
        <p role="status" className="mb-3 rounded-lg border border-[var(--mc-advisory)]/40 bg-[var(--mc-advisory)]/10 px-3 py-2 text-sm text-[var(--mc-advisory)]">
          Replay mode: showing a recorded run. {st.banner.message}
        </p>
      )}

      {failed && (
        <div className="mb-4">
          <ErrorCard title="The connection was lost" message={st.error ?? 'The live connection could not be restored.'} onRetry={load}>
            <button
              onClick={() => {
                teardown()
                void begin('replay')
              }}
              className="rounded-md border border-[var(--mc-line)] px-4 py-2 text-sm hover:bg-[var(--mc-line)]"
            >
              Try recorded run
            </button>
          </ErrorCard>
        </div>
      )}

      {idle && !failed ? (
        <StartCard
          scenario={scenario}
          busy={phase === 'starting'}
          onStart={(m) => void begin(m)}
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
          <div className="space-y-3">
            <TranscriptPanel turns={st.turns} findings={st.findings} scenario={scenario} onOpen={setOpen} />
            <section aria-label="Stage" className="rounded-xl border border-[var(--mc-line)] bg-[var(--mc-surface)] px-4 py-3">
              <StageLine />
            </section>
          </div>
          <div className="space-y-4">
            <CoachCard rules={rules} voiceOn={voiceOn} onVoice={setVoiceOn} />
            <RiskMeter />
            <FindingList findings={st.findings} rules={rules} onOpen={setOpen} />
          </div>
        </div>
      )}

      <DetailDrawer finding={open} rule={rule(open)} onClose={closeDrawer} />
      {st.status === 'ended' && st.summary && summaryOpen && (
        <SummaryModal
          summary={st.summary}
          findings={st.findings}
          rules={rules}
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
  if (needKeys && !hasKeys)
    return (
      <section className="rise mx-auto mt-6 max-w-xl rounded-2xl border border-[var(--mc-line)] bg-[var(--mc-surface)] p-6 text-center sm:p-8">
        <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-[var(--mc-accent)]">Needs your keys</p>
        <h2 className="mb-2 text-xl font-semibold">Add your keys to start a live call</h2>
        <p className="mb-6 text-sm text-[var(--mc-muted)]">
          Live calls use your own Gnani key and your own language model. This site keeps no keys of its own. The recorded run needs none.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Link to="/settings" className="rounded-full bg-[var(--mc-accent)] px-6 py-3 text-sm font-semibold text-white hover:brightness-110">
            Open Settings
          </Link>
          <button
            disabled={busy}
            onClick={() => onStart('replay')}
            className="rounded-full border border-[var(--mc-line)] px-5 py-3 text-sm hover:bg-[var(--mc-line)] disabled:opacity-60"
          >
            Play recorded run
          </button>
        </div>
      </section>
    )
  return (
    <section className="rise mx-auto mt-6 max-w-xl rounded-2xl border border-[var(--mc-line)] bg-[var(--mc-surface)] p-6 text-center sm:p-8">
      <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-[var(--mc-accent)]">Ready</p>
      <h2 className="mb-2 text-xl font-semibold">{scenario.title}</h2>
      <p className="mb-6 text-sm text-[var(--mc-muted)]">{scenario.summary.replace(/^HERO\.\s*/, '')}</p>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <button
          disabled={busy}
          onClick={() => (hasKeys ? onStart('live') : setNeedKeys(true))}
          className="inline-flex items-center gap-2 rounded-full bg-[var(--mc-accent)] px-6 py-3 text-sm font-semibold text-white hover:brightness-110 disabled:opacity-60"
        >
          <Play className="h-4 w-4 fill-current" aria-hidden /> {busy ? 'Starting…' : 'Start live call'}
          {!hasKeys && !busy && (
            <span className="rounded-full bg-white/20 px-2 py-0.5 text-[11px] font-medium">Needs your keys</span>
          )}
        </button>
        <button
          disabled={busy}
          onClick={() => onStart('replay')}
          className="rounded-full border border-[var(--mc-line)] px-5 py-3 text-sm hover:bg-[var(--mc-line)] disabled:opacity-60"
        >
          Play recorded run
        </button>
      </div>
      <p className="mt-4 text-xs text-[var(--mc-muted)]">
        Press start to allow sound. The coach card shows on screen; its voice is optional.
      </p>
    </section>
  )
}
