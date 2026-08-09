/**
 * The shapes `/v1/slack/*` returns.
 *
 * Kept in one file so the demo scenario and the live client are typed by the
 * *same* contract. A demo that drifts from the API is worse than no demo: it
 * shows a product that does not exist.
 */

/** Every label the classifier can assign. */
export type SlackClassification =
  | 'needs_reply' | 'action_required' | 'decision_requested'
  | 'fyi' | 'acknowledgement' | 'social' | 'low_priority'

/** How the inbox buckets those labels. */
export type InboxGroup = 'needs_reply' | 'action' | 'fyi' | 'done'

export type SlackConversation = {
  id: string
  channelId: string
  kind: 'im' | 'mpim' | 'channel' | 'group'
  name: string
  counterpart: string
  /** Drives the recipient-safety filter on the server. */
  audience: 'internal' | 'external'
  memberCount: number
  lastMessageAt: string | null
}

export type SlackMessage = {
  id: string
  ts: string
  threadTs: string | null
  author: string
  direction: 'incoming' | 'outgoing'
  text: string
  classification: SlackClassification
  group: InboxGroup
  /** Injection screening flagged this text. Shown, never obeyed. */
  flagged: boolean
  handled: boolean
  occurredAt: string | null
}

export type SlackSource = {
  type: string
  id: string
  label: string
  facts: string[]
}

export type SlackDraft = {
  id: string
  conversationId: string | null
  messageId: string | null
  kind: 'reply' | 'compose'
  text: string
  status: 'draft' | 'sending' | 'sent' | 'failed' | 'discarded'
  classification: SlackClassification
  sources: SlackSource[]
  /** How many facts the recipient filter removed before the draft was written. */
  withheldCount: number
  approvalId: string | null
  updatedAt: string | null
  /** Always true. Stated by the server so the UI never has to infer it. */
  sendsRequireApproval: boolean
}

export type SlackInboxItem = {
  conversation: SlackConversation | null
  message: SlackMessage
  group: InboxGroup
  draft: SlackDraft | null
}

export type SlackCounts = Record<InboxGroup, number> & { [key: string]: number }

export type SlackDelivery = {
  transport: 'socket' | 'http'
  socketModeConfigured: boolean
  signingSecretConfigured: boolean
  requiresPublicUrl: boolean
  eventsPath: string | null
}

export type SlackStatus = {
  enabled: boolean
  connected: boolean
  connectionId: string | null
  account: string | null
  capabilities: string[]
  lastActivityAt: string | null
  accessMode: 'standard' | 'personal'
  personalMessagesAvailable: boolean
  counts: Partial<SlackCounts>
  sendsRequireApproval: boolean
  delivery: SlackDelivery
}

export type SlackPreferences = {
  draftDirectMessages: boolean
  draftMentions: boolean
  draftParticipatingThreads: boolean
  draftAllChannelMessages: boolean
  autoPrepare: boolean
  contextSources: string[]
  usePreviousConversations: boolean
  recipientProtection: boolean
  accessMode: 'standard' | 'personal'
  /** Not a setting — a statement. Rendered locked. */
  neverAutomaticallySend: true
}

export type SlackContextSource = {
  id: string
  label: string
  requires: string | null
  available: boolean
  alwaysOn: boolean
}

export type SlackSettingsPayload = {
  settings: SlackPreferences
  sources: SlackContextSource[]
  effectiveSources: string[]
  accessModes: string[]
}

export type SlackThread = {
  conversation: SlackConversation
  messages: SlackMessage[]
  draft: SlackDraft | null
}

/** A candidate rewrite from the assistant. Not applied until "Use this". */
export type SlackProposal = {
  draftId: string
  instruction: string
  current: string
  proposed: string
  changed: boolean
}

export const TRANSFORMS = [
  { id: 'shorter', label: 'Shorter' },
  { id: 'direct', label: 'More direct' },
  { id: 'detailed', label: 'More detailed' },
  { id: 'friendly', label: 'Friendly' },
] as const

export type TransformId = (typeof TRANSFORMS)[number]['id']

export const INBOX_FILTERS: Array<{ id: 'all' | InboxGroup; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'needs_reply', label: 'Needs reply' },
  { id: 'action', label: 'Action' },
  { id: 'fyi', label: 'FYI' },
  { id: 'done', label: 'Done' },
]

/** The badge under an inbox row. Says what DayPilot did, not how it feels. */
export function badgeFor(item: SlackInboxItem): { label: string; tone: string } | null {
  if (item.group === 'done') return { label: 'Done', tone: 'done' }
  if (item.draft && item.draft.status === 'draft') return { label: 'Draft ready', tone: 'draft' }
  if (item.group === 'action') return { label: 'Action needed', tone: 'action' }
  if (item.group === 'fyi') return { label: 'FYI', tone: 'fyi' }
  return null
}

/** "09:12" — the inbox has room for exactly that much. */
export function clockTime(iso: string | null): string {
  if (!iso) return ''
  const when = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`)
  if (Number.isNaN(when.getTime())) return ''
  return when.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
}

/** "#platform" for a channel, a person's name for a DM. */
export function conversationTitle(conversation: SlackConversation | null): string {
  if (!conversation) return 'Slack'
  if (conversation.kind === 'im') return conversation.counterpart || 'Direct message'
  return conversation.name || conversation.channelId
}

export function conversationSubtitle(conversation: SlackConversation | null): string {
  if (!conversation) return ''
  if (conversation.kind === 'im') return `Direct message · ${conversation.counterpart || 'Slack'}`
  if (conversation.kind === 'mpim') return `Group message · ${conversation.name}`
  const members = conversation.memberCount ? ` · ${conversation.memberCount} members` : ''
  return `Channel · ${conversation.name}${members}`
}
