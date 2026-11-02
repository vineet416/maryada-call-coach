/** Live-call limits shown on the Settings page. They must equal the backend defaults; backend/tests/test_ui_limits.py checks it. */
export const CALL_LIMIT_S = 200
export const CONCURRENT_CALLS = 3
/** Speak live call length; must equal the backend MIC_SESSION_MAX_S (backend/tests/test_ui_limits.py checks it). */
export const MIC_CALL_LIMIT_S = 180
