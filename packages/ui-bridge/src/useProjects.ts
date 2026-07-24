/**
 * Shared projects state hook (Issue 4).
 *
 * Both the desktop and mobile shells use this, so a project created in one is
 * the same record the other loads from the backend — no more independent local
 * copies. In demo mode it stays on the seeded sample projects (offline, no API).
 */
import { useCallback, useEffect, useState } from 'react'
import type { DayPilotProject } from '@daypilot/shared-types'
import { isDemoMode } from './env'
import { projectsApi } from './projectsClient'
import type { NewProject } from './projects/ProjectWizard'

export function useProjects(seed: () => DayPilotProject[]) {
  const [projects, setProjects] = useState<DayPilotProject[]>(seed)

  const reload = useCallback(() => {
    if (isDemoMode()) return
    projectsApi.list().then((list) => setProjects(list))
  }, [])

  useEffect(() => { reload() }, [reload])

  /** Persist a new project and prepend the real, server-owned record. Falls back
   *  to a local record only if the backend is unreachable, so the UI never dead-
   *  ends — but the persisted path is the norm. */
  const createProject = useCallback(async (np: NewProject, localFallback: (np: NewProject) => DayPilotProject) => {
    if (isDemoMode()) {
      const local = localFallback(np)
      setProjects((cur) => [local, ...cur])
      return local
    }
    const created = await projectsApi.create(np)
    const project = created ?? localFallback(np)
    setProjects((cur) => [project, ...cur.filter((p) => p.id !== project.id)])
    return project
  }, [])

  return { projects, setProjects, reload, createProject }
}
