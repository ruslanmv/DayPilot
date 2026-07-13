/**
 * Data + geometry for the Minute Plan calendar.
 *
 * Everything is minute-based so events, slot lines, and the current-time
 * indicator all position from the same math (no hard-coded pixel offsets).
 * A calendar-shaped demo dataset (gated behind demo mode) reproduces the
 * approved reference design; in clean mode the grid renders real tasks and is
 * otherwise an empty, professional day/week timetable with the live time line.
 */
import type { DayPilotTask } from '@daypilot/shared-types'
import { isDemoMode } from '../env'

export type CalCategory = 'calendar' | 'deep' | 'review' | 'meeting' | 'personal'
export type CalStatus = 'confirmed' | 'pending' | 'none'

export type CalEvent = {
  id: string
  title: string
  dayIndex: number // 0 = Monday … 6 = Sunday
  start: string // "HH:MM"
  end: string
  owner?: string
  source?: string
  category: CalCategory
  status?: CalStatus
  allDay?: boolean
  task?: DayPilotTask
}

// ---- geometry ---------------------------------------------------------------

export const DAY_START_MIN = 8 * 60 // 08:00
export const DAY_END_MIN = 18 * 60 // 18:00
export const SLOT_MIN = 30
export const SLOT_HEIGHT = 48
export const PX_PER_MIN = SLOT_HEIGHT / SLOT_MIN
export const GRID_HEIGHT = ((DAY_END_MIN - DAY_START_MIN) / SLOT_MIN) * SLOT_HEIGHT

export function minutesOf(hhmm: string): number {
  const [h, m] = hhmm.split(':')
  return Number(h) * 60 + Number(m)
}

export function topPx(startMin: number): number {
  return ((startMin - DAY_START_MIN) / SLOT_MIN) * SLOT_HEIGHT
}

export function heightPx(startMin: number, endMin: number): number {
  return Math.max(((endMin - startMin) / SLOT_MIN) * SLOT_HEIGHT, 22)
}

/** Slot labels for the time gutter (08:00 … 17:30). */
export function slotLabels(): { min: number; label: string; hour: boolean }[] {
  const out: { min: number; label: string; hour: boolean }[] = []
  for (let m = DAY_START_MIN; m < DAY_END_MIN; m += SLOT_MIN) {
    const hh = String(Math.floor(m / 60)).padStart(2, '0')
    const mm = String(m % 60).padStart(2, '0')
    out.push({ min: m, label: `${hh}:${mm}`, hour: m % 60 === 0 })
  }
  return out
}

// ---- week dates -------------------------------------------------------------

const WEEKDAY_INDEX: Record<string, number> = {
  Monday: 0, Tuesday: 1, Wednesday: 2, Thursday: 3, Friday: 4, Saturday: 5, Sunday: 6,
}
const WEEKDAY_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/** Monday-based index for a JS Date (0 = Mon … 6 = Sun). */
export function mondayIndex(d: Date): number {
  return (d.getDay() + 6) % 7
}

/** The seven dates of the week containing `ref`, Monday first. */
export function weekDates(ref: Date): { index: number; short: string; date: number; iso: string; isToday: boolean; weekend: boolean }[] {
  const monday = new Date(ref)
  monday.setDate(ref.getDate() - mondayIndex(ref))
  const today = new Date()
  const todayKey = today.toDateString()
  return WEEKDAY_SHORT.map((short, i) => {
    const d = new Date(monday)
    d.setDate(monday.getDate() + i)
    return {
      index: i,
      short,
      date: d.getDate(),
      iso: d.toISOString().slice(0, 10),
      isToday: d.toDateString() === todayKey,
      weekend: i >= 5,
    }
  })
}

// ---- category classification (real tasks) -----------------------------------

export function categorize(title: string): CalCategory {
  const t = title.toLowerCase()
  if (/(personal|lunch|recharge|break|off\b|out of office|ooo)/.test(t)) return 'personal'
  if (/(review|approv)/.test(t)) return 'review'
  if (/(meeting|sync|call|standup|1:1|interview|demo|team|client|stakeholder)/.test(t)) return 'meeting'
  if (/(deep|implement|build|code|refactor|write|research|prototype|architect|design work)/.test(t)) return 'deep'
  return 'calendar'
}

function ownerName(owner: string): string {
  return owner === 'you' ? 'You' : owner === 'ai' ? 'AI' : owner === 'team' ? 'Team' : owner === 'system' ? 'System' : owner
}

/** Map real DayPilot tasks onto calendar events (timed, this-week). */
export function tasksToEvents(tasks: DayPilotTask[]): CalEvent[] {
  return tasks
    .filter((t) => t.start && t.end && t.day in WEEKDAY_INDEX)
    .map((t) => ({
      id: t.id,
      title: t.title,
      dayIndex: WEEKDAY_INDEX[t.day],
      start: t.start,
      end: t.end,
      owner: ownerName(t.owner),
      source: t.source || t.executor,
      category: categorize(t.title),
      status: t.status === 'needs_approval' ? 'pending' : t.status === 'done' ? 'confirmed' : 'none',
      task: t,
    }))
}

// ---- overlap layout ---------------------------------------------------------

/** Assign each event a column within its overlap cluster so blocks sit
 *  side-by-side instead of covering one another. */
