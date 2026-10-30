import { create } from 'zustand'
import { getHealth, type Health } from '@/lib/api'

export type ServerStatus = 'checking' | 'ready' | 'unreachable'

interface ServerState {
  status: ServerStatus
  health: Health | null
  check: () => Promise<void>
}

export const useServerStore = create<ServerState>((set, get) => ({
  status: 'checking',
  health: null,
  check: async () => {
    if (get().status === 'ready') return
    set({ status: 'checking' })
    try {
      set({ status: 'ready', health: await getHealth() })
    } catch {
      set({ status: 'unreachable' })
    }
  },
}))
