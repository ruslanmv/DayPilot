export type BlockKind = 'deep' | 'meeting' | 'admin' | 'review' | 'break'

export type PlanUIBlock = {
  id: string
  title: string
  kind: BlockKind
  start: string // "HH:MM"
  end: string
  status: 'scheduled' | 'done' | 'focus'
}

export const KIND_LABEL: Record<BlockKind, string> = {
  deep: 'Deep work',
  meeting: 'Meeting',
  review: 'Review',
  admin: 'Admin',
  break: 'Break',
}

/** The optimized day the multi-agent planner produced (demo data mirroring the
 *  backend: deep work mornings, meetings after lunch, admin last, lunch kept). */
export const INITIAL_PLAN: PlanUIBlock[] = [
  { id: 'b1', title: 'Implement routing failover', kind: 'deep', start: '08:30', end: '10:00', status: 'scheduled' },
  { id: 'b2', title: 'Design eval harness architecture', kind: 'deep', start: '10:15', end: '11:45', status: 'scheduled' },
  { id: 'b3', title: 'Lunch & recharge', kind: 'break', start: '12:30', end: '13:15', status: 'scheduled' },
  { id: 'b4', title: 'Client Alpha sync meeting', kind: 'meeting', start: '13:15', end: '14:00', status: 'scheduled' },
  { id: 'b5', title: 'Review GitPilot patch', kind: 'review', start: '14:15', end: '15:00', status: 'scheduled' },
  { id: 'b6', title: '1:1 with platform team', kind: 'meeting', start: '15:15', end: '16:00', status: 'scheduled' },
  { id: 'b7', title: 'Email triage & expense report', kind: 'admin', start: '16:15', end: '16:45', status: 'scheduled' },
]

export const INITIAL_SCORE = 84
export const INITIAL_FOCUS_MINUTES = 180

export type PlanTurn = { role: 'user' | 'assistant'; body: string }

export const PLAN_CHAT_SEED: PlanTurn[] = [
  {
    role: 'assistant',
    body: 'Your day is optimized: 2 deep-work blocks (180 focused minutes) protected in the morning, meetings batched after lunch, admin closed out at the end. Plan score 84/100. Ask me to move things or replan.',
  },
]

export const PLAN_SUGGESTIONS = [
  'Move admin to the end of the day',
  'Protect my morning for deep work',
  'How much focus time do I have?',
]

export function minutesOf(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}
