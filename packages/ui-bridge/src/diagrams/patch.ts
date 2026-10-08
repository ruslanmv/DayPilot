/**
 * Patch proposals (batch B6). A model, the solver or a person proposes a bounded list of
 * operations against a specific document state; the editor shows the diff and the person
 * applies it explicitly. Nothing is applied partially: either every operation holds and the
 * result is a valid dmind/v1 document, or the patch is rejected with the reason.
 */
import { diffDiagrams, type DiagramDiff } from './diff'
import { clone, validateDiagram, type Diagram, type DiagramEdge, type DiagramNode } from './dmind'

export const PATCH_SCHEMA = 'dmind-patch/v1'
export const MAX_PATCH_OPS = 200
export type PatchOrigin = 'model' | 'solver' | 'user'

type NodeSet = Partial<Pick<DiagramNode, 'label' | 'notes' | 'collapsed'>>
type EdgeSet = Partial<Pick<DiagramEdge, 'source' | 'target' | 'kind' | 'label'>>
export type PatchOp =
  | { op: 'set_title'; title: string }
  | { op: 'add_node'; node: { id: string; label: string; notes?: string } }
  | { op: 'update_node'; id: string; set: NodeSet }
  | { op: 'remove_node'; id: string }
  | { op: 'add_edge'; edge: DiagramEdge }
  | { op: 'update_edge'; id: string; set: EdgeSet }
  | { op: 'remove_edge'; id: string }
export type Patch = {
  schema: typeof PATCH_SCHEMA
  /** The exact document state the patch was written against (see `hashDiagram`). */
  base: { id: string; hash: string }
  origin: PatchOrigin
  summary: string
  ops: PatchOp[]
}
export type PatchResult =
  | { ok: true; diagram: Diagram; diff: DiagramDiff }
  | { ok: false; reason: 'stale' | 'invalid'; message: string }

const NODE_SET = ['label', 'notes', 'collapsed']
const EDGE_SET = ['source', 'target', 'kind', 'label']

function canonical(v: unknown): string {
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']'
  if (v && typeof v === 'object')
    return '{' + Object.keys(v).sort().map((k) => JSON.stringify(k) + ':' + canonical((v as Record<string, unknown>)[k])).join(',') + '}'
  return JSON.stringify(v)
}

/** SHA-256 of the canonical JSON of a document; positions are part of the state. */
export async function hashDiagram(d: Diagram): Promise<string> {
  const bytes = new TextEncoder().encode(canonical(d))
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))
  return [...digest].map((b) => b.toString(16).padStart(2, '0')).join('')
}

export async function makePatch(base: Diagram, origin: PatchOrigin, summary: string, ops: PatchOp[]): Promise<Patch> {
  return { schema: PATCH_SCHEMA, base: { id: base.id, hash: await hashDiagram(base) }, origin, summary, ops }
}

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const only = (o: Record<string, unknown>, allowed: string[], where: string) => {
  const extra = Object.keys(o).filter((k) => !allowed.includes(k))
  if (extra.length) throw new Error(`${where}: unexpected ${extra.join(', ')}`)
}

