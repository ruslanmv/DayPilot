/**
 * Client for server-owned Knowledge Sources (Issue 1).
 *
 * The Settings screen lists real, persisted sources and its buttons do real
 * work: adding a local folder posts a validated server path, re-indexing
 * enqueues a durable job, and removing deletes the grant.
 */
import { api } from '../apiClient'
import { workspaceId } from '../env'

export type KnowledgeSource = {
  id: string
  provider: 'local' | 'box' | 'vault'
  displayName: string
  location: string
  scope: string
  permission: string
  status: 'queued' | 'indexing' | 'indexed' | 'failed' | 'unconfigured'
  projectIds: string[]
  lastIndexedAt?: string | null
  lastError?: string | null
}

export type SourcesResponse = { sources: KnowledgeSource[]; boxAvailable: boolean }

const ws = () => workspaceId()

export const knowledgeApi = {
  list: () => api.get<SourcesResponse>(`/v1/knowledge/sources?workspaceId=${ws()}`),
  addLocal: (path: string, displayName?: string) =>
    api.post<{ source: KnowledgeSource; jobId: string }>('/v1/knowledge/sources/local', { path, displayName, workspaceId: ws() }),
  reindex: (id: string) =>
    api.post<{ source: KnowledgeSource; jobId: string }>(`/v1/knowledge/sources/${encodeURIComponent(id)}/reindex`, { workspaceId: ws() }),
  remove: (id: string) =>
    api.del(`/v1/knowledge/sources/${encodeURIComponent(id)}?workspaceId=${ws()}`),
  boxStart: () => api.post<{ available: boolean; message?: string; authUrl?: string; state?: string }>('/v1/knowledge/box/oauth/start', { workspaceId: ws() }),
}

export function sourceStatusLabel(status: string): string {
  switch (status) {
    case 'queued': return 'Index queued'
    case 'indexing': return 'Indexing…'
    case 'indexed': return 'Indexed'
    case 'failed': return 'Failed'
    default: return status
  }
}
