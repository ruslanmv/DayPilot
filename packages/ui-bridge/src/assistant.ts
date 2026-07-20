/**
 * The assistant — thin client (Batch 4).
 *
 * All intent routing and capability dispatch now live in the backend
 * orchestrator (`/v1/assistant/turn`). The browser sends the user's message and
 * renders what came back: a deterministic reply and an optional UI action. It no
 * longer classifies intents or calls planner/integration/approval endpoints
 * itself — the backend is the single authority for what the assistant does, and
 * it never sends email or calls a provider directly (every write stays
 * approval-gated server-side).
 *
 * When the backend is unreachable this says so honestly and never fabricates a
 * plan or a status.
 */
import { api } from './apiClient'
import { workspaceId } from './env'

export type AssistantAction =
  | { kind: 'navigate'; target: 'planning' | 'projects' | 'calendar' | 'agents' }
  | { kind: 'openProjectWizard' }
  | { kind: 'openApprovals' }

export type AssistantReply = { text: string; action?: AssistantAction }

export type AssistantTool = { capability: string; risk: string }
export type AssistantTurn = {
  runId: string
  intent: string
  state: string
  reply: string
  action?: AssistantAction | null
  tools: AssistantTool[]
  limited: boolean
  error?: string | null
}

/** Ask the backend orchestrator. Returns the reply + optional action, or an
 *  honest connection-failure message (never a guessed answer). */
export async function askAssistant(q: string, sessionId?: string): Promise<AssistantReply> {
  const question = q.trim()
  if (!question) return { text: 'Ask me about today, your plan, projects, integrations, email, or approvals.' }
  const res = await api.post<AssistantTurn>('/v1/assistant/turn', {
    message: question, workspaceId: workspaceId(), sessionId: sessionId ?? null,
  })
  if (!res.ok) {
    return { text: `I couldn't reach the assistant (${res.error}). Once the backend is running I can help with your day, integrations, email, and approvals.` }
  }
  const d = res.data
  return { text: d.reply, action: d.action ?? undefined }
}
