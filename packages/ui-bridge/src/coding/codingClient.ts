/**
 * Client for starting and steering coding runs.
 *
 * Everything here is asked of the backend rather than assumed: which executors
 * are enabled, which AI coders the chosen executor can actually run on its host,
 * and which repository a project builds in. A picker that offers an option the
 * deployment cannot honour is worse than no picker, so unavailable coders arrive
 * with the reason they are unavailable and are shown disabled, never hidden.
 */
import type {
  DayPilotCoderOption,
  DayPilotCodingMode,
  DayPilotCodingRun,
} from '@daypilot/shared-types'
import { api } from '../apiClient'
import { workspaceId } from '../env'

export type ExecutorOption = {
  executor: string
  enabled: boolean
  default: boolean
  supportsPlanMode: boolean
}

export type CoderCatalog = {
  coders: DayPilotCoderOption[]
  /** False when the executor could not be reached — say so, don't show an empty list. */
  reachable: boolean
  detail: string
}

export type StartRunInput = {
  task: string
  /** Optional: a run on a project inherits that project's repository. */
  repo?: string
  mode: DayPilotCodingMode
  executor?: string
  coder?: { provider: string; model: string }
  projectId?: string | null
  taskId?: string | null
  baseBranch?: string
}

export type StartRunResult =
  | { ok: true; run: DayPilotCodingRun }
  | { ok: false; error: string }

export const codingApi = {
  executors: async (): Promise<ExecutorOption[]> => {
    const res = await api.get<{ executors?: ExecutorOption[] }>('/v1/coding/executors')
    return res.ok ? res.data.executors || [] : []
  },

  /** The coders the chosen executor reports it can run, with honest availability. */
  coders: async (executor?: string, projectId?: string | null): Promise<CoderCatalog> => {
    const params = new URLSearchParams()
    if (executor) params.set('executor', executor)
    if (projectId) params.set('projectId', projectId)
    const query = params.toString()
    const res = await api.get<CoderCatalog>(`/v1/coding/coders${query ? `?${query}` : ''}`)
    if (!res.ok) return { coders: [], reachable: false, detail: 'could not reach the coding service' }
    return { coders: res.data.coders || [], reachable: res.data.reachable, detail: res.data.detail || '' }
  },

  start: async (input: StartRunInput): Promise<StartRunResult> => {
    const res = await api.post<DayPilotCodingRun>('/v1/coding/runs', {
      task: input.task,
      repo: input.repo || '',
      mode: input.mode,
      executor: input.executor || null,
      coder: input.coder && input.coder.provider ? input.coder : null,
      baseBranch: input.baseBranch || 'main',
      projectId: input.projectId || null,
      taskId: input.taskId || null,
      workspaceId: workspaceId(),
    })
    // The gateway's `detail` already arrives as the error text (e.g. "this run
    // needs a repository"), so the reason reaches the person who can fix it.
    if (!res.ok) return { ok: false, error: res.error || 'the run could not be started' }
    return { ok: true, run: res.data }
  },
}
