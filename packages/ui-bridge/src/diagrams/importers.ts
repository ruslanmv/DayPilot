/**
 * Import-only adapters for other tools' files (batch B10): OPML and XMind (Zen, content.json).
 * They never write those formats, always produce a new dmind draft, bound every dimension and say
 * exactly what could not be carried over. No XML entity or DOCTYPE is ever expanded or fetched.
 */
import { newId, validateDiagram, type Diagram, type DiagramEdge, type DiagramNode } from './dmind'
import { readZip, ZipError } from './zip'

export const MAX_IMPORT_BYTES = 10_000_000
const MAX_NODES = 1000
const MAX_DEPTH = 100

export type Fidelity = {
  format: 'opml' | 'xmind'
  nodes: number
  /** What was kept, in words. */
  carried: string[]
  /** What was not: [what, how many]. */
  dropped: [string, number][]
}
export type Imported = { diagram: Diagram; fidelity: Fidelity }

class Builder {
  nodes: DiagramNode[] = []
  edges: DiagramEdge[] = []
  truncated = 0
  add(label: string, notes: string | undefined, parent: string | null): string {
    if (this.nodes.length >= MAX_NODES) throw new Error(`This file has more than ${MAX_NODES} topics; split it first.`)
    const id = this.nodes.length ? 'n' + this.nodes.length : 'root'
    let text = label.replace(/\s+/g, ' ').trim() || 'Untitled'
    if ([...text].length > 500) {
      text = [...text].slice(0, 500).join('')
      this.truncated++
    }
    const node: DiagramNode = { id, label: text }
    if (notes && notes.trim()) {
      node.notes = [...notes].slice(0, 20000).join('')
      if ([...notes].length > 20000) this.truncated++
    }
    this.nodes.push(node)
    if (parent) this.edges.push({ id: 'e' + this.edges.length, source: parent, target: id, kind: 'branch' })
    return id
  }
  finish(title: string): Diagram {
    const t = [...(title.trim() || this.nodes[0].label)].slice(0, 200).join('')
    return validateDiagram({
      schema_version: 'dmind/v1',
      id: newId(),
      title: t,
      kind: 'mindmap',
      nodes: this.nodes,
      edges: this.edges,
      metadata: { generator: 'dmind-import' },
    })
  }
}

function tally(map: Map<string, number>, key: string, n = 1) {
  map.set(key, (map.get(key) || 0) + n)
}
const dropped = (m: Map<string, number>): [string, number][] => [...m].filter(([, n]) => n > 0)

// ---- OPML -----------------------------------------------------------------------------------

