/**
 * Start a recorded run at once when the visitor clicked a link inside the app.
 *
 * The click passes `AUTOSTART` as router state. The call page reads it once, removes it from the history entry, and starts
 * playback only if the browser says this page has had a user gesture (so sound is allowed). A page opened directly,
 * refreshed or reached from a pasted link has no state, so it shows the Ready card instead.
 */
export const AUTOSTART = { autostart: true } as const

export function isAutostart(state: unknown): boolean {
  return typeof state === 'object' && state !== null && (state as { autostart?: unknown }).autostart === true
}

type WithActivation = { userActivation?: { hasBeenActive?: boolean } }

/** True only when the browser reports a past user gesture on this page. A browser without the API gets the Ready card. */
export function soundAllowed(nav: WithActivation | undefined = typeof navigator === 'undefined' ? undefined : navigator): boolean {
  return nav?.userActivation?.hasBeenActive === true
}
