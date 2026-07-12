/**
 * Client for persistent assistant chat sessions.
 *
 * Wraps the `/v1/chat/sessions` API so the web shell can offer ChatGPT/Claude
 * -style history: new conversation, resume, rename, clear, and delete, all
 * surviving a refresh. Falls back gracefully (returns empty) when the backend
 * is unreachable so the assistant still works in-memory.
 */
import { api } from './apiClient'
import { workspaceId } from './env'
import type { AssistantAction } from './assistant'

export type ChatMessageDTO = {
  id: string
  role: 'user' | 'assistant'
  body: string
  action?: AssistantAction | null
  createdAt?: string | null
}

export type ChatSessionSummary = {
  id: string
  title: string
  messageCount: number
  lastMessageAt?: string | null
  updatedAt?: string | null
}

export type ChatSessionDetail = ChatSessionSummary & { messages: ChatMessageDTO[] }

const ws = () => workspaceId()

export async function listSessions(): Promise<ChatSessionSummary[]> {
  const res = await api.get<{ sessions: ChatSessionSummary[] }>(`/v1/chat/sessions?workspaceId=${ws()}`)
  return res.ok ? res.data.sessions : []
}

export async function createSession(title?: string): Promise<ChatSessionSummary | null> {
  const res = await api.post<ChatSessionSummary>('/v1/chat/sessions', { workspaceId: ws(), title })
  return res.ok ? res.data : null
}

export async function getSession(id: string): Promise<ChatSessionDetail | null> {
  const res = await api.get<ChatSessionDetail>(`/v1/chat/sessions/${id}?workspaceId=${ws()}`)
  return res.ok ? res.data : null
}

export async function renameSession(id: string, title: string): Promise<boolean> {
  const res = await api.patch(`/v1/chat/sessions/${id}`, { workspaceId: ws(), title })
  return res.ok
}

export async function deleteSession(id: string): Promise<boolean> {
  const res = await api.del(`/v1/chat/sessions/${id}?workspaceId=${ws()}`)
  return res.ok
}

export async function clearSession(id: string): Promise<boolean> {
  const res = await api.del(`/v1/chat/sessions/${id}/messages?workspaceId=${ws()}`)
  return res.ok
}

export async function appendMessage(
  id: string,
  role: 'user' | 'assistant',
  body: string,
  action?: AssistantAction | null,
): Promise<boolean> {
  const res = await api.post(`/v1/chat/sessions/${id}/messages`, {
    workspaceId: ws(), role, body, action: action ?? null,
  })
  return res.ok
}
