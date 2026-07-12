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

export type PlannerBlock = {
  id?: string
  taskId?: string | null
  title: string
  kind: 'deep' | 'meeting' | 'admin' | 'review' | 'break'
  start: string
  end: string
  owner?: string
  status?: string
}

export type PlannerPlan = {
  planDate: string
  state?: string
  summary?: string
  score?: number
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

export async function chatPlan(message: string, date = isoToday()): Promise<PlannerChatResult | null> {
  const res = await api.post<PlannerChatResult>(`/v1/planner/plans/${date}/chat`, {
    workspaceId: workspaceId(), message,
  })
  return res.ok ? res.data : null
}

export { isoToday }
