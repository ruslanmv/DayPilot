/**
 * Client for the backend-owned AI profile, goals, and onboarding (Phase 1/3).
 *
 * The backend is the single source of truth. The browser holds only the current
 * revision (for optimistic concurrency) and transient form drafts — never the
 * authoritative profile or completion state. Cookie-authenticated writes echo
 * the readable `dp_csrf` cookie as `X-CSRF-Token`; in local-first mode where no
 * session exists the header is simply ignored server-side.
 */
import { api, type ApiResult } from '../apiClient'

export type UseCase =
  | 'plan_day' | 'manage_projects' | 'draft_communications'
  | 'research_knowledge' | 'coordinate_agents'

export type WorkingWindow = { days: number[]; start: string; end: string }

export type ScheduleDoc = {
  workingWindows?: WorkingWindow[]
  strictness?: 'strict' | 'flexible'
  quietHours?: { start: string; end: string } | null
}

export type PlanningDoc = {
  focusMinutes?: number
  meetingBufferMinutes?: number
  planningHorizonDays?: number
  taskChunkMinutes?: number
  prioritization?: 'deadlines' | 'impact' | 'quick_wins' | 'manual'
}

export type CommunicationDoc = {
  tone?: 'friendly' | 'neutral' | 'formal' | 'direct'
  detail?: 'concise' | 'balanced' | 'detailed'
  format?: 'bullets' | 'prose' | 'mixed'
  languages?: string[]
  draftingGreeting?: string
  draftingSignoff?: string
  uncertainty?: 'flag_and_proceed' | 'ask_first'
}

export type BoundaryRule = { kind: string; value?: string }
export type BoundariesDoc = { rules?: BoundaryRule[]; notes?: string }

export type ConsentCategory =
  | 'identity' | 'schedule' | 'planning' | 'communication'
  | 'accessibility' | 'goals' | 'boundaries'

export type AiProfile = {
  revision: number
  schemaVersion: number
  exists: boolean
  timezone: string | null
  locale: string | null
  preferredName: string | null
  pronouns: string | null
  useCases: UseCase[]
  schedule: ScheduleDoc
  planning: PlanningDoc
  communication: CommunicationDoc
  accessibility: Record<string, unknown>
  boundaries: BoundariesDoc
  categoryConsent: Record<ConsentCategory, boolean>
  reviewedAt: string | null
  updatedAt: string | null
}

export type ProfileGoal = {
  id: string
  title: string
  detail: string
  status: 'active' | 'upcoming' | 'archived'
  priority: number
  reviewAt: string | null
}

export type OnboardingView = {
  flowVersion: number
  status: 'not_started' | 'in_progress' | 'completed'
  currentStep: string
  completedSteps: string[]
  dismissedAt: string | null
  completedAt: string | null
  profile: AiProfile & { completeness: ProfileCompleteness }
  capabilities: {
    provider: { connected: boolean; active?: string | null }
    mail: { connected: boolean }
    calendar: { connected: boolean }
    knowledge: { connected: boolean; count?: number }
  }
}

export type ProfileCompleteness = {
  requiredComplete: boolean
  missing: string[]
  hasSchedule: boolean
  hasCommunication: boolean
  reviewed: boolean
}

export type Observation = {
  id: string
  category: string
  value: Record<string, unknown>
  sourceType: string
  confidence: number
  state: 'suggested' | 'confirmed' | 'rejected' | 'expired'
  observedAt: string | null
  expiresAt: string | null
}

export type ContextPreview = {
  purpose: string
  profileRevision: number
  includedCategories: string[]
  provenance: Record<string, string>
  [key: string]: unknown
}

export type ProfilePatch = Partial<{
  timezone: string
  locale: string
  preferredName: string
  pronouns: string
  useCases: UseCase[]
  schedule: ScheduleDoc
  planning: PlanningDoc
  communication: CommunicationDoc
  accessibility: Record<string, unknown>
  boundaries: BoundariesDoc
  categoryConsent: Partial<Record<ConsentCategory, boolean>>
}>

function csrfHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...(extra || {}) }
  if (typeof document !== 'undefined') {
    const match = document.cookie.match(/(?:^|;\s*)dp_csrf=([^;]+)/)
    if (match) headers['X-CSRF-Token'] = decodeURIComponent(match[1])
  }
  return headers
}

export const profileClient = {
  getProfile: () => api.get<AiProfile>('/v1/profile/ai'),

  /** Merge the provided fields, guarding the write with the known revision. A
   * stale revision resolves to `{ ok:false, status:409 }` so the caller can
   * refetch and re-apply. */
  saveProfile: (revision: number, patch: ProfilePatch): Promise<ApiResult<AiProfile>> =>
    api.patch<AiProfile>('/v1/profile/ai', patch, {
      headers: csrfHeaders(revision > 0 ? { 'If-Match': `"${revision}"` } : {}),
    }),

  getGoals: () => api.get<{ goals: ProfileGoal[] }>('/v1/profile/goals'),
  createGoal: (body: { title: string; detail?: string; priority?: number; reviewAt?: string }) =>
    api.post<ProfileGoal>('/v1/profile/goals', body, { headers: csrfHeaders() }),
  updateGoal: (id: string, body: Partial<{ title: string; detail: string; status: string; priority: number; reviewAt: string }>) =>
    api.patch<ProfileGoal>(`/v1/profile/goals/${id}`, body, { headers: csrfHeaders() }),
  deleteGoal: (id: string) => api.del<void>(`/v1/profile/goals/${id}`, { headers: csrfHeaders() }),

  contextPreview: (purpose: string) =>
    api.get<ContextPreview>(`/v1/profile/ai/context-preview?purpose=${encodeURIComponent(purpose)}`),
  exportProfile: () => api.get<Record<string, unknown>>('/v1/profile/ai/export'),
  resetLearned: () => api.del<{ reset: boolean; removed: number }>('/v1/profile/ai/learned', { headers: csrfHeaders() }),

  listObservations: (state?: string) =>
    api.get<{ observations: Observation[] }>(`/v1/profile/ai/observations${state ? `?state=${state}` : ''}`),
  confirmObservation: (id: string) =>
    api.post<Observation>(`/v1/profile/ai/observations/${id}/confirm`, undefined, { headers: csrfHeaders() }),
  rejectObservation: (id: string) =>
    api.post<Observation>(`/v1/profile/ai/observations/${id}/reject`, undefined, { headers: csrfHeaders() }),

  getOnboarding: () => api.get<OnboardingView>('/v1/onboarding'),
  patchOnboarding: (body: Partial<{ currentStep: string; completedSteps: string[]; dismissed: boolean }>) =>
    api.patch<OnboardingView>('/v1/onboarding', body, { headers: csrfHeaders() }),
  completeOnboarding: () => api.post<OnboardingView>('/v1/onboarding/complete', undefined, { headers: csrfHeaders() }),
  importLegacy: (fields: Record<string, unknown>) =>
    api.post<{ imported: string[]; profile: AiProfile }>('/v1/profile/ai/import-legacy', { fields }, { headers: csrfHeaders() }),
}

export const USE_CASE_LABELS: Record<UseCase, string> = {
  plan_day: 'Plan my day',
  manage_projects: 'Manage projects',
  draft_communications: 'Draft communications',
  research_knowledge: 'Research & knowledge',
  coordinate_agents: 'Coordinate agents',
}

export const CONSENT_LABELS: Record<ConsentCategory, string> = {
  identity: 'Identity (timezone, locale)',
  schedule: 'Working hours & schedule',
  planning: 'Planning preferences',
  communication: 'Communication style',
  accessibility: 'Accessibility notes',
  goals: 'Goals',
  boundaries: 'Boundaries',
}