/** Shape check of untrusted patch JSON (for example a model reply). Throws a readable error. */
export function parsePatch(value: unknown): Patch {
  if (!isObj(value)) throw new Error('Patch must be an object')
  only(value, ['schema', 'base', 'origin', 'summary', 'ops'], 'patch')
  if (value.schema !== PATCH_SCHEMA) throw new Error(`Patch schema must be ${PATCH_SCHEMA}`)
  const base = value.base
  if (!isObj(base) || typeof base.id !== 'string' || typeof base.hash !== 'string' || !/^[0-9a-f]{64}$/.test(base.hash))
    throw new Error('Patch needs base.id and a 64-character base.hash')
  if (!['model', 'solver', 'user'].includes(value.origin as string)) throw new Error('Patch origin must be model, solver or user')
  if (typeof value.summary !== 'string' || value.summary.length > 500) throw new Error('Patch summary must be text up to 500 characters')
  if (!Array.isArray(value.ops) || !value.ops.length) throw new Error('Patch has no operations')
  if (value.ops.length > MAX_PATCH_OPS) throw new Error(`A patch may hold at most ${MAX_PATCH_OPS} operations`)
  value.ops.forEach((raw, i) => {
    const w = `op ${i + 1}`
    if (!isObj(raw)) throw new Error(`${w}: must be an object`)
    switch (raw.op) {
      case 'set_title':
        only(raw, ['op', 'title'], w)
        if (typeof raw.title !== 'string') throw new Error(`${w}: title must be text`)
        break
      case 'add_node':
        only(raw, ['op', 'node'], w)
        if (!isObj(raw.node)) throw new Error(`${w}: node required`)
        only(raw.node, ['id', 'label', 'notes'], w)
        break
      case 'update_node':
      case 'update_edge': {
        only(raw, ['op', 'id', 'set'], w)
        if (typeof raw.id !== 'string' || !isObj(raw.set) || !Object.keys(raw.set).length) throw new Error(`${w}: id and a non-empty set required`)
        only(raw.set, raw.op === 'update_node' ? NODE_SET : EDGE_SET, w)
        break
      }
      case 'remove_node':
      case 'remove_edge':
        only(raw, ['op', 'id'], w)
        if (typeof raw.id !== 'string') throw new Error(`${w}: id required`)
        break
      case 'add_edge':
        only(raw, ['op', 'edge'], w)
        if (!isObj(raw.edge)) throw new Error(`${w}: edge required`)
        only(raw.edge, ['id', 'source', 'target', 'kind', 'label'], w)
        break
      default:
        throw new Error(`${w}: unknown operation`)
    }
  })
  return value as unknown as Patch
}

/**
 * Apply a patch to the document it was written against. Rejected as `stale` when the base id or
 * hash differs, and as `invalid` when an operation does not hold or the result breaks the contract.
 */
export async function applyPatch(current: Diagram, patch: Patch): Promise<PatchResult> {
  try {
    parsePatch(patch)
  } catch (e) {
    return { ok: false, reason: 'invalid', message: (e as Error).message }
  }
  if (patch.base.id !== current.id || patch.base.hash !== (await hashDiagram(current)))
    return { ok: false, reason: 'stale', message: 'The diagram changed after this proposal was made. Ask for a new one.' }
  const next = clone(current)
  try {
    patch.ops.forEach((op, i) => step(next, op, `op ${i + 1}`))
    const diagram = validateDiagram(next)
    return { ok: true, diagram, diff: diffDiagrams(current, diagram) }
  } catch (e) {
    return { ok: false, reason: 'invalid', message: (e as Error).message }
  }
}

function step(d: Diagram, op: PatchOp, w: string) {
  const node = (id: string) => d.nodes.find((n) => n.id === id)
  const edge = (id: string) => d.edges.find((e) => e.id === id)
  switch (op.op) {
    case 'set_title':
      d.title = op.title
      break
    case 'add_node':
      if (node(op.node.id)) throw new Error(`${w}: topic ${op.node.id} already exists`)
      d.nodes.push({ ...op.node })
      break
    case 'update_node': {
      const n = node(op.id)
      if (!n) throw new Error(`${w}: no topic ${op.id}`)
      Object.assign(n, op.set)
      break
    }
    case 'remove_node':
      if (!node(op.id)) throw new Error(`${w}: no topic ${op.id}`)
      d.nodes = d.nodes.filter((n) => n.id !== op.id)
      d.edges = d.edges.filter((e) => e.source !== op.id && e.target !== op.id)
      if (!d.nodes.length) throw new Error(`${w}: a diagram needs at least one topic`)
      break
    case 'add_edge':
      if (edge(op.edge.id)) throw new Error(`${w}: link ${op.edge.id} already exists`)
      d.edges.push({ ...op.edge })
      break
    case 'update_edge': {
      const e = edge(op.id)
      if (!e) throw new Error(`${w}: no link ${op.id}`)
      Object.assign(e, op.set)
      break
    }
    case 'remove_edge':
      if (!edge(op.id)) throw new Error(`${w}: no link ${op.id}`)
      d.edges = d.edges.filter((e) => e.id !== op.id)
      break
  }
}
