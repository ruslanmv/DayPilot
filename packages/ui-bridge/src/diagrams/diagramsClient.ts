import { api } from '../apiClient'
import { workspaceId } from '../env'
import type { Diagram, DiagramKind } from './dmind'
import type { Patch } from './patch'
import type { SourceRef } from './provenance'
export type SavedDiagram = {
  id: string
  revision: number
  archived: boolean
  document: Diagram
}
export type DiagramSummary = {
  id: string
  title: string
  revision: number
  archived: boolean
  updatedAt?: string | null
  tags?: string[]
  projectId?: string | null
}
export type DiagramPage = {
  items: DiagramSummary[]
  nextCursor: string | null
  hasMore: boolean
}
export type ListQuery = {
  q?: string
  tag?: string
  projectId?: string
  archived?: 'include' | 'exclude' | 'only'
  cursor?: string | null
  limit?: number
}
export type RevisionSummary = {
  revision: number
  createdAt?: string | null
  title?: string
  nodes: number
  edges: number
  document?: Diagram
}
export type RevisionPage = {
  items: RevisionSummary[]
  hasMore: boolean
  nextBefore: number | null
}
export type Extracted = {
  text: string
  source: Omit<SourceRef, 'id'> & { chars?: number }
  warnings: string[]
}
export type InputCapabilities = {
  text: boolean
  docx: boolean
  pdf: boolean
  ocr: boolean
  urlFetch: boolean
  limits: { fileBytes: number; textChars: number; pdfPages: number; pageBytes: number }
}
export type AssistAction = 'chat' | 'generate' | 'grow' | 'explain' | 'reorganize' | 'refine'
export type AssistRequest = {
  action: AssistAction
  document?: Diagram | null
  focus?: string[]
  prompt?: string
  history?: { role: 'user' | 'assistant'; content: string }[]
  options?: { count?: number; mode?: string; language?: string }
}
export type AssistReply = {
  mode: 'model' | 'offline'
  message: string
  patch?: Patch
  title?: string | null
  outline?: string
  credits?: { charged: number; balance: number }
}
export type CreditSummary = {
  enabled: boolean
  balance?: number
  monthlyAllowance?: number
  costs: Record<string, number>
}
const query = (params: Record<string, string | number | null | undefined>) => {
  const search = new URLSearchParams()
  for (const [k, v] of Object.entries(params))
    if (v !== undefined && v !== null && v !== '') search.set(k, String(v))
  const text = search.toString()
  return text ? '?' + text : ''
}
function headers() {
  const match = document.cookie.match(/(?:^|;\s*)dp_csrf=([^;]+)/)
  return {
    headers: { 'X-CSRF-Token': match ? decodeURIComponent(match[1]) : '' },
  }
}
export const diagramsApi = {
  list: (q: ListQuery = {}) =>
    api.get<DiagramPage>(
      '/v1/diagrams' +
        query({
          q: q.q,
          tag: q.tag,
          project_id: q.projectId,
          archived: q.archived,
          cursor: q.cursor,
          limit: q.limit ?? 50,
        }),
    ),
  load: (id: string) =>
    api.get<SavedDiagram>(`/v1/diagrams/${encodeURIComponent(id)}`),
  create: (document: Diagram) =>
    api.post<SavedDiagram>('/v1/diagrams', { document }, headers()),
  save: (
    id: string,
    document: Diagram,
    expectedRevision: number,
    archived = false,
  ) =>
    api.put<SavedDiagram>(
      `/v1/diagrams/${encodeURIComponent(id)}`,
      { document, expectedRevision, archived },
      headers(),
    ),
  revisions: (id: string, before?: number | null) =>
    api.get<RevisionPage>(
      `/v1/diagrams/${encodeURIComponent(id)}/revisions` +
        query({ summary: 'true', limit: 20, before }),
    ),
  revision: (id: string, revision: number) =>
    api.get<RevisionSummary & { document: Diagram }>(
      `/v1/diagrams/${encodeURIComponent(id)}/revisions/${revision}`,
    ),
  projects: () =>
    api.get<{ items: { id: string; name: string }[] }>(
      `/v1/projects?workspaceId=${encodeURIComponent(workspaceId())}&limit=200`,
    ),
  generate: (
    topic: string,
    content: string,
    kind: DiagramKind,
    useDesigner: boolean,
    candidateId: string,
  ) =>
    api.post<{ diagram: Diagram; mode: string }>(
      '/v1/diagrams/generate',
      { topic, content, kind, useDesigner, candidateId },
      headers(),
    ),
  bundle: (document: Diagram, candidateId: string) =>
    api.post<{
      bundle: Record<string, unknown>
      validation: Record<string, unknown>
    }>('/v1/diagrams/design-bundle', { document, candidateId }, headers()),
  assistStatus: () => api.get<{ available: boolean; actions: string[]; credits: CreditSummary }>('/v1/diagrams/assist/status'),
  assist: (body: AssistRequest) => api.post<AssistReply>('/v1/diagrams/assist', body, headers()),
  pushTasks: (
    id: string,
    items: { id: string; title: string; context: string; due: string | null; priority: string }[],
  ) =>
    api.post<{ created: number; skipped: number }>(
      `/v1/diagrams/${encodeURIComponent(id)}/tasks`,
      { items: items.map((i) => ({ ...i, due: i.due ?? undefined })) },
      headers(),
    ),
  inputCapabilities: () => api.get<InputCapabilities>('/v1/diagram-inputs/capabilities'),
  extract: (file: File) => {
    const form = new FormData()
    form.append('file', file, file.name)
    return api.postForm<Extracted>('/v1/diagram-inputs/extract', form, headers())
  },
  fetchUrl: (url: string) =>
    api.post<Extracted>('/v1/diagram-inputs/fetch-url', { url }, headers()),
}
