/**
 * Source provenance (batch B3): which document or page each generated topic came from.
 *
 * Matching is by content, not position, so it survives the person editing the text, mixing
 * several sources, or reordering lines: a topic cites a source when its label equals a line of
 * that source's extracted text. Topics the person wrote themselves carry no citation.
 */
import { clone, outlineLabel, validateDiagram, type Diagram } from './dmind'

export type SourceRef = {
  id: string
  kind: 'file' | 'url'
  name?: string
  url?: string
  bytes?: number
  sha256?: string
  extractor?: string
  pages?: number
  title?: string
  fetched_at?: string
}
export type SourceText = { ref: SourceRef; text: string }
export type Citation = { source: string; line: number }

export const MAX_CITATIONS = 3

/** A short, stable id for a source within one diagram. */
export function sourceId(index: number): string {
  return `src${index + 1}`
}

export function describeSource(ref: SourceRef): string {
  const what = ref.kind === 'url' ? ref.url || 'web page' : ref.name || 'document'
  const extra = [ref.extractor, ref.pages ? `${ref.pages} pages` : '', ref.bytes ? `${ref.bytes} bytes` : '']
    .filter(Boolean)
    .join(', ')
  return extra ? `${what} (${extra})` : what
}

export function attachProvenance(d: Diagram, sources: SourceText[]): Diagram {
  if (!sources.length) return d
  const index = new Map<string, Citation[]>()
  for (const { ref, text } of sources)
    text.split(/\r\n|[\n\r]/).forEach((line, i) => {
      const label = outlineLabel(line).replace(/\s+/g, ' ')
      if (!label) return
      const list = index.get(label) || []
      if (list.length < MAX_CITATIONS) list.push({ source: ref.id, line: i + 1 })
      index.set(label, list)
    })
  const out = clone(d)
  const cited = new Set<string>()
  out.nodes.forEach((n) => {
    if (n.id === 'root') return // the topic the person typed is theirs
    const hits = index.get(n.label.replace(/\s+/g, ' '))
    if (!hits) return
    n.metadata = { ...n.metadata, provenance: hits }
    hits.forEach((h) => cited.add(h.source))
  })
  const used = sources.filter((s) => cited.has(s.ref.id)).map((s) => s.ref)
  if (used.length) out.metadata = { ...out.metadata, sources: used }
  return validateDiagram(out)
}

/** The citations on a topic, resolved against the diagram's sources, for display. */
export function citationsFor(d: Diagram, nodeId: string): { text: string }[] {
  const node = d.nodes.find((n) => n.id === nodeId)
  const cites = (node?.metadata?.provenance as Citation[] | undefined) || []
  const refs = (d.metadata?.sources as SourceRef[] | undefined) || []
  return cites.map((c) => {
    const ref = refs.find((r) => r.id === c.source)
    return { text: `${ref ? describeSource(ref) : c.source}, line ${c.line}` }
  })
}
