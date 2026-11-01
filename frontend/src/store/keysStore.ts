/**
 * The visitor's own keys. Held in this browser tab (sessionStorage) unless "Remember on this device" is on
 * (localStorage). Every storage access is wrapped: the page must work with storage blocked.
 * Keys are sent only in the body of an HTTPS POST when a call starts or a connection is tested; never in a URL.
 */
import { create } from 'zustand'

export interface Keys {
  gnaniKey: string
  provider: string // preset id from lib/providers
  baseUrl: string
  llmKey: string
  model: string
}

const EMPTY: Keys = { gnaniKey: '', provider: 'groq', baseUrl: '', llmKey: '', model: '' }
const DATA = 'maryada.keys'
const REMEMBER = 'maryada.remember'

function store(kind: 'local' | 'session'): Storage | null {
  try {
    return kind === 'local' ? window.localStorage : window.sessionStorage
  } catch {
    return null
  }
}

function read(s: Storage | null): Keys | null {
  try {
    const raw = s?.getItem(DATA)
    return raw ? { ...EMPTY, ...(JSON.parse(raw) as Partial<Keys>) } : null
  } catch {
    return null
  }
}

function write(keys: Keys, remember: boolean) {
  try {
    store(remember ? 'session' : 'local')?.removeItem(DATA) // never leave a copy in the other place
    store(remember ? 'local' : 'session')?.setItem(DATA, JSON.stringify(keys))
    store('local')?.setItem(REMEMBER, remember ? '1' : '0')
  } catch {
    /* storage unavailable: keys stay in memory for this page only */
  }
}

function initial(): { keys: Keys; remember: boolean } {
  let remember = false
  try {
    remember = store('local')?.getItem(REMEMBER) === '1'
  } catch {
    /* ignore */
  }
  return { keys: (remember ? read(store('local')) : read(store('session'))) ?? EMPTY, remember }
}

interface State {
  keys: Keys
  remember: boolean
  set: (patch: Partial<Keys>) => void
  setRemember: (v: boolean) => void
  clear: () => void
}

export const useKeysStore = create<State>((set, get) => ({
  ...initial(),
  set: (patch) => {
    const keys = { ...get().keys, ...patch }
    set({ keys })
    write(keys, get().remember)
  },
  setRemember: (remember) => {
    set({ remember })
    write(get().keys, remember)
  },
  clear: () => {
    set({ keys: EMPTY })
    try {
      store('local')?.removeItem(DATA)
      store('session')?.removeItem(DATA)
    } catch {
      /* ignore */
    }
  },
}))

export const keysComplete = (k: Keys) => !!(k.gnaniKey.trim() && k.baseUrl.trim() && k.llmKey.trim() && k.model.trim())
export const useHasKeys = () => useKeysStore((s) => keysComplete(s.keys))
