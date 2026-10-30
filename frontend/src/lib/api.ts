export const API_BASE: string = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export interface Health {
  status: string
  version: string
  mode_capable: 'live' | 'replay'
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { signal })
  if (!res.ok) throw new Error(`${path} failed with status ${res.status}`)
  return (await res.json()) as T
}

export const getHealth = (signal?: AbortSignal) => getJson<Health>('/health', signal)
