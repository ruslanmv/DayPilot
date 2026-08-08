/**
 * Client for the Daily Standup Copilot.
 *
 * Every call hits DayPilot's own gateway — the browser never talks to Slack,
 * and never holds a Slack token. The gateway resolves the thread, holds the
 * approved snapshot and performs the send, so a compromised browser tab cannot
 * post to a channel on the user's behalf.
 */
import { api } from '../apiClient'
import { workspaceId } from '../env'

const ws = () => workspaceId()
const q = (extra?: Record<string, string>) =>
  new URLSearchParams({ workspaceId: ws(), ...(extra || {}) }).toString()

export type DeliveryMode = 'next_workday' | 'same_day'

export type StandupWorkflow = {
  id: string
  name: string
  enabled: boolean
  timezone: string
  workingDays: number[]
  reviewTime: string
  reminderTime: string
  deliveryMode: DeliveryMode
  slackConnectionId?: string | null
  slackChannelId: string
  slackChannelName: string
  reminderSignature: string
  reminderBotId?: string | null
  threadResolutionMode: 'adopt' | 'own'
  evidenceSources: Record<string, boolean>
  approvalPolicy: string
  emptyDayPolicy: 'honest' | 'skip'
  nextReviewAt?: string | null
}

/** Draft lifecycle. Only the first group may still be edited. */
export type DraftStatus =
  | 'COLLECTING' | 'DRAFT' | 'NEEDS_REVIEW'
  | 'APPROVED' | 'WAITING_FOR_THREAD' | 'SENDING' | 'SENT'
  | 'THREAD_NOT_FOUND' | 'SEND_FAILED' | 'SKIPPED' | 'EXPIRED'

/** How much DayPilot actually knows about a bullet. */
export type BulletKind = 'observed' | 'manual' | 'needs_confirmation'

export type Bullet = { text: string; evidenceIds: string[]; kind: BulletKind }

export type StandupDraft = {
  id: string
  workflowId: string
  reportingDate: string
  targetStandupDate: string
  yesterday: string
  today: string
  blockers: string
  provenance: { yesterday?: Bullet[]; today?: Bullet[]; blockers?: Bullet[] }
  status: DraftStatus
  detail: string
  contentHash?: string | null
  approvedAt?: string | null
  editable: boolean
  slackThreadTs?: string | null
  slackMessageTs?: string | null
  sentAt?: string | null
  attempts: number
  slackPreview: string
}

export type StandupEvidence = {
  id: string
  source: 'daypilot' | 'github' | 'calendar' | 'agents' | 'manual'
  sourceRef: string
  activityType: 'completed' | 'progress' | 'blocked' | 'planned' | 'meeting'
  summary: string
  projectName: string
  occurredAt?: string | null
  confidence: number
  included: boolean
  metadata: Record<string, unknown>
}

export type StandupStatus =
  | { configured: false; workflows: StandupWorkflow[] }
  | {
      configured: true
      workflow: StandupWorkflow
      reportingDate: string
      signals: number
      projects: number
      possibleBlockers: number
      draft: StandupDraft | null
    }

export type ThreadProbe =
  | { found: true; threadTs: string; channelName: string; preview: string; matchedOn: string[]; message: string }
  | { found: false; reason: string; channelName: string }

export const standupApi = {
  status: () => api.get<StandupStatus>(`/v1/standup/status?${q()}`),

  listWorkflows: () => api.get<{ workflows: StandupWorkflow[] }>(`/v1/standup/workflows?${q()}`),
  createWorkflow: (body: Partial<StandupWorkflow>) =>
    api.post<StandupWorkflow>(`/v1/standup/workflows?${q()}`, body),
  updateWorkflow: (id: string, body: Partial<StandupWorkflow>) =>
    api.patch<StandupWorkflow>(`/v1/standup/workflows/${encodeURIComponent(id)}?${q()}`, body),

  /** Prove the thread against live Slack before trusting it daily. */
  testThread: (id: string) =>
    api.post<ThreadProbe>(`/v1/standup/workflows/${encodeURIComponent(id)}/test-thread-resolution?${q()}`),

  collect: (id: string, reportingDate?: string) =>
    api.post<{ reportingDate: string; collected: number; included: number; evidence: StandupEvidence[] }>(
      `/v1/standup/workflows/${encodeURIComponent(id)}/collect?${q(reportingDate ? { reportingDate } : undefined)}`,
    ),
  generate: (id: string, reportingDate?: string) =>
    api.post<StandupDraft>(
      `/v1/standup/workflows/${encodeURIComponent(id)}/generate?${q(reportingDate ? { reportingDate } : undefined)}`,
    ),
  addNote: (id: string, text: string, reportingDate?: string) =>
    api.post<StandupEvidence>(`/v1/standup/workflows/${encodeURIComponent(id)}/notes?${q()}`, {
      text, reportingDate,
    }),

  draftForDate: (reportingDate: string, workflowId?: string) =>
    api.get<StandupDraft>(
      `/v1/standup/drafts/${encodeURIComponent(reportingDate)}?${q(workflowId ? { workflowId } : undefined)}`,
    ),
  editDraft: (draftId: string, body: { yesterday?: string; today?: string; blockers?: string }) =>
    api.patch<StandupDraft>(`/v1/standup/drafts/${encodeURIComponent(draftId)}?${q()}`, body),
  approve: (draftId: string) =>
    api.post<StandupDraft>(`/v1/standup/drafts/${encodeURIComponent(draftId)}/approve?${q()}`),
  skip: (draftId: string, reason = '') =>
    api.post<StandupDraft>(`/v1/standup/drafts/${encodeURIComponent(draftId)}/skip?${q()}`, { reason }),
  sendNow: (draftId: string) =>
    api.post<{ status: string; messageTs?: string; duplicate?: boolean; draft: StandupDraft }>(
      `/v1/standup/drafts/${encodeURIComponent(draftId)}/send-now?${q()}`,
    ),

  evidence: (draftId: string) =>
    api.get<{ evidence: StandupEvidence[] }>(`/v1/standup/drafts/${encodeURIComponent(draftId)}/evidence?${q()}`),
  includeEvidence: (draftId: string, evidenceId: string) =>
    api.post<StandupEvidence>(
      `/v1/standup/drafts/${encodeURIComponent(draftId)}/evidence/${encodeURIComponent(evidenceId)}/include?${q()}`,
    ),
  excludeEvidence: (draftId: string, evidenceId: string) =>
    api.post<StandupEvidence>(
      `/v1/standup/drafts/${encodeURIComponent(draftId)}/evidence/${encodeURIComponent(evidenceId)}/exclude?${q()}`,
    ),
}

/** Status → what the user should read. Text, never colour alone. */
export function draftStatusLabel(status: DraftStatus): string {
  switch (status) {
    case 'COLLECTING': return 'Collecting activity'
    case 'DRAFT': case 'NEEDS_REVIEW': return 'Draft ready'
    case 'APPROVED': case 'WAITING_FOR_THREAD': return 'Approved — waiting for the thread'
    case 'SENDING': return 'Sending'
    case 'SENT': return 'Posted to Slack'
    case 'THREAD_NOT_FOUND': return 'Standup thread not found'
    case 'SEND_FAILED': return 'Slack send failed'
    case 'SKIPPED': return 'Skipped'
    case 'EXPIRED': return 'Expired — the standup day passed'
  }
}

/** A bullet DayPilot did not observe must say so, not blend in. */
export function bulletKindLabel(kind: BulletKind): string {
  return kind === 'observed' ? '' : kind === 'manual' ? 'Manual statement' : 'Needs confirmation'
}
