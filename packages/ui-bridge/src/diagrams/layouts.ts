/**
 * Layout engines (batch B4). Pure functions: a diagram in, top-left positions out.
 *
 * Every layout is deterministic, finite and kept inside the schema's position bound (a deep or
 * huge graph is scaled to fit rather than rejected). Topics are 200 x 64; layouts keep centres far
 * enough apart that boxes do not overlap for any graph whose depth and width fit the bound.
 */
import type { Diagram } from './dmind'

export const NODE_W = 200
export const NODE_H = 64
export const POSITION_LIMIT = 90_000 // schema bound is 100000; stay clear of it
const MARGIN = 40

export type LayoutName = 'columns' | 'tree' | 'orgchart' | 'radial' | 'fishbone' | 'grid' | 'layered'
export const LAYOUTS: { id: LayoutName; label: string; hint: string }[] = [
  { id: 'tree', label: 'Tree (left to right)', hint: 'Branches grow to the right' },
  { id: 'orgchart', label: 'Org chart (top down)', hint: 'Branches grow downward' },
  { id: 'radial', label: 'Radial mind map', hint: 'Branches radiate from the centre' },
  { id: 'fishbone', label: 'Fishbone', hint: 'Causes along a spine to the first topic' },
  { id: 'layered', label: 'Flow (top down)', hint: 'Follows flow and dependency links' },
  { id: 'grid', label: 'Grid', hint: 'Rows and columns in topic order' },
  { id: 'columns', label: 'Columns', hint: 'One column per level' },
]
export type Point = { x: number; y: number }

export function isLayoutName(value: unknown): value is LayoutName {
  return typeof value === 'string' && LAYOUTS.some((l) => l.id === value)
}
export function defaultLayout(d: Diagram): LayoutName {
  const chosen = d.metadata?.layout
  if (isLayoutName(chosen)) return chosen
  return d.kind === 'flowchart' ? 'layered' : 'tree'
}

// ----------------------------------------------------------------------------- hierarchy

export type Hierarchy = {
  roots: string[]
  children: Map<string, string[]>
  parent: Map<string, string>
  depth: Map<string, number>
  maxDepth: number
  order: Map<string, number>
}

/**
 * The tree a layout draws: branch links when there are any, otherwise a spanning forest of the
 * flow/dependency links so flowcharts and systems still lay out as hierarchies. Children keep
 * topic order. Iterative, so a very deep chain cannot exhaust the call stack.
 */
export function hierarchy(d: Diagram): Hierarchy {
  const order = new Map(d.nodes.map((n, i) => [n.id, i]))
  const byOrder = (a: string, b: string) => order.get(a)! - order.get(b)!
  const branch = d.edges.filter((e) => e.kind === 'branch')
  const links = branch.length ? branch : d.edges.filter((e) => e.source !== e.target)
  const parent = new Map<string, string>()
  const children = new Map<string, string[]>(d.nodes.map((n) => [n.id, []]))
  if (branch.length) {
    for (const e of links) {
      parent.set(e.target, e.source)
      children.get(e.source)!.push(e.target)
    }
  } else {
    const out = new Map<string, string[]>(d.nodes.map((n) => [n.id, []]))
    const indeg = new Map(d.nodes.map((n) => [n.id, 0]))
    for (const e of links) {
      out.get(e.source)!.push(e.target)
      indeg.set(e.target, indeg.get(e.target)! + 1)
    }
    const seen = new Set<string>()
    const starts = d.nodes.filter((n) => indeg.get(n.id) === 0).map((n) => n.id)
    const queue: string[] = []
    const walk = (start: string) => {
      if (seen.has(start)) return
      seen.add(start)
      queue.push(start)
      while (queue.length) {
        const id = queue.shift()!
        for (const next of out.get(id)!.sort(byOrder)) {
          if (seen.has(next)) continue
          seen.add(next)
          parent.set(next, id)
          children.get(id)!.push(next)
          queue.push(next)
        }
      }
    }
    starts.forEach(walk)
    d.nodes.forEach((n) => walk(n.id)) // pure cycles have no source: start at the first topic
  }
  children.forEach((list) => list.sort(byOrder))
  const roots = d.nodes.filter((n) => !parent.has(n.id)).map((n) => n.id)
  const depth = new Map<string, number>()
  let maxDepth = 0
  const stack: (readonly [string, number])[] = roots.map((r) => [r, 0] as const).reverse()
  while (stack.length) {
    const [id, dep] = stack.pop()!
    depth.set(id, dep)
    maxDepth = Math.max(maxDepth, dep)
    const kids = children.get(id)!
    for (let i = kids.length - 1; i >= 0; i--) stack.push([kids[i], dep + 1])
  }
  return { roots, children, parent, depth, maxDepth, order }
}

