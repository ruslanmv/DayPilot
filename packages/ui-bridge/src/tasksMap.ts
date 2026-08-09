/**
 * Turning API tasks into the shell's task shape.
 *
 * The API and the shell disagree about several fields — `day` is a weekday
 * name here and was an ISO date in older rows, and owner/priority/status are
 * open strings on the wire but closed unions in the UI. Guessing wrong shows a
 * task under the wrong day or with no owner, so the rules are pure functions
 * with type-only imports and are tested directly.
 */
import type { DayPilotTask } from '@daypilot/shared-types'

export type ServerTask = {
  id: string
  title: string
  owner?: string
  executor?: string
  priority?: string
  status?: string
  day?: string | null
  start?: string | null
  end?: string | null
  context?: string | null
  source?: string | null
  confidence?: number | null
  risk?: string | null
  projectId?: string | null
  skipImpact?: string | null
  parallelAi?: string | null
  nextAction?: string | null
}

const WEEKDAYS: DayPilotTask['day'][] = [
  'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
]
const OWNERS: DayPilotTask['owner'][] = ['you', 'ai', 'team', 'system']
const PRIORITIES: DayPilotTask['priority'][] = ['critical', 'high', 'medium', 'low']
const STATUSES: DayPilotTask['status'][] = [
  'active', 'running', 'scheduled', 'blocked', 'done', 'needs_approval',
]

/** `Task.day` is a weekday name; today is the honest fallback for a task without one. */
export function toWeekday(day: string | null | undefined, now: Date = new Date()): DayPilotTask['day'] {
  const named = WEEKDAYS.find((d) => d.toLowerCase() === (day || '').toLowerCase())
  if (named) return named
  // An ISO date is also accepted — older rows stored one, and dropping such a
  // task out of the week entirely would be worse than placing it correctly.
  const parsed = day ? new Date(`${day}T12:00:00`) : null
  const source = parsed && !Number.isNaN(parsed.getTime()) ? parsed : now
  return WEEKDAYS[(source.getDay() + 6) % 7]
}

export function toDayPilotTask(t: ServerTask, now: Date = new Date()): DayPilotTask {
  const owner = (t.owner || 'you').toLowerCase() as DayPilotTask['owner']
  const priority = (t.priority || 'medium').toLowerCase() as DayPilotTask['priority']
  const status = (t.status || 'scheduled').toLowerCase() as DayPilotTask['status']
  return {
    id: t.id,
    title: t.title,
    day: toWeekday(t.day, now),
    start: t.start || '',
    end: t.end || '',
    owner: OWNERS.includes(owner) ? owner : 'you',
    executor: t.executor || '',
    priority: PRIORITIES.includes(priority) ? priority : 'medium',
    status: STATUSES.includes(status) ? status : 'scheduled',
    context: t.context || '',
    source: t.source || undefined,
    confidence: t.confidence ?? undefined,
    risk: (t.risk as DayPilotTask['risk']) || undefined,
    projectId: t.projectId || undefined,
    skipImpact: t.skipImpact || undefined,
    parallelAi: t.parallelAi || undefined,
    nextAction: t.nextAction || undefined,
  }
}

/**
 * What "start focus" should open.
 *
 * The block already running, otherwise the earliest thing still ahead. Picking
 * the first row of an arbitrary list would drop the user into whatever the API
 * happened to return first — often something already finished.
 */
export function focusCandidate(tasks: DayPilotTask[]): DayPilotTask | undefined {
  const open = tasks.filter((t) => t.status !== 'done')
  const running = open.find((t) => t.status === 'active' || t.status === 'running')
  if (running) return running
  const scheduled = open.filter((t) => t.start).sort((a, b) => a.start.localeCompare(b.start))
  return scheduled[0] || open[0]
}
