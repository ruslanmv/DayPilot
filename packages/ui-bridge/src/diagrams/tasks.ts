/**
 * Tasks on a map (batch C4): per-topic status, dates and owner, a work breakdown taken from the
 * map's own structure, a dependency-aware schedule and the rows a Gantt chart needs. Pure and
 * deterministic: no AI is needed (AI can improve wording through the normal proposal flow).
 */
import { clone, type Diagram, type DiagramNode } from './dmind'

export type TaskStatus = 'todo' | 'doing' | 'done'
export type Priority = 'low' | 'medium' | 'high'
export type TaskInfo = { status: TaskStatus; start?: string; days?: number; owner?: string; priority?: Priority }
export const STATUSES: TaskStatus[] = ['todo', 'doing', 'done']
export const PRIORITIES: Priority[] = ['low', 'medium', 'high']
export const MAX_DAYS = 3650
export const MAX_TASKS = 500

const DAY_MS = 86_400_000
const DATE = /^\d{4}-\d{2}-\d{2}$/

/** Day number for a calendar date, or null when it is not a real date (2026-02-30 is not). */
export function dayNumber(date: string): number | null {
  if (!DATE.test(date)) return null
  const ms = Date.parse(date + 'T00:00:00Z')
  if (!Number.isFinite(ms)) return null
  const back = new Date(ms).toISOString().slice(0, 10)
  const year = Number(date.slice(0, 4))
  return back === date && year >= 1970 && year <= 2200 ? Math.round(ms / DAY_MS) : null
}
export const dateOf = (n: number): string => new Date(n * DAY_MS).toISOString().slice(0, 10)

export function readTask(node: DiagramNode): TaskInfo | null {
  const raw = node.metadata?.task as Partial<TaskInfo> | undefined
  if (!raw || typeof raw !== 'object') return null
  const info: TaskInfo = { status: STATUSES.includes(raw.status as TaskStatus) ? (raw.status as TaskStatus) : 'todo' }
  if (typeof raw.start === 'string' && dayNumber(raw.start) !== null) info.start = raw.start
  if (Number.isInteger(raw.days) && raw.days! >= 1 && raw.days! <= MAX_DAYS) info.days = raw.days
  if (typeof raw.owner === 'string' && raw.owner.trim()) info.owner = raw.owner.trim().slice(0, 80)
  if (PRIORITIES.includes(raw.priority as Priority)) info.priority = raw.priority
  return info
}

/** Set (or with `null` clear) a topic's task. Throws a readable error for bad dates or sizes. */
export function setTask(d: Diagram, id: string, task: TaskInfo | null): Diagram {
  if (!d.nodes.some((n) => n.id === id)) throw new Error('No such topic')
  if (task) {
    if (!STATUSES.includes(task.status)) throw new Error('Status must be todo, doing or done')
    if (task.start !== undefined && dayNumber(task.start) === null) throw new Error('Start must be a real date (YYYY-MM-DD)')
    if (task.days !== undefined && (!Number.isInteger(task.days) || task.days < 1 || task.days > MAX_DAYS)) throw new Error(`Days must be a whole number from 1 to ${MAX_DAYS}`)
    if (task.owner !== undefined && task.owner.length > 80) throw new Error('Owner is limited to 80 characters')
    if (task.priority !== undefined && !PRIORITIES.includes(task.priority)) throw new Error('Priority must be low, medium or high')
    if (d.nodes.filter((n) => readTask(n)).length >= MAX_TASKS && !readTask(d.nodes.find((n) => n.id === id)!))
      throw new Error(`At most ${MAX_TASKS} tasks per map`)
  }
  const out = clone(d)
  const node = out.nodes.find((n) => n.id === id)!
  const meta = { ...(node.metadata ?? {}) }
  if (task) meta.task = { ...task }
  else delete meta.task
  if (Object.keys(meta).length) node.metadata = meta
  else delete node.metadata
  return out
}

