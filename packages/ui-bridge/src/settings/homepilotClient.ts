/**
 * Client for the backend-owned HomePilot connection + agent references.
 *
 * HomePilot owns the agents; DayPilot connects to them. The browser never talks
 * to HomePilot directly — every call here hits DayPilot's gateway, which holds
 * the API key server-side (secret-by-reference) and proxies HomePilot. When the
 * HomePilot runtime flag is off, these endpoints 404 (status 404) and the panel
 * shows a "turned off" state.
 */
import { api } from '../apiClient'
import { workspaceId } from '../env'

export type HomePilotConnectionStatus = 'connected' | 'unreachable' | 'unauthorized' | 'unconfigured'

export type HomePilotConnection = {
  id: string
  workspaceId: string
  baseUrl: string
  status: HomePilotConnectionStatus
  capabilities: string[]
  /** Which HomePilot account this connection is bound to (multi-account
   * security). Label is safe to show; ref is opaque; the key is never sent. */
  accountRef?: string
  accountLabel?: string
  remoteKind?: 'local' | 'cloud'
  /** Whether this HomePilot supports the propose bridge, or is legacy chat-only. */
  chatMode?: 'bridge' | 'chat_only' | 'unknown'
  bridgeVersion?: string
  lastTestedAt?: string | null
  lastError?: string | null
}

export type AgentProfile = {
  id: string
  connectionId: string
  homepilotProjectId: string
  homepilotModelId: string
  name: string
  role: string
  description: string
  avatarUrl?: string | null
  capabilities: string[]
  enabled: boolean
  favorite: boolean
  status: 'available' | 'working' | 'busy' | 'needs_approval' | 'offline' | 'disabled'
}

export type SyncResult = { code: string; synced?: number; offline?: number; total?: number; agents?: string[] }

/** One persisted turn in an agent conversation (backend shape). */
export type AgentTurnMessage = {
  id: string
  role: 'user' | 'assistant'
  body: string
  action?: Record<string, unknown> | null
  createdAt?: string | null
}

export type AgentSession = {
  sessionId: string
  agentId: string
  agentName?: string
  /** 'bridge' (directives supported), 'chat_only' (legacy), or 'unknown'. */
  mode?: 'bridge' | 'chat_only' | 'unknown'
  /** True when HomePilot is offline — the thread is served from saved history. */
  degraded?: boolean
  messages: AgentTurnMessage[]
}

/** Result of one turn. `mode` is 'bridge' when HomePilot returned directives,
 * 'chat_only' when a legacy HomePilot just replied. */
export type AgentTurnResult = {
  code: string
  sessionId: string
  mode: 'bridge' | 'chat_only'
  proposals: number
  userMessage: AgentTurnMessage
  reply: AgentTurnMessage
}

/** Approval lifecycle of an agent-proposed action (A8). */
export type AgentLifecycle =
  | 'prepared' | 'awaiting' | 'approved' | 'executing' | 'completed' | 'rejected' | 'failed'

/** One task an agent owns, with its lifecycle (backend shape). */
export type AgentTaskRow = {
  id: string
  title: string
  status: string
  priority: string
  progress: number
  owner: string
  lifecycle?: AgentLifecycle | null
  capability?: string | null
  approvalId?: string | null
  updatedAt?: string | null
}

/** The onboarding connection-state machine (backend shape). Drives the settings
 * page + wizard: the integration is enabled by default, so `not_connected` is a
 * setup prompt, never an error. `admin_disabled` is the one hard-off state. */
export type HomePilotConnectionState =
  | 'not_connected'
  | 'detecting'
  | 'detected'
  | 'connecting'
  | 'connected'
  | 'syncing'
  | 'needs_attention'
  | 'offline'
  | 'admin_disabled'

/** Per-connection sync + agent-behavior preferences (the approval rule is not
 * a preference — external actions always require approval). */
export type HomePilotPrefs = {
  autoSync: boolean
  syncOnStart: boolean
  syncIntervalMinutes: number
  newAgentsDisabled: boolean
  showOffline: boolean
  useSessions: boolean
  allowDelegation: boolean
}

export type HomePilotSetupConnection = {
  id: string
  displayName: string
  browserUrl: string
  apiUrl: string
  health: 'healthy' | 'starting' | 'unreachable'
  version?: string
  agentCount: number
  chatMode?: 'bridge' | 'chat_only' | 'unknown'
  accountLabel?: string
  remoteKind?: 'local' | 'cloud'
  prefs?: HomePilotPrefs
  lastSyncedAt?: string | null
  lastError?: string | null
}

export type HomePilotSetupStatus = {
  featureEnabled: boolean
  adminLocked: boolean
  connectionState: HomePilotConnectionState
  detectionAvailable: boolean
  installWizardAvailable: boolean
  connection: HomePilotSetupConnection | null
}

export type HomePilotDetectedInstance = {
  apiUrl: string
  browserUrl: string
  health: 'healthy' | 'starting' | 'unreachable'
  version?: string | null
  installationType: 'desktop' | 'single_container' | 'docker_compose' | 'remote' | 'unknown'
}

export type HomePilotDetectResult = {
  detected: boolean
  instance: HomePilotDetectedInstance | null
  probes: { apiUrl: string; health: string }[]
}

export type HomePilotTestCheck = { key: string; ok: boolean; label: string }
export type HomePilotTestResult = {
  ok: boolean
  code: string
  checks: HomePilotTestCheck[]
  personaCount: number
  chatCount: number
  version?: string | null
  chatMode: 'bridge' | 'chat_only' | 'unknown'
}

const ws = () => workspaceId()