/** Post-order list (children before parents), iterative. */
function postOrder(h: Hierarchy): string[] {
  const out: string[] = []
  const stack = h.roots.map((r) => [r, false] as [string, boolean]).reverse()
  while (stack.length) {
    const [id, expanded] = stack.pop()!
    if (expanded) {
      out.push(id)
      continue
    }
    stack.push([id, true])
    const kids = h.children.get(id)!
    for (let i = kids.length - 1; i >= 0; i--) stack.push([kids[i], false])
  }
  return out
}

// ----------------------------------------------------------------------------- shared

/** Shift to the margin, round, and scale down uniformly if the drawing exceeds the position bound. */
function finalize(raw: Map<string, Point>): Map<string, Point> {
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity
  raw.forEach((p) => {
    minX = Math.min(minX, p.x)
    minY = Math.min(minY, p.y)
    maxX = Math.max(maxX, p.x)
    maxY = Math.max(maxY, p.y)
  })
  const extent = Math.max(maxX - minX, maxY - minY, 1)
  const scale = extent > POSITION_LIMIT - MARGIN * 2 ? (POSITION_LIMIT - MARGIN * 2) / extent : 1
  const out = new Map<string, Point>()
  raw.forEach((p, id) =>
    out.set(id, {
      x: Math.round((p.x - minX) * scale) + MARGIN,
      y: Math.round((p.y - minY) * scale) + MARGIN,
    }),
  )
  return out
}

/** Spacing that shrinks only when a very deep chain would otherwise leave the position bound. */
const gap = (base: number, levels: number) => Math.min(base, (POSITION_LIMIT * 0.9) / Math.max(levels, 1))

// ----------------------------------------------------------------------------- layouts

function leafSlots(h: Hierarchy): Map<string, number> {
  // Leaves take consecutive slots; a parent sits at the middle of its children.
  const slot = new Map<string, number>()
  let next = 0
  for (const id of postOrder(h)) {
    const kids = h.children.get(id)!
    if (!kids.length) slot.set(id, next++)
    else slot.set(id, (slot.get(kids[0])! + slot.get(kids[kids.length - 1])!) / 2)
  }
  return slot
}

function treeLayout(d: Diagram, horizontal: boolean): Map<string, Point> {
  const h = hierarchy(d)
  const slot = leafSlots(h)
  const levelGap = gap(horizontal ? 270 : 130, h.maxDepth + 1)
  const slotGap = horizontal ? 96 : 230
  const out = new Map<string, Point>()
  for (const n of d.nodes) {
    const level = h.depth.get(n.id)! * levelGap
    const across = slot.get(n.id)! * slotGap
    out.set(n.id, horizontal ? { x: level, y: across } : { x: across, y: level })
  }
  return finalize(out)
}

function columnsLayout(d: Diagram): Map<string, Point> {
  const h = hierarchy(d)
  const colGap = gap(260, h.maxDepth + 1)
  const out = new Map<string, Point>()
  let row = 0
  for (const n of d.nodes) {
    const x = d.kind === 'flowchart' ? 0 : h.depth.get(n.id)! * colGap
    out.set(n.id, { x, y: row++ * 100 })
  }
  return finalize(out)
}

