/**
 * First-run setup state (v2).
 *
 * Replaces the single boolean `daypilot.onboarded`, whose bug was that
 * "Skip for now" marked setup *completed* and permanently hid the wizard even
 * though the provider, mailbox, and knowledge steps were never done. Setup is
 * now an explicit state machine:
 *
 *   not_started → in_progress → completed
 *
 * Only an explicit finish ("Enter DayPilot") sets `completed`. Skipping records
 * `in_progress` + a `dismissedAt` timestamp, so the wizard can be reopened and
 * setup can be resumed. The legacy `daypilot.onboarded=true` flag is migrated to
 * `completed` so existing users are not forced to re-onboard.
 */
export type SetupStepKey = 'provider' | 'profile' | 'mailbox' | 'knowledge'
export type SetupStatus = 'not_started' | 'in_progress' | 'completed'

export type SetupState = {
  version: 2
  status: SetupStatus
  completedSteps: Record<SetupStepKey, boolean>
  aiReady: boolean
  dismissedAt?: string
  completedAt?: string
}

const SETUP_KEY = 'daypilot.setup'
const LEGACY_ONBOARDED = 'daypilot.onboarded'
const LEGACY_AI_READY = 'daypilot.ai_ready'
const RESET_EVENT = 'daypilot:setup-reset'

const EMPTY: SetupState = {
  version: 2,
  status: 'not_started',
  completedSteps: { provider: false, profile: false, mailbox: false, knowledge: false },
  aiReady: false,
}

function safeParse(raw: string | null): SetupState | null {
  if (!raw) return null
  try {
    const obj = JSON.parse(raw) as Partial<SetupState>
    if (obj && obj.version === 2 && typeof obj.status === 'string') {
      return { ...EMPTY, ...obj, completedSteps: { ...EMPTY.completedSteps, ...(obj.completedSteps || {}) } }
    }
  } catch {
    /* fall through to migration */
  }
  return null
}

export function readSetup(): SetupState {
  try {
    const parsed = safeParse(localStorage.getItem(SETUP_KEY))
    if (parsed) return parsed
    // Migrate the legacy boolean: a previously "onboarded" install is treated as
    // completed so we never force existing users back through the wizard.
    if (localStorage.getItem(LEGACY_ONBOARDED) === 'true') {
      const aiReady = localStorage.getItem(LEGACY_AI_READY) === 'true'
      const migrated: SetupState = {
        ...EMPTY,
        status: 'completed',
        aiReady,
        completedSteps: { provider: aiReady, profile: true, mailbox: false, knowledge: false },
        completedAt: new Date().toISOString(),
      }
      writeSetup(migrated)
      return migrated
    }
  } catch {
    /* ignore storage access failures */
  }
  return { ...EMPTY }
}

export function writeSetup(state: SetupState): void {
  try {
    localStorage.setItem(SETUP_KEY, JSON.stringify(state))
    // Keep the legacy AI-ready flag in sync for any older reader.
    localStorage.setItem(LEGACY_AI_READY, state.aiReady ? 'true' : 'false')
  } catch {
    /* ignore */
  }
}

export function patchSetup(patch: Partial<SetupState>): SetupState {
  const next = { ...readSetup(), ...patch }
  writeSetup(next)
  return next
}

/** The wizard appears whenever setup is not explicitly completed. */
export function isSetupComplete(): boolean {
  return readSetup().status === 'completed'
}

export function isAiReady(): boolean {
  return readSetup().aiReady
}

/** "Skip for now": mark in-progress + dismissed, never completed. */
export function dismissSetup(steps?: Partial<Record<SetupStepKey, boolean>>): void {
  const cur = readSetup()
  patchSetup({
    status: 'in_progress',
    dismissedAt: new Date().toISOString(),
    completedSteps: { ...cur.completedSteps, ...(steps || {}) },
  })
}

/** The final, explicit "Enter DayPilot" action — the only thing that completes. */
export function completeSetup(steps: Partial<Record<SetupStepKey, boolean>>, aiReady: boolean): void {
  const cur = readSetup()
  patchSetup({
    status: 'completed',
    aiReady,
    completedAt: new Date().toISOString(),
    completedSteps: { ...cur.completedSteps, ...steps },
  })
}

/** Restart setup from scratch (Settings → Profile). Reopens the wizard. */
export function resetSetup(): void {
  try {
    localStorage.removeItem(SETUP_KEY)
    localStorage.removeItem(LEGACY_ONBOARDED)
    localStorage.removeItem(LEGACY_AI_READY)
  } catch {
    /* ignore */
  }
  try {
    window.dispatchEvent(new Event(RESET_EVENT))
  } catch {
    /* ignore (non-browser) */
  }
}

export function onSetupReset(handler: () => void): () => void {
  window.addEventListener(RESET_EVENT, handler)
  return () => window.removeEventListener(RESET_EVENT, handler)
}
