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
export const getRules = (signal?: AbortSignal) => getJson<Rule[]>('/api/rules', signal)
export const createSession = (scenario_id: string, mode: 'live' | 'replay') =>
  request<SessionStart>('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario_id, mode }),
  })

export const audioUrl = (path: string) => `${API_BASE}${path}`
export const wsUrl = (path: string) => API_BASE.replace(/^http/, 'ws') + path