function gridLayout(d: Diagram): Map<string, Point> {
  const cols = Math.max(1, Math.ceil(Math.sqrt(d.nodes.length * 1.6)))
  const out = new Map<string, Point>()
  d.nodes.forEach((n, i) => out.set(n.id, { x: (i % cols) * 260, y: Math.floor(i / cols) * 110 }))
  return finalize(out)
}

function radialLayout(d: Diagram): Map<string, Point> {
  const h = hierarchy(d)
  const leaves = new Map<string, number>()
  for (const id of postOrder(h)) {
    const kids = h.children.get(id)!
    leaves.set(id, kids.length ? kids.reduce((s, k) => s + leaves.get(k)!, 0) : 1)
  }
  // Angular span per topic, proportional to its leaves; the first root sits at the centre when alone.
  const total = h.roots.reduce((s, r) => s + leaves.get(r)!, 0)
  const spans = new Map<string, [number, number]>()
  let cursor = 0
  for (const r of h.roots) {
    const w = (leaves.get(r)! / total) * Math.PI * 2
    spans.set(r, [cursor, cursor + w])
    cursor += w
  }
  const stack = [...h.roots].reverse()
  while (stack.length) {
    const id = stack.pop()!
    const [a, b] = spans.get(id)!
    let at = a
    for (const k of h.children.get(id)!) {
      const w = ((b - a) * leaves.get(k)!) / leaves.get(id)!
      spans.set(k, [at, at + w])
      at += w
    }
    for (const k of [...h.children.get(id)!].reverse()) stack.push(k)
  }
  const single = h.roots.length === 1
  const byDepth = new Map<number, string[]>()
  d.nodes.forEach((n) => {
    const dep = h.depth.get(n.id)! + (single ? 0 : 1)
    byDepth.set(dep, [...(byDepth.get(dep) || []), n.id])
  })
  // Ring radius: at least one ring gap further out, and wide enough that neighbours do not touch.
  const radius = new Map<number, number>([[0, 0]])
  const mid = (id: string) => (spans.get(id)![0] + spans.get(id)![1]) / 2
  const ring = gap(260, byDepth.size)
  for (const dep of [...byDepth.keys()].sort((x, y) => x - y)) {
    if (dep === 0) continue
    const ids = byDepth.get(dep)!
    let need = 0
    if (ids.length > 1) {
      const angles = ids.map((id) => ({ a: mid(id), w: spans.get(id)![1] - spans.get(id)![0] })).sort((p, q) => p.a - q.a)
      let minSep = Infinity
      for (let i = 0; i < angles.length; i++) {
        const next = angles[(i + 1) % angles.length]
        const sep = (angles[i].w + next.w) / 2
        minSep = Math.min(minSep, sep)
      }
      need = minSep > 0 ? 240 / Math.min(minSep, Math.PI) : 0
    }
    radius.set(dep, Math.max((radius.get(dep - 1) ?? 0) + ring, need))
  }
  const out = new Map<string, Point>()
  for (const n of d.nodes) {
    const dep = h.depth.get(n.id)! + (single ? 0 : 1)
    const r = radius.get(dep)!
    const a = mid(n.id)
    out.set(n.id, { x: r * Math.cos(a), y: r * Math.sin(a) })
  }
  return finalize(out)
}

