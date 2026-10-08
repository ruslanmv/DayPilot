/**
 * Pure editing operations (batch B4): multi-selection, re-parenting, metadata, links and
 * keyboard navigation. Each returns a new diagram (or null/an error) and never mutates its input.
 */
import { clone, layout, newId, type Diagram, type DiagramNode } from './dmind'
import { MAX_MARKERS, cleanMarkers, markerById } from './style'

const POSITION_CLAMP = 99_000

function branchChildren(d: Diagram): Map<string, string[]> {
  const children = new Map<string, string[]>()
  for (const e of d.edges)
    if (e.kind === 'branch') children.set(e.source, [...(children.get(e.source) || []), e.target])
  return children
}

/** Every topic beneath `id` along branch links (not including `id`). */
export function descendants(d: Diagram, id: string): Set<string> {
  const children = branchChildren(d)
  const out = new Set<string>()
  const stack = [...(children.get(id) || [])]
  while (stack.length) {
    const next = stack.pop()!
    if (out.has(next)) continue
    out.add(next)
    stack.push(...(children.get(next) || []))
  }
  return out
}

/** Topics `id` may move under: everything except itself and its own branches. */
export function validParents(d: Diagram, id: string): string[] {
  const below = descendants(d, id)
  return d.nodes.filter((n) => n.id !== id && !below.has(n.id)).map((n) => n.id)
}

export function parentOf(d: Diagram, id: string): string | null {
  return d.edges.find((e) => e.kind === 'branch' && e.target === id)?.source ?? null
}

/** Move `id` (with its branch) under `parentId`, or make it a root with `null`. */
export function reparent(
  d: Diagram,
  id: string,
  parentId: string | null,
): { diagram: Diagram } | { error: string } {
  if (!d.nodes.some((n) => n.id === id)) return { error: 'That topic no longer exists.' }
  if (parentId !== null) {
    if (!d.nodes.some((n) => n.id === parentId)) return { error: 'The new parent no longer exists.' }
    if (parentId === id || descendants(d, id).has(parentId))
      return { error: 'A topic cannot move under itself or one of its own branches.' }
  }
  if (parentOf(d, id) === parentId) return { diagram: d }
  const edges = d.edges.filter((e) => !(e.kind === 'branch' && e.target === id))
  if (parentId !== null) edges.push({ id: newId(), source: parentId, target: id, kind: 'branch' })
  return { diagram: { ...d, edges } }
}

/** Remove several topics and their branches. Null when nothing would remain (or nothing matched). */
export function removeBranches(d: Diagram, ids: Iterable<string>): Diagram | null {
  const children = branchChildren(d)
  const removed = new Set<string>()
  for (const id of ids) {
    if (!d.nodes.some((n) => n.id === id)) continue
    removed.add(id)
    const stack = [...(children.get(id) || [])]
    while (stack.length) {
      const next = stack.pop()!
      if (removed.has(next)) continue
      removed.add(next)
      stack.push(...(children.get(next) || []))
    }
  }
  if (!removed.size || removed.size >= d.nodes.length) return null
  return {
    ...d,
    nodes: d.nodes.filter((n) => !removed.has(n.id)),
    edges: d.edges.filter((e) => !removed.has(e.source) && !removed.has(e.target)),
  }
}

/** Shift topics by (dx, dy). Every topic gets a concrete position first, so nothing else moves. */
export function moveNodes(d: Diagram, ids: Iterable<string>, dx: number, dy: number): Diagram {
  const set = new Set(ids)
  const full = layout(d)
  const clamp = (v: number) => Math.max(-POSITION_CLAMP, Math.min(POSITION_CLAMP, Math.round(v)))
  return {
    ...full,
    nodes: full.nodes.map((n) =>
      set.has(n.id) ? { ...n, position: { x: clamp(n.position!.x + dx), y: clamp(n.position!.y + dy) } } : n,
    ),
  }
}

export function patchNodes(d: Diagram, ids: Iterable<string>, patch: Partial<DiagramNode>): Diagram {
  const set = new Set(ids)
  return { ...d, nodes: d.nodes.map((n) => (set.has(n.id) ? { ...n, ...patch } : n)) }
}

/** Set (or with undefined, remove) one metadata key on several topics. */
export function setNodeMeta(d: Diagram, ids: Iterable<string>, key: string, value: unknown): Diagram {
  const set = new Set(ids)
  return {
    ...d,
    nodes: d.nodes.map((n) => {
      if (!set.has(n.id)) return n
      const meta = { ...n.metadata }
      if (value === undefined) delete meta[key]
      else meta[key] = clone(value)
      const next: DiagramNode = { ...n, metadata: meta }
      if (!Object.keys(meta).length) delete next.metadata
      return next
    }),
  }
}

/** Add the marker to every selected topic, or remove it if all of them already have it. */
export function toggleMarker(d: Diagram, ids: Iterable<string>, marker: string): Diagram {
  if (!markerById(marker)) return d
  const set = new Set(ids)
  const targets = d.nodes.filter((n) => set.has(n.id))
  const all = targets.length > 0 && targets.every((n) => cleanMarkers(n.metadata?.markers).includes(marker))
  return {
    ...d,
    nodes: d.nodes.map((n) => {
      if (!set.has(n.id)) return n
      const have = cleanMarkers(n.metadata?.markers)
      const next = all ? have.filter((m) => m !== marker) : have.includes(marker) ? have : [...have, marker].slice(0, MAX_MARKERS)
      const meta = { ...n.metadata }
      if (next.length) meta.markers = next
      else delete meta.markers
      const out: DiagramNode = { ...n, metadata: meta }
      if (!Object.keys(meta).length) delete out.metadata
      return out
    }),
  }
}

export { safeHref } from './links'

export type Direction = 'left' | 'right' | 'up' | 'down'
/** The topic nearest to `from` in a direction, preferring ones that are roughly in line with it. */
export function nearestInDirection(
  positions: Map<string, { x: number; y: number }>,
  from: string,
  dir: Direction,
  allowed?: Set<string>,
): string | null {
  const origin = positions.get(from)
  if (!origin) return null
  let best: string | null = null
  let bestScore = Infinity
  for (const [id, p] of positions) {
    if (id === from || (allowed && !allowed.has(id))) continue
    const dx = p.x - origin.x,
      dy = p.y - origin.y
    const along = dir === 'right' ? dx : dir === 'left' ? -dx : dir === 'down' ? dy : -dy
    const across = dir === 'left' || dir === 'right' ? Math.abs(dy) : Math.abs(dx)
    if (along <= 0 || across > along * 2.5 + 40) continue
    const score = along + across * 2
    if (score < bestScore || (score === bestScore && best !== null && id < best)) {
      best = id
      bestScore = score
    }
  }
  return best
}