export function layoutColumns(events: CalEvent[]): Map<string, { col: number; cols: number }> {
  const result = new Map<string, { col: number; cols: number }>()
  const sorted = [...events].sort((a, b) => minutesOf(a.start) - minutesOf(b.start) || minutesOf(a.end) - minutesOf(b.end))

  let cluster: CalEvent[] = []
  let clusterEnd = -1
  const flush = () => {
    if (!cluster.length) return
    const colEnds: number[] = []
    const assigned: { e: CalEvent; col: number }[] = []
    for (const e of cluster) {
      const s = minutesOf(e.start)
      let col = colEnds.findIndex((end) => s >= end)
      if (col === -1) { col = colEnds.length; colEnds.push(0) }
      colEnds[col] = minutesOf(e.end)
      assigned.push({ e, col })
    }
    for (const { e, col } of assigned) result.set(e.id, { col, cols: colEnds.length })
    cluster = []
    clusterEnd = -1
  }
  for (const e of sorted) {
    if (cluster.length && minutesOf(e.start) >= clusterEnd) flush()
    cluster.push(e)
    clusterEnd = Math.max(clusterEnd, minutesOf(e.end))
  }
  flush()
  return result
}

// ---- demo dataset (gated) ---------------------------------------------------

const DEMO_TIMED: CalEvent[] = [
  // Mon
  { id: 'd-mon-1', title: 'Focus Block', dayIndex: 0, start: '09:00', end: '10:00', owner: 'You', source: 'Calendar', category: 'calendar', status: 'confirmed' },
  { id: 'd-mon-2', title: 'Project Review', dayIndex: 0, start: '11:00', end: '12:00', owner: 'Alex R.', source: 'Project Apollo', category: 'review', status: 'confirmed' },
  { id: 'd-mon-3', title: 'Deep Work', dayIndex: 0, start: '14:00', end: '15:30', owner: 'You', source: 'Tasks', category: 'deep', status: 'confirmed' },
  // Tue
  { id: 'd-tue-1', title: 'Team Sync', dayIndex: 1, start: '09:30', end: '10:15', owner: 'Team', source: 'Teams', category: 'meeting', status: 'confirmed' },
  { id: 'd-tue-2', title: 'Client Call', dayIndex: 1, start: '13:30', end: '14:30', owner: 'Jamie L.', source: 'Calendar', category: 'calendar', status: 'confirmed' },
  { id: 'd-tue-3', title: 'Design Review', dayIndex: 1, start: '16:00', end: '17:00', owner: 'Design', source: 'Figma', category: 'meeting', status: 'confirmed' },
  // Wed
  { id: 'd-wed-1', title: 'Deep Work', dayIndex: 2, start: '08:30', end: '10:00', owner: 'You', source: 'Tasks', category: 'deep', status: 'confirmed' },
  { id: 'd-wed-2', title: 'Client Call', dayIndex: 2, start: '11:00', end: '12:00', owner: 'Acme Corp', source: 'Zoom', category: 'calendar', status: 'confirmed' },
  { id: 'd-wed-3', title: 'Project Review', dayIndex: 2, start: '13:00', end: '14:00', owner: 'Alex R.', source: 'Project Apollo', category: 'review', status: 'confirmed' },
  { id: 'd-wed-4', title: 'Approval Review', dayIndex: 2, start: '15:00', end: '16:00', owner: 'You', source: 'Approvals', category: 'review', status: 'pending' },
  // Thu
  { id: 'd-thu-1', title: 'Focus Block', dayIndex: 3, start: '09:00', end: '10:00', owner: 'You', source: 'Calendar', category: 'calendar', status: 'confirmed' },
  { id: 'd-thu-2', title: 'Team Sync', dayIndex: 3, start: '11:00', end: '12:00', owner: 'Team', source: 'Teams', category: 'meeting', status: 'confirmed' },
  { id: 'd-thu-3', title: 'Deep Work', dayIndex: 3, start: '14:00', end: '15:30', owner: 'You', source: 'Tasks', category: 'deep', status: 'confirmed' },
  // Fri
  { id: 'd-fri-1', title: 'Project Review', dayIndex: 4, start: '10:00', end: '11:00', owner: 'Stakeholders', source: 'Conf Rm', category: 'review', status: 'confirmed' },
  { id: 'd-fri-2', title: 'Client Call', dayIndex: 4, start: '13:30', end: '14:30', owner: 'Beta Ltd', source: 'Zoom', category: 'calendar', status: 'confirmed' },
  { id: 'd-fri-3', title: 'Approval Review', dayIndex: 4, start: '15:30', end: '16:30', owner: 'You', source: 'Approvals', category: 'review', status: 'confirmed' },
  // Sun
  { id: 'd-sun-1', title: 'Personal Time', dayIndex: 6, start: '13:00', end: '15:00', owner: '', source: 'Calendar', category: 'personal', status: 'pending' },
]

const DEMO_ALLDAY: CalEvent[] = [
  { id: 'a-mon', title: 'Product Strategy Review', dayIndex: 0, start: '00:00', end: '00:00', category: 'calendar', allDay: true },
  { id: 'a-tue', title: 'Offsite Planning', dayIndex: 1, start: '00:00', end: '00:00', category: 'review', allDay: true },
  { id: 'a-wed', title: 'Board Prep', dayIndex: 2, start: '00:00', end: '00:00', category: 'deep', allDay: true },
  { id: 'a-fri', title: 'Release Candidate', dayIndex: 4, start: '00:00', end: '00:00', category: 'meeting', allDay: true },
  { id: 'a-sun', title: 'Personal', dayIndex: 6, start: '00:00', end: '00:00', category: 'personal', allDay: true },
]

export function calendarEvents(tasks: DayPilotTask[]): { timed: CalEvent[]; allDay: CalEvent[] } {
  if (isDemoMode()) return { timed: DEMO_TIMED, allDay: DEMO_ALLDAY }
  return { timed: tasksToEvents(tasks), allDay: [] }
}
