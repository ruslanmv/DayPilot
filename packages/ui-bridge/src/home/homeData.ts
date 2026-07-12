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

export const NEXT_PRIORITY = {
  title: 'Continue DayPilot UI implementation',
  project: 'DayPilot Portal',
  time: '08:30 – 12:00',
  support: 'The email workspace structure is approved. Continue implementing dark-mode details.',
}

export const TODAY_PLAN: AgendaItem[] = [
  { time: '08:30', title: 'Daily plan review', tag: 'Calendar' },
  { time: '10:00', title: 'DayPilot email workspace', tag: 'Focus', end: '10:00 – 12:00' },
  { time: '13:00', title: 'GitPilot patch review', tag: 'Project' },
  { time: '15:30', title: 'Client Alpha follow-up', tag: 'Email' },
  { time: '17:00', title: 'Risk alignment', tag: 'Meeting' },
]

export const CONTINUE_ITEMS: ContinueItem[] = [
  {
    id: 'c1', icon: '📄', name: 'DayPilot Portal', status: 'Email workspace structure approved',
    next: 'Implement dark-mode details', progress: 76, accent: 'green',
  },
  {
    id: 'c2', icon: '⟨⟩', name: 'GitPilot Connector', status: 'Tests still failing',
    next: 'Review authentication boundary', progress: 32, accent: 'purple',
  },
]

export type HomeTurn = { role: 'user' | 'assistant'; body: string; time?: string; action?: { label: string; target: string } }

export const AI_WELCOME =
  'Good morning, Ruslan.\nHere’s your plan for today.'

export const AI_PLAN_BULLETS = [
  'Continue DayPilot UI implementation',
  'Review GitPilot patch',
  'Matrix Designer feedback',
  'Client Alpha follow-up',
]

export const AI_SEED: HomeTurn[] = [
  { role: 'user', body: "What's the status of the email workspace implementation?", time: '10:28 AM' },
  {
    role: 'assistant',
    body: 'The email workspace structure is complete. Dark-mode details are in progress. 32 of 42 tasks completed (76%). Would you like me to open the project?',
    time: '10:28 AM',
  },
  { role: 'user', body: 'Yes, open it please.', time: '10:29 AM' },
  { role: 'assistant', body: 'Opening DayPilot Portal project…', time: '10:29 AM', action: { label: 'Open in Projects', target: 'projects' } },
]

export const HOME_SUGGESTIONS = [
  { label: 'Move admin work to afternoon', icon: '◷' },
  { label: 'Prepare for Client Alpha meeting', icon: '⌘' },
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
