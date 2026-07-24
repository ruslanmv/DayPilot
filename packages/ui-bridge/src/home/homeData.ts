import { isDemoMode } from '../env'

export type AgendaItem = { time: string; title: string; tag: string; end?: string }
export type ContinueItem = {
  id: string
  icon: string
  name: string
  status: string
  next: string
  progress: number
  accent: 'blue' | 'purple' | 'green'
}

type NextPriority = { title: string; project: string; time: string; support: string } | null

const DEMO_NEXT_PRIORITY: NextPriority = {
  title: 'Continue DayPilot UI implementation',
  project: 'DayPilot Portal',
  time: '08:30 – 12:00',
  support: 'The email workspace structure is approved. Continue implementing dark-mode details.',
}

const DEMO_TODAY_PLAN: AgendaItem[] = [
  { time: '08:30', title: 'Daily plan review', tag: 'Calendar' },
  { time: '10:00', title: 'DayPilot email workspace', tag: 'Focus', end: '10:00 – 12:00' },
  { time: '13:00', title: 'GitPilot patch review', tag: 'Project' },
  { time: '15:30', title: 'Client Alpha follow-up', tag: 'Email' },
  { time: '17:00', title: 'Risk alignment', tag: 'Meeting' },
]

const DEMO_CONTINUE_ITEMS: ContinueItem[] = [
  {
    id: 'c1', icon: '📄', name: 'DayPilot Portal', status: 'Email workspace structure approved',
    next: 'Implement dark-mode details', progress: 76, accent: 'green',
  },
  {
    id: 'c2', icon: '⟨⟩', name: 'GitPilot Connector', status: 'Tests still failing',
    next: 'Review authentication boundary', progress: 32, accent: 'purple',
  },
]

// Clean-data by default: the Home surface starts empty and fills from real
// plans/projects. Sample content only appears in demo mode.
export const NEXT_PRIORITY: NextPriority = isDemoMode() ? DEMO_NEXT_PRIORITY : null
export const TODAY_PLAN: AgendaItem[] = isDemoMode() ? DEMO_TODAY_PLAN : []
export const CONTINUE_ITEMS: ContinueItem[] = isDemoMode() ? DEMO_CONTINUE_ITEMS : []

// --- Needs your attention (a decision queue, not an analytics panel) ---------
export type AttentionItem = {
  id: string
  kind: 'approvals' | 'blocked' | 'integration'
  count: number
  label: string
  detail: string
}

const DEMO_ATTENTION: AttentionItem[] = [
  { id: 'a1', kind: 'approvals', count: 2, label: 'Approvals', detail: 'Awaiting your review' },
  { id: 'a2', kind: 'blocked', count: 1, label: 'Blocked work', detail: 'Needs your input' },
  { id: 'a3', kind: 'integration', count: 1, label: 'Integration issue', detail: 'GitPilot auth boundary' },
]

export const ATTENTION_ITEMS: AttentionItem[] = isDemoMode() ? DEMO_ATTENTION : []

// --- AI working now (observable background agents) ---------------------------
export type WorkingAgent = { id: string; name: string; activity: string; accent: 'blue' | 'purple' | 'green' }

const DEMO_AGENTS: WorkingAgent[] = [
  { id: 'g1', name: 'Project Analyst', activity: 'Analyzing delivery risks', accent: 'blue' },
  { id: 'g2', name: 'GitPilot', activity: 'Running test suite', accent: 'purple' },
  { id: 'g3', name: 'Email Sentinel', activity: 'Scanning for issues', accent: 'green' },
]

export const WORKING_AGENTS: WorkingAgent[] = isDemoMode() ? DEMO_AGENTS : []

/** Time-of-day greeting for the Home header. */
export function greeting(name?: string): string {
  const h = new Date().getHours()
  const part = h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
  const first = (name || '').trim().split(/\s+/)[0]
  return first ? `${part}, ${first}` : part
}

export function longDate(): string {
  return new Date().toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })
}

export function clockTime(): string {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export type HomeTurn = { role: 'user' | 'assistant'; body: string; time?: string; action?: { label: string; target: string } }

// The assistant does not fabricate a plan on load. In demo mode it shows a
// sample greeting; in clean mode it opens with a neutral, honest prompt.
export const AI_WELCOME = isDemoMode()
  ? 'Good morning.\nHere’s your plan for today.'
  : 'Hi — I’m connected to your DayPilot workspace. Ask me about today, your plan, projects, or integration status.'

export const AI_PLAN_BULLETS: string[] = isDemoMode()
  ? ['Continue DayPilot UI implementation', 'Review GitPilot patch', 'Matrix Designer feedback', 'Client Alpha follow-up']
  : []

export const AI_SEED: HomeTurn[] = isDemoMode()
  ? [
      { role: 'user', body: "What's the status of the email workspace implementation?", time: '10:28 AM' },
      {
        role: 'assistant',
        body: 'The email workspace structure is complete. Dark-mode details are in progress. 32 of 42 tasks completed (76%). Would you like me to open the project?',
        time: '10:28 AM',
      },
      { role: 'user', body: 'Yes, open it please.', time: '10:29 AM' },
      { role: 'assistant', body: 'Opening DayPilot Portal project…', time: '10:29 AM', action: { label: 'Open in Projects', target: 'projects' } },
    ]
  : []

export const HOME_SUGGESTIONS = [
  { label: 'What day is it today?', icon: '📅' },
  { label: "Generate today's plan", icon: '◷' },
  { label: 'Check integration status', icon: '⚙' },
  { label: 'Show what needs approval', icon: '✓' },
]

/** Deterministic, offline-safe assistant reply used by the Home AI panel and the
 *  full-screen mobile chat so both surfaces behave identically. */
export function aiReply(q: string): string {
  const l = q.toLowerCase()
  if (l.includes('approv')) return 'You have 3 items awaiting approval: a GitPilot patch, an email reply, and a calendar change. Open the Approval Center to review them.'
  if (l.includes('client alpha') || l.includes('meeting')) return "I've gathered the Client Alpha thread, the revised timeline, and the open risks. Want me to draft a short agenda?"
  if (l.includes('admin') || l.includes('afternoon')) return "I've moved your admin blocks to the afternoon and protected the morning for deep work. Review the updated plan?"
  return "Here's what I can do: continue a project, prepare a meeting, draft a reply, or show what needs approval. Which would you like?"
}
