import { CircleHelp, Eye, EyeOff, LoaderCircle } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { listModels, testGnani, testLlm, type TestResult } from '@/lib/api'
import { GNANI_KEY_URL, PROVIDERS } from '@/lib/providers'
import { useKeysStore } from '@/store/keysStore'

const box = 'rounded-2xl border border-[var(--mc-line)] bg-[var(--mc-surface)] p-5'
const input =
  'w-full rounded-md border border-[var(--mc-line)] bg-[var(--mc-bg)] px-3 py-2 text-sm outline-none focus:border-[var(--mc-accent)] disabled:opacity-70'
const btn = 'rounded-md border border-[var(--mc-line)] px-3 py-1.5 text-sm hover:bg-[var(--mc-line)] disabled:opacity-60'

export function Settings() {
  const { keys, remember, set, setRemember, clear } = useKeysStore()
  const provider = PROVIDERS.find((p) => p.id === keys.provider) ?? PROVIDERS[0]
  const custom = provider.id === 'custom'
  const baseUrl = custom ? keys.baseUrl : provider.baseUrl

  const [models, setModels] = useState<string[] | null>(null)
  const [modelsBusy, setModelsBusy] = useState(false)
  const [modelsError, setModelsError] = useState<string | null>(null)
  const [gnaniTest, setGnaniTest] = useState<TestResult | 'busy' | null>(null)
  const [llmTest, setLlmTest] = useState<TestResult | 'busy' | null>(null)
  const [cleared, setCleared] = useState(false)
  const seq = useRef(0)

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
    <div className="mx-auto max-w-2xl space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="mt-1 text-sm text-[var(--mc-muted)]">
          Live calls use <strong>your own</strong> Gnani key and <strong>your own</strong> language model. This site keeps no keys of
          its own. Recorded runs need no keys.
        </p>
        <p className="mt-2 rounded-lg border border-[var(--mc-line)] px-3 py-2 text-xs text-[var(--mc-muted)]">
          Your keys stay in your browser and are sent over HTTPS only when you start a call or test a connection. They are not stored or
          logged on the server. Use a key with a spend limit and revoke it afterwards.
        </p>
      </header>

      <section className={box} aria-labelledby="gnani-h">
        <div className="mb-3 flex items-center gap-2">
          <h2 id="gnani-h" className="font-semibold">Gnani speech key</h2>
          <Help label="How to get a Gnani key">
            <p>
              Sign up on the Gnani API platform and generate a key from the dashboard:{' '}
              <a className="underline" href={GNANI_KEY_URL} target="_blank" rel="noreferrer">app.gnani.ai/voice</a>. Paste it here.
            </p>
            <p className="mt-1">The key is sent to Gnani as the <code>X-API-Key-ID</code> header. The docs do not say whether a free tier exists.</p>
          </Help>
        </div>
        <SecretField label="Gnani API key" value={keys.gnaniKey} onChange={(v) => { set({ gnaniKey: v }); setGnaniTest(null) }} />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button className={btn} disabled={!keys.gnaniKey.trim() || gnaniTest === 'busy'} onClick={() => void run('gnani')}>
            Test connection
          </button>
          <Result r={gnaniTest} />
        </div>
        <p className="mt-2 text-xs text-[var(--mc-muted)]">The test opens the speech connection and waits for the greeting. No audio is sent.</p>
      </section>

      <section className={box} aria-labelledby="llm-h">
        <div className="mb-3 flex items-center gap-2">
          <h2 id="llm-h" className="font-semibold">Language model</h2>
          <Help label="Choosing a provider">
            <p>Any OpenAI-compatible service works. Pick a provider and paste a key from its page:</p>
            <ul className="mt-1 space-y-1">
              {PROVIDERS.filter((p) => p.keyUrl).map((p) => (
                <li key={p.id}>
                  <a className="underline" href={p.keyUrl} target="_blank" rel="noreferrer">{p.keyLabel}</a> · {p.tier}
                </li>
              ))}
            </ul>
          </Help>
        </div>

        <div role="radiogroup" aria-label="Provider" className="mb-3 flex flex-wrap gap-2">
          {PROVIDERS.map((p) => (
            <button
              key={p.id}
              role="radio"
              aria-checked={p.id === provider.id}
              onClick={() => choose(p.id)}
              className={`rounded-full border px-3 py-1 text-sm ${
                p.id === provider.id ? 'border-[var(--mc-accent)] bg-[var(--mc-accent)] text-white' : 'border-[var(--mc-line)] hover:bg-[var(--mc-line)]'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <p className="mb-3 text-xs text-[var(--mc-muted)]">{provider.tier}</p>

        <label className="mb-1 block text-sm" htmlFor="base-url">Base URL</label>
        <input
          id="base-url"
          className={`${input} mb-3`}
          value={baseUrl}
          readOnly={!custom}
          disabled={!custom}
          placeholder="https://api.example.com/v1"
          onChange={(e) => { set({ baseUrl: e.target.value }); setModels(null) }}
          autoComplete="off"
          spellCheck={false}
        />

        <SecretField
          label="API key"
          value={keys.llmKey}
          onChange={(v) => { set({ llmKey: v }); setModels(null); setLlmTest(null) }}
          onBlur={() => void loadModels()}
        />

        <div className="mb-1 mt-3 flex items-center justify-between">
          <label className="text-sm" htmlFor="model">Model</label>
          <button className="text-xs underline disabled:opacity-60" disabled={modelsBusy || !keys.llmKey.trim() || !baseUrl.trim()} onClick={() => void loadModels()}>
            {modelsBusy ? 'Loading…' : 'Load models'}
          </button>
        </div>
        {models && models.length > 0 ? (
          <select id="model" className={input} value={keys.model} onChange={(e) => { set({ model: e.target.value }); setLlmTest(null) }}>
            <option value="" disabled>Choose a model</option>
            {models.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        ) : (
          <input
            id="model"
            className={input}
            value={keys.model}
            placeholder={modelsBusy ? 'Loading models…' : 'Model name, e.g. gpt-4o-mini'}
            onChange={(e) => { set({ model: e.target.value }); setLlmTest(null) }}
            autoComplete="off"
            spellCheck={false}
          />
        )}
        {modelsError && <p role="alert" className="mt-1 text-xs text-[var(--mc-violation)]">{modelsError.replace(/\.?\s*$/, '.')} You can type a model name instead.</p>}
        {models && models.length === 0 && <p className="mt-1 text-xs text-[var(--mc-muted)]">The provider listed no chat models. Type a model name.</p>}
        <p className="mt-1 text-xs text-[var(--mc-muted)]">Tuned on gpt-5.4-mini; results vary on other models.</p>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button className={btn} disabled={!keys.llmKey.trim() || !keys.model.trim() || !baseUrl.trim() || llmTest === 'busy'} onClick={() => void run('llm')}>
            Test connection
          </button>
          <Result r={llmTest} />
        </div>
        <p className="mt-2 text-xs text-[var(--mc-muted)]">The test sends one short sample line and checks the reply is valid JSON (a few hundred tokens at most).</p>
      </section>

      <section className={box}>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          <span>
            Remember on this device
            <span className="block text-xs text-[var(--mc-muted)]">
              Off: keys live in this browser tab only and disappear when it closes. On: they stay in this browser until you clear them.
            </span>
          </span>
        </label>
        <div className="mt-4 flex items-center gap-3">
          <button className={btn} onClick={() => { clear(); setModels(null); setGnaniTest(null); setLlmTest(null); setCleared(true) }}>
            Clear all keys
          </button>
          {cleared && <span role="status" className="text-xs text-[var(--mc-muted)]">All keys removed from this browser.</span>}
        </div>
      </section>
    </div>
  )
}

function SecretField({ label, value, onChange, onBlur }: { label: string; value: string; onChange: (v: string) => void; onBlur?: () => void }) {
  const [show, setShow] = useState(false)
  const id = `f-${label.replace(/\s+/g, '-').toLowerCase()}`
  return (
    <div>
      <label className="mb-1 block text-sm" htmlFor={id}>{label}</label>
      <div className="relative">
        <input
          id={id}
          className={`${input} pr-10`}
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
          className="absolute inset-y-0 right-0 px-3 text-[var(--mc-muted)]"
        >
          {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
    </div>
  )
}

function Result({ r }: { r: TestResult | 'busy' | null }) {
  if (r === null) return null
  if (r === 'busy')
    return (
      <span role="status" className="flex items-center gap-1.5 text-sm text-[var(--mc-muted)]">
        <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> Testing…
      </span>
    )
  return (
    <span role="status" className={`text-sm ${r.ok ? 'text-[var(--mc-good-practice)]' : 'text-[var(--mc-violation)]'}`}>
      {r.ok ? '✓ ' : '✗ '}
      {r.message_user}
    </span>
  )
}

function Help({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="relative">
      <button type="button" aria-label={label} aria-expanded={open} onClick={() => setOpen(!open)} className="text-[var(--mc-muted)] hover:text-[var(--mc-text)]">
        <CircleHelp className="h-4 w-4" />
      </button>
      {open && (
        <div role="dialog" aria-label={label} className="fixed inset-x-4 z-20 mt-2 rounded-lg border border-[var(--mc-line)] bg-[var(--mc-surface)] p-3 text-xs shadow-lg sm:absolute sm:inset-x-auto sm:left-0 sm:top-6 sm:mt-0 sm:w-96">
          {children}
          <button className="mt-2 underline" onClick={() => setOpen(false)}>Close</button>
        </div>
      )}
    </span>
  )
}
