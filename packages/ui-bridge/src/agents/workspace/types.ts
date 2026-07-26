/**
 * Data contract for the dedicated agent workspace (Batch A4).
 *
 * The workspace is READ-ONLY in A4: the live chat bridge (A6) and the
 * directive→task mapping (A7) fill these in later. Every panel accepts its data
 * as props with an honest empty state, so wiring the real feeds in a later batch
 * is a pure data change — no layout churn.
 */

/** A unit of work an agent owns, shown in the task panel's three columns. */
export type AgentTaskState = 'active' | 'waiting' | 'completed'

export type AgentWorkTask = {
  id: string
  title: string
  state: AgentTaskState
  /** 0–100. Drives the progress bar; waiting/active only. */
  progress: number
  /** Who the next step belongs to. "you" = waiting on your approval/input. */
  owner: 'agent' | 'you'
  updatedAt?: string | null
}

/** One turn in the read-only conversation. */
export type AgentMessage = {
  id: string
  role: 'you' | 'agent'
  body: string
  createdAt?: string | null
  /** A propose-only draft awaiting approval (never auto-sent). */
  proposal?: boolean
}

/** An entry in the Activity tab (audit-style, newest first). */
export type AgentActivityEntry = {
  id: string
  at?: string | null
  summary: string
  kind?: 'proposed' | 'approved' | 'declined' | 'synced' | 'status' | 'note'
}

/** A file the agent referenced or produced (Files tab). */
export type AgentFileRef = {
  id: string
  name: string
  meta?: string | null
}

export const TASK_COLUMNS: { state: AgentTaskState; label: string }[] = [
  { state: 'active', label: 'Active' },
  { state: 'waiting', label: 'Waiting' },
  { state: 'completed', label: 'Completed' },
]

export function taskOwnerLabel(owner: AgentWorkTask['owner']): string {
  return owner === 'you' ? 'You' : 'Agent'
}
