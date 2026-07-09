export type InstallState =
  | 'INSTALLED_DISABLED'
  | 'REVIEWED'
  | 'ENABLED_FOR_READ_ONLY'
  | 'ENABLED_WITH_APPROVALS'
  | 'ENABLED_AUTONOMOUS_LIMITED'

export type DayPilotPersona = {
  id: string
  label: string
  role: string
  source: 'daypilot' | 'homepilot'
  installState: InstallState
  allowedTools: string[]
}

export type ApprovalRequest = {
  id: string
  personaId: string
  action: string
  risk: 'low' | 'medium' | 'high'
  status: 'pending' | 'approved' | 'rejected'
}

export type DayPilotTaskOwner = 'commander' | 'agent'
export type DayPilotTaskPriority = 'critical' | 'high' | 'medium' | 'low'
export type DayPilotTaskStatus = 'active' | 'running' | 'scheduled' | 'blocked' | 'done'

export type DayPilotTask = {
  id: string
  title: string
  day: 'Monday' | 'Tuesday' | 'Wednesday' | 'Thursday' | 'Friday' | 'Saturday' | 'Sunday'
  start: string
  end: string
  owner: DayPilotTaskOwner
  executor: string
  priority: DayPilotTaskPriority
  status: DayPilotTaskStatus
  context: string
  source?: string
}

export type DayPilotMessage = {
  id: string
  role: 'commander' | 'assistant'
  body: string
  createdAt: string
}