function hierarchy(d: Diagram) {
  const kind = d.kind === 'flowchart' ? 'flow' : 'branch'
  const parent = new Map<string, string>()
  const kids = new Map<string, string[]>()
  for (const e of d.edges)
    if (e.kind === kind && !parent.has(e.target)) {
      parent.set(e.target, e.source)
      kids.set(e.source, [...(kids.get(e.source) ?? []), e.target])
    }
  return { parent, kids }
}

export type Row = { id: string; label: string; path: string[]; phase: string }

/** The work in a map: its leaf topics in outline order, each with the path of topics above it. */
export function breakdown(d: Diagram): Row[] {
  const { parent, kids } = hierarchy(d)
  const byId = new Map(d.nodes.map((n) => [n.id, n]))
  const roots = d.nodes.filter((n) => !parent.has(n.id))
  const rows: Row[] = []
  const stack = roots.map((r) => r.id).reverse()
  const seen = new Set<string>()
  while (stack.length) {
    const id = stack.pop()!
    if (seen.has(id)) continue
    seen.add(id)
    const children = kids.get(id) ?? []
    if (!children.length && parent.has(id)) {
      const path: string[] = []
      for (let p = parent.get(id); p; p = parent.get(p)) path.unshift(byId.get(p)!.label)
      rows.push({ id, label: byId.get(id)!.label, path, phase: path[1] ?? path[0] ?? '' })
    }
    for (let i = children.length - 1; i >= 0; i--) stack.push(children[i])
  }
  return rows
}

/** Mark every leaf topic as a task (existing tasks are kept). Returns the new map and how many were added. */
export function makeTasks(d: Diagram, defaults: { days?: number } = {}): { diagram: Diagram; added: number } {
  const rows = breakdown(d).filter((r) => !readTask(d.nodes.find((n) => n.id === r.id)!))
  const room = MAX_TASKS - d.nodes.filter((n) => readTask(n)).length
  if (rows.length > room) throw new Error(`This would create ${rows.length} tasks; a map holds at most ${MAX_TASKS}.`)
  let out = d
  for (const r of rows) out = setTask(out, r.id, { status: 'todo', days: defaults.days ?? 2 })
  return { diagram: out, added: rows.length }
}

/** Predecessors of a task: `dependency` and `flow` links between task topics, source first. */
function predecessors(d: Diagram, ids: Set<string>): Map<string, string[]> {
  const out = new Map<string, string[]>()
  for (const e of d.edges)
    if ((e.kind === 'dependency' || e.kind === 'flow') && ids.has(e.source) && ids.has(e.target) && e.source !== e.target)
      out.set(e.target, [...(out.get(e.target) ?? []), e.source])
  return out
}

export class ScheduleError extends Error {}

/**
 * Give every task a start date. Tasks under the same phase (a child of the root) run in parallel,
 * phases run one after another, and a dependency link makes a task wait for the end of its
 * predecessors. A loop of dependencies cannot be scheduled and is reported by name.
 */