function fishboneLayout(d: Diagram): Map<string, Point> {
  const h = hierarchy(d)
  const head = h.roots[0]
  const out = new Map<string, Point>()
  const cats = h.children.get(head)!
  const headX = (Math.ceil(cats.length / 2) + 1) * 340
  out.set(head, { x: headX, y: 0 })
  cats.forEach((cat, i) => {
    const side = i % 2 === 0 ? -1 : 1
    const x = headX - 340 * (Math.floor(i / 2) + 1)
    out.set(cat, { x, y: side * 220 })
    let rib = 0
    const stack: (readonly [string, number])[] = [...h.children.get(cat)!].reverse().map((id) => [id, 1] as const)
    while (stack.length) {
      const [id, rel] = stack.pop()!
      rib++
      out.set(id, { x: x - 30 * Math.min(rel, 3), y: side * (220 + 100 * rib) })
      const kids = h.children.get(id)!
      for (let k = kids.length - 1; k >= 0; k--) stack.push([kids[k], rel + 1] as const)
    }
  })
  // Anything outside the first topic's tree goes in rows beneath the diagram.
  const rest = d.nodes.filter((n) => !out.has(n.id))
  let maxY = 0
  out.forEach((p) => (maxY = Math.max(maxY, p.y)))
  const cols = Math.max(1, Math.ceil(Math.sqrt(rest.length * 1.6)))
  rest.forEach((n, i) => out.set(n.id, { x: (i % cols) * 260, y: maxY + 220 + Math.floor(i / cols) * 110 }))
  return finalize(out)
}

/** Layered drawing of directed links: back edges are ignored for layering, longest path decides rows. */
function layeredLayout(d: Diagram): Map<string, Point> {
  const links = d.edges.filter((e) => e.kind !== 'branch' && e.source !== e.target)
  if (!links.length) return treeLayout(d, false)
  const order = new Map(d.nodes.map((n, i) => [n.id, i]))
  const out_ = new Map<string, string[]>(d.nodes.map((n) => [n.id, []]))
  const indeg = new Map(d.nodes.map((n) => [n.id, 0]))
  for (const e of links) {
    out_.get(e.source)!.push(e.target)
    indeg.set(e.target, indeg.get(e.target)! + 1)
  }
  out_.forEach((l) => l.sort((a, b) => order.get(a)! - order.get(b)!))
  // 1. find back edges with an iterative depth-first search from the sources (then any leftovers)
  const state = new Map<string, 0 | 1 | 2>()
  const back = new Set<string>()
  const dfs = (start: string) => {
    if (state.has(start)) return
    const stack: [string, number][] = [[start, 0]]
    state.set(start, 1)
    while (stack.length) {
      const top = stack[stack.length - 1]
      const [id, i] = top
      const next = out_.get(id)![i]
      if (next === undefined) {
        state.set(id, 2)
        stack.pop()
        continue
      }
      top[1]++
      if (!state.has(next)) {
        state.set(next, 1)
        stack.push([next, 0])
      } else if (state.get(next) === 1) back.add(id + '\u0000' + next)
    }
  }
  d.nodes.filter((n) => indeg.get(n.id) === 0).forEach((n) => dfs(n.id))
  d.nodes.forEach((n) => dfs(n.id))
  // 2. longest-path layering on the remaining DAG (Kahn)
  const layer = new Map(d.nodes.map((n) => [n.id, 0]))
  const left = new Map(d.nodes.map((n) => [n.id, 0]))
  const preds = new Map<string, string[]>(d.nodes.map((n) => [n.id, []]))
  for (const e of links) {
    if (back.has(e.source + '\u0000' + e.target)) continue
    left.set(e.target, left.get(e.target)! + 1)
    preds.get(e.target)!.push(e.source)
  }
  const ready = d.nodes.filter((n) => left.get(n.id) === 0).map((n) => n.id)
  while (ready.length) {
    const id = ready.shift()!
    for (const next of out_.get(id)!) {
      if (back.has(id + '\u0000' + next)) continue
      layer.set(next, Math.max(layer.get(next)!, layer.get(id)! + 1))
      left.set(next, left.get(next)! - 1)
      if (left.get(next) === 0) ready.push(next)
    }
  }
  // 3. order within each layer: topic order, then two barycentre sweeps to reduce crossings
  const layers: string[][] = []
  d.nodes.forEach((n) => (layers[layer.get(n.id)!] ||= []).push(n.id))
  const pos = new Map<string, number>()
  const place = () => layers.forEach((ids) => ids.forEach((id, i) => pos.set(id, i)))
  place()
  const succs = new Map<string, string[]>(d.nodes.map((n) => [n.id, []]))
  preds.forEach((ps, id) => ps.forEach((p) => succs.get(p)!.push(id)))
  const sweep = (neighbours: Map<string, string[]>, from: number, to: number, step: number) => {
    for (let l = from; l !== to; l += step) {
      const ids = layers[l] || []
      const key = (id: string) => {
        const ns = neighbours.get(id)!.filter((n) => layer.get(n) !== layer.get(id))
        return ns.length ? ns.reduce((s, n) => s + pos.get(n)!, 0) / ns.length : pos.get(id)!
      }
      ids.sort((a, b) => key(a) - key(b) || order.get(a)! - order.get(b)!)
      ids.forEach((id, i) => pos.set(id, i))
    }
  }
  for (let pass = 0; pass < 2; pass++) {
    sweep(preds, 1, layers.length, 1)
    sweep(succs, layers.length - 2, -1, -1)
  }
  const colGap = 240
  const rowGap = gap(130, layers.length)
  const out = new Map<string, Point>()
  layers.forEach((ids, l) => ids.forEach((id, i) => out.set(id, { x: i * colGap, y: l * rowGap })))
  return finalize(out)
}

