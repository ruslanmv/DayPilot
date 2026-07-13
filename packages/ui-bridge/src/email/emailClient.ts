/**
 * Client for the real DayPilot email API (`/v1/email/*`).
 *
 * Every folder, message, draft, send, and AI reply the Email workspace shows
 * comes from these calls against an authenticated account — never placeholder
 * data. Sending stays approval-gated on the backend; this client only asks and
 * reports what came back. No tokens or credentials pass through here.
 */
import { api } from '../apiClient'
import { workspaceId } from '../env'

export type EmailCapabilities = {
  read: boolean; send: boolean; drafts: boolean; labels: boolean
  folders: boolean; attachments: boolean; pushNotifications: boolean
}
export type EmailAccount = {
  provider: string; emailAddress: string; displayName?: string | null
  status: string; capabilities: EmailCapabilities
}
export type OnboardingProvider = { id: string; label: string; auth: string }
export type EmailStatus = {
  enabled: boolean; connected: boolean
  account: EmailAccount | null; providers?: OnboardingProvider[]
}
export type EmailSummary = {
  id: string; externalId: string; subject: string; sender: string
  urgency: string; intent: string; status: string
  scheduleImpact?: boolean; actionItems: string[]
}
export type EmailDetail = {
  uid: string; folder: string; subject: string; from: string; to: string[]
  receivedAt?: string | null; flags: string[]; text: string; html: string; hasAttachments: boolean
}
export type DraftReply = { draftUid: string; body: string; approvalId: string; approvalStatus: string; requiresApproval: boolean }

const ws = () => workspaceId()

export const emailApi = {
  status: () => api.get<EmailStatus>('/v1/email/status'),
  folders: () => api.get<{ folders: string[] }>('/v1/email/folders'),
  messages: (q?: string) => api.get<{ items: EmailSummary[]; query?: string }>(
    `/v1/email/messages?workspaceId=${ws()}${q ? `&q=${encodeURIComponent(q)}` : ''}`),
  message: (uid: string) => api.get<EmailDetail>(`/v1/email/messages/${encodeURIComponent(uid)}`),
  draftReply: (uid: string, tone: string) => api.post<DraftReply>(
    `/v1/email/messages/${encodeURIComponent(uid)}/draft-reply`, { uid, tone, workspaceId: ws() }),
  revise: (uid: string, current: string, instruction: string, tone: string) => api.post<{ body: string }>(
    '/v1/email/ai/revise', { uid, current, instruction, tone, workspaceId: ws() }),
  send: (draftUid: string, to: string[], subject: string, text: string, approved: boolean) => api.post<{ smtpStatus: string; sentUid?: string }>(
    '/v1/email/drafts/send', { draftUid, to, subject, text, workspaceId: ws(), approval: { confirmed_by_user: approved, visible_action_text: subject } }),
}

/** Classify a backend folder name into a stable type for icon/semantics. */
export function folderType(name: string): string {
  const n = name.toLowerCase()
  if (n.includes('inbox')) return 'inbox'
  if (n.includes('draft')) return 'drafts'
  if (n.includes('sent')) return 'sent'
  if (n.includes('archive')) return 'archive'
  if (n.includes('important') || n.includes('star') || n.includes('flag')) return 'important'
  if (n.includes('spam') || n.includes('junk')) return 'spam'
  if (n.includes('trash') || n.includes('deleted')) return 'trash'
  return 'custom'
}
