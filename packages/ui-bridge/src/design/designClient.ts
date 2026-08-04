/**
 * Client for the design chain: propose → adjust → design → schedule.
 *
 * Matrix Designer proposes three candidate plans for an idea; the person picks
 * one, optionally adjusts it in words, and only then is it designed in full and
 * taken in as scheduled work. Nothing here invents a plan: a designer that
 * refuses or cannot be reached returns an error the surface shows, never an
 * empty roadmap that looks like a real one.
 */
import type {
  DayPilotDesignBundle,
  DayPilotDesignProposal,
  DayPilotDesignReview,
} from '@daypilot/shared-types'
import { api } from '../apiClient'
import { workspaceId } from '../env'

export type DesignResult<T> = { ok: true; value: T } | { ok: false; error: string }

/** What intake created: the project and the batch tasks now on the board. */
export type DesignIntake = {
  projectId: string
  projectName: string
  repository: string
  taskIds: string[]
  batches: number
}

export type DesignedBundle = {
  bundle: DayPilotDesignBundle
  intake?: DesignIntake
}

function fail<T>(error: string): DesignResult<T> {
  return { ok: false, error }
}

export const designApi = {
  /** Three candidate plans for an idea, simplest to most complete. */
  blueprints: async (idea: string): Promise<DesignResult<DayPilotDesignProposal>> => {
    const res = await api.post<DayPilotDesignProposal>('/v1/design/blueprints', { idea })
    return res.ok ? { ok: true, value: res.data } : fail(res.error || 'the designer could not be reached')
  },

  /** Adjust a chosen candidate from free text, before committing to it. */
  refine: async (
    idea: string,
    message: string,
    candidateId: string,
  ): Promise<DesignResult<DayPilotDesignProposal>> => {
    const res = await api.post<DayPilotDesignProposal>('/v1/design/refine', {
      idea,
      message,
      candidateId,
    })
    return res.ok ? { ok: true, value: res.data } : fail(res.error || 'the change could not be applied')
  },

  /** Govern a plan before anything is built. */
  review: async (idea: string, candidateId: string): Promise<DesignResult<DayPilotDesignReview>> => {
    const res = await api.post<DayPilotDesignReview>('/v1/design/review', {
      idea,
      candidateId,
      workspaceId: workspaceId(),
    })
    return res.ok ? { ok: true, value: res.data } : fail(res.error || 'the plan could not be reviewed')
  },

  /**
   * Design the chosen plan in full and take it in as work: one project, one
   * task per batch, in dependency order.
   */
  build: async (
    idea: string,
    candidateId: string,
    repository: string,
  ): Promise<DesignResult<DesignedBundle>> => {
    const res = await api.post<DesignedBundle>('/v1/design/bundles', {
      idea,
      candidateId,
      repository,
      intake: true,
      workspaceId: workspaceId(),
    })
    return res.ok ? { ok: true, value: res.data } : fail(res.error || 'the plan could not be scheduled')
  },
}
