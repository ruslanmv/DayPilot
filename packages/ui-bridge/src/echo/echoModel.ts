/**
 * Echo Show display mode — the pure part.
 *
 * The Echo dashboard is a wall/kitchen display that people read from across a
 * room and trust at a glance. So the rules that decide what it says — which
 * failure a request ran into, when to retry, which events are "today", which
 * tasks count as blocked — are pure functions with type-only imports, tested
 * directly (tests/test_echo_model.py), not through a browser.
 *
 * Nothing here invents data: every number the dashboard shows is derived from
 * an API response, and every empty or failed state says so in words.
 */
import type { DayPilotProject, DayPilotTask } from '@daypilot/shared-types'

// ---------------------------------------------------------------- sections

export type EchoSection = 'today' | 'calendar' | 'tasks' | 'projects' | 'assistant' | 'agents' | 'approvals'

export const ECHO_SECTIONS: { id: EchoSection; label: string }[] = [
  { id: 'today', label: 'Today' },
  { id: 'calendar', label: 'Calendar' },
  { id: 'tasks', label: 'Tasks' },
  { id: 'projects', label: 'Projects' },
  { id: 'assistant', label: 'Assistant' },
  { id: 'agents', label: 'Agents' },
  { id: 'approvals', label: 'Approvals' },
]

