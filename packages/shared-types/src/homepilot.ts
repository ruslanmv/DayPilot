/**
 * HomePilot remote-agent integration — shared types.
 *
 * HomePilot owns the agents; DayPilot stores remote *references* and manages the
 * work. These types mirror the backend contract in
 * services/orchestrator/daypilot_orchestrator/homepilot/contracts.py and the
 * agent-profile / connection API shapes.
 */

export type HomePilotConnectionStatus = 'connected' | 'unreachable' | 'unauthorized' | 'unconfigured'

/** Safe, non-secret view of a HomePilot connection (base URL host only, no key). */
export interface HomePilotConnection {
  id: string
  workspaceId: string
  baseUrl: string
  status: HomePilotConnectionStatus
  capabilities: string[]
  lastTestedAt?: string | null
  lastError?: string | null
}

/** Presence of an agent in DayPilot's directory (text + colour, never colour alone). */
export type AgentStatus = 'available' | 'working' | 'busy' | 'needs_approval' | 'offline' | 'disabled'

/**
 * A DayPilot-side reference to a HomePilot persona. Identity/memory/prompt live
 * in HomePilot; DayPilot only stores display metadata + local ownership flags.
 */
export interface AgentProfile {
  id: string
  connectionId: string
  homepilotProjectId: string
  homepilotModelId: string        // persona:<project_id>
  name: string
  role: string
  description: string
  avatarUrl?: string | null
  thumbnailUrl?: string | null
  capabilities: string[]
  memoryMode?: string | null
  sourceVersion?: string | null
  enabled: boolean                // whether this agent is enabled in DayPilot
  favorite: boolean
  status: AgentStatus
  lastSyncedAt?: string | null
  lastSeenAt?: string | null
}

/** DayPilot always uses 'propose'; HomePilot returns directives, never executes. */
export type ToolMode = 'disabled' | 'propose' | 'execute'

export type DirectiveType =
  | 'task.create'
  | 'task.update'
  | 'task.complete'
  | 'task.block'
  | 'progress.report'
  | 'delegate.request'
  | 'daypilot.action.propose'
  | 'artifact.attach'

/** A structured proposal returned by a bridged HomePilot persona (untrusted). */
export interface HomePilotDirective {
  type: DirectiveType
  title?: string
  capability?: string             // for daypilot.action.propose
  arguments?: Record<string, unknown>
  taskId?: string
  agent?: string                  // for delegate.request
  progressPercent?: number
}

export interface HomePilotTurnResponse {
  reply: string
  sessionId: string
  remoteSessionId?: string | null
  remoteConversationId?: string | null
  directives: HomePilotDirective[]
}

/** Optional HomePilot capability advertisement (Phase 12). Absent → legacy chat-only. */
export interface HomePilotCapabilities {
  bridgeVersion: number
  features: {
    personaDiscovery: boolean
    personaChat: boolean
    externalSessionId: boolean
    toolModePropose: boolean
    directives: boolean
    attachments: boolean
  }
}