const ENTITIES: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" }
function unescapeXml(s: string): string {
  return s.replace(/&(#x[0-9a-fA-F]{1,6}|#[0-9]{1,7}|[a-zA-Z]+);/g, (m, e: string) => {
    if (e[0] === '#') {
      const cp = e[1] === 'x' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10)
      return cp > 0 && cp <= 0x10ffff && !(cp >= 0xd800 && cp <= 0xdfff) ? String.fromCodePoint(cp) : ''
    }
    return ENTITIES[e] ?? m // unknown entities stay as text; none is ever expanded or fetched
  })
}
function attrs(src: string): Record<string, string> {
  const out: Record<string, string> = {}
  const re = /([A-Za-z_][\w:.-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')/g
  let m: RegExpExecArray | null
  while ((m = re.exec(src))) out[m[1]] = unescapeXml(m[2] ?? m[3])
  return out
}

export function importOpml(text: string): Imported {
  if (text.length > MAX_IMPORT_BYTES) throw new Error('Use an OPML file smaller than 10 MB.')
  if (/<!DOCTYPE|<!ENTITY/i.test(text)) throw new Error('This OPML file declares a DOCTYPE or entities, which are not accepted.')
  const body = text.replace(/<!--[\s\S]*?-->/g, '').replace(/<\?[\s\S]*?\?>/g, '')
  if (!/<opml[\s>]/i.test(body)) throw new Error('This is not an OPML file.')
  const title = unescapeXml((/<head[\s>][\s\S]*?<title>([\s\S]*?)<\/title>/i.exec(body)?.[1] ?? '').trim())
  const start = body.search(/<body[\s>]/i)
  if (start < 0) throw new Error('This OPML file has no body.')
  const b = new Builder()
  const lost = new Map<string, number>()
  const stack: (string | null)[] = []
  let depthDrops = 0
  const re = /<(\/?)outline\b([^>]*?)(\/?)>/gi
  re.lastIndex = start
  let m: RegExpExecArray | null
  let roots = 0
  while ((m = re.exec(body))) {
    const [, closing, rest, selfClose] = m
    if (closing) {
      stack.pop()
      continue
    }
    const a = attrs(rest)
    const label = a.text ?? a.title ?? ''
    Object.keys(a).forEach((k) => !['text', 'title', '_note'].includes(k) && tally(lost, `attribute ${k}`))
    const depth = stack.length
    let id: string | null
    if (depth >= MAX_DEPTH) {
      depthDrops++
      id = null
    } else {
      const parent = stack.length ? stack[stack.length - 1] : null
      if (depth === 0) roots++
      id = b.add(label, a._note, parent)
    }
    if (!selfClose) stack.push(id)
  }
  if (!b.nodes.length) throw new Error('This OPML file has no outlines.')
  return finishOpml(b, title, roots, lost, depthDrops)
}

function finishOpml(b: Builder, title: string, roots: number, lost: Map<string, number>, depthDrops: number): Imported {
  // Several top-level outlines become children of one new root named after the file.
  if (roots > 1) {
    const rootId = 'root'
    const remap = new Map<string, string>()
    b.nodes.forEach((n, i) => remap.set(n.id, 'n' + (i + 1)))
    const nodes = [{ id: rootId, label: title || 'Imported outline' }, ...b.nodes.map((n) => ({ ...n, id: remap.get(n.id)! }))]
    const hasParent = new Set(b.edges.map((e) => e.target))
    const edges: DiagramEdge[] = b.edges.map((e, i) => ({ id: 'e' + i, source: remap.get(e.source)!, target: remap.get(e.target)!, kind: 'branch' }))
    b.nodes.forEach((n) => !hasParent.has(n.id) && edges.push({ id: 'e' + edges.length, source: rootId, target: remap.get(n.id)!, kind: 'branch' }))
    if (nodes.length > MAX_NODES) throw new Error(`This file has more than ${MAX_NODES} topics; split it first.`)
    b.nodes = nodes
    b.edges = edges
  }
  const diagram = b.finish(title)
  const drops = dropped(lost)
  if (depthDrops) drops.push([`outlines nested deeper than ${MAX_DEPTH}`, depthDrops])
  if (b.truncated) drops.push(['text cut to the size limit', b.truncated])
  return {
    diagram,
    fidelity: {
      format: 'opml',
      nodes: diagram.nodes.length,
      carried: ['outline hierarchy', 'topic text', roots > 1 ? 'several top-level outlines (joined under a new root)' : 'single root', ...(diagram.nodes.some((n) => n.notes) ? ['notes (_note)'] : [])],
      dropped: drops,
    },
  }
}

// ---- XMind (Zen) ----------------------------------------------------------------------------

type XTopic = {
  id?: string
  title?: unknown
  notes?: { plain?: { content?: unknown } }
  children?: { attached?: XTopic[]; detached?: XTopic[]; summary?: unknown[] }
  [k: string]: unknown
}
const str = (v: unknown) => (typeof v === 'string' ? v : '')

export async function importXmind(bytes: Uint8Array): Promise<Imported> {
  if (bytes.length > MAX_IMPORT_BYTES * 3) throw new Error('Use an XMind file smaller than 30 MB.')
  let entries: Map<string, Uint8Array>
  try {
    entries = await readZip(bytes, { maxEntries: 200, maxEntryBytes: 10_000_000, maxTotalBytes: 40_000_000, maxRatio: 200 })
  } catch (e) {
    if (e instanceof ZipError) throw new Error(e.message)
    throw e
  }
  const content = entries.get('content.json')
  if (!content) {
    if (entries.has('content.xml'))
      throw new Error('This is an older XMind file (content.xml). Open it in XMind and export OPML or save it as a current .xmind, then import that.')
    throw new Error('This ZIP is not an XMind file (no content.json).')
  }
  let sheets: { title?: unknown; rootTopic?: XTopic; relationships?: { end1Id?: string; end2Id?: string; title?: unknown }[] }[]
  try {
    sheets = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(content))
  } catch {
    throw new Error('The XMind content could not be read.')
  }
  if (!Array.isArray(sheets) || !sheets[0]?.rootTopic) throw new Error('This XMind file has no topics.')
  const sheet = sheets[0]
  const b = new Builder()
  const lost = new Map<string, number>()
  const ids = new Map<string, string>()
  if (sheets.length > 1) tally(lost, 'extra sheets', sheets.length - 1)
  const work: [XTopic, string | null, number][] = [[sheet.rootTopic!, null, 0]]
  while (work.length) {
    const [t, parent, depth] = work.pop()!
    if (depth > MAX_DEPTH) {
      tally(lost, `topics nested deeper than ${MAX_DEPTH}`)
      continue
    }
    const id = b.add(str(t.title), str(t.notes?.plain?.content), parent)
    if (t.id) ids.set(t.id, id)
    for (const k of Object.keys(t))
      if (['markers', 'labels', 'href', 'image', 'style', 'extensions', 'structureClass', 'branch', 'customWidth', 'position'].includes(k) && t[k] != null)
        tally(lost, k === 'markers' ? 'markers' : k === 'labels' ? 'labels' : k === 'href' ? 'links' : k === 'image' ? 'images' : 'styles and layout')
    if (t.notes && !t.notes.plain) tally(lost, 'rich-text notes')
    const kids = t.children
    if (kids?.detached?.length) tally(lost, 'floating topics', kids.detached.length)
    if (kids?.summary?.length) tally(lost, 'summaries', kids.summary.length)
    const attached = kids?.attached ?? []
    for (let i = attached.length - 1; i >= 0; i--) work.push([attached[i], id, depth + 1])
  }
  let related = 0
  for (const r of sheet.relationships ?? []) {
    const s = ids.get(str(r.end1Id)), e = ids.get(str(r.end2Id))
    if (s && e && s !== e && b.edges.length < 4000) {
      const edge: DiagramEdge = { id: 'e' + b.edges.length, source: s, target: e, kind: 'relationship' }
      const label = str(r.title).trim()
      if (label) edge.label = [...label].slice(0, 200).join('')
      b.edges.push(edge)
      related++
    } else tally(lost, 'relationships with a missing end')
  }
  const diagram = b.finish(str(sheet.title))
  const drops = dropped(lost)
  if (b.truncated) drops.push(['text cut to the size limit', b.truncated])
  return {
    diagram,
    fidelity: {
      format: 'xmind',
      nodes: diagram.nodes.length,
      carried: ['topic hierarchy', 'topic text', ...(diagram.nodes.some((n) => n.notes) ? ['plain-text notes'] : []), ...(related ? [`${related} relationship link(s)`] : [])],
      dropped: drops,
    },
  }
}

/** One sentence for the person, listing what did not come across. */
export function describeFidelity(f: Fidelity): string {
  const head = `Imported ${f.nodes} topic(s) from ${f.format === 'opml' ? 'OPML' : 'XMind'}.`
  return f.dropped.length ? `${head} Not carried over: ${f.dropped.map(([w, n]) => `${w} (${n})`).join(', ')}.` : head
}
