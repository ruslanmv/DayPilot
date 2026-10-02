import { api } from '../apiClient'
import type { Diagram, DiagramKind } from './dmind'
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
}
function headers() {
  const match = document.cookie.match(/(?:^|;\s*)dp_csrf=([^;]+)/)
  return {
    headers: { 'X-CSRF-Token': match ? decodeURIComponent(match[1]) : '' },
  }
}
export const diagramsApi = {
  list: () => api.get<{ items: DiagramSummary[] }>('/v1/diagrams'),
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
  revisions: (id: string) =>
    api.get<{ items: { revision: number; document: Diagram }[] }>(
      `/v1/diagrams/${encodeURIComponent(id)}/revisions`,
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
}
