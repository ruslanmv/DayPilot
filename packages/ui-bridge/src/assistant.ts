/**
 * The connected AI assistant.
 *
 * Instead of a canned "here's what I can do" menu, the assistant routes each
 * question to the real backend and answers from live data:
 *   - date/time questions are answered from the real clock,
 *   - "today's plan" / "replan" call the multi-agent planner,
 *   - "integration status" reads the live integrations + provider health,
 *   - "what needs approval" reads the Approval Center summary,
 *   - "new project" opens the project wizard.
 *
 * When the backend is unreachable it says so honestly (never fabricates a
 * plan or a status), and for genuinely unrelated questions it gives a short,
 * truthful scope statement rather than repeating a fixed fallback.
 *
 * The assistant is read-only and orchestration-only: it never sends email or
 * calls a provider directly, and every write stays approval-gated on the
 * backend. It only *asks* the backend and reports what came back.
 */
import { api } from './apiClient'
import { workspaceId } from './env'

export type AssistantAction =
  | { kind: 'navigate'; target: 'planning' | 'projects' | 'calendar' | 'agents' }
  | { kind: 'openProjectWizard' }
  | { kind: 'openApprovals' }

export type AssistantReply = { text: string; action?: AssistantAction }

function today(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

function longDate(): string {
  return new Date().toLocaleDateString(undefined, {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  })
}

type Intent = 'date' | 'plan' | 'replan' | 'integrations' | 'approvals' | 'new_project' | 'unknown'

/** Classify with word-ish matching so "today" doesn't match inside other words. */
export function classifyIntent(q: string): Intent {
  const l = ` ${q.toLowerCase()} `
  const has = (...ws: string[]) => ws.some((w) => l.includes(w))
  if (has(' move ', ' replan', ' reschedul', ' push ', ' batch ', ' protect ', ' swap ')) return 'replan'
  if (has(' what day', ' which day', "today's date", ' date today', ' what is today', " what's today", ' current date', ' what time')) return 'date'
  // Email/calendar/integration/provider questions — including "can you access
  // my email?" — must be answered truthfully from real connection status, so
  // they are classified before the generic plan/schedule intent.
  if (has(' email', ' e-mail', ' mailbox', ' inbox', ' calendar', ' integration', ' connected',
          ' provider', ' ollabridge', ' health', ' access to ', ' access my ', ' can you access')) return 'integrations'
  if (has(' new project', ' create project', ' start a project', ' add project', ' create a project')) return 'new_project'
  if (has(' plan', ' schedule', ' agenda', ' my day')) return 'plan'
  if (has(' approv', ' pending', ' review queue')) return 'approvals'
  return 'unknown'
}

async function answerReplan(message: string): Promise<AssistantReply> {
  const res = await api.post<{ reply?: string; plan?: { summary?: string } }>(
    `/v1/planner/plans/${today()}/chat`, { workspaceId: workspaceId(), message })
  if (!res.ok) {
    return { text: `I couldn't reach the planner (${res.error}). Once the backend is running I can adjust your day.` }
  }
  return {
    text: res.data.reply || res.data.plan?.summary || 'Updated your plan.',
    action: { kind: 'navigate', target: 'planning' },
  }
}

async function answerPlan(): Promise<AssistantReply> {
  const res = await api.post<{ summary?: string; score?: number; blocks?: unknown[] }>(
    `/v1/planner/plans/${today()}/generate`, { workspaceId: workspaceId() })
  if (!res.ok) {
    return { text: `I couldn't reach the planner (${res.error}). Once the backend is running I can generate your day.` }
  }
  const d = res.data
  const n = Array.isArray(d.blocks) ? d.blocks.length : 0
  const summary = d.summary || `Planned ${n} block(s) for today.`
  const score = typeof d.score === 'number' ? ` Plan score ${d.score}/100.` : ''
  return { text: `${summary}${score}`, action: { kind: 'navigate', target: 'planning' } }
}

type Connection = { provider?: string; name?: string; status?: string; kind?: string }

function mentions(q: string, ...ws: string[]): boolean {
  const l = ` ${q.toLowerCase()} `
  return ws.some((w) => l.includes(w))
}

function isConnected(status?: string): boolean {
  return ['connected', 'active', 'healthy', 'paired', 'ready'].includes((status || '').toLowerCase())
}

/** Answer a specific "can you access my email/calendar?" question truthfully —
 *  based on real connection status, never a guess. */
function accessAnswer(cons: Connection[], label: string, ...keys: string[]): AssistantReply {
  const match = cons.find((c) => keys.some((k) =>
    `${c.provider || ''} ${c.name || ''} ${c.kind || ''}`.toLowerCase().includes(k)))
  if (!match) {
    return { text: `No ${label} account is connected, so I can't access your ${label} yet. Connect one in Settings → Integrations (or Mail settings), and I'll never send anything without your approval.` }
  }
  if (isConnected(match.status)) {
    return { text: `Yes — your ${label} (${match.name || match.provider}) is connected, so I can read and prepare drafts. I never send or make changes without your approval.` }
  }
  return { text: `Your ${label} (${match.name || match.provider}) is set up but currently ${match.status || 'unavailable'}. Reconnect it in Settings to give me access.` }
}

async function answerIntegrations(question = ''): Promise<AssistantReply> {
  const ws = workspaceId()
  const [integ, health] = await Promise.all([
    api.get<{ connections?: Connection[] }>(`/v1/integrations?workspaceId=${ws}`),
    api.get<{ status?: string; latencyMs?: number }>(`/v1/providers/health`),
  ])
  const cons = integ.ok ? integ.data.connections || [] : []

  // Specific access questions get a specific, truthful answer.
  if (integ.ok && mentions(question, ' email', ' e-mail', ' mailbox', ' inbox')) {
    return accessAnswer(cons, 'email', 'mail', 'imap', 'smtp', 'gmail', 'outlook', 'inbox')
  }
  if (integ.ok && mentions(question, ' calendar')) {
    return accessAnswer(cons, 'calendar', 'calendar', 'google', 'm365', 'outlook')
  }

  const parts: string[] = []
  if (integ.ok) {
    parts.push(cons.length
      ? `Connected: ${cons.map((c) => `${c.name || c.provider} (${c.status || 'unknown'})`).join(', ')}.`
      : 'No integrations are connected yet. Add one in Settings → Integrations.')
  } else {
    parts.push(`I couldn't read integrations (${integ.error}).`)
  }
  if (health.ok) {
    parts.push(`AI provider: ${health.data.status || 'unknown'}${health.data.latencyMs ? ` (~${health.data.latencyMs}ms)` : ''}.`)
  } else {
    parts.push(`AI provider health is unavailable (${health.error}).`)
  }
  return { text: parts.join(' ') }
}

async function answerApprovals(): Promise<AssistantReply> {
  const ws = workspaceId()
  const res = await api.get<{ pending?: number; total?: number }>(`/v1/approvals/summary?workspaceId=${ws}`)
  if (!res.ok) {
    return { text: `I couldn't reach the Approval Center (${res.error}).` }
  }
  const pending = res.data.pending ?? 0
  return pending > 0
    ? { text: `You have ${pending} item(s) awaiting approval.`, action: { kind: 'openApprovals' } }
    : { text: 'Nothing is waiting for your approval right now.' }
}

/** Answer a free-text question against real backend data. */
export async function askAssistant(q: string): Promise<AssistantReply> {
  const question = q.trim()
  if (!question) return { text: 'Ask me about today, your plan, projects, integrations, or approvals.' }
  switch (classifyIntent(question)) {
    case 'date':
      return { text: `Today is ${longDate()}.` }
    case 'plan':
      return answerPlan()
    case 'replan':
      return answerReplan(question)
    case 'integrations':
      return answerIntegrations(question)
    case 'approvals':
      return answerApprovals()
    case 'new_project':
      return { text: 'Opening the new-project wizard.', action: { kind: 'openProjectWizard' } }
    default:
      return {
        text:
          "I'm connected to your DayPilot workspace — I can answer about today's date, generate or adjust your plan, " +
          'check integration and AI-provider status, open the project wizard, or show what needs approval. ' +
          "I don't have information about that specific request.",
      }
  }
}
