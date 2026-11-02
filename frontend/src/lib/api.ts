export const API_BASE: string = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export interface Health {
  status: string
  version: string
  mode_capable: 'live' | 'replay'
}

export interface ScenarioSummary {
  id: string
  title: string
  summary: string
  hero: boolean
  duration_s: number | null
  has_replay: boolean
  tags: string[]
}

export interface ScenarioTurn {
  idx: number
  speaker: 'agent' | 'borrower' | 'third_party'
  offset_ms: number
  duration_ms: number
  audio_url: string
}

export interface ScenarioDetail {
  id: string
  title: string
  summary: string
  hero: boolean
  has_replay: boolean
  simulated_start_time: string | null
  turns: ScenarioTurn[]
  call_audio_url: string | null
  duration_ms: number | null
}

export interface Rule {
  id: string
  title: string
  kind_default: string
  rbi_ref: string
  summary: string
  why: string
}

export interface Prf {
  tp: number
  fp: number
  fn: number
  p: number | null
  r: number | null
  f1: number | null
}
export interface ScoreBlock {
  strict: Prf
  with_review: Prf
  needs_review: { on_label: number; off_label: number }
}
export type Unit = [string, number, string] // call, agent turn, rule
export interface PerCall {
  call_id: string
  hard_negative: boolean
  expected: Unit[]
  hit: Unit[]
  hit_with_review: Unit[]
  missed: Unit[]
  missed_with_review: Unit[]
  false_alarms: Unit[]
  false_alarms_with_review: Unit[]
}
export interface Score {
  n_calls: number
  per_rule: Record<string, ScoreBlock>
  overall: ScoreBlock
  per_call: PerCall[]
  negatives: { calls: number; calls_with_false_alarm: number; calls_with_false_alarm_with_review: number; false_alarm_units: number }
  call_level: { expected: number; caught: number; caught_with_review: number }
  g1: { findings: number; agent_turns_with_g1: number }
}
export interface EvalExample {
  type: 'false_alarm' | 'miss'
  call: string
  turn: number
  rule: string
  text: string
  labelled_phrase: string | null
  detection: { kind: string; confidence: number; source: string; quote: string } | null
}
export interface RunResult {
  calls_run: number
  complete: boolean
  all?: Score | null
  tune?: Score | null
  held_out?: Score | null
  seen_in_development?: Score | null
  examples?: EvalExample[]
  stt: { turns: number; requests_made: number; avg_latency_ms: number }
  llm: { requests: number; cache_hits: number; skipped: number; degraded: number; tokens: number }
}
export interface LabelChange {
  changed_on: string
  call: string
  turn: number
  rule: string
  action: string
  label_hash_before: string
  label_hash_after: string
  reason: string
}
export interface EvalResults {
  generated_at: string
  labels_hash: string
  n_calls: number
  status: 'partial' | 'complete'
  limits: string[]
  label_changes: LabelChange[]
  model_info?: { stt?: string; llm?: string; thresholds?: { violation: number; needs_review: number } }
  full: Record<string, RunResult>
  ablation_llm_off: Record<string, RunResult>
}
export interface LatencyRow {
  label: string
  n: number
  p50_ms: number | null
  p95_ms: number | null
}
export interface ReviewView {
  flags: number
  correct_original: number
  correct_low: number
  correct_high: number
  extras_real: number
  extras_unsure: number
  extras_not_a_violation: number
  precision_original: number | null
  precision_low: number | null
  precision_high: number | null
  recall: number | null
}
export interface ReviewGroup {
  strict: ReviewView
  with_review: ReviewView
}
export interface EvalReview {
  reviewer: string | null
  reviewed_on: string | null
  items: { call: string; turn: number; rule: string; verdict: string; note: string }[]
  adjusted: Record<string, { all?: ReviewGroup; held_out?: ReviewGroup }>
}
export interface EvalPayload {
  results: EvalResults | null
  review: EvalReview | null
  latency: { calls: string[]; rows: LatencyRow[]; method: string }
}

export interface SessionStart {
  session_id: string
  effective_mode: 'live' | 'replay'
  ws_url: string
  reason?: string
}

/** A failure shown to the user as a friendly card (never raw JSON). */
export class ApiError extends Error {
  retryable: boolean
  constructor(message: string, retryable = true) {
    super(message)
    this.retryable = retryable
  }
}

async function parse<T>(res: Response): Promise<T> {
  if (res.ok) return (await res.json()) as T
  let message = 'Something went wrong on the server. Please try again.'
  let retryable = res.status >= 500
  try {
    const body = await res.json()
    const e = body?.detail?.error ?? body?.error
    if (e?.message_user) message = e.message_user
    if (typeof e?.retryable === 'boolean') retryable = e.retryable
  } catch {
    /* keep the friendly default */
  }
  throw new ApiError(message, retryable)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, init)
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new ApiError('Cannot reach the server. Check your connection and try again.')
  }
  return parse<T>(res)
}

export const getJson = <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal })
export const getHealth = (signal?: AbortSignal) => getJson<Health>('/health', signal)
export const getScenarios = (signal?: AbortSignal) => getJson<ScenarioSummary[]>('/api/scenarios', signal)
export const getScenario = (id: string, signal?: AbortSignal) =>
  getJson<ScenarioDetail>(`/api/scenarios/${encodeURIComponent(id)}`, signal)
export const getEval = (signal?: AbortSignal) => getJson<EvalPayload>('/api/eval', signal)
export const getRules = (signal?: AbortSignal) => getJson<Rule[]>('/api/rules', signal)
export interface Credentials {
  gnani: { api_key: string }
  llm: { base_url: string; api_key: string; model: string }
}

/** Keys travel only in this POST body (HTTPS), never in a URL or query string. */
export const createSession = (
  scenario_id: string,
  mode: 'live' | 'replay',
  credentials?: Credentials,
  pause_for_coach = false,
) =>
  request<SessionStart>('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(
      credentials && mode === 'live'
        ? { scenario_id, mode, credentials, pause_for_coach }
        : { scenario_id, mode, pause_for_coach },
    ),
  })

const post = <T>(path: string, body: object) =>
  request<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export interface TestResult {
  ok: boolean
  message_user: string
  tokens?: number
}

export const testGnani = (api_key: string) => post<TestResult>('/api/credentials/test', { kind: 'gnani', api_key })
export const testLlm = (base_url: string, api_key: string, model: string) =>
  post<TestResult>('/api/credentials/test', { kind: 'llm', base_url, api_key, model })
export const listModels = (base_url: string, api_key: string) =>
  post<{ models: string[] }>('/api/llm/models', { base_url, api_key })

export const audioUrl = (path: string) => `${API_BASE}${path}`
export const wsUrl = (path: string) => API_BASE.replace(/^http/, 'ws') + path
