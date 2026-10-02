/**
 * Outline editing (batch B4): the branch hierarchy as an indented list that can be edited with the
 * keyboard. Sibling order is the order of topics in the document, so moving a topic up or down
 * reorders that list; indent and outdent rewire the single branch link into the topic.
 */
import { newId, type Diagram, type DiagramNode } from './dmind'

export type OutlineRow = {
  id: string
  depth: number
  label: string
  hasChildren: boolean
  collapsed: boolean
  index: number
  /** What each outline action can do, decided once per row so a long outline renders cheaply. */
  canIndent: boolean
  canOutdent: boolean
  canMoveUp: boolean
  canMoveDown: boolean
}

type Tree = { roots: string[]; children: Map<string, string[]>; parent: Map<string, string>; index: Map<string, number> }

function tree(d: Diagram): Tree {
  const index = new Map(d.nodes.map((n, i) => [n.id, i]))
  const parent = new Map<string, string>()
  const children = new Map<string, string[]>(d.nodes.map((n) => [n.id, []]))
  for (const e of d.edges)
    if (e.kind === 'branch') {
      parent.set(e.target, e.source)
      children.get(e.source)!.push(e.target)
    }
  children.forEach((list) => list.sort((a, b) => index.get(a)! - index.get(b)!))
  return { roots: d.nodes.filter((n) => !parent.has(n.id)).map((n) => n.id), children, parent, index }
}

/** Depth-first rows in outline order, showing collapsed branches as a single row. */
export function outlineRows(d: Diagram, includeCollapsed = false): OutlineRow[] {
  const t = tree(d)
  const byId = new Map(d.nodes.map((n) => [n.id, n]))
  const rows: OutlineRow[] = []
  const place = new Map<string, number>() // position among siblings
  for (const list of [t.roots, ...t.children.values()]) list.forEach((id, i) => place.set(id, i))
  const stack = [...t.roots].reverse().map((id) => [id, 0] as [string, number])
  while (stack.length) {
    const [id, depth] = stack.pop()!
    const n = byId.get(id)!
    const kids = t.children.get(id)!
    const at = place.get(id)!
    const count = (t.parent.has(id) ? t.children.get(t.parent.get(id)!)! : t.roots).length
    rows.push({
      id,
      depth,
      label: n.label,
      hasChildren: kids.length > 0,
      collapsed: !!n.collapsed,
      index: t.index.get(id)!,
      canIndent: at > 0,
      canOutdent: t.parent.has(id),
      canMoveUp: at > 0,
      canMoveDown: at < count - 1,
    })
    if (n.collapsed && !includeCollapsed) continue
    for (let i = kids.length - 1; i >= 0; i--) stack.push([kids[i], depth + 1])
  }
  return rows
}

function moveTo(nodes: DiagramNode[], id: string, after: string): DiagramNode[] {
  const moving = nodes.find((n) => n.id === id)!
  const rest = nodes.filter((n) => n.id !== id)
  rest.splice(rest.findIndex((n) => n.id === after) + 1, 0, moving)
  return rest
}

function siblings(t: Tree, id: string): string[] {
  const p = t.parent.get(id)
  return p === undefined ? t.roots : t.children.get(p)!
}

/** Make the topic the last child of the sibling before it. Null when it has no previous sibling. */
export function indentNode(d: Diagram, id: string): Diagram | null {
  const t = tree(d)
  if (!t.index.has(id)) return null
  const sibs = siblings(t, id)
  const at = sibs.indexOf(id)
  if (at <= 0) return null
  const newParent = sibs[at - 1]
  const kids = t.children.get(newParent)!
  const last = kids.length ? kids.reduce((a, b) => (t.index.get(a)! > t.index.get(b)! ? a : b)) : newParent
  const edges = d.edges.filter((e) => !(e.kind === 'branch' && e.target === id))
  edges.push({ id: newId(), source: newParent, target: id, kind: 'branch' })
  const nodes = t.index.get(id)! > t.index.get(last)! ? d.nodes : moveTo(d.nodes, id, last)
  return { ...d, nodes, edges }
}

/** Make the topic the next sibling of its parent. Null when it is already at the top level. */
export function outdentNode(d: Diagram, id: string): Diagram | null {
  const t = tree(d)
  const parent = t.parent.get(id)
  if (parent === undefined) return null
  const grand = t.parent.get(parent)
  const edges = d.edges.filter((e) => !(e.kind === 'branch' && e.target === id))
  if (grand !== undefined) edges.push({ id: newId(), source: grand, target: id, kind: 'branch' })
  return { ...d, nodes: moveTo(d.nodes, id, parent), edges }
}

/** Swap the topic with its previous (-1) or next (+1) sibling. Null at either end. */
export function moveSibling(d: Diagram, id: string, dir: -1 | 1): Diagram | null {
  const t = tree(d)
  if (!t.index.has(id)) return null
  const sibs = siblings(t, id)
  const other = sibs[sibs.indexOf(id) + dir]
  if (other === undefined) return null
  const a = t.index.get(id)!,
    b = t.index.get(other)!
  const nodes = [...d.nodes]
  ;[nodes[a], nodes[b]] = [nodes[b], nodes[a]]
  return { ...d, nodes }
}

/**
 * A new topic as the next sibling of `id`, directly after it in the outline (after its whole
 * branch). The new topic is a branch child of the same parent, or a top-level topic when `id` is.
 */
export function addSiblingAfter(
  d: Diagram,
  id: string,
  label = 'New idea',
  newNodeId: string = newId(),
): { diagram: Diagram; id: string } | null {
  const t = tree(d)
  if (!t.index.has(id)) return null
  const parent = t.parent.get(id)
  const edges = parent === undefined ? d.edges : [...d.edges, { id: newId(), source: parent, target: newNodeId, kind: 'branch' as const }]
  const nodes = [...d.nodes]
  nodes.splice(t.index.get(id)! + 1, 0, { id: newNodeId, label, notes: '' })
  return { diagram: { ...d, nodes, edges }, id: newNodeId }
}
