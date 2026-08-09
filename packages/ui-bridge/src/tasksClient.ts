/**
 * The workspace's tasks.
 *
 * The shell held tasks in React state seeded from `demoData`, which is empty
 * outside demo mode. Three primary views read that list — Calendar ("Minute
 * Plan"), Tasks ("You vs AI") and Focus Mode — so in a real workspace all
 * three were blank and Home's most prominent button, **Start focus**, did
 * nothing at all. `/v1/tasks` has served this data since the domain API landed.
 *
 * `toDayPilotTask` is the whole reason this file is separate from a one-line
 * fetch: the API and the shell disagree about several fields, and quietly
 * guessing wrong shows a task under the wrong day or with no owner.
 */
import type { DayPilotTask } from '@daypilot/shared-types'

import { api } from './apiClient'
import { workspaceId } from './env'
import { toDayPilotTask, type ServerTask } from './tasksMap'

export * from './tasksMap'

export async function fetchTasks(limit = 100): Promise<DayPilotTask[]> {
  const r = await api.get<{ items?: ServerTask[] }>(
    `/v1/tasks?workspaceId=${workspaceId()}&limit=${limit}`,
  )
  if (!r.ok) return []
  return (r.data.items || []).map((t) => toDayPilotTask(t))
}
