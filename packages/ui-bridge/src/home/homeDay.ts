/**
 * Home, from the real day — the pure part.
 *
 * Home's three main regions — Next priority, Today's plan, Continue from
 * yesterday — used to render from constants in `homeData.ts` that are empty
 * outside demo mode. The backend has produced this data since the Today engine
 * landed (`/v1/today`, `/v1/plans/{date}`, `/v1/continuity`); nothing was
 * reading it. So the first screen of a "connected to real data" product showed
 * either sample content or three empty cards.
 *
 * Everything here is a pure function of an API response, with type-only
 * imports, so the interesting decisions — which projects genuinely carried
 * something over, what a block is called, what to show when a task has no
 * scheduled time — are tested directly rather than through a browser.
 */
import type { AgendaItem, ContinueItem, NextPriority } from './homeData'

export type TodayTask = {
  id: string
  title: string
  owner?: string
  executor?: string
  priority?: string
  status?: string
  start?: string | null
  end?: string | null
  context?: string | null
  projectId?: string | null
  nextAction?: string | null
}

export type PlanBlockDTO = {
  id: string
  taskId?: string | null
  title: string
  start?: string | null
  end?: string | null
  owner?: string
  source?: string
  status?: string
  orderIndex?: number
}

export type ContinuityDTO = {
  projectId: string
  name: string
  risk?: string
  progress?: number
  yesterday?: string[]
  today?: string[]
  aiActivity?: string | null
  blockers?: string[]
  nextAction?: string | null
  continueAction?: string | null
}

export type HomeDay = {
  priority: NextPriority
  agenda: AgendaItem[]
  continues: ContinueItem[]
}

export const EMPTY_DAY: HomeDay = { priority: null, agenda: [], continues: [] }

/** Human labels for a block's source. Anything unknown is shown as written. */
const SOURCE_LABELS: Record<string, string> = {
  planner: 'Focus',
  calendar: 'Calendar',
  meeting: 'Meeting',
  email: 'Email',
  gitpilot: 'GitPilot',
  claude_code: 'Claude Code',
  codex: 'Codex',
  design: 'Design',
  standup: 'Standup',
}

function titleCase(s: string): string {
  return s.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function blockTag(block: PlanBlockDTO): string {
  if ((block.owner || '').toLowerCase() === 'ai') return 'AI'
  const source = (block.source || '').trim().toLowerCase()
  if (!source) return 'Focus'
  return SOURCE_LABELS[source] || titleCase(source)
}

/** `09:00 – 11:30`, or just the start when a block has no end. */
export function timeRange(start?: string | null, end?: string | null): string {
  const from = (start || '').trim()
  const to = (end || '').trim()
  if (from && to) return `${from} – ${to}`
  return from || to || ''
}

export function toAgenda(blocks: PlanBlockDTO[]): AgendaItem[] {
  return blocks
    .slice()
    .sort((a, b) => (a.orderIndex ?? 0) - (b.orderIndex ?? 0))
    .map((b) => {
      const range = timeRange(b.start, b.end)
      return {
        time: (b.start || '').trim() || '—',
        title: b.title,
        tag: blockTag(b),
        // Only worth repeating when it says more than the start column already does.
        end: range.includes('–') ? range : undefined,
      }
    })
}

/**
 * The one thing to do next.
 *
 * `/v1/today` already decides what "now" is; this adds the two things a card
 * needs and the API does not return inline — the block's scheduled time and the
 * project's name.
 */
export function toPriority(
  now: TodayTask | null,
  blocks: PlanBlockDTO[],
  projectNames: Record<string, string>,
): NextPriority {
  if (!now) return null
  const block = blocks.find((b) => b.taskId && b.taskId === now.id)
  return {
    title: now.title,
    project: (now.projectId && projectNames[now.projectId]) || '',
    time: timeRange(block?.start ?? now.start, block?.end ?? now.end),
    support: (now.context || now.nextAction || '').trim(),
  }
}

const RISK_ACCENT: Record<string, ContinueItem['accent']> = {
  high: 'purple',
  medium: 'blue',
  low: 'green',
}

/**
 * What a project's line actually says.
 *
 * A blocker outranks progress: the point of this card is resuming, and a
 * project you cannot resume is the more useful thing to read first.
 */
export function continuityStatus(item: ContinuityDTO): string {
  const blockers = item.blockers || []
  if (blockers.length) return `Blocked: ${blockers[0]}`
  const yesterday = item.yesterday || []
  if (yesterday.length) return yesterday[0]
  if (item.aiActivity) return item.aiActivity
  return 'In progress'
}

/**
 * Projects with something to carry over.
 *
 * `/v1/continuity` returns every project, most-at-risk first — as a list that
 * is fine, but on Home a project with no history is noise, and a wall of
 * "Next: Review project status" is exactly the generic filler this product is
 * supposed to avoid.
 */
export function toContinue(items: ContinuityDTO[], limit = 3): ContinueItem[] {
  return items
    .filter((i) => (i.blockers?.length || i.yesterday?.length || i.aiActivity))
    .slice(0, limit)
    .map((i) => ({
      id: i.projectId,
      icon: i.blockers?.length ? '⚠' : '◆',
      name: i.name,
      status: continuityStatus(i),
      next: (i.nextAction || i.continueAction || 'Continue work').trim(),
      progress: Math.max(0, Math.min(100, Math.round(i.progress ?? 0))),
      accent: RISK_ACCENT[(i.risk || 'low').toLowerCase()] || 'green',
    }))
}

/** Today's date as the plan API keys it. */
export function planDateKey(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}
