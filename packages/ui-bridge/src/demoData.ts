/**
 * Clean-data gate.
 *
 * In production (default) the shell starts empty and connected to real data.
 * The rich sample content in `spaceBridgeData.ts` / `home/homeData.ts` is only
 * surfaced when `VITE_DAYPILOT_DEMO_MODE=true`. Everything else in the app
 * imports its seed data from *here* rather than importing the demo modules
 * directly, so there is a single switch between "empty, real" and "demo".
 */
import type {
  DayPilotAgent,
  DayPilotDocument,
  DayPilotDocumentSource,
  DayPilotMessage,
  DayPilotProject,
  DayPilotTask,
} from '@daypilot/shared-types'
import { isDemoMode } from './env'
import {
  documentSources as demoSources,
  initialAgents as demoAgents,
  initialDocuments as demoDocuments,
  initialMessages as demoMessages,
  initialProjects as demoProjects,
  initialTasks as demoTasks,
} from './spaceBridgeData'

const empty = <T>(demo: T[]): T[] => (isDemoMode() ? demo : [])

export const seedMessages = (): DayPilotMessage[] => empty(demoMessages)
export const seedTasks = (): DayPilotTask[] => empty(demoTasks)
export const seedProjects = (): DayPilotProject[] => empty(demoProjects)
export const seedDocuments = (): DayPilotDocument[] => empty(demoDocuments)
export const seedAgents = (): DayPilotAgent[] => empty(demoAgents)
export const seedDocumentSources = (): DayPilotDocumentSource[] => empty(demoSources)

export { isDemoMode }
