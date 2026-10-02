/** Semantic comparison of two dmind documents (batch B2), used for revision history and later patches. */
import type { Diagram, DiagramEdge, DiagramNode } from './dmind'

export type NodeChange = { id: string; label: string; fields: string[]; before: DiagramNode; after: DiagramNode }
export type EdgeChange = { id: string; fields: string[]; before: DiagramEdge; after: DiagramEdge }
export type DiagramDiff = {
  title?: [string, string]
  kind?: [string, string]
  nodes: { added: DiagramNode[]; removed: DiagramNode[]; changed: NodeChange[]; moved: string[] }
  edges: { added: DiagramEdge[]; removed: DiagramEdge[]; changed: EdgeChange[] }
  summary: string[]
  empty: boolean
}

const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null)
const q = (s: string) => `"${s.length > 40 ? s.slice(0, 39) + '…' : s}"`

export function diffDiagrams(before: Diagram, after: Diagram): DiagramDiff {
  const a = new Map(before.nodes.map((n) => [n.id, n]))
  const b = new Map(after.nodes.map((n) => [n.id, n]))
  const nodes: DiagramDiff['nodes'] = { added: [], removed: [], changed: [], moved: [] }
  for (const [id, n] of b) {
    const old = a.get(id)
    if (!old) {
      nodes.added.push(n)
      continue
    }
    const fields = ['label', 'notes', 'collapsed', 'metadata'].filter(
      (f) => !same((old as Record<string, unknown>)[f], (n as Record<string, unknown>)[f]),
    )
    if (fields.length) nodes.changed.push({ id, label: n.label, fields, before: old, after: n })
    if (!same(old.position, n.position) && old.position && n.position) nodes.moved.push(id)
  }
  for (const [id, n] of a) if (!b.has(id)) nodes.removed.push(n)

  const ea = new Map(before.edges.map((e) => [e.id, e]))
  const eb = new Map(after.edges.map((e) => [e.id, e]))
  const edges: DiagramDiff['edges'] = { added: [], removed: [], changed: [] }
  for (const [id, e] of eb) {
    const old = ea.get(id)
    if (!old) edges.added.push(e)
    else {
      const fields = ['source', 'target', 'kind', 'label'].filter(
        (f) => !same((old as Record<string, unknown>)[f], (e as Record<string, unknown>)[f]),
      )
      if (fields.length) edges.changed.push({ id, fields, before: old, after: e })
    }
  }
  for (const [id, e] of ea) if (!eb.has(id)) edges.removed.push(e)

  const out: DiagramDiff = { nodes, edges, summary: [], empty: false }
  if (before.title !== after.title) out.title = [before.title, after.title]
  if (before.kind !== after.kind) out.kind = [before.kind, after.kind]
  const s = out.summary
  if (out.title) s.push(`Title: ${q(out.title[0])} → ${q(out.title[1])}`)
  if (out.kind) s.push(`Type: ${out.kind[0]} → ${out.kind[1]}`)
  nodes.added.forEach((n) => s.push(`Added topic ${q(n.label)}`))
  nodes.removed.forEach((n) => s.push(`Removed topic ${q(n.label)}`))
  nodes.changed.forEach((c) => {
    if (c.fields.includes('label')) s.push(`Renamed ${q(c.before.label)} → ${q(c.after.label)}`)
    const rest = c.fields.filter((f) => f !== 'label')
    if (rest.length) s.push(`Changed ${rest.join(', ')} of ${q(c.after.label)}`)
  })
  if (nodes.moved.length) s.push(`Moved ${nodes.moved.length} topic(s)`)
  const name = (d: Diagram, id: string) => d.nodes.find((n) => n.id === id)?.label ?? id
  edges.added.forEach((e) => s.push(`Added ${e.kind} link ${q(name(after, e.source))} → ${q(name(after, e.target))}${e.label ? ` (${e.label})` : ''}`))
  edges.removed.forEach((e) => s.push(`Removed ${e.kind} link ${q(name(before, e.source))} → ${q(name(before, e.target))}`))
  edges.changed.forEach((c) => s.push(`Changed ${c.fields.join(', ')} of a ${c.after.kind} link`))
  out.empty = s.length === 0
  return out
}
