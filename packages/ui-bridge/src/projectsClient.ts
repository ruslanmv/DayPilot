/**
 * Client for server-owned Projects (Issue 4).
 *
 * Projects are persisted by the backend and are the single source of truth —
 * created projects survive refresh, appear on Home and in the planner, and are
 * the same on every device. The browser no longer keeps projects in local
 * React state as the record of truth; it loads and mutates them here.
 */
import { api } from './apiClient'
import { workspaceId } from './env'
import type { DayPilotProject, DayPilotProjectStatus, DayPilotRiskLevel } from '@daypilot/shared-types'
import type { NewProject } from './projects/ProjectWizard'

type ServerProject = {
  id: string; name: string; progress: number; status: string; risk: string
  aiActivity: string; nextHumanAction: string; continueAction: string
  aiActions?: unknown[]; designerInput?: unknown[]; recentSignals?: unknown[]
  linkedSources?: unknown[]; yesterday?: unknown[]; today?: unknown[]; blocked?: unknown[]
}

const strList = (v: unknown[] | undefined): string[] =>
  (v || []).map((x) => (typeof x === 'string' ? x : (x as { ref?: string })?.ref ?? JSON.stringify(x)))

/** Map a server project into the shell's DayPilotProject shape. */
export function toDayPilotProject(p: ServerProject): DayPilotProject {
  return {
    id: p.id,
    name: p.name,
    progress: p.progress ?? 0,
    status: (p.status as DayPilotProjectStatus) || 'Active',
    risk: (p.risk as DayPilotRiskLevel) || 'low',
    aiActivity: p.aiActivity || '',
    nextHumanAction: p.nextHumanAction || '',
    continueAction: p.continueAction || '',
    aiActions: strList(p.aiActions),
    designerInput: strList(p.designerInput),
    recentSignals: strList(p.recentSignals),
    linkedSources: strList(p.linkedSources),
    yesterday: strList(p.yesterday),
    today: strList(p.today),
    blocked: strList(p.blocked),
  }
}

export const projectsApi = {
  list: async (): Promise<DayPilotProject[]> => {
    const res = await api.get<{ items?: ServerProject[] }>(`/v1/projects?workspaceId=${workspaceId()}&limit=100`)
    return res.ok ? (res.data.items || []).map(toDayPilotProject) : []
  },
  create: async (np: NewProject): Promise<DayPilotProject | null> => {
    const res = await api.post<ServerProject>('/v1/projects', {
      name: np.name, goal: np.goal, stack: np.stack, repository: np.repo,
      milestone: np.milestone, workspaceId: workspaceId(),
    })
    return res.ok ? toDayPilotProject(res.data) : null
  },
  update: async (id: string, patch: Partial<{ progress: number; status: string; nextHumanAction: string }>): Promise<boolean> => {
    const res = await api.patch<ServerProject>(`/v1/projects/${encodeURIComponent(id)}`, patch)
    return res.ok
  },
  remove: async (id: string): Promise<boolean> => {
    const res = await api.del(`/v1/projects/${encodeURIComponent(id)}`)
    return res.ok
  },
}
