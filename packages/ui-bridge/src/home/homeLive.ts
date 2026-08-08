/**
 * Home, from the real day — the loading part.
 *
 * The mapping lives in `homeDay.ts`; this is the piece that talks to the API
 * and the piece React calls. Both shells use the same hook: a phone that
 * disagreed with the laptop about what is next would be worse than useless.
 */
import { useEffect, useState } from 'react'

import { api } from '../apiClient'
import { isDemoMode, workspaceId } from '../env'
import { CONTINUE_ITEMS, NEXT_PRIORITY, TODAY_PLAN } from './homeData'
import {
  EMPTY_DAY,
  planDateKey,
  toAgenda,
  toContinue,
  toPriority,
  type ContinuityDTO,
  type HomeDay,
  type PlanBlockDTO,
  type TodayTask,
} from './homeDay'

export * from './homeDay'

/**
 * Load the day. Demo mode keeps its sample content so the seeded tour and the
 * marketing story stay reproducible; everything else reads the workspace.
 */
export async function loadHomeDay(): Promise<HomeDay> {
  if (isDemoMode()) {
    return { priority: NEXT_PRIORITY, agenda: TODAY_PLAN, continues: CONTINUE_ITEMS }
  }
  const ws = workspaceId()
  const [today, plan, continuity, projects] = await Promise.all([
    api.get<{ now?: TodayTask | null }>(`/v1/today?workspaceId=${ws}`),
    api.get<{ blocks?: PlanBlockDTO[] }>(`/v1/plans/${planDateKey()}?workspaceId=${ws}`),
    api.get<{ items?: ContinuityDTO[] }>(`/v1/continuity?workspaceId=${ws}`),
    api.get<{ items?: Array<{ id: string; name: string }> }>(`/v1/projects?workspaceId=${ws}`),
  ])

  // No plan for today is a 404, not a failure — the day simply has not been
  // planned yet, and Home says so.
  const blocks = plan.ok ? plan.data.blocks || [] : []
  const names: Record<string, string> = {}
  if (projects.ok) for (const p of projects.data.items || []) names[p.id] = p.name

  return {
    priority: today.ok ? toPriority(today.data.now || null, blocks, names) : null,
    agenda: toAgenda(blocks),
    continues: continuity.ok ? toContinue(continuity.data.items || []) : [],
  }
}

/** The day, for both shells. Desktop Home and the mobile Home render the same
 *  workspace, so they must not diverge into two versions of "today". */
export function useHomeDay(): HomeDay {
  const [day, setDay] = useState<HomeDay>(EMPTY_DAY)
  useEffect(() => {
    let cancelled = false
    loadHomeDay().then((d) => { if (!cancelled) setDay(d) }).catch(() => {})
    return () => { cancelled = true }
  }, [])
  return day
}