/** Positions (top-left) for every topic under the named layout. */
export function computeLayout(d: Diagram, name: LayoutName = defaultLayout(d)): Map<string, Point> {
  switch (name) {
    case 'orgchart':
      return treeLayout(d, false)
    case 'radial':
      return radialLayout(d)
    case 'fishbone':
      return fishboneLayout(d)
    case 'grid':
      return gridLayout(d)
    case 'layered':
      return layeredLayout(d)
    case 'columns':
      return columnsLayout(d)
    default:
      return treeLayout(d, true)
  }
}

/** A copy of the diagram with every topic positioned by the named layout and the choice recorded. */
export function applyLayout(d: Diagram, name: LayoutName): Diagram {
  const pos = computeLayout(d, name)
  return {
    ...d,
    metadata: { ...d.metadata, layout: name },
    nodes: d.nodes.map((n) => ({ ...n, position: pos.get(n.id)! })),
  }
}

// ----------------------------------------------------------------------------- edges

export type EdgeGeometry = { d: string; mid: Point }

/** A smooth connector between two topic boxes, leaving and entering through facing sides. */
export function edgePath(a: Point, b: Point): EdgeGeometry {
  if (a.x === b.x && a.y === b.y) {
    // A link from a topic to itself (a retry or feedback loop) arcs over the top.
    const x = a.x + NODE_W / 2
    return { d: `M${x - 40},${a.y} C${x - 60},${a.y - 70} ${x + 60},${a.y - 70} ${x + 40},${a.y}`, mid: { x, y: a.y - 52 } }
  }
  const dx = b.x - a.x,
    dy = b.y - a.y
  if (Math.abs(dx) >= Math.abs(dy) * 1.2) {
    const s: Point = { x: a.x + (dx > 0 ? NODE_W : 0), y: a.y + NODE_H / 2 }
    const t: Point = { x: b.x + (dx > 0 ? 0 : NODE_W), y: b.y + NODE_H / 2 }
    const k = Math.abs(t.x - s.x) / 2
    const sign = dx > 0 ? 1 : -1
    return {
      d: `M${s.x},${s.y} C${s.x + sign * k},${s.y} ${t.x - sign * k},${t.y} ${t.x},${t.y}`,
      mid: { x: (s.x + t.x) / 2, y: (s.y + t.y) / 2 },
    }
  }
  const s: Point = { x: a.x + NODE_W / 2, y: a.y + (dy > 0 ? NODE_H : 0) }
  const t: Point = { x: b.x + NODE_W / 2, y: b.y + (dy > 0 ? 0 : NODE_H) }
  const k = Math.abs(t.y - s.y) / 2
  const sign = dy > 0 ? 1 : -1
  return {
    d: `M${s.x},${s.y} C${s.x},${s.y + sign * k} ${t.x},${t.y - sign * k} ${t.x},${t.y}`,
    mid: { x: (s.x + t.x) / 2, y: (s.y + t.y) / 2 },
  }
}
