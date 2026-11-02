/**
 * Live calls with the visitor's own keys are paused: Home and the call page offer no way to start one.
 * The live code, the Settings keys page and the provider presets stay, so the live modes can switch this on.
 */
export const LIVE_CALLS_ENABLED = false

/** Speak live (the visitor speaks as the agent into the microphone). The backend side is SPEAK_LIVE_ENABLED in its settings; both are off until the page ships. */
export const SPEAK_LIVE_ENABLED = false
