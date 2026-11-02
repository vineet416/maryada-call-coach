/**
 * Live calls with the visitor's own keys are paused: Home and the call page offer no way to start one.
 * The live code, the Settings keys page and the provider presets stay, so the live modes can switch this on.
 */
export const LIVE_CALLS_ENABLED = false

/**
 * Speak live (the visitor speaks as the agent into the microphone). Off in committed code; it is switched on for local
 * testing only with VITE_SPEAK_LIVE=1. The backend side is SPEAK_LIVE_ENABLED in its environment.
 */
export const SPEAK_LIVE_ENABLED = import.meta.env.VITE_SPEAK_LIVE === '1'
