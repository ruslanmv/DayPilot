/**
 * Client for the multi-agent day planner.
 *
 * Backs the live Planning surface: load the persisted plan, generate/replan,
 * and chat with the plan. Replans run on the backend graph and persist into the
 * DayPlan lifecycle, so the timeline the user sees is the real, stored plan —
 * not a client-side simulation. Falls back gracefully when offline.
 */
import { api } from './apiClient'
import { workspaceId } from './env'

export type PlannerBlockType = 'calendar_event' | 'focus' | 'task' | 'admin' | 'meeting' | 'break' | 'buffer'

export type PlannerBlock = {
  id?: string
  taskId?: string | null
  title: string
  kind: 'deep' | 'meeting' | 'admin' | 'review' | 'break'
  type?: PlannerBlockType
  start: string
  end: string
  owner?: string
  status?: string
  reason?: string
}

export type PlannerQuality = { score: number; label: string; strengths: string[]; warnings: string[] }

export type PlannerPlan = {
  planDate: string
  state?: string
  summary?: string
  score?: number
  quality?: PlannerQuality
  blocks: PlannerBlock[]
}

export type PlannerChatResult = {
  reply: string
  replanned: boolean
  plan?: PlannerPlan
}

function isoToday(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

export type PlannerReadiness = {
  planDate: string
  hasPlan: boolean
  workingHoursConfigured: boolean
  calendarConnected: boolean
  tasksOpen: number
  tasksDueToday: number
  projectsActive: number
  focusPrefsConfigured: boolean
  sufficient: boolean
}

export async function loadReadiness(date = isoToday()): Promise<PlannerReadiness | null> {
  const res = await api.get<PlannerReadiness>(`/v1/planner/plans/${date}/readiness?workspaceId=${workspaceId()}`)
  return res.ok ? res.data : null
}

export async function loadPlan(date = isoToday()): Promise<PlannerPlan | null> {
  const res = await api.get<PlannerPlan>(`/v1/planner/plans/${date}?workspaceId=${workspaceId()}`)
  return res.ok ? res.data : null
}

export async function generatePlan(date = isoToday(), instruction?: string): Promise<PlannerPlan | null> {
  const res = await api.post<PlannerPlan>(`/v1/planner/plans/${date}/generate`, {
    workspaceId: workspaceId(), instruction,
  })
  return res.ok ? res.data : null
}

export type PlanProposal = {
  id: string
  title: string
  tier: 'medium' | 'major'
  reasons: string[]
  signature: string
  instruction: string
}

export type PlanSyncResult = {
  planDate: string
  hasPlan: boolean
  tier: 'none' | 'minor' | 'medium' | 'major'
  statusUpdates: string[]
  proposal: PlanProposal | null
}

export type DailyReviewResult = PlanSyncResult & {
  regenerated: boolean
  blocks: number
  done: number
  missed: number
}

/** One smart-sync pass: minor status updates are applied server-side; new work
 *  comes back as a proposal the user can apply or discard. */
export async function syncPlan(date = isoToday()): Promise<PlanSyncResult | null> {
  const res = await api.post<PlanSyncResult>(`/v1/planner/plans/${date}/sync`, { workspaceId: workspaceId() })
  return res.ok ? res.data : null
}

/** Start-of-day review: reconciles statuses and auto-builds the plan when
 *  sources are ready, so each day opens optimized without manual setup. */
export async function dailyReview(date = isoToday()): Promise<DailyReviewResult | null> {
  const res = await api.post<DailyReviewResult>(`/v1/planner/plans/${date}/daily-review`, { workspaceId: workspaceId() })
  return res.ok ? res.data : null
}

export async function applyProposal(p: PlanProposal, date = isoToday()): Promise<PlannerPlan | null> {
  const res = await api.post<PlannerPlan>(`/v1/planner/plans/${date}/proposal/apply`, {
    workspaceId: workspaceId(), proposalId: p.id, instruction: p.instruction,
  })
  return res.ok ? res.data : null
}

/** "I'm already on it": keep the plan untouched and silence this suggestion. */
export async function discardProposal(p: PlanProposal, date = isoToday()): Promise<boolean> {
  const res = await api.post(`/v1/planner/plans/${date}/proposal/discard`, {
    workspaceId: workspaceId(), proposalId: p.id, signature: p.signature, reason: 'user_already_working',
  })
  return res.ok
}

export async function chatPlan(message: string, date = isoToday()): Promise<PlannerChatResult | null> {
  const res = await api.post<PlannerChatResult>(`/v1/planner/plans/${date}/chat`, {
    workspaceId: workspaceId(), message,
  })
  return res.ok ? res.data : null
}

/** Create a task so the planner has a real work source. Returns true on success;
 *  the readiness check then reports tasksOpen > 0 and the plan can be built. */
export async function createQuickTask(title: string, dueToday = false): Promise<boolean> {
  const trimmed = title.trim()
  if (!trimmed) return false
  const res = await api.post('/v1/tasks', {
    workspaceId: workspaceId(),
    title: trimmed,
    owner: 'you',
    priority: 'medium',
    status: 'active',
    source: 'planner_setup',
    ...(dueToday ? { day: isoToday() } : {}),
  })
  return res.ok
}

export { isoToday }
