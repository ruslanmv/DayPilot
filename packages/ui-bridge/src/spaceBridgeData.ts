import type { DayPilotMessage, DayPilotTask } from '@daypilot/shared-types'

export const initialMessages: DayPilotMessage[] = [
  {
    id: 'msg-001',
    role: 'assistant',
    createdAt: '08:12',
    body:
      'Welcome back, Commander. I reorganized today around one critical inbox sweep, one protected model-runtime focus block, and two quiet autonomous agent runs. Click any block for telemetry without leaving the workspace.',
  },
]

export const initialTasks: DayPilotTask[] = [
  {
    id: 'task-101',
    day: 'Monday',
    start: '09:00',
    end: '10:30',
    title: 'Inbox Sweep & Contract Telemetry',
    priority: 'critical',
    owner: 'agent',
    executor: 'Sec-Core',
    status: 'running',
    source: 'Matrix RAG · IMAP ingest',
    context:
      'Parsing incoming compliance emails, extracting obligations, and matching clauses against Matrix Contract vectors. Commander interruption is not required unless a blocker is detected.',
  },
  {
    id: 'task-102',
    day: 'Monday',
    start: '11:00',
    end: '13:00',
    title: 'Refactor Model Execution Boundaries',
    priority: 'high',
    owner: 'commander',
    executor: 'Commander',
    status: 'active',
    source: 'model-serving · orchestrator',
    context:
      'Protected deep-work block for separating local model connectors from external ingress, with special attention to vLLM, Ollama, and approval boundaries.',
  },
  {
    id: 'task-103',
    day: 'Tuesday',
    start: '14:00',
    end: '16:00',
    title: 'GitPilot Dependency Patch Review',
    priority: 'high',
    owner: 'agent',
    executor: 'Git-Core',
    status: 'scheduled',
    source: 'GitPilot · branch diff queue',
    context:
      'Autonomous dependency patch generation and regression scan. Output is staged for review in the drawer before any repository write is approved.',
  },
  {
    id: 'task-104',
    day: 'Wednesday',
    start: '16:30',
    end: '17:30',
    title: 'Ecosystem Synchronization Briefing',
    priority: 'medium',
    owner: 'commander',
    executor: 'Commander',
    status: 'scheduled',
    source: 'Calendar Core · weekly command cycle',
    context:
      'Review cross-system operating state, decide which .hpersona processes remain read-only, and approve the next workday allocation.',
  },
  {
    id: 'task-105',
    day: 'Thursday',
    start: '09:00',
    end: '10:00',
    title: 'Meeting Prep: Team Architecture Review',
    priority: 'high',
    owner: 'commander',
    executor: 'Commander',
    status: 'scheduled',
    source: 'Calendar invite · local notes',
    context:
      'AI-prepared brief containing open design questions, expected decisions, and repository files likely to be discussed by the team.',
  },
]

export const weekDays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'] as const
export const dayHours = ['08:00', '09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00', '17:00', '18:00']
export const weekSlots = ['09:00', '11:00', '14:00', '16:00', '18:00']
