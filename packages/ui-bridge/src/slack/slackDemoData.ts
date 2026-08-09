/**
 * The demo scenario, typed by the same contract as the live API.
 *
 * This exists for screenshots, the tour, and offline showcases — and it is
 * strictly opt-in (`VITE_DAYPILOT_DEMO_MODE=true`). Production **never** falls
 * back to it: a connected workspace with nothing in it shows an honest empty
 * state, because a fictional message that looks real is the fastest way to lose
 * someone's trust in an assistant that drafts on their behalf.
 */
import type {
  SlackConversation,
  SlackCounts,
  SlackDraft,
  SlackInboxItem,
  SlackMessage,
  SlackStatus,
  SlackThread,
} from './slackTypes'

const TODAY = new Date().toISOString().slice(0, 10)
const at = (hhmm: string) => `${TODAY}T${hhmm}:00Z`

function conversation(over: Partial<SlackConversation> & { id: string }): SlackConversation {
  return {
    channelId: over.id.toUpperCase(), kind: 'im', name: '', counterpart: '',
    audience: 'internal', memberCount: 0, lastMessageAt: null, ...over,
  }
}

function message(over: Partial<SlackMessage> & { id: string; text: string }): SlackMessage {
  return {
    ts: over.id, threadTs: null, author: '', direction: 'incoming',
    classification: 'needs_reply', group: 'needs_reply', flagged: false,
    handled: false, occurredAt: null, ...over,
  }
}

export const DEMO_CONVERSATIONS: SlackConversation[] = [
  conversation({ id: 'c-jane', kind: 'im', counterpart: 'Jane Smith', lastMessageAt: at('09:12') }),
  conversation({ id: 'c-platform', kind: 'channel', name: '#platform', memberCount: 38, lastMessageAt: at('09:25') }),
  conversation({ id: 'c-elena', kind: 'im', counterpart: 'Elena Garcia', lastMessageAt: at('08:47') }),
  conversation({ id: 'c-alpha', kind: 'channel', name: '#alpha-project', memberCount: 12, lastMessageAt: at('08:15') }),
  conversation({ id: 'c-david', kind: 'im', counterpart: 'David Rossi', lastMessageAt: at('07:58') }),
]

/** The reply DayPilot prepared for Jane — assembled from four sources. */
export const DEMO_DRAFT: SlackDraft = {
  id: 'd-jane',
  conversationId: 'c-jane',
  messageId: 'm-jane',
  kind: 'reply',
  text: [
    'Yes, Friday testing still looks achievable.',
    'The API changes are complete, but the authentication review is the remaining dependency.',
    "If that clears by Thursday morning, I expect we can deploy Thursday afternoon. I'll confirm once the security review is complete.",
  ].join('\n'),
  status: 'draft',
  classification: 'needs_reply',
  sources: [
    { type: 'project', id: 'p-alpha', label: 'Project Alpha', facts: ['Project Alpha is 82% complete.', 'Next action: approve the API contract.'] },
    { type: 'github', id: 'pr-142', label: 'PR #142', facts: ['PR #142 is awaiting security review.'] },
    { type: 'email', id: 'e-1', label: 'Customer email', facts: ['A related email thread constrains what can be promised here.'] },
    { type: 'conversation', id: '', label: 'Current Slack thread', facts: ['Jane Smith said: Do you think we can deliver the Alpha API changes before Thursday?'] },
  ],
  withheldCount: 1,
  approvalId: null,
  updatedAt: at('09:13'),
  sendsRequireApproval: true,
}

