import { usePageTitle } from '@/lib/usePageTitle'
import { ChevronDown, Eye, EyeOff, Lock, LoaderCircle } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Switch } from '@/components/Switch'
import { audio } from '@/lib/audioEngine'
import { getRules, listModels, testGnani, testLlm, type TestResult } from '@/lib/api'
import { CONCURRENT_CALLS, MIC_CALL_LIMIT_S } from '@/lib/limits'
import { GNANI_KEY_URL, PROVIDERS } from '@/lib/providers'
import { useKeysStore } from '@/store/keysStore'

type Test = TestResult | 'busy' | null

/** After the last keyboard step on the volume slider, the sample plays this long after. */
const SETTLE_MS = 250

export function Settings() {
  usePageTitle('Settings · Maryada')
  const { keys, remember, set, setRemember, clear } = useKeysStore()
  const provider = PROVIDERS.find((p) => p.id === keys.provider) ?? PROVIDERS[0]
  const custom = provider.id === 'custom'
  const baseUrl = custom ? keys.baseUrl : provider.baseUrl

  const [models, setModels] = useState<string[] | null>(null)
  const [modelsBusy, setModelsBusy] = useState(false)
  const [modelsError, setModelsError] = useState<string | null>(null)
  const [gnaniTest, setGnaniTest] = useState<Test>(null)
  const [llmTest, setLlmTest] = useState<Test>(null)
  const [cleared, setCleared] = useState(false)
  const [pauseCoach, setPauseCoach] = useState(audio.pauseForCoach)
  const [voice, setVoice] = useState(audio.coachVoice)
  const [volume, setVolume] = useState(audio.coachVolume)
  const [sample, setSample] = useState<string | null>(null) // an existing coach clip, to hear the level
  const [sampling, setSampling] = useState(false)
  const seq = useRef(0)

  useEffect(() => {
    const ctl = new AbortController()
    getRules(ctl.signal)
      .then((r) => setSample(r.find((x) => x.coach_clip)?.coach_clip ?? null))
      .catch(() => undefined) // without it the sample button stays off; the slider still works
    return () => {
      ctl.abort()
      audio.stopCoach()
    }
  }, [])

  // a disabled sample button always says why (while a sample plays, its own label "Playing…" is the reason)
  const noSampleWhy = !voice ? 'Turn on the coach voice to preview' : !sample ? 'Sample not available' : null

  const playSample = () => {
    if (!sample) return
    // previewCoach stops a clip that is still playing first, so samples never overlap; its end callback runs before the new
    // clip starts, hence "Playing…" is set after it
    audio.previewCoach(sample, () => setSampling(false))
    setSampling(true)
  }

  // After the slider moves, the sample plays once the change has settled: on release of a mouse or touch drag, or SETTLE_MS after
  // the last keyboard step. Never on page load, and never while the coach voice is off.
  const dragging = useRef(false)
  const settle = useRef<number | undefined>(undefined)
  const latest = useRef({ voice, sample, play: playSample })
  latest.current = { voice, sample, play: playSample }
  const playIfAllowed = () => {
    const l = latest.current
    if (l.voice && l.sample) l.play()
  }
  useEffect(() => {
    const release = () => {
      if (!dragging.current) return
      dragging.current = false
      window.clearTimeout(settle.current)
      playIfAllowed()
    }
    window.addEventListener('pointerup', release)
    window.addEventListener('pointercancel', release)
    return () => {
      window.removeEventListener('pointerup', release)
      window.removeEventListener('pointercancel', release)
      window.clearTimeout(settle.current)
    }
  }, [])

  // The preset decides the stored base URL; Custom keeps what the visitor typed.
  useEffect(() => {
    if (!custom && keys.baseUrl !== provider.baseUrl) set({ baseUrl: provider.baseUrl })
  }, [custom, provider.baseUrl, keys.baseUrl, set])

  const loadModels = async () => {
    if (!baseUrl.trim() || !keys.llmKey.trim()) return
    const mine = ++seq.current
    setModelsBusy(true)
    setModelsError(null)
    try {
      const r = await listModels(baseUrl.trim(), keys.llmKey.trim())
      if (mine !== seq.current) return
      setModels(r.models)
      if (r.models.length && !r.models.includes(keys.model)) set({ model: '' })
    } catch (e) {
      if (mine !== seq.current) return
      setModels(null)
      setModelsError(e instanceof Error ? e.message : 'Could not load the model list.')
    } finally {
      if (mine === seq.current) setModelsBusy(false)
    }
  }

  const choose = (id: string) => {
    seq.current++
    setModels(null)
    setModelsError(null)
    setLlmTest(null)
    set({ provider: id, model: '', baseUrl: PROVIDERS.find((p) => p.id === id)?.baseUrl ?? '' })
  }

  const run = async (kind: 'gnani' | 'llm') => {
    const setter = kind === 'gnani' ? setGnaniTest : setLlmTest
    setter('busy')
    try {
      setter(
        kind === 'gnani'
          ? await testGnani(keys.gnaniKey.trim())
          : await testLlm(baseUrl.trim(), keys.llmKey.trim(), keys.model.trim()),
      )
    } catch (e) {
      setter({ ok: false, message_user: e instanceof Error ? e.message : 'The check failed.' })
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[28px] font-bold tracking-[-0.025em]">Settings</h1>
        <p className="mt-0.5 max-w-[700px] text-sm text-[var(--mc-muted)]">
          Live calls run on your own speech and language keys. Recorded runs need no keys at all.
        </p>
      </div>

      <div className="flex flex-wrap items-start gap-6">
        <div className="flex min-w-0 flex-[999_1_620px] flex-col gap-5">
          {/* Speech to text */}
          <section className="card relative z-[3] flex flex-col gap-4 p-5 sm:p-6" aria-labelledby="gnani-h">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 id="gnani-h" className="text-[17px] font-semibold tracking-tight">Speech to text</h2>
                <p className="text-[13px] text-[var(--mc-muted)]">Gnani Prisma transcribes the call as it happens. Your key, your account.</p>
              </div>
              <StatusChip t={gnaniTest} />
            </div>
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-2">
                <label className="text-[13px] font-semibold text-[var(--mc-text-2)]" htmlFor="f-gnani-api-key">Gnani API key</label>
                <Help label="How to get a Gnani key">
                  <p className="mb-2 text-sm font-semibold">How to get a Gnani API key</p>
                  <p>
                    Sign up on the Gnani API platform and generate a key from the dashboard:{' '}
                    <a className="link" href={GNANI_KEY_URL} target="_blank" rel="noreferrer">app.gnani.ai/voice</a>. Paste it here.
                  </p>
                  <p className="mt-2">
                    The key is sent to Gnani as the <code>X-API-Key-ID</code> header. Gnani docs do not say whether a free tier exists.
                  </p>
                </Help>
              </div>
              <SecretField label="Gnani API key" value={keys.gnaniKey} onChange={(v) => { set({ gnaniKey: v }); setGnaniTest(null) }} />
              <p className="text-[12.5px] text-[var(--mc-muted)]">
                No key yet? Sign up at{' '}
                <a className="link !font-medium" href={GNANI_KEY_URL} target="_blank" rel="noreferrer">app.gnani.ai/voice ↗</a>
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2.5">
              <button className="btn" disabled={!keys.gnaniKey.trim() || gnaniTest === 'busy'} onClick={() => void run('gnani')}>
                Test connection
              </button>
              <Result r={gnaniTest} idle="Opens the speech connection and waits for the greeting. No audio is sent." />
            </div>
          </section>

          {/* Language model */}
          <section className="card relative z-[2] flex flex-col gap-4 p-5 sm:p-6" aria-labelledby="llm-h">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 id="llm-h" className="text-[17px] font-semibold tracking-tight">Language model</h2>
                <p className="text-[13px] text-[var(--mc-muted)]">
                  Any OpenAI-compatible service. It runs the deep rule check. Pick a provider to fill in the address for you.
                </p>
              </div>
              <StatusChip t={llmTest} />
            </div>

            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <span className="text-[13px] font-semibold text-[var(--mc-text-2)]" id="provider-l">Provider</span>
                <Help label="How to get a language model key">
                  <p className="mb-2 text-sm font-semibold">Getting a key</p>
                  <p>Any OpenAI-compatible service works. Pick a provider and paste a key from its page:</p>
                  <ul className="mt-2 space-y-1.5">
                    {PROVIDERS.filter((p) => p.keyUrl).map((p) => (
                      <li key={p.id}>
                        <a className="link" href={p.keyUrl} target="_blank" rel="noreferrer">{p.keyLabel} ↗</a> · {p.tier}
                      </li>
                    ))}
                  </ul>
                </Help>
              </div>
              <div role="radiogroup" aria-labelledby="provider-l" className="flex flex-wrap gap-2.5">
                {PROVIDERS.map((p) => {
                  const on = p.id === provider.id
                  return (
                    <button
                      key={p.id}
                      role="radio"
                      aria-checked={on}
                      onClick={() => choose(p.id)}
                      className={`flex min-h-[52px] flex-col items-start justify-center gap-0.5 rounded-xl border px-3.5 py-2 text-left ${
                        on ? 'border-[var(--mc-accent)] bg-[var(--mc-accent-tint)]' : 'border-[var(--mc-field)] bg-white hover:bg-[var(--mc-line-soft)]'
                      } ${p.id === 'custom' ? 'border-dashed' : ''}`}
                    >
                      <b className={`text-[13px] font-semibold ${on ? 'text-[var(--mc-accent-dark)]' : ''}`}>{p.label}</b>
                      <span className={`text-xs ${p.noteTone === 'free' ? 'font-semibold text-[var(--mc-good-practice-ink)]' : 'text-[var(--mc-muted)]'}`}>{p.note}</span>
                    </button>
                  )
                })}
              </div>
              <p className="flex flex-wrap items-center gap-x-1.5 text-[12.5px] text-[var(--mc-muted)]">
                {provider.keyUrl ? (
                  <>
                    New to {provider.label}?{' '}
                    <a className="link !font-medium" href={provider.keyUrl} target="_blank" rel="noreferrer">Get a key at {provider.keyLabel} ↗</a>
                  </>
                ) : null}
                <span>{provider.keyUrl ? '· ' : ''}{provider.tier}</span>
              </p>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-[13px] font-semibold text-[var(--mc-text-2)]" htmlFor="base-url">Base URL</label>
              <div className="relative">
                <input
                  id="base-url"
                  className="input"
                  style={{ paddingRight: custom ? undefined : 124 }}
                  value={baseUrl}
                  readOnly={!custom}
                  disabled={!custom}
                  placeholder="https://api.example.com/v1"
                  onChange={(e) => { set({ baseUrl: e.target.value }); setModels(null) }}
                  autoComplete="off"
                  spellCheck={false}
                />
                {!custom && <span className="chip chip-accent absolute right-2 top-2">Filled for you</span>}
              </div>
              <p className="text-[12.5px] text-[var(--mc-muted)]">Editable only when the provider is Custom. Must be a public https address.</p>
            </div>

            <div className="flex flex-col gap-1.5">
              <SecretField
                label="API key"
                value={keys.llmKey}
                onChange={(v) => { set({ llmKey: v }); setModels(null); setLlmTest(null) }}
                onBlur={() => void loadModels()}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <label className="text-[13px] font-semibold text-[var(--mc-text-2)]" htmlFor="model">Model</label>
                <span className="flex items-center gap-3 text-xs">
                  {models && models.length > 0 && <span className="font-medium text-[var(--mc-good-practice-ink)]">Loaded from your provider · {models.length} models</span>}
                  <button className="link !font-medium disabled:opacity-60" disabled={modelsBusy || !keys.llmKey.trim() || !baseUrl.trim()} onClick={() => void loadModels()}>
                    {modelsBusy ? 'Loading…' : 'Load models'}
                  </button>
                </span>
              </div>
              {models && models.length > 0 ? (
                <div className="relative">
                  <select
                    id="model"
                    className="input appearance-none pr-10"
                    value={keys.model}
                    onChange={(e) => { set({ model: e.target.value }); setLlmTest(null) }}
                  >
                    <option value="" disabled>Choose a model</option>
                    {models.map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#475467]" aria-hidden />
                </div>
              ) : (
                <input
                  id="model"
                  className="input"
                  value={keys.model}
                  placeholder={modelsBusy ? 'Loading models…' : 'Model name, e.g. gpt-4o-mini'}
                  onChange={(e) => { set({ model: e.target.value }); setLlmTest(null) }}
                  autoComplete="off"
                  spellCheck={false}
                />
              )}
              {modelsError && (
                <p role="alert" className="text-xs text-[var(--mc-violation-ink)]">
                  {modelsError.replace(/\.?\s*$/, '.')} You can type a model name instead.
                </p>
              )}
              {models && models.length === 0 && <p className="text-xs text-[var(--mc-muted)]">The provider listed no chat models. Type a model name.</p>}
              <p className="text-xs text-[var(--mc-muted)]">
                Maryada was tuned on gpt-5.4-mini. Other models work, but results vary, especially on Hindi and English mixed speech.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2.5">
              <button className="btn" disabled={!keys.llmKey.trim() || !keys.model.trim() || !baseUrl.trim() || llmTest === 'busy'} onClick={() => void run('llm')}>
                Test connection
              </button>
              <Result r={llmTest} idle="Sends one short sample and checks the reply format. Uses a few hundred tokens at most." />
            </div>
          </section>

          {/* Where keys are kept */}
          <section className="card flex flex-col gap-4 p-5 sm:p-6" aria-labelledby="keep-h">
            <h2 id="keep-h" className="text-[17px] font-semibold tracking-tight">Where keys are kept</h2>
            <div role="radiogroup" aria-labelledby="keep-h" className="flex flex-col gap-2.5">
              <KeepOption on={!remember} onSelect={() => setRemember(false)} title="This browser tab only" text="Cleared when you close the tab. Recommended." />
              <KeepOption on={remember} onSelect={() => setRemember(true)} title="Remember on this device" text="Keeps keys in this browser until you clear them. Not for shared computers." />
            </div>
            <p className="text-[12.5px] text-[var(--mc-muted)]">Changes here are saved as you make them.</p>
            <div className="flex flex-wrap items-center gap-2.5">
              <button
                className="btn btn-danger"
                onClick={() => { clear(); setModels(null); setGnaniTest(null); setLlmTest(null); setCleared(true) }}
              >
                Clear all keys
              </button>
              {cleared && <span role="status" className="text-xs text-[var(--mc-muted)]">All keys removed from this browser.</span>}
            </div>
          </section>
        </div>

        <aside className="flex min-w-0 max-w-full flex-[1_1_320px] flex-col gap-5 lg:max-w-[400px]">
          <section className="card flex flex-col gap-3 p-5">
            <div className="flex items-center gap-2.5">
              <span className="flex h-[34px] w-[34px] items-center justify-center rounded-[10px] bg-[var(--mc-accent-tint)]">
                <Lock className="h-[18px] w-[18px] text-[var(--mc-accent)]" aria-hidden />
              </span>
              <h2 className="text-[15px] font-semibold">How your keys are handled</h2>
            </div>
            <div className="flex flex-col gap-2.5 text-[13.5px] leading-relaxed text-[var(--mc-text-2)]">
              <p>Keys stay in your browser and are sent over HTTPS only when a call starts or a connection is tested.</p>
              <p>The server holds them in memory for that call and never stores or logs them.</p>
              <p>This site holds no keys of its own, so there is nothing to fall back to: if your key fails, you see the error. Use a key with a spend limit and revoke it afterwards.</p>
            </div>
          </section>


          <section className="card flex flex-col gap-3 p-5" aria-labelledby="prefs-h">
            <h2 id="prefs-h" className="text-[15px] font-semibold">Preferences</h2>
            <div className="flex items-center justify-between gap-3 text-[13.5px]">
              <span id="voice-l">Play the coach voice</span>
              <Switch label="Play the coach voice" checked={voice} onChange={(v) => { audio.setCoachVoice(v); setVoice(v) }} />
            </div>
            <div className="flex flex-col gap-1.5 text-[13.5px]">
              <div className="flex items-center justify-between gap-3">
                <label htmlFor="coach-volume">Coach voice volume</label>
                <output htmlFor="coach-volume" className="mono text-[13px] font-semibold">{volume}</output>
              </div>
              <div className="flex flex-col gap-2">
                <input
                  id="coach-volume"
                  type="range"
                  min={0}
                  max={100}
                  step={1}
                  value={volume}
                  disabled={!voice}
                  aria-valuetext={`${volume} out of 100`}
                  onPointerDown={() => {
                    dragging.current = true
                  }}
                  onChange={(e) => {
                    const v = Number(e.target.value)
                    audio.setCoachVolume(v)
                    setVolume(v)
                    window.clearTimeout(settle.current)
                    if (!dragging.current) settle.current = window.setTimeout(playIfAllowed, SETTLE_MS) // keyboard: wait for the last step
                  }}
                  className="h-6 w-full min-w-0 cursor-pointer accent-[var(--mc-accent)] disabled:cursor-not-allowed disabled:opacity-50"
                />
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <button type="button" onClick={playSample} disabled={!voice || !sample || sampling} aria-describedby={noSampleWhy ? 'sample-why' : undefined} className="btn btn-sm">
                    {sampling ? 'Playing…' : 'Play sample'}
                  </button>
                  {noSampleWhy && <span id="sample-why" className="text-xs text-[var(--mc-muted)]">{noSampleWhy}</span>}
                </div>
              </div>
              <span className="text-xs text-[var(--mc-muted)]">
                Applies to the next coach clip, in recorded runs and in Speak live. The call audio keeps its quiet mix.
                {!voice && ' Turn the coach voice on to change it.'}
              </span>
            </div>
            <div className="flex items-start justify-between gap-3 text-[13.5px]">
              <span>
                <span id="pause-l">Pause the call while the coach speaks</span>
                <span className="mt-0.5 block text-xs text-[var(--mc-muted)]">
                  Off by default: the call plays on and the coach is heard quietly on top. Applies to the next call you start.
                </span>
              </span>
              <Switch
                label="Pause the call while the coach speaks"
                checked={pauseCoach}
                onChange={(v) => { audio.setPauseForCoach(v); setPauseCoach(v) }}
              />
            </div>
          </section>

          <section className="card flex flex-col gap-3 p-5">
            <h2 className="text-[15px] font-semibold">Live call limits</h2>
            <dl className="overflow-hidden rounded-xl border border-[#eaecf0] text-[13px]">
              <Row k="Who pays" v="Your own accounts" />
              <Row k="Call length" v={`${MIC_CALL_LIMIT_S} s`} />
              <Row k="Calls at once" v={String(CONCURRENT_CALLS)} last />
            </dl>
          </section>

          <section className="card flex flex-col gap-2.5 border-[var(--mc-accent-ring)] bg-[#f8f8ff] p-5">
            <h2 className="text-[15px] font-semibold text-[var(--mc-accent-dark)]">No keys? Use recorded runs</h2>
            <p className="text-[13.5px] leading-relaxed text-[var(--mc-text-2)]">
              Calls that have a recorded run play with the real findings and coach nudges. They need no keys and are free to play as often as you like.
            </p>
            <Link to="/" className="link text-[13.5px]">Browse recorded runs →</Link>
          </section>

        </aside>
      </div>
    </div>
  )
}

function Row({ k, v, last = false }: { k: string; v: string; last?: boolean }) {
  return (
    <div className={`flex justify-between px-3.5 py-2.5 ${last ? '' : 'border-b border-[#eaecf0]'}`}>
      <dt className="text-[var(--mc-muted)]">{k}</dt>
      <dd className="font-semibold">{v}</dd>
    </div>
  )
}

function KeepOption({ on, onSelect, title, text }: { on: boolean; onSelect: () => void; title: string; text: string }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={on}
      onClick={onSelect}
      className={`flex items-start gap-3 rounded-xl border px-4 py-3.5 text-left ${on ? 'border-[var(--mc-accent-ring)] bg-[#f8f8ff]' : 'border-[var(--mc-line)] hover:bg-[var(--mc-line-soft)]'}`}
    >
      <span
        className="mt-0.5 h-[18px] w-[18px] flex-none rounded-full bg-white"
        style={{ border: on ? '5px solid var(--mc-accent)' : '2px solid #98a2b3' }}
        aria-hidden
      />
      <span>
        <span className="block text-sm font-semibold">{title}</span>
        <span className="block text-[13px] text-[var(--mc-muted)]">{text}</span>
      </span>
    </button>
  )
}

function StatusChip({ t }: { t: Test }) {
  if (t === 'busy') return <span className="chip">Testing…</span>
  if (t === null) return <span className="chip bg-[#f9fafb]">Not tested yet</span>
  return t.ok ? <span className="chip chip-ok">Connected</span> : <span className="chip chip-violation">Check failed</span>
}

function SecretField({ label, value, onChange, onBlur }: { label: string; value: string; onChange: (v: string) => void; onBlur?: () => void }) {
  const [show, setShow] = useState(false)
  const id = `f-${label.replace(/\s+/g, '-').toLowerCase()}`
  return (
    <div className="flex flex-col gap-1.5">
      {label !== 'Gnani API key' && <label className="text-[13px] font-semibold text-[var(--mc-text-2)]" htmlFor={id}>{label}</label>}
      <div className="relative">
        <input
          id={id}
          className="input pr-11"
          type={show ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          autoComplete="off"
          spellCheck={false}
        />
        <button
          type="button"
          onClick={() => setShow(!show)}
          aria-label={show ? `Hide ${label}` : `Show ${label}`}
          className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-[10px] text-[var(--mc-muted)] hover:text-[var(--mc-text)]"
        >
          {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
    </div>
  )
}

function Result({ r, idle }: { r: Test; idle: string }) {
  if (r === null) return <span className="text-[12.5px] text-[var(--mc-muted)]">{idle}</span>
  if (r === 'busy')
    return (
      <span role="status" className="flex items-center gap-1.5 text-[12.5px] text-[var(--mc-muted)]">
        <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> Testing…
      </span>
    )
  return (
    <span role="status" className={`text-[12.5px] font-medium ${r.ok ? 'text-[var(--mc-good-practice-ink)]' : 'text-[var(--mc-violation-ink)]'}`}>
      {r.ok ? '✓ ' : '✗ '}
      {r.message_user}
    </span>
  )
}

function Help({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('mousedown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onDown)
    }
  }, [open])
  return (
    <span ref={box} className="relative inline-flex">
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex h-[22px] w-[22px] items-center justify-center rounded-full border border-[var(--mc-accent)] bg-[var(--mc-accent-tint)] text-xs font-bold text-[var(--mc-accent)]"
      >
        ?
      </button>
      {open && (
        <div
          role="dialog"
          aria-label={label}
          className="fixed inset-x-4 z-20 mt-8 rounded-xl border border-[var(--mc-field)] bg-white p-4 text-[13px] leading-relaxed text-[var(--mc-text-2)] shadow-[0_12px_32px_rgb(16_24_40/0.14)] sm:absolute sm:inset-x-auto sm:left-0 sm:top-7 sm:mt-0 sm:w-[420px]"
        >
          {children}
          <button className="link mt-3 text-xs" onClick={() => setOpen(false)}>Close</button>
        </div>
      )}
    </span>
  )
}
