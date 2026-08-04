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
export type MailboxConnection = {
  id: string; provider: string; emailAddress: string; displayName?: string | null
  imapHost?: string | null; imapPort: number; imapSecurity: string
  smtpHost?: string | null; smtpPort: number; smtpSecurity: string
  status: string; lastTestedAt?: string | null; lastErrorCode?: string | null
}
export type EmailStatus = {
  enabled: boolean; connected: boolean
  account: EmailAccount | null; providers?: OnboardingProvider[]
  connection?: MailboxConnection | null
}
export type MailboxTestInput = {
  provider: string; emailAddress?: string; displayName?: string | null
  username?: string; password?: string
  imapHost?: string; imapPort?: number; imapSecurity?: string
  smtpHost?: string; smtpPort?: number; smtpSecurity?: string
}
export type MailboxProbeResult = {
  code: string; checks?: Record<string, string>; degraded?: boolean
  connection?: MailboxConnection | null
}
export type OAuthStartResult = {
  available: boolean; reason?: string; fallback?: string; message?: string; provider?: string
  authorizationUrl?: string; state?: string
}
export type MailDiscovery = {
  status: 'found' | 'manual_required'
  username?: string
  appPasswordRecommended?: boolean
  settings?: {
    imapHost: string; imapPort: number; imapSecurity: string
    smtpHost: string; smtpPort: number; smtpSecurity: string
  }
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
  status: () => api.get<EmailStatus>(`/v1/email/status?workspaceId=${ws()}`),
  folders: () => api.get<{ folders: string[] }>(`/v1/email/folders?workspaceId=${ws()}`),
  messages: (q?: string) => api.get<{ items: EmailSummary[]; query?: string }>(
    `/v1/email/messages?workspaceId=${ws()}${q ? `&q=${encodeURIComponent(q)}` : ''}`),
  message: (uid: string) => api.get<EmailDetail>(
    `/v1/email/messages/${encodeURIComponent(uid)}?workspaceId=${ws()}`),
  draftReply: (uid: string, tone: string) => api.post<DraftReply>(
    `/v1/email/messages/${encodeURIComponent(uid)}/draft-reply`, { uid, tone, workspaceId: ws() }),
  revise: (uid: string, current: string, instruction: string, tone: string) => api.post<{ body: string }>(
    '/v1/email/ai/revise', { uid, current, instruction, tone, workspaceId: ws() }),
  send: (draftUid: string, to: string[], subject: string, text: string, approved: boolean) => api.post<{ smtpStatus: string; sentUid?: string }>(
    '/v1/email/drafts/send', { draftUid, to, subject, text, workspaceId: ws(), approval: { confirmed_by_user: approved, visible_action_text: subject } }),

  // --- mailbox setup wizard (Batch 3) ---------------------------------------
  discover: (emailAddress: string) => api.post<MailDiscovery>(
    '/v1/email/discover', { emailAddress, workspaceId: ws() }),
  test: (input: MailboxTestInput) => api.post<MailboxProbeResult>(
    '/v1/email/test', { ...input, workspaceId: ws() }),
  connect: (input: MailboxTestInput) => api.post<MailboxProbeResult>(
    '/v1/email/connect', { ...input, workspaceId: ws() }),
  disconnect: () => api.post<{ disconnected: boolean; connection: MailboxConnection | null }>(
    '/v1/email/disconnect', { workspaceId: ws() }),
  reconnect: () => api.post<MailboxProbeResult>('/v1/email/reconnect', { workspaceId: ws() }),
  oauthStart: (provider: string) => api.post<OAuthStartResult>(
    `/v1/email/oauth/${encodeURIComponent(provider)}/start`, { workspaceId: ws() }),
}

/** Human-readable, honest explanation for a probe error code. */
export function mailErrorMessage(code: string): string {
  switch (code) {
    case 'connected': return 'Connected.'
    case 'missing_host': return 'Enter the IMAP server hostname.'
    case 'missing_credentials': return 'Enter your email address and password.'
    case 'dns_error': return "That server hostname couldn't be found. Check the IMAP/SMTP host."
    case 'connection_refused': return 'The server refused the connection. Check the host and port.'
    case 'timeout': return 'The server took too long to respond. Check the host, port, and network.'
    case 'tls_error': return 'The secure connection failed. Try switching between SSL and STARTTLS.'
    case 'imap_auth_failed': return 'IMAP sign-in was rejected. Check the username and password (or app password).'
    case 'imap_select_failed': return 'Signed in, but the INBOX could not be opened.'
    case 'smtp_auth_failed': return 'Sending sign-in was rejected. Reads work, but sending would fail.'
    case 'smtp_error': return 'The outgoing (SMTP) server could not be reached. Reads work, but sending would fail.'
    default: return 'The mailbox could not be verified. Check the settings and try again.'
  }
}

export type MailRecoveryAction = 'retry' | 'app_password_help' | 'manual_settings' | 'advanced' | 'security_activity'
export type MailRecovery = {
  title: string
  message: string
  field?: 'emailAddress' | 'password' | 'imapHost' | 'smtpHost'
  primary: MailRecoveryAction
  secondary?: MailRecoveryAction
}

/**
 * Map a backend probe code to a premium, actionable recovery: what failed, what
 * to do, and which field it belongs to. Consumes the existing granular codes so
 * the backend contract is unchanged.
 */
export function mailRecovery(code: string, appPasswordRecommended?: boolean): MailRecovery {
  switch (code) {
    case 'imap_auth_failed':
      return appPasswordRecommended
        ? { title: 'We couldn’t sign in', field: 'password', primary: 'app_password_help', secondary: 'retry',
            message: 'The password was not accepted. This service needs a password created for external email apps.' }
        : { title: 'We couldn’t sign in', field: 'password', primary: 'retry', secondary: 'app_password_help',
            message: 'The password was not accepted by your email service. Check for typos, or use an app password.' }
    case 'imap_select_failed':
      return { title: 'Email app access may be disabled', primary: 'retry',
        message: 'Your email service signed you in but wouldn’t open the inbox. Enable IMAP / external app access in your email settings, then try again.' }
    case 'dns_error':
    case 'missing_host':
      return { title: 'We couldn’t find your mail settings', field: 'imapHost', primary: 'manual_settings', secondary: 'retry',
        message: 'DayPilot couldn’t discover the secure incoming and outgoing servers for this address.' }
    case 'tls_error':
      return { title: 'We couldn’t create a secure connection', primary: 'advanced', secondary: 'retry',
        message: 'The server was found, but its encryption settings didn’t match what we detected. Review Advanced settings.' }
    case 'timeout':
    case 'connection_refused':
      return { title: 'Your email server isn’t responding', primary: 'retry', secondary: 'advanced',
        message: 'Your details may be correct, but the server didn’t respond in time. Please try again.' }
    case 'smtp_auth_failed':
    case 'smtp_error':
      return { title: 'Your inbox is available', primary: 'retry', secondary: 'advanced',
        message: 'DayPilot can read and organize this account, but it couldn’t verify outgoing mail. Sending stays disabled until this is fixed.' }
    case 'missing_credentials':
      return { title: 'Enter your sign-in details', field: 'password', primary: 'retry',
        message: 'Add your email address and password (or app password) to connect.' }
    default:
      return { title: 'We couldn’t complete the connection', primary: 'retry', secondary: 'advanced',
        message: 'DayPilot couldn’t verify this mailbox. Check the details and try again.' }
  }
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