export function schedule(d: Diagram, projectStart: string): Diagram {
  const parsed = dayNumber(projectStart)
  if (parsed === null) throw new ScheduleError('Pick a real start date.')
  const base: number = parsed
  const tasks = d.nodes.filter((n) => readTask(n))
  if (!tasks.length) throw new ScheduleError('Mark some topics as tasks first.')
  const ids = new Set(tasks.map((t) => t.id))
  const info = new Map(tasks.map((t) => [t.id, readTask(t)!]))
  const { parent } = hierarchy(d)
  const phaseOf = (id: string): string => {
    let cur = id
    let prev = id
    while (parent.has(cur)) {
      prev = cur
      cur = parent.get(cur)!
    }
    return cur === id ? id : prev // the topic directly under the root
  }
  const phases: string[] = []
  tasks.forEach((t) => {
    const p = phaseOf(t.id)
    if (!phases.includes(p)) phases.push(p)
  })
  const pred = predecessors(d, ids)
  const start = new Map<string, number>()
  const end = new Map<string, number>()
  const state = new Map<string, 0 | 1 | 2>()
  const label = new Map(d.nodes.map((n) => [n.id, n.label]))

  function resolve(root: string) {
    // iterative post-order so a long chain cannot overflow the stack
    const stack: [string, number][] = [[root, 0]]
    while (stack.length) {
      const [id, i] = stack[stack.length - 1]
      if (i === 0) {
        if (state.get(id) === 2) {
          stack.pop()
          continue
        }
        if (state.get(id) === 1) throw new ScheduleError(`Tasks depend on each other in a loop through “${label.get(id)}”.`)
        state.set(id, 1)
      }
      const needs = pred.get(id) ?? []
      if (i < needs.length) {
        stack[stack.length - 1][1]++
        if (state.get(needs[i]) !== 2) stack.push([needs[i], 0])
        continue
      }
      const given = info.get(id)!.start
      let s = given ? dayNumber(given)! : base + (phaseIndexStart.get(phaseOf(id)) ?? 0)
      for (const p of needs) s = Math.max(s, end.get(p)!)
      start.set(id, s)
      end.set(id, s + (info.get(id)!.days ?? 1))
      state.set(id, 2)
      stack.pop()
    }
  }
  // Phase offsets: each phase begins when the previous one's tasks (without explicit starts) end.
  const phaseIndexStart = new Map<string, number>()
  let cursor = 0
  for (const ph of phases) {
    phaseIndexStart.set(ph, cursor)
    let longest = 0
    for (const t of tasks) if (phaseOf(t.id) === ph) longest = Math.max(longest, info.get(t.id)!.days ?? 1)
    cursor += longest
  }
  tasks.forEach((t) => resolve(t.id))
  let out = d
  for (const t of tasks) out = setTask(out, t.id, { ...info.get(t.id)!, start: dateOf(start.get(t.id)!), days: info.get(t.id)!.days ?? 1 })
  return out
}

export type GanttRow = {
  id: string
  label: string
  status: TaskStatus
  start: number
  end: number // exclusive
  owner?: string
  waitsFor: string[]
}
export type Gantt = { rows: GanttRow[]; first: number; last: number; unscheduled: string[] }

export function gantt(d: Diagram): Gantt {
  const tasks = d.nodes.filter((n) => readTask(n))
  const ids = new Set(tasks.map((t) => t.id))
  const pred = predecessors(d, ids)
  const rows: GanttRow[] = []
  const unscheduled: string[] = []
  for (const t of tasks) {
    const info = readTask(t)!
    if (!info.start) {
      unscheduled.push(t.id)
      continue
    }
    const s = dayNumber(info.start)!
    rows.push({ id: t.id, label: t.label, status: info.status, start: s, end: s + (info.days ?? 1), owner: info.owner, waitsFor: pred.get(t.id) ?? [] })
  }
  rows.sort((a, b) => a.start - b.start || a.end - b.end)
  return { rows, first: rows.length ? Math.min(...rows.map((r) => r.start)) : 0, last: rows.length ? Math.max(...rows.map((r) => r.end)) : 0, unscheduled }
}

export function progress(d: Diagram): { total: number; done: number; doing: number; percent: number } {
  const all = d.nodes.map(readTask).filter((t): t is TaskInfo => !!t)
  const done = all.filter((t) => t.status === 'done').length
  return { total: all.length, done, doing: all.filter((t) => t.status === 'doing').length, percent: all.length ? Math.round((done / all.length) * 100) : 0 }
}

/** What would be sent to the task list: open tasks only, with their path as context. */
export function exportable(d: Diagram): { id: string; title: string; context: string; due: string | null; owner: string | null; priority: Priority }[] {
  const { parent } = hierarchy(d)
  const byId = new Map(d.nodes.map((n) => [n.id, n]))
  return d.nodes.flatMap((n) => {
    const t = readTask(n)
    if (!t || t.status === 'done') return []
    const path: string[] = []
    for (let p = parent.get(n.id); p; p = parent.get(p)) path.unshift(byId.get(p)!.label)
    const due = t.start ? dateOf(dayNumber(t.start)! + (t.days ?? 1) - 1) : null
    return [{ id: n.id, title: n.label, context: [...path, n.notes ?? ''].filter(Boolean).join(' › ').slice(0, 2000), due, owner: t.owner ?? null, priority: t.priority ?? 'medium' }]
  })
}
