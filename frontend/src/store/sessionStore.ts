import { create } from 'zustand'

export type SessionStatus = 'idle' | 'connecting' | 'live' | 'ended' | 'error'
export type Mode = 'live' | 'replay'

interface SessionState {
  status: SessionStatus
  mode: Mode
  setStatus: (status: SessionStatus) => void
  setMode: (mode: Mode) => void
}

export const useSessionStore = create<SessionState>((set) => ({
  status: 'idle',
  mode: 'live',
  setStatus: (status) => set({ status }),
  setMode: (mode) => set({ mode }),
}))