/** `#/approvals` → 'approvals'. Anything unknown opens Today, never a blank page. */
export function parseEchoHash(hash: string): EchoSection {
  const id = (hash || '').replace(/^#\/?/, '').split(/[/?]/)[0]
  return ECHO_SECTIONS.some((s) => s.id === id) ? (id as EchoSection) : 'today'
}

export function echoHash(section: EchoSection): string {
  return `#/${section}`
}

// ---------------------------------------------------------------- failures

export type FailureKind =
  | 'offline'      // the device has no network
  | 'unreachable'  // network up, DayPilot did not answer
  | 'timeout'      // DayPilot answered too slowly
  | 'auth'         // the session ended (401)
  | 'forbidden'    // the signed-in role may not see or do this (403)
  | 'not_found'    // 404 — meaning depends on the endpoint
  | 'conflict'     // 409 — e.g. an approval someone already decided
  | 'misrouted'    // an HTML page came back: /api does not reach the gateway
  | 'server'       // 5xx
  | 'error'

export type EchoFailure = { kind: FailureKind; status?: number; detail: string }

/** Turn an `api` failure into something the dashboard can explain and act on. */
export function classifyFailure(
  r: { error: string; status?: number },
  ctx: { online: boolean; timedOut?: boolean },
): EchoFailure {
  const detail = r.error || 'error'
  if (ctx.timedOut) return { kind: 'timeout', detail }
  if (detail === 'gateway_html_response') return { kind: 'misrouted', status: r.status, detail }
  const s = r.status
  if (s === undefined || s === 0) return { kind: ctx.online ? 'unreachable' : 'offline', detail }
  if (s === 401) return { kind: 'auth', status: s, detail }
  if (s === 403) return { kind: 'forbidden', status: s, detail }
  if (s === 404) return { kind: 'not_found', status: s, detail }
  if (s === 409) return { kind: 'conflict', status: s, detail }
  if (s >= 500) return { kind: 'server', status: s, detail }
  return { kind: 'error', status: s, detail }
}

/** One calm sentence per failure. A server's own explanation is kept for 403/409. */
export function failureText(f: EchoFailure): string {
  switch (f.kind) {
    case 'offline': return 'This device is offline.'
    case 'unreachable': return 'DayPilot is not responding.'
    case 'timeout': return 'DayPilot took too long to answer.'
    case 'auth': return 'Your session has ended. Sign in again.'
    case 'forbidden': return f.detail && !/^HTTP \d+$/.test(f.detail) ? f.detail : 'Your role does not allow this.'
    case 'not_found': return 'Not available on this server.'
    case 'conflict': return f.detail && !/^HTTP \d+$/.test(f.detail) ? f.detail : 'This changed elsewhere.'
    case 'misrouted': return 'The DayPilot API is not reachable at this address.'
    case 'server': return `DayPilot had a problem (HTTP ${f.status}).`
    default: return 'Something went wrong.'
  }
}

/** Failures worth retrying on a timer. A 401/403/404 will not fix itself. */
export function isRetryable(f: EchoFailure): boolean {
  return ['offline', 'unreachable', 'timeout', 'server', 'misrouted', 'error'].includes(f.kind)
}

// ---------------------------------------------------------------- timing

export const ECHO_TIMING = {
  /** Today, the plan and approvals: what changes during a day. */
  liveMs: 60_000,
  /** Tasks, projects, calendar, agents, assistant availability. */
  slowMs: 300_000,
  /** After this long without a touch the live tier slows to `slowMs`. */
  idleAfterMs: 30 * 60_000,
  /** A request that has not answered by now is abandoned and retried. */
  timeoutMs: 15_000,
  /** First retry after a failure; doubles per failure up to `maxBackoffMs`. */
  retryBaseMs: 15_000,
  maxBackoffMs: 300_000,
} as const

/** 15 s, 30 s, 60 s, 120 s, 240 s, 300 s, 300 s … — never a tight loop. */
export function retryDelay(failures: number, baseMs: number = ECHO_TIMING.retryBaseMs, maxMs: number = ECHO_TIMING.maxBackoffMs): number {
  if (failures <= 0) return baseMs
  return Math.min(maxMs, baseMs * 2 ** (failures - 1))
}

/** How long until the next refresh of a tier, given its last outcome. */
export function nextRefreshIn(tier: 'live' | 'slow', failures: number, idle: boolean): number {
  if (failures > 0) return retryDelay(failures)
  if (tier === 'live' && !idle) return ECHO_TIMING.liveMs
  return ECHO_TIMING.slowMs
}

export function msToNextMinute(now: Date): number {
  return 60_000 - (now.getSeconds() * 1000 + now.getMilliseconds()) + 50
}

// ---------------------------------------------------------------- clock & copy

export function greeting(now: Date, name?: string | null): string {
  const h = now.getHours()
  const part = h >= 5 && h < 12 ? 'Good morning' : h >= 12 && h < 18 ? 'Good afternoon' : 'Good evening'
  const first = (name || '').trim().split(/\s+/)[0]
  return first ? `${part}, ${first}` : part
}

export function clockText(now: Date, locale?: string): { time: string; date: string } {
  return {
    time: new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit' }).format(now),
    date: new Intl.DateTimeFormat(locale, { weekday: 'long', day: 'numeric', month: 'long' }).format(now),
  }
}

/** "Updated just now" / "Updated 4 min ago" / "Updated at 09:12". */
export function updatedLabel(at: number | null | undefined, now: number, locale?: string): string {
  if (!at) return 'Not loaded yet'
  const s = Math.max(0, Math.round((now - at) / 1000))
  if (s < 45) return 'Updated just now'
  const m = Math.round(s / 60)
  if (m < 60) return `Updated ${m} min ago`
  return `Updated at ${new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit' }).format(new Date(at))}`
}

// ---------------------------------------------------------------- calendar

export type CalendarEventDTO = {
  id: string
  title: string
  startAt?: string | null
  endAt?: string | null
  status?: string | null
}

export type EchoEvent = {
  id: string
  title: string
  start: Date
  end: Date | null
  allDay: boolean
  isNow: boolean
  isPast: boolean
  conflict: boolean
  tentative: boolean
}

/** ISO from the API. A time without an offset is the user's wall-clock time. */
export function parseWhen(iso?: string | null): Date | null {
  if (!iso) return null
  const d = new Date(/^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T00:00:00` : iso)
  return Number.isNaN(d.getTime()) ? null : d
}

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n)
}

function toEchoEvent(e: CalendarEventDTO, start: Date, end: Date | null, now: Date, conflictIds: Set<string>): EchoEvent {
  const allDay = /^\d{4}-\d{2}-\d{2}$/.test(e.startAt || '') ||
    (start.getHours() === 0 && start.getMinutes() === 0 && !!end && end.getTime() - start.getTime() >= 86_400_000)
  return {
    id: e.id,
    title: e.title || 'Untitled event',
    start,
    end,
    allDay,
    isNow: start <= now && (end ? end > now : false),
    isPast: (end || start) <= now,
    conflict: conflictIds.has(e.id),
    tentative: ['tentative', 'draft'].includes((e.status || '').toLowerCase()),
  }
}

/**
 * Events on `day` (local), in order. Cancelled events are dropped — showing a
 * meeting that is not happening is exactly the false data this display must
 * not show. A multi-day event appears on each day it covers.
 */
export function eventsOnDay(
  events: CalendarEventDTO[],
  day: Date,
  now: Date,
  conflicts: Array<{ a: string; b: string }> = [],
): EchoEvent[] {
  const from = startOfDay(day)
  const to = addDays(from, 1)
  const conflictIds = new Set(conflicts.flatMap((c) => [c.a, c.b]))
  const out: EchoEvent[] = []
  for (const e of events) {
    if ((e.status || '').toLowerCase() === 'cancelled') continue
    const start = parseWhen(e.startAt)
    if (!start) continue
    const end = parseWhen(e.endAt)
    const overlaps = start < to && (end ? end > from : start >= from)
    if (overlaps) out.push(toEchoEvent(e, start, end, now, conflictIds))
  }
  return out.sort((a, b) => Number(b.allDay) - Number(a.allDay) || a.start.getTime() - b.start.getTime())
}

/** The next days that have events, after today. */
export function upcomingDays(
  events: CalendarEventDTO[],
  now: Date,
  days = 6,
): Array<{ day: Date; events: EchoEvent[] }> {
  const out: Array<{ day: Date; events: EchoEvent[] }> = []
  for (let i = 1; i <= days; i++) {
    const day = addDays(startOfDay(now), i)
    const list = eventsOnDay(events, day, now)
    if (list.length) out.push({ day, events: list })
  }
  return out
}

export function eventTime(e: EchoEvent, locale?: string): string {
  if (e.allDay) return 'All day'
  const f = new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit' })
  return e.end ? `${f.format(e.start)} – ${f.format(e.end)}` : f.format(e.start)
}

// ---------------------------------------------------------------- tasks

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export function weekdayName(d: Date): string {
  return WEEKDAYS[(d.getDay() + 6) % 7]
}

export type TaskGroups = {
  open: number
  blocked: DayPilotTask[]
  needsApproval: DayPilotTask[]
  inProgress: DayPilotTask[]
  today: DayPilotTask[]
  later: DayPilotTask[]
}

const PRIORITY_RANK: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 }

function byTimeThenPriority(a: DayPilotTask, b: DayPilotTask): number {
  return (a.start || '99:99').localeCompare(b.start || '99:99') ||
    (PRIORITY_RANK[a.priority] ?? 9) - (PRIORITY_RANK[b.priority] ?? 9)
}

/**
 * Open tasks, each in exactly one group, most urgent group first. "Blocked"
 * means `status === 'blocked'` — the same rule as the server's blocker count
 * on `/v1/today`, so the tile and the list can never disagree.
 */
export function groupTasks(tasks: DayPilotTask[], now: Date): TaskGroups {
  const today = weekdayName(now)
  const g: TaskGroups = { open: 0, blocked: [], needsApproval: [], inProgress: [], today: [], later: [] }
  for (const t of tasks) {
    if (t.status === 'done') continue
    g.open++
    if (t.status === 'blocked') g.blocked.push(t)
    else if (t.status === 'needs_approval') g.needsApproval.push(t)
    else if (t.status === 'active' || t.status === 'running') g.inProgress.push(t)
    else if (t.day === today) g.today.push(t)
    else g.later.push(t)
  }
  for (const list of [g.blocked, g.needsApproval, g.inProgress, g.today, g.later]) list.sort(byTimeThenPriority)
  return g
}

// ---------------------------------------------------------------- projects

const RISK_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 }

/** Riskiest first. "Needs attention" is `risk !== 'low'`, as on the server. */
export function rankProjects(projects: DayPilotProject[]): DayPilotProject[] {
  return projects.slice().sort((a, b) =>
    (RISK_RANK[a.risk] ?? 0) - (RISK_RANK[b.risk] ?? 0) || a.name.localeCompare(b.name))
}

export function needsAttention(p: DayPilotProject): boolean {
  return (p.risk || 'low') !== 'low'
}

// ---------------------------------------------------------------- agents

export type AgentRunDTO = {
  id: string
  name: string
  agentKind?: string | null
  currentWork?: string | null
  state?: string | null
  status?: string | null
  provider?: string | null
  model?: string | null
  lastError?: string | null
  projectId?: string | null
  updatedAt?: string | null
}

/** Running = `state === 'running'`, matching the server's "AI running" count. */
export function splitRuns(runs: AgentRunDTO[]): { running: AgentRunDTO[]; attention: AgentRunDTO[]; recent: AgentRunDTO[] } {
  const running: AgentRunDTO[] = []
  const attention: AgentRunDTO[] = []
  const recent: AgentRunDTO[] = []
  for (const r of runs) {
    const state = (r.state || '').toLowerCase()
    if (state === 'running') running.push(r)
    else if (state === 'failed' || /approval|blocked/i.test(r.status || '')) attention.push(r)
    else recent.push(r)
  }
  return { running, attention, recent }
}

// ---------------------------------------------------------------- change detection

/** Skip a re-render when a refresh returned exactly what is already shown. */
export function sameData(a: unknown, b: unknown): boolean {
  if (a === b) return true
  try {
    return JSON.stringify(a) === JSON.stringify(b)
  } catch {
    return false
  }
}