const DEMO_MESSAGES: Record<string, SlackMessage[]> = {
  'c-jane': [
    message({
      id: 'm-jane', author: 'Jane Smith', occurredAt: at('09:12'),
      classification: 'needs_reply', group: 'needs_reply',
      text: 'Do you think we can deliver the Alpha API changes before Thursday? The customer wants to test Friday morning.',
    }),
  ],
  'c-platform': [
    message({
      id: 'm-platform', author: 'Marco Bianchi', occurredAt: at('09:25'),
      classification: 'decision_requested', group: 'action',
      text: "@Ruslan should we move forward with Option B or wait for tomorrow's architecture meeting?",
    }),
  ],
  'c-elena': [
    message({
      id: 'm-elena', author: 'Elena Garcia', occurredAt: at('08:47'),
      classification: 'action_required', group: 'action',
      text: "Could you review PR #142 today if you have a moment? It's blocking tomorrow's deployment.",
    }),
  ],
  'c-alpha': [
    message({
      id: 'm-alpha', author: 'Sofia Rinaldi', occurredAt: at('08:15'),
      classification: 'fyi', group: 'fyi',
      text: "What's the plan for the deployment tomorrow?",
    }),
  ],
  'c-david': [
    message({
      id: 'm-david', author: 'David Rossi', occurredAt: at('07:58'),
      classification: 'acknowledgement', group: 'fyi',
      text: 'Deployed to staging 👍',
    }),
  ],
}

/** Titles are DayPilot's one-line read of each thread, not Slack metadata. */
const DEMO_SUBJECTS: Record<string, string> = {
  'c-jane': 'Project Alpha delivery date?',
  'c-platform': 'Decision on Option B',
  'c-elena': 'PR #142 review',
  'c-alpha': 'EOD update',
  'c-david': 'Deployed to staging 👍',
}

const DEMO_REPLY_COUNTS: Record<string, number> = {
  'c-jane': 4, 'c-platform': 6, 'c-elena': 3, 'c-alpha': 5, 'c-david': 0,
}

export function demoSubject(conversationId: string): string {
  return DEMO_SUBJECTS[conversationId] || ''
}

export function demoReplyCount(conversationId: string): number {
  return DEMO_REPLY_COUNTS[conversationId] || 0
}

export const DEMO_ITEMS: SlackInboxItem[] = DEMO_CONVERSATIONS.map((c) => {
  const messages = DEMO_MESSAGES[c.id] || []
  const latest = messages[messages.length - 1]
  return {
    conversation: c,
    message: latest,
    group: latest.group,
    // Only two of five earn a draft. That ratio is the product's whole
    // argument: an assistant that drafted all five would be noise.
    draft: c.id === 'c-jane' ? DEMO_DRAFT
      : c.id === 'c-elena' ? { ...DEMO_DRAFT, id: 'd-elena', conversationId: 'c-elena', messageId: 'm-elena', text: "Taking a look at PR #142 now — I'll leave comments before end of day so it isn't blocking tomorrow's deploy." }
        : null,
  }
})

export const DEMO_COUNTS: SlackCounts = {
  needs_reply: 4, action: 2, fyi: 8, done: 3,
} as SlackCounts

/** "All" is every open item, so it is a sum rather than its own number. */
export const DEMO_TOTAL = DEMO_COUNTS.needs_reply + DEMO_COUNTS.action + DEMO_COUNTS.fyi + DEMO_COUNTS.done

export const DEMO_STATUS: SlackStatus = {
  enabled: true,
  connected: true,
  connectionId: 'conn-demo',
  account: 'ruslan@acme.com',
  capabilities: ['chat.read', 'chat.history', 'chat.send'],
  lastActivityAt: at('09:25'),
  accessMode: 'standard',
  personalMessagesAvailable: false,
  counts: DEMO_COUNTS,
  sendsRequireApproval: true,
  delivery: {
    transport: 'socket', socketModeConfigured: true, signingSecretConfigured: true,
    requiresPublicUrl: false, eventsPath: null,
  },
}

export const DEMO_WORKSPACE_NAME = 'Acme Corp workspace'

export function demoThread(conversationId: string): SlackThread {
  const conversation = DEMO_CONVERSATIONS.find((c) => c.id === conversationId) || DEMO_CONVERSATIONS[0]
  const item = DEMO_ITEMS.find((i) => i.conversation?.id === conversation.id)
  return {
    conversation,
    messages: DEMO_MESSAGES[conversation.id] || [],
    draft: item?.draft ?? null,
  }
}

/** What the assistant proposes when asked to tighten the Jane reply. */
export const DEMO_IMPROVED = [
  "Yes, we're still on track for Friday testing. The API changes are complete, and the only remaining dependency is the authentication review (PR #142).",
  "If that's approved by Thursday morning, we'll deploy Thursday afternoon.",
  "I'll update you as soon as the security review is complete.",
].join('\n\n')