export const homepilotApi = {
  // Onboarding / setup (H2). status is always reachable — even under an admin lock.
  setupStatus: () => api.get<HomePilotSetupStatus>(`/v1/homepilot/setup/status?workspaceId=${ws()}`),
  detect: () => api.post<HomePilotDetectResult>('/v1/homepilot/setup/detect', {}),
  testAddress: (baseUrl: string, apiKey?: string, allowPrivate = true) =>
    api.post<HomePilotTestResult>('/v1/homepilot/setup/test', { baseUrl, apiKey, allowPrivate }),
  listConnections: () => api.get<{ connections: HomePilotConnection[] }>(`/v1/homepilot/connections?workspaceId=${ws()}`),
  connect: (baseUrl: string, apiKey?: string, browserUrl?: string) =>
    api.post<{ connection: HomePilotConnection; code: string }>('/v1/homepilot/connections', { workspaceId: ws(), baseUrl, apiKey, browserUrl }),
  test: (id: string) =>
    api.post<{ code: string; connection: HomePilotConnection }>(`/v1/homepilot/connections/${encodeURIComponent(id)}/test`, { workspaceId: ws() }),
  disconnect: (id: string) =>
    api.del(`/v1/homepilot/connections/${encodeURIComponent(id)}?workspaceId=${ws()}`),
  patchPrefs: (id: string, prefs: Partial<HomePilotPrefs>) =>
    api.patch<{ connection: HomePilotConnection }>(`/v1/homepilot/connections/${encodeURIComponent(id)}`, { workspaceId: ws(), ...prefs }),
  sync: (id: string) =>
    api.post<SyncResult>(`/v1/homepilot/connections/${encodeURIComponent(id)}/sync`, { workspaceId: ws() }),
  listProfiles: () => api.get<{ profiles: AgentProfile[] }>(`/v1/agents/profiles?workspaceId=${ws()}`),
  setEnabled: (id: string, enabled: boolean) =>
    api.patch<AgentProfile>(`/v1/agents/profiles/${encodeURIComponent(id)}`, { workspaceId: ws(), enabled }),
  setFavorite: (id: string, favorite: boolean) =>
    api.patch<AgentProfile>(`/v1/agents/profiles/${encodeURIComponent(id)}`, { workspaceId: ws(), favorite }),
  // Agent chat bridge (A6). getSession creates the conversation on first open.
  getAgentSession: (id: string) =>
    api.get<AgentSession>(`/v1/agents/profiles/${encodeURIComponent(id)}/session?workspaceId=${ws()}`),
  sendTurn: (id: string, message: string) =>
    api.post<AgentTurnResult>(`/v1/agents/profiles/${encodeURIComponent(id)}/turn`, { workspaceId: ws(), message }),
  getAgentTasks: (id: string) =>
    api.get<{ agentId: string; tasks: AgentTaskRow[] }>(`/v1/agents/profiles/${encodeURIComponent(id)}/tasks?workspaceId=${ws()}`),
  getAgentDelegations: (id: string) =>
    api.get<{ agentId: string; delegations: AgentDelegationRow[] }>(`/v1/agents/profiles/${encodeURIComponent(id)}/delegations?workspaceId=${ws()}`),
  // Add-agent flow (A10). Adding happens in HomePilot; DayPilot connects + refreshes.
  addInfo: () => api.get<AddAgentInfo>(`/v1/homepilot/add-info?workspaceId=${ws()}`),
  hpersonaPreview: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.postForm<HpersonaReport>('/v1/homepilot/hpersona/preview', form)
  },
  hpersonaImport: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.postForm<{ code: string; agentId?: string; name?: string }>(`/v1/homepilot/hpersona/import?workspaceId=${ws()}`, form)
  },
}

export type AddAgentInfo = {
  connected: boolean
  connectionId?: string | null
  galleryUrl: string
  importsEnabled: boolean
}

export type HpersonaDep = { name: string; status: string }
export type HpersonaReport = {
  valid: boolean
  errors: string[]
  preview: { name?: string; role?: string; description?: string; capabilities?: string[]; contentRating?: string }
  dependencies: { models: HpersonaDep[]; tools: HpersonaDep[]; mcpServers: HpersonaDep[]; a2aAgents: HpersonaDep[]; allSatisfied: boolean }
}

/** One manager→worker delegation, with its responsibility chain (A9). */
export type AgentDelegationRow = {
  id: string
  manager: string
  managerLinkId: string
  worker: string
  workerLinkId: string
  capability?: string
  depth: number
  status: string
  childTaskId?: string | null
  /** e.g. ["You", "Scarlett", "Atlas"] */
  chain: string[]
  createdAt?: string | null
}

/** Short label for an approval lifecycle state, surfaced in the workspace. */
export function agentLifecycleLabel(state?: string | null): string {
  switch (state) {
    case 'prepared': return 'Prepared'
    case 'awaiting': return 'Awaiting approval'
    case 'approved': return 'Approved'
    case 'executing': return 'Executing'
    case 'completed': return 'Completed'
    case 'rejected': return 'Rejected'
    case 'failed': return 'Failed'
    default: return ''
  }
}

/** Human-readable label + tone for an agent presence status (text + colour). */
export function agentStatusLabel(status: string): string {
  switch (status) {
    case 'available': return 'Available'
    case 'working': return 'Working'
    case 'busy': return 'Busy'
    case 'needs_approval': return 'Needs approval'
    case 'offline': return 'Offline'
    case 'disabled': return 'Disabled'
    default: return status
  }
}

/** Human-readable text for a connection status / probe code. */
export function homepilotStatusText(status: string): string {
  switch (status) {
    case 'connected': return 'Connected'
    case 'unreachable': return 'Not reachable'
    case 'unauthorized': return 'Key rejected'
    case 'unconfigured': return 'Not configured'
    default: return status
  }
}
