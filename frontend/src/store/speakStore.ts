import { create } from 'zustand'

const CLOCK = /^([01]\d|2[0-3]):[0-5]\d$/

/** Speak live set-up state that must survive the move from the set-up page to the call page. Memory only. */
interface SpeakState {
  /** Test clock for R1 ("HH:MM"), read once on the set-up page from the address; null for the real clock. */
  clock: string | null
  /** The session created by the Start button. */
  session: { id: string; wsUrl: string } | null
  setClockFromAddress: (raw: string | null) => void
  setSession: (s: { id: string; wsUrl: string } | null) => void
}

export const useSpeakStore = create<SpeakState>((set) => ({
  clock: null,
  session: null,
  setClockFromAddress: (raw) => {
    set({ clock: raw !== null && CLOCK.test(raw) ? raw : null })
  },
  setSession: (session) => set({ session }),
}))
