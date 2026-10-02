import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { workspaceId } from '../env'
import {
  diagramsApi,
  type DiagramSummary,
  type Extracted,
  type RevisionSummary,
  type SavedDiagram,
} from './diagramsClient'
import { diffDiagrams } from './diff'
import type { DraftRecord } from './draftStore'
import { relativeTime } from './format'
import { SourcePanel } from './SourcePanel'
import { RefinePanel } from './RefinePanel'
import { ContextMenu, type MenuItem } from './ContextMenu'
import { NodeStyleControls } from './NodeStyleControls'
import { OutlineEditor } from './OutlineEditor'
import { applyLayout, defaultLayout, edgePath, LAYOUTS, isLayoutName } from './layouts'
import { moveNodes, nearestInDirection, patchNodes, reparent, removeBranches } from './edit'
import { safeHref } from './links'
import { accentById, cleanMarkers, markerById, markerNames } from './style'
import { addSiblingAfter, moveSibling, indentNode, outdentNode } from './outline'
import {
  attachProvenance,
  citationsFor,
  describeSource,
  type SourceText,
} from './provenance'
import { normalizeTags, sameContent, withRetry } from './saveQueue'
import { useDrafts } from './useDrafts'
import {
  addTopic,
  commitHistory,
  download,
  fromOutline,
  graphAnalysis,
  layout,
  newId,
  redoHistory,
  startHistory,
  toCodingBrief,
  toMarkdown,
  toMermaid,
  toShareHtml,
  toSvg,
  undoHistory,
  validateDiagram,
  visibleNodes,
  type Diagram,
  type DiagramEdge,
  type DiagramKind,
  type DiagramNode,
  type EdgeKind,
  type History,
} from './dmind'
import {
  DMIND_MIME,
  describeUnknown,
  dmindFileName,
  importAny,
  serializeDmind,
} from './dmindFile'
import './diagrams.css'

type NodeViewProps = {
  n: DiagramNode
  x: number
  y: number
  selected: boolean
  primary: boolean
  onSelect: (id: string, additive: boolean) => void
  onDragStart: (e: React.PointerEvent<SVGGElement>, n: DiagramNode) => void
  onMenu: (id: string, at: { x: number; y: number }) => void
}
// Memoised: during a drag only the moved topics receive new props.
const NodeView = React.memo(function NodeView({
  n,
  x,
  y,
  selected,
  primary,
  onSelect,
  onDragStart,
  onMenu,
}: NodeViewProps) {
  const accent = accentById(n.metadata?.accent)
  const marks = cleanMarkers(n.metadata?.markers)
  const href = safeHref(n.metadata?.link)
  const names = markerNames(n.metadata?.markers)
  const name =
    n.label +
    (n.collapsed ? ', collapsed' : '') +
    (names ? `, ${names}` : '') +
    (href ? ', has a link' : '')
  return (
    <g
      data-node={n.id}
      transform={`translate(${x},${y})`}
      role="button"
      tabIndex={0}
      aria-label={name}
      aria-pressed={selected}
      aria-keyshortcuts="Shift+F10"
      onClick={(e) => onSelect(n.id, e.shiftKey || e.ctrlKey || e.metaKey)}
      onContextMenu={(e) => {
        e.preventDefault()
        onMenu(n.id, { x: e.clientX, y: e.clientY })
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect(n.id, e.shiftKey || e.ctrlKey || e.metaKey)
        } else if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) {
          e.preventDefault()
          const r = e.currentTarget.getBoundingClientRect()
          onMenu(n.id, { x: r.left + 20, y: r.bottom })
        }
      }}
      onPointerDown={(e) => onDragStart(e, n)}
    >
      <rect
        width="200"
        height="64"
        rx="12"
        className={selected ? (primary ? 'is-selected is-primary' : 'is-selected') : ''}
        style={accent ? { stroke: accent.hex, strokeWidth: selected ? 4 : 2.5 } : undefined}
      />
      {accent && (
        <rect className="dmind-accent" width="7" height="64" rx="3" style={{ fill: accent.hex }} />
      )}
      <text x="14" y="28">
        {n.label.length > 24 ? n.label.slice(0, 23) + '…' : n.label}
        {n.collapsed ? ' ⊕' : ''}
      </text>
      {(marks.length > 0 || href) && (
        <text className="dmind-glyphs" x="14" y="52" aria-hidden="true">
          {marks.map((m) => markerById(m)!.glyph).join(' ')}
          {href ? ' ↗' : ''}
        </text>
      )}
      <title>{n.label}</title>
    </g>
  )
})
const EdgesView = React.memo(function EdgesView({
  edges,
  byId,
}: {
  edges: DiagramEdge[]
  byId: Map<string, DiagramNode>
}) {
  return (
    <>
      {edges.map((e) => {
        const g = edgePath(byId.get(e.source)!.position!, byId.get(e.target)!.position!)
        return (
          <g key={e.id}>
            <path
              d={g.d}
              className={`dmind-edge dmind-edge-${e.kind}`}
              markerEnd={e.kind === 'branch' ? undefined : 'url(#dmind-arrow)'}
            />
            {e.label && (
              <text x={g.mid.x} y={g.mid.y - 6} textAnchor="middle">
                {e.label}
              </text>
            )}
          </g>
        )
      })}
    </>
  )
})

export function DiagramsWorkspace({
  accountKey = 'local',
}: {
  accountKey?: string
}) {
  const workspace = workspaceId()
  const drafts = useDrafts(accountKey, workspace)
  const draftId = useRef<string>(newId()) // one draft per open diagram: the saved id, or a fresh id
  const [items, setItems] = useState<DiagramSummary[]>([]),
    [showArchived, setShowArchived] = useState(false)
  const [search, setSearch] = useState(''),
    [tagFilter, setTagFilter] = useState(''),
    [projectFilter, setProjectFilter] = useState('')
  const [nextCursor, setNextCursor] = useState<string | null>(null),
    [knownTags, setKnownTags] = useState<string[]>([]),
    [projects, setProjects] = useState<{ id: string; name: string }[]>([])
  const [revMore, setRevMore] = useState<number | null>(null),
    [changes, setChanges] = useState<{ revision: number; lines: string[] } | null>(null)
  const [history, setHistory] = useState<History | null>(null),
    [saved, setSaved] = useState<SavedDiagram | null>(null)
  const [dirty, setDirty] = useState(false),
    [selected, setSelected] = useState(''),
    [busy, setBusy] = useState(false)
  const [dropping, setDropping] = useState(false)
  const [sources, setSources] = useState<SourceText[]>([])
  const [message, setMessage] = useState(''),
    [wizard, setWizard] = useState(0)
  const [topic, setTopic] = useState(''),
    [content, setContent] = useState(''),
    [kind, setKind] = useState<DiagramKind>('mindmap')
  const [useDesigner, setUseDesigner] = useState(false),
    [tier, setTier] = useState('standard'),
    [preview, setPreview] = useState<Diagram | null>(null)
  const [linkTarget, setLinkTarget] = useState(''),
    [linkKind, setLinkKind] = useState<EdgeKind>('flow'),
    [linkLabel, setLinkLabel] = useState('')
  const [revisions, setRevisions] = useState<RevisionSummary[]>([]),
    [zoom, setZoom] = useState(1)
  const [validationReport, setValidationReport] = useState<Record<
    string,
    unknown
  > | null>(null)
  const [extra, setExtra] = useState<string[]>([]),
    [menu, setMenu] = useState<{ id: string; x: number; y: number } | null>(null),
    [outlineFocus, setOutlineFocus] = useState('')
  const [dragDelta, setDragDelta] = useState<{
    ids: Set<string>
    dx: number
    dy: number
  } | null>(null)
  const drag = useRef<{
    id: string
    ids: string[]
    clientX: number
    clientY: number
  } | null>(null)
  const ignoreClick = useRef(false)
  const labelInput = useRef<HTMLInputElement>(null)
  const pan = useRef<{
    x: number
    y: number
    left: number
    top: number
  } | null>(null)
  const viewport = useRef<HTMLDivElement>(null),
    input = useRef<HTMLInputElement>(null)
  const legacyDraftKey = `daypilot.dmind.draft:${workspace}:${accountKey}`
  const diagram = history?.present || null
  const arranged = useMemo(() => (diagram ? layout(diagram) : null), [diagram])
  // Pointer moves re-render this component many times a second: keep derived data memoised
  // so a drag only touches the dragged topic (measured: 1000 topics, see docs).
  const visible = useMemo(
    () => (arranged ? visibleNodes(arranged) : []),
    [arranged],
  )
  const byId = useMemo(
    () => new Map(arranged?.nodes.map((n) => [n.id, n]) || []),
    [arranged],
  )
  const visibleEdges = useMemo(() => {
    const ids = new Set(visible.map((n) => n.id))
    return (arranged?.edges || []).filter(
      (e) => ids.has(e.source) && ids.has(e.target),
    )
  }, [arranged, visible])
  const node = diagram?.nodes.find((n) => n.id === selected)
  const group = useMemo(
    () => [selected, ...extra.filter((id) => id !== selected)].filter((id) => diagram?.nodes.some((n) => n.id === id)),
    [selected, extra, diagram],
  )
  const groupSet = useMemo(() => new Set(group), [group])
  const visibleIds = useMemo(() => new Set(visible.map((n) => n.id)), [visible])
  const analysis = useMemo(
    () => (diagram ? graphAnalysis(diagram) : null),
    [diagram],
  )
  const { minX, minY, width, height } = useMemo(() => {
    let x0 = 0,
      y0 = 0,
      x1 = 800,
      y1 = 500
    for (const n of visible) {
      x0 = Math.min(x0, n.position!.x - 30)
      y0 = Math.min(y0, n.position!.y - 100)
      x1 = Math.max(x1, n.position!.x + 240)
      y1 = Math.max(y1, n.position!.y + 100)
    }
    return { minX: x0, minY: y0, width: x1 - x0, height: y1 - y0 }
  }, [visible])

  const listQuery = useMemo(
    () => ({
      q: search.trim(),
      tag: tagFilter,
      projectId: projectFilter,
      archived: showArchived ? ('include' as const) : ('exclude' as const),
    }),
    [search, tagFilter, projectFilter, showArchived],
  )
  async function refresh(more = false) {
    const result = await diagramsApi.list({
      ...listQuery,
      cursor: more ? nextCursor : null,
    })
    if (result.ok) {
      setItems((prev) => (more ? [...prev, ...result.data.items] : result.data.items))
      setNextCursor(result.data.nextCursor)
      setKnownTags((prev) =>
        [...new Set([...prev, ...result.data.items.flatMap((i) => i.tags || [])])].sort(),
      )
    } else
      setMessage(
        'Saved diagrams unavailable. You can create, edit and export a local draft. ' +
          result.error,
      )
  }
  useEffect(() => {
    // Searching waits for a pause in typing; filters apply at once.
    const timer = setTimeout(() => void refresh(), search ? 250 : 0)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listQuery])
  useEffect(() => {
    void diagramsApi.projects().then((r) => r.ok && setProjects(r.data.items || []))
  }, [])
  // Drafts saved by the earlier single-slot cache move into the durable store once.
  useEffect(() => {
    if (!drafts.ready) return
    try {
      const raw = localStorage.getItem(legacyDraftKey)
      if (!raw) return
      localStorage.removeItem(legacyDraftKey)
      const old = JSON.parse(raw)
      void drafts.save({
        id: newId(),
        kind: 'draft',
        document: validateDiagram(old.document),
        saved: old.saved ? { id: old.saved.id, revision: old.saved.revision } : null,
        updatedAt: Date.now(),
      })
    } catch {
      /* an unreadable legacy draft is dropped */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drafts.ready])
  useEffect(() => {
    function beforeUnload(e: BeforeUnloadEvent) {
      if (dirty) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => window.removeEventListener('beforeunload', beforeUnload)
  }, [dirty])
  const pending = useRef<DraftRecord | null>(null)
  useEffect(() => {
    // Every edit is written to the durable store a moment after it happens, and at once if the
    // page is hidden or closed.
    if (!diagram || !dirty) {
      pending.current = null
      return
    }
    const record: DraftRecord = {
      id: draftId.current,
      kind: 'draft',
      document: diagram,
      saved: saved ? { id: saved.id, revision: saved.revision } : null,
      updatedAt: Date.now(),
    }
    pending.current = record
    const timer = setTimeout(() => {
      pending.current = null
      void drafts.save(record)
    }, 200)
    return () => clearTimeout(timer)
  }, [diagram, dirty, saved, drafts.save])
  useEffect(() => {
    const flush = () => {
      if (pending.current) void drafts.save(pending.current)
      pending.current = null
    }
    const hidden = () => document.visibilityState === 'hidden' && flush()
    window.addEventListener('pagehide', flush)
    document.addEventListener('visibilitychange', hidden)
    return () => {
      window.removeEventListener('pagehide', flush)
      document.removeEventListener('visibilitychange', hidden)
    }
  }, [drafts.save])

  useEffect(() => {
    if (diagram && !diagram.nodes.some((n) => n.id === selected))
      setSelected(diagram.nodes[0].id)
    if (diagram && extra.some((id) => !diagram.nodes.some((n) => n.id === id)))
      setExtra(extra.filter((id) => diagram.nodes.some((n) => n.id === id)))
  }, [diagram, selected, extra])

  const chooseNode = useCallback(
    (id: string, additive: boolean) => {
      if (ignoreClick.current) return // the click that ends a drag is not a selection
      if (!additive) {
        setSelected(id)
        setExtra([])
        return
      }
      const all = [selected, ...extra.filter((x) => x !== selected)]
      if (all.includes(id)) {
        if (all.length === 1) return
        const rest = all.filter((x) => x !== id)
        setSelected(rest[rest.length - 1])
        setExtra(rest.slice(0, -1))
      } else {
        setExtra(all)
        setSelected(id)
      }
    },
    [selected, extra],
  )
  const startDrag = useCallback(
    (e: React.PointerEvent<SVGGElement>, n: DiagramNode) => {
      if (busy || e.button !== 0) return
      e.stopPropagation()
      if (e.shiftKey || e.ctrlKey || e.metaKey) return // modifiers select on click
      const inGroup = n.id === selected || extra.includes(n.id)
      if (!inGroup) {
        setSelected(n.id)
        setExtra([])
      }
      drag.current = {
        id: n.id,
        ids: inGroup ? [selected, ...extra.filter((x) => x !== selected)] : [n.id],
        clientX: e.clientX,
        clientY: e.clientY,
      }
      e.currentTarget.setPointerCapture(e.pointerId)
    },
    [busy, selected, extra],
  )
  function open(
    d: Diagram,
    persisted: SavedDiagram | null = null,
    isDirty = true,
    draft?: string,
  ) {
    const safe = validateDiagram(d)
    draftId.current = draft ?? persisted?.id ?? newId()
    setHistory(startHistory(safe))
    setSaved(persisted)
    setDirty(isDirty)
    setSelected(safe.nodes[0].id)
    setValidationReport(null)
    setWizard(0)
    setRevisions([])
    setRevMore(null)
    setChanges(null)
    setLinkTarget('')
    setZoom(1)
  }
  function canLeave() {
    return (
      !dirty ||
      window.confirm(
        'Open another diagram? This replaces the current draft. Save or export it first to keep it.',
      )
    )
  }
  function commit(d: Diagram, key?: string) {
    try {
      const next = validateDiagram(d)
      setHistory((h) => commitHistory(h, next, key))
      setDirty(true)
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Invalid diagram')
    }
  }
  function undo() {
    setHistory((h) => (h ? undoHistory(h) : h))
    setDirty(true)
  }
  function redo() {
    setHistory((h) => (h ? redoHistory(h) : h))
    setDirty(true)
  }
  function changeNode(patch: Partial<NonNullable<typeof node>>) {
    if (diagram && node)
      commit({
        ...diagram,
        nodes: diagram.nodes.map((n) =>
          n.id === node.id ? { ...n, ...patch } : n,
        ),
      }, 'label' in patch || 'notes' in patch ? `${Object.keys(patch)[0]}:${node.id}` : undefined)
  }
  function addChild(sibling = false) {
    if (!diagram || !node) return
    const added = addTopic(diagram, selected, sibling)
    if (!added) return
    commit(added.diagram)
    setSelected(added.id)
  }
  function removeNode() {
    if (!diagram || !node) return
    const next = removeBranches(diagram, group)
    if (!next) {
      setMessage('Keep at least one node. Create a new diagram to start again.')
      return
    }
    commit(next)
    setSelected(next.nodes[0].id)
    setExtra([])
  }
  function focusNode(id: string) {
    requestAnimationFrame(() =>
      document.querySelector<SVGGElement>(`[data-node="${CSS.escape(id)}"]`)?.focus(),
    )
  }
  function menuItems(id: string): MenuItem[] {
    if (!diagram) return []
    const n = diagram.nodes.find((x) => x.id === id)!
    const members = groupSet.has(id) ? group : [id]
    return [
      { label: 'Add child', onSelect: () => addChild(false) },
      { label: 'Add sibling', onSelect: () => addChild(true) },
      { label: 'Rename', onSelect: () => labelInput.current?.focus() },
      {
        label: n.collapsed ? 'Expand branch' : 'Collapse branch',
        onSelect: () => commit(patchNodes(diagram, members, { collapsed: !n.collapsed })),
      },
      { label: 'Move up', disabled: !moveSibling(diagram, id, -1), onSelect: () => commit(moveSibling(diagram, id, -1)!) },
      { label: 'Move down', disabled: !moveSibling(diagram, id, 1), onSelect: () => commit(moveSibling(diagram, id, 1)!) },
      { label: 'Indent', disabled: !indentNode(diagram, id), onSelect: () => commit(indentNode(diagram, id)!) },
      { label: 'Outdent', disabled: !outdentNode(diagram, id), onSelect: () => commit(outdentNode(diagram, id)!) },
      { label: members.length > 1 ? `Delete ${members.length} topics` : 'Delete', disabled: members.length >= diagram.nodes.length, onSelect: removeNode },
    ]
  }
  async function save(copy = false, archive = saved?.archived ?? false) {
    if (!diagram) return
    setMessage('')
    setBusy(true)
    const update = saved && !copy
    const attempt = () =>
      update
        ? diagramsApi.save(saved.id, diagram, saved.revision, archive)
        : diagramsApi.create(diagram)
    let tries = 1
    // Only updates are retried: they are guarded by the expected revision, so repeating one is
    // safe. A create is never repeated automatically, because a lost response could duplicate it.
    let result = update
      ? await withRetry(attempt, {
          onRetry: (n) => {
            tries = n
            setMessage(`Connection problem. Retrying (${n}/4)…`)
          },
        })
      : await attempt()
    if (!result.ok && result.status === 409 && tries > 1 && update) {
      // A retry that now conflicts may be our own first attempt, which did land.
      const now = await diagramsApi.load(saved.id)
      if (
        now.ok &&
        now.data.revision === saved.revision + 1 &&
        now.data.archived === archive &&
        sameContent(now.data.document, { ...diagram, id: saved.id })
      )
        result = now
    }
    setBusy(false)
    if (result.ok) {
      await drafts.discard(draftId.current)
      open(result.data.document, result.data, false)
      setMessage(
        `Saved revision ${result.data.revision}${result.data.archived ? ' · archived' : ''}`,
      )
      await refresh()
    } else if (result.status === 409 && update) {
      await drafts.save({
        id: 'conflict-' + newId(),
        kind: 'conflict',
        document: diagram,
        saved: { id: saved.id, revision: saved.revision },
        updatedAt: Date.now(),
        reason: 'Saved from another tab or device first',
      })
      setMessage(
        'This diagram changed elsewhere. Your edits are kept as a conflict copy in this browser. Save a copy, or reload the latest revision.',
      )
    } else if (result.status === undefined || result.status >= 500)
      setMessage(
        `Could not reach the server (${result.error}). ${
          drafts.enabled
            ? 'Your work is kept in this browser; press Save again when the connection is back.'
            : 'Export a .dmind file to keep your work, then try again.'
        }`,
      )
    else setMessage(result.error)
  }
  function useExtracted(x: Extracted) {
    const joined = content ? content + '\n' + x.text : x.text
    if (joined.length > 100000) {
      setMessage('The combined text would exceed 100000 characters. Remove a source or split the document.')
      return
    }
    let n = sources.length + 1
    while (sources.some((s) => s.ref.id === `src${n}`)) n++
    const ref = { ...x.source, id: `src${n}`, kind: x.source.kind ?? 'file', fetched_at: new Date().toISOString() }
    setSources([...sources, { ref, text: x.text }])
    setContent(joined)
    if (!topic)
      setTopic((x.source.title || x.source.name || '').replace(/\.[^.]+$/, '').slice(0, 200))
    setMessage(`Added ${describeSource(ref)}. Review the text, then continue.`)
  }
  async function openDraft(rec: DraftRecord) {
    if (!canLeave()) return
    let persisted: SavedDiagram | null = null
    if (rec.saved) {
      // Keep the revision the draft was based on: a newer one is a conflict at save time.
      const current = await diagramsApi.load(rec.saved.id)
      if (current.ok)
        persisted = {
          id: rec.saved.id,
          revision: rec.saved.revision,
          archived: current.data.archived,
          document: rec.document,
        }
      else
        setMessage(
          'The saved diagram is no longer available. Saving will create a new diagram.',
        )
    }
    open(rec.document, persisted, true, rec.id)
    if (persisted || !rec.saved)
      setMessage(
        rec.kind === 'conflict'
          ? 'Conflict copy opened. Save a copy to keep it, or reload the latest revision.'
          : 'Recovered a local draft. Save or export it to preserve it.',
      )
  }
  async function loadRevisions(older = false) {
    if (!saved) return
    const r = await diagramsApi.revisions(saved.id, older ? revMore : null)
    if (!r.ok) return setMessage(r.error)
    setRevisions((prev) => (older ? [...prev, ...r.data.items] : r.data.items))
    setRevMore(r.data.hasMore ? r.data.nextBefore : null)
  }
  async function fetchRevision(n: number) {
    if (!saved) return null
    const r = await diagramsApi.revision(saved.id, n)
    if (!r.ok) {
      setMessage(r.error)
      return null
    }
    return r.data.document
  }
  async function load(id: string) {
    if (!canLeave()) return
    setMessage('')
    setBusy(true)
    const r = await diagramsApi.load(id)
    setBusy(false)
    if (r.ok) {
      open(r.data.document, r.data, false)
      setMessage('Loaded revision ' + r.data.revision)
    } else setMessage(r.error)
  }
  async function generate() {
    setBusy(true)
    setMessage('')
    try {
      let d: Diagram
      if (useDesigner) {
        const r = await diagramsApi.generate(topic, content, kind, true, tier)
        if (!r.ok) throw new Error(r.error)
        d = r.data.diagram
      } else d = attachProvenance(fromOutline(topic, content, kind), sources)
      setPreview(layout(validateDiagram(d)))
      setWizard(3)
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Generation failed')
    } finally {
      setBusy(false)
    }
  }
  async function readFile(file?: File) {
    if (!file) return
    try {
      if (file.size > 62_000_000) throw new Error('Use a file smaller than 62 MB.')
      const result = await importAny(file.name, new Uint8Array(await file.arrayBuffer()))
      if (result.kind === 'text') {
        setContent(result.text)
        if (!topic) setTopic(result.name.replace(/\.[^.]+$/, '').slice(0, 200))
        setMessage(
          'Text loaded. Indentation becomes branches; each line becomes a topic.',
        )
      } else {
        const d = result.diagram
        setPreview({ ...d, id: newId() })
        setTopic(d.title)
        setWizard(3)
        setMessage([describeUnknown(result.report), ...(result.warnings ?? [])].filter(Boolean).join(' '))
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Import failed')
    }
    if (input.current) input.current.value = ''
  }
  function exportAs(format: string) {
    if (!diagram) return
    const name = diagram.title.slice(0, 80)
    if (format === 'json')
      download(dmindFileName(diagram.title), serializeDmind(diagram), DMIND_MIME)
    if (format === 'md')
      download(name + '.md', toMarkdown(diagram), 'text/markdown')
    if (format === 'mermaid')
      download(name + '.mmd', toMermaid(diagram), 'text/plain')
    if (format === 'svg')
      download(name + '.svg', toSvg(diagram), 'image/svg+xml')
    if (format === 'html')
      download(name + '.html', toShareHtml(diagram), 'text/html')
    if (format === 'coding')
      download(
        name + '-coding-brief.md',
        toCodingBrief(diagram),
        'text/markdown',
      )
    if (format === 'original' && diagram.metadata?.design_bundle)
      download(
        name + '-original-design-bundle.json',
        JSON.stringify(diagram.metadata.design_bundle, null, 2),
        'application/json',
      )
  }
  async function handoff() {
    if (!diagram) return
    setMessage('')
    setBusy(true)
    const r = await diagramsApi.bundle(diagram, tier)
    setBusy(false)
    if (r.ok) {
      download(
        diagram.title + '-design-bundle.json',
        JSON.stringify(r.data.bundle, null, 2),
        'application/json',
      )
      setValidationReport(r.data.validation)
      setMessage(
        `Design Bundle exported · validation: ${String(r.data.validation.status || 'review required')}. Download the report and review batch scope before coding.`,
      )
    } else setMessage(r.error)
  }
  // Stable wrappers around the latest handlers, so memoised panels are not re-rendered by drags.
  const latest = useRef({
    commit,
    choose: chooseNode,
    addSibling: (_id: string) => {},
  })
  latest.current = {
    commit,
    choose: chooseNode,
    addSibling: (id: string) => {
      if (!diagram) return
      const added =
        diagram.kind === 'flowchart' ? addTopic(diagram, id, true) : addSiblingAfter(diagram, id)
      if (!added) return
      commit(added.diagram)
      setSelected(added.id)
      setExtra([])
      setOutlineFocus(added.id)
    },
  }
  const outlineHandlers = useMemo(
    () => ({
      onSelect: (id: string) => latest.current.choose(id, false),
      onChange: (next: Diagram, key?: string) => latest.current.commit(next, key),
      onAddSibling: (id: string) => latest.current.addSibling(id),
    }),
    [],
  )
  const onStyleChange = outlineHandlers.onChange
  const clearOutlineFocus = useCallback(() => setOutlineFocus(''), [])
  function keyDown(e: React.KeyboardEvent) {
    e.stopPropagation() // Keep canvas shortcuts within dmind; shell F opens Focus Mode.
    const target = e.target as HTMLElement
    if (
      busy ||
      wizard ||
      !diagram ||
      target.matches('input,textarea,select')
    )
      return
    const mod = e.ctrlKey || e.metaKey
    if (mod && e.key.toLowerCase() === 'z') {
      e.preventDefault()
      e.shiftKey ? redo() : undo()
    }
    if (mod && e.key.toLowerCase() === 's') {
      e.preventDefault()
      void save()
    }
    const onTopic = !!target.closest?.('[data-node]')
    if (e.key === 'Escape') {
      if (menu) setMenu(null)
      else if (extra.length) setExtra([])
    }
    if (e.key === 'Insert') {
      e.preventDefault()
      addChild(e.shiftKey)
    }
    if (e.key === 'Delete') {
      e.preventDefault()
      removeNode()
    }
    if (!onTopic) return
    if (e.key === 'F2') {
      e.preventDefault()
      labelInput.current?.focus()
    } else if (mod && e.key.toLowerCase() === 'a') {
      e.preventDefault()
      const all = visible.map((n) => n.id)
      setSelected(selected)
      setExtra(all.filter((id) => id !== selected))
    } else if (e.key === '-' || e.key === '+' || e.key === '=') {
      e.preventDefault()
      commit(patchNodes(diagram, group, { collapsed: e.key === '-' }))
    } else if (e.key.startsWith('Arrow')) {
      e.preventDefault()
      const dir = ({ ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' } as const)[
        e.key as 'ArrowLeft' | 'ArrowRight' | 'ArrowUp' | 'ArrowDown'
      ]
      if (e.altKey) {
        const step = e.shiftKey ? 50 : 10
        commit(
          moveNodes(
            diagram,
            group,
            dir === 'left' ? -step : dir === 'right' ? step : 0,
            dir === 'up' ? -step : dir === 'down' ? step : 0,
          ),
        )
      } else {
        const positions = new Map(visible.map((n) => [n.id, n.position!]))
        const from = target.closest('[data-node]')!.getAttribute('data-node')!
        const next = nearestInDirection(positions, from, dir, visibleIds)
        if (next) {
          chooseNode(next, false)
          focusNode(next)
        }
      }
    }
  }
  return (
    <section
      className={`dmind${dropping ? ' dmind-dropping' : ''}`}
      aria-label="dmind diagrams workspace"
      onKeyDown={keyDown}
      onDragOver={(e) => {
        if (e.dataTransfer?.types.includes('Files')) {
          e.preventDefault()
          setDropping(true)
        }
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDropping(false)
      }}
      onDrop={(e) => {
        if (!e.dataTransfer?.files.length) return
        e.preventDefault()
        setDropping(false)
        if (canLeave()) void readFile(e.dataTransfer.files[0])
      }}
    >
      <header className="dmind-header">
        <div>
          <span className="dmind-brand">dmind</span>
          <h2>Turn ideas into diagrams</h2>
          <p>
            Brainstorm, inspect flows, and prepare systems for Claude Code or
            Codex.
          </p>
        </div>
        <button
          disabled={busy}
          onClick={() => {
            if (canLeave()) {
              setWizard(1)
              setPreview(null)
              // Sending text to a provider is an opt-in for this run only.
              setUseDesigner(false)
              setSources([])
              setTopic('')
              setContent('')
            }
          }}
        >
          New diagram
        </button>
      </header>
      <p className="dmind-status" role="status" aria-live="polite">
        {busy && !message
          ? 'Working…'
          : message ||
            (dirty
              ? 'Unsaved draft · cached in this browser'
              : 'Diagrams stay in your workspace until you export a snapshot.')}
      </p>
      <input
        ref={input}
        className="dmind-file"
        type="file"
        accept=".txt,.md,.markdown,.json,.dmind,.opml,.xmind"
        aria-label="Import source or diagram"
        onChange={(e) => void readFile(e.target.files?.[0])}
      />
      <fieldset disabled={busy} className="dmind-controls">
        {wizard > 0 && (
          <div className="dmind-wizard" aria-label="Create diagram wizard">
            <ol>
              <li aria-current={wizard === 1 ? 'step' : undefined}>
                1. Source
              </li>
              <li aria-current={wizard === 2 ? 'step' : undefined}>
                2. Structure
              </li>
              <li aria-current={wizard === 3 ? 'step' : undefined}>
                3. Review
              </li>
            </ol>
            {wizard === 1 && (
              <>
                <label>
                  Topic
                  <input
                    value={topic}
                    maxLength={200}
                    placeholder="e.g. An order processing algorithm"
                    onChange={(e) => setTopic(e.target.value)}
                  />
                </label>
                <label>
                  Brainstorm or outline
                  <textarea
                    rows={7}
                    maxLength={100000}
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    placeholder={
                      'Receive order\n  Validate items\n  Reserve stock\nCharge payment\n  Success\n  Retry or cancel'
                    }
                  />
                </label>
                <p>
                  Start with any topic. Add one idea per line; indent for child
                  topics.
                </p>
                <button onClick={() => input.current?.click()}>
                  Attach text or open a .dmind, .opml or .xmind file
                </button>
                <SourcePanel
                  sources={sources}
                  onUse={useExtracted}
                  onRemove={(id) => setSources(sources.filter((s) => s.ref.id !== id))}
                  disabled={busy}
                />
                <button disabled={!topic.trim()} onClick={() => setWizard(2)}>
                  Next: structure
                </button>
              </>
            )}
            {wizard === 2 && (
              <>
                <label>
                  Diagram type
                  <select
                    value={kind}
                    onChange={(e) => setKind(e.target.value as DiagramKind)}
                  >
                    <option value="mindmap">
                      Mind map · ideas and branches
                    </option>
                    <option value="flowchart">Flowchart · ordered steps</option>
                    <option value="system">
                      System · components and dependencies
                    </option>
                  </select>
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={useDesigner}
                    onChange={(e) => setUseDesigner(e.target.checked)}
                  />{' '}
                  Ask Matrix Designer for a system proposal
                </label>
                <p>
                  {useDesigner
                    ? `Sends the topic and attached text${sources.length ? ` (including the extracted text of ${sources.length} source${sources.length > 1 ? 's' : ''})` : ''} to your configured Matrix Designer provider. Returns batches and dependencies for review.`
                    : 'Local outline mode works without AI or a network connection. Flowcharts connect the lines in order; you can add decision links in the editor.'}
                </p>
                {useDesigner && (
                  <label>
                    Blueprint tier
                    <select
                      value={tier}
                      onChange={(e) => setTier(e.target.value)}
                    >
                      <option>minimal</option>
                      <option>standard</option>
                      <option>production</option>
                    </select>
                  </label>
                )}
                <button onClick={() => setWizard(1)}>Back</button>
                <button onClick={() => void generate()}>
                  Generate preview
                </button>
              </>
            )}
            {wizard === 3 && preview && (
              <>
                <h3>{preview.title}</h3>
                <p>
                  {preview.nodes.length} topics · {preview.edges.length} links ·{' '}
                  {preview.kind}. Check the proposed structure before editing.
                </p>
                <ul className="dmind-preview">
                  {preview.nodes.map((n) => (
                    <li key={n.id}>{n.label}</li>
                  ))}
                </ul>
                <button onClick={() => setWizard(2)}>Back</button>
                <button
                  onClick={() => {
                    if (!canLeave()) return
                    open(preview)
                    setMessage(
                      'Draft created. Select a topic to edit it; save when ready.',
                    )
                  }}
                >
                  Use this diagram
                </button>
              </>
            )}
            <button onClick={() => setWizard(0)}>Close wizard</button>
          </div>
        )}
        <div className="dmind-layout">
          <aside className="dmind-library">
            <h3>My diagrams</h3>
            <label>
              Search
              <input
                type="search"
                aria-label="Search diagrams"
                value={search}
                maxLength={200}
                placeholder="Title"
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            {knownTags.length > 0 && (
              <div className="dmind-tags" aria-label="Filter by tag">
                {knownTags.map((t) => (
                  <button
                    key={t}
                    aria-pressed={tagFilter === t}
                    onClick={() => setTagFilter(tagFilter === t ? '' : t)}
                  >
                    #{t}
                  </button>
                ))}
              </div>
            )}
            {projects.length > 0 && (
              <label>
                Project
                <select
                  aria-label="Filter by project"
                  value={projectFilter}
                  onChange={(e) => setProjectFilter(e.target.value)}
                >
                  <option value="">All projects</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <button onClick={() => void refresh()}>Refresh</button>
            <label>
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(e) => setShowArchived(e.target.checked)}
              />{' '}
              Include archived
            </label>
            <div className="dmind-saved">
              {items.map((i) => (
                <button
                  key={i.id}
                  aria-pressed={saved?.id === i.id}
                  onClick={() => void load(i.id)}
                >
                  {i.title}
                  <small>
                    Revision {i.revision}
                    {i.archived ? ' · archived' : ''}
                    {i.updatedAt ? ' · ' + relativeTime(i.updatedAt) : ''}
                  </small>
                  {!!i.tags?.length && (
                    <small>{i.tags.map((t) => '#' + t).join(' ')}</small>
                  )}
                </button>
              ))}
              {!items.length && <p>Your saved diagrams appear here.</p>}
              {nextCursor && (
                <button onClick={() => void refresh(true)}>Load more</button>
              )}
            </div>
            <h4>Local drafts</h4>
            <div className="dmind-drafts">
              {drafts.drafts.map((rec) => (
                <div key={rec.id} className="dmind-draft">
                  <button onClick={() => void openDraft(rec)}>
                    {rec.kind === 'conflict' ? 'Conflict copy: ' : ''}
                    {rec.document.title}
                    <small>
                      {rec.saved ? `Based on r${rec.saved.revision}` : 'Not saved yet'}
                      {' · '}
                      {relativeTime(rec.updatedAt)}
                    </small>
                  </button>
                  <button
                    aria-label={`Discard draft ${rec.document.title}`}
                    onClick={() => void drafts.discard(rec.id)}
                  >
                    Discard
                  </button>
                </div>
              ))}
              {!drafts.drafts.length && (
                <p>Unsaved work is kept here automatically.</p>
              )}
              {drafts.ready && !drafts.durable && (
                <p role="note">
                  This browser blocks local storage, so drafts are kept in memory
                  only. Export a .dmind file to keep your work.
                </p>
              )}
              <label>
                <input
                  type="checkbox"
                  checked={drafts.enabled}
                  onChange={(e) => void drafts.setEnabled(e.target.checked)}
                />{' '}
                Keep drafts in this browser
              </label>
            </div>
            <button
              onClick={() => {
                const latest = drafts.drafts.find((r) => r.kind === 'draft') || drafts.drafts[0]
                if (!latest) setMessage('No cached draft.')
                else void openDraft(latest).then(() => setMessage('Recovered browser draft. Save or export it to preserve it.'))
              }}
            >
              Recover browser draft
            </button>
            <button onClick={() => input.current?.click()}>
              Import a copy
            </button>
          </aside>
          {!diagram && !wizard && (
            <div className="dmind-empty">
              <h3>A clear place to think</h3>
              <p>
                Create a mind map, flowchart, or system diagram from a topic,
                brainstorm or attachment.
              </p>
              <button onClick={() => setWizard(1)}>Start the wizard</button>
            </div>
          )}
          {diagram && (
            <div className="dmind-editor">
              <div className="dmind-toolbar">
                <button onClick={() => void save()}>
                  Save{saved ? ` · r${saved.revision}` : ''}
                </button>
                <button onClick={() => void save(true)}>Save a copy</button>
                <button disabled={!history?.past.length} onClick={undo}>
                  Undo
                </button>
                <button disabled={!history?.future.length} onClick={redo}>
                  Redo
                </button>
                <button
                  onClick={() => commit(applyLayout(diagram, defaultLayout(diagram)))}
                >
                  Auto-layout
                </button>
                <label>
                  Layout
                  <select
                    aria-label="Layout"
                    value={defaultLayout(diagram)}
                    onChange={(e) =>
                      isLayoutName(e.target.value) &&
                      commit(applyLayout(diagram, e.target.value))
                    }
                  >
                    {LAYOUTS.map((l) => (
                      <option key={l.id} value={l.id} title={l.hint}>
                        {l.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Zoom
                  <input
                    type="range"
                    aria-label="Canvas zoom"
                    min="0.25"
                    max="2"
                    step="0.05"
                    value={zoom}
                    onChange={(e) => setZoom(Number(e.target.value))}
                  />
                </label>
                <select
                  aria-label="Export diagram"
                  value=""
                  onChange={(e) => exportAs(e.target.value)}
                >
                  <option value="">Export / share…</option>
                  <option value="json">dmind file (.dmind)</option>
                  <option value="md">Markdown outline</option>
                  <option value="mermaid">Mermaid</option>
                  <option value="svg">SVG image</option>
                  <option value="html">Read-only HTML / print PDF</option>
                  <option value="coding">Claude Code / Codex brief</option>
                  {diagram.metadata?.design_bundle != null && (
                    <option value="original">
                      Original Matrix Design Bundle
                    </option>
                  )}
                </select>
              </div>
              <label className="dmind-title">
                Diagram title
                <input
                  value={diagram.title}
                  maxLength={200}
                  onChange={(e) =>
                    commit({ ...diagram, title: e.target.value })
                  }
                />
              </label>
              <div className="dmind-meta">
                <label>
                  Tags
                  <input
                    key={JSON.stringify(diagram.metadata?.tags || [])}
                    aria-label="Tags"
                    placeholder="comma separated"
                    defaultValue={((diagram.metadata?.tags as string[]) || []).join(', ')}
                    onBlur={(e) => {
                      const tags = normalizeTags(e.target.value.split(','))
                      if (JSON.stringify(tags) !== JSON.stringify(diagram.metadata?.tags || []))
                        commit({ ...diagram, metadata: { ...diagram.metadata, tags } })
                    }}
                    onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
                  />
                </label>
                {projects.length > 0 && (
                  <label>
                    Project
                    <select
                      aria-label="Project"
                      value={(diagram.metadata?.project_id as string) || ''}
                      onChange={(e) => {
                        const meta = { ...diagram.metadata }
                        if (e.target.value) meta.project_id = e.target.value
                        else delete meta.project_id
                        commit({ ...diagram, metadata: meta })
                      }}
                    >
                      <option value="">No project</option>
                      {projects.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
              <RefinePanel diagram={diagram} onApply={(next) => commit(next)} />
              <p>
                {diagram.nodes.length} topics · {diagram.edges.length} links ·{' '}
                {analysis?.decisions} branching decisions
                {analysis?.feedback
                  ? ' · Feedback loop: define retry or termination conditions.'
                  : ''}
              </p>
              <div
                className="dmind-canvas"
                ref={viewport}
                onPointerDown={(e) => {
                  if ((e.target as Element).closest('[data-node]')) return
                  pan.current = {
                    x: e.clientX,
                    y: e.clientY,
                    left: e.currentTarget.scrollLeft,
                    top: e.currentTarget.scrollTop,
                  }
                  e.currentTarget.setPointerCapture(e.pointerId)
                }}
                onPointerMove={(e) => {
                  if (pan.current) {
                    e.currentTarget.scrollLeft =
                      pan.current.left - (e.clientX - pan.current.x)
                    e.currentTarget.scrollTop =
                      pan.current.top - (e.clientY - pan.current.y)
                  }
                }}
                onPointerUp={() => {
                  pan.current = null
                }}
                onPointerCancel={() => {
                  pan.current = null
                }}
              >
                <svg
                  width={width * zoom}
                  height={height * zoom}
                  viewBox={`${minX} ${minY} ${width} ${height}`}
                  aria-label={`${diagram.title} graph`}
                  role="group"
                  onPointerMove={(e) => {
                    if (!drag.current) return
                    const a = drag.current
                    setDragDelta({
                      ids: new Set(a.ids),
                      dx: (e.clientX - a.clientX) / zoom,
                      dy: (e.clientY - a.clientY) / zoom,
                    })
                  }}
                  onPointerUp={(e) => {
                    if (!drag.current) return
                    const a = drag.current
                    drag.current = null
                    setDragDelta(null)
                    const dx = (e.clientX - a.clientX) / zoom,
                      dy = (e.clientY - a.clientY) / zoom
                    if (Math.abs(e.clientX - a.clientX) + Math.abs(e.clientY - a.clientY) <= 3) return
                    ignoreClick.current = true // the click that follows a drag is not a selection
                    setTimeout(() => (ignoreClick.current = false), 0)
                    if (e.altKey && diagram.kind !== 'flowchart') {
                      // Alt-drop onto another topic moves the dragged topic and its branch under it.
                      const target = document
                        .elementsFromPoint(e.clientX, e.clientY)
                        .map((el) => el.closest('[data-node]')?.getAttribute('data-node'))
                        .find((id) => id && id !== a.id)
                      if (target) {
                        const r = reparent(diagram, a.id, target)
                        if ('error' in r) setMessage(r.error)
                        else {
                          commit(r.diagram)
                          setMessage('Moved under ' + (diagram.nodes.find((n) => n.id === target)?.label ?? 'the topic') + '.')
                        }
                        return
                      }
                    }
                    commit(moveNodes(diagram, a.ids, dx, dy))
                  }}
                  onPointerCancel={() => {
                    drag.current = null
                    setDragDelta(null)
                  }}
                >
                  <defs>
                    <marker
                      id="dmind-arrow"
                      markerWidth="8"
                      markerHeight="8"
                      refX="7"
                      refY="4"
                      orient="auto"
                    >
                      <path d="M0,0 L8,4 L0,8" fill="currentColor" />
                    </marker>
                  </defs>
                  <EdgesView edges={visibleEdges} byId={byId} />
                  {visible.map((n) => {
                    const moving = dragDelta?.ids.has(n.id)
                    return (
                      <NodeView
                        key={n.id}
                        n={n}
                        x={n.position!.x + (moving ? dragDelta!.dx : 0)}
                        y={n.position!.y + (moving ? dragDelta!.dy : 0)}
                        selected={groupSet.has(n.id)}
                        primary={selected === n.id}
                        onSelect={chooseNode}
                        onDragStart={startDrag}
                        onMenu={(id, at) => {
                          if (!groupSet.has(id)) chooseNode(id, false)
                          setMenu({ id, ...at })
                        }}
                      />
                    )
                  })}
                </svg>
              </div>
              <OutlineEditor
                diagram={diagram}
                selected={selected}
                group={groupSet}
                focusId={outlineFocus}
                onFocused={clearOutlineFocus}
                handlers={outlineHandlers}
              />
              <details className="dmind-keys">
                <summary>Keyboard shortcuts</summary>
                <ul>
                  <li>Arrow keys: move between topics. Alt+Arrow: nudge (Shift for more).</li>
                  <li>Enter or Space: select. Shift or Ctrl/⌘ with Enter or click: add to the selection.</li>
                  <li>Insert: add a child. Shift+Insert: add a sibling. Delete: remove the selection.</li>
                  <li>F2: rename. − and +: collapse and expand. Ctrl/⌘ A: select all visible topics.</li>
                  <li>Shift+F10 or the menu key: topic menu. Alt-drag a topic onto another to move it under it.</li>
                  <li>Ctrl/⌘ Z and Shift+Z: undo and redo. Ctrl/⌘ S: save.</li>
                </ul>
              </details>
            </div>
          )}
          {diagram && node && (
            <aside className="dmind-inspector">
              <h3>Topic details</h3>
              {group.length > 1 && (
                <p role="status" className="dmind-hint">
                  {group.length} topics selected. Colour, markers, collapse and delete apply to all of them.
                </p>
              )}
              <label>
                Label
                <input
                  ref={labelInput}
                  value={node.label}
                  maxLength={500}
                  onChange={(e) => changeNode({ label: e.target.value })}
                />
              </label>
              <label>
                Notes / algorithm
                <textarea
                  rows={6}
                  value={node.notes || ''}
                  maxLength={20000}
                  onChange={(e) => changeNode({ notes: e.target.value })}
                />
              </label>
              {citationsFor(diagram, node.id).length > 0 && (
                <>
                  <h4>Sources</h4>
                  <ul aria-label="Topic sources">
                    {citationsFor(diagram, node.id).map((c, i) => (
                      <li key={i}>{c.text}</li>
                    ))}
                  </ul>
                </>
              )}
              <NodeStyleControls
                diagram={diagram}
                ids={group}
                primary={selected}
                onChange={onStyleChange}
                onError={setMessage}
              />
              <button onClick={() => addChild()}>Add child · Insert</button>
              <button onClick={() => addChild(true)}>Add sibling</button>
              <button
                onClick={() =>
                  commit(patchNodes(diagram, group, { collapsed: !node.collapsed }))
                }
              >
                {node.collapsed ? 'Expand' : 'Collapse'} branch
              </button>
              <button
                disabled={diagram.nodes.length === 1}
                onClick={removeNode}
              >
                Remove branch · Delete
              </button>
              <h4>Directed links</h4>
              <label>
                Target
                <select
                  value={linkTarget}
                  onChange={(e) => setLinkTarget(e.target.value)}
                >
                  <option value="">Choose topic</option>
                  {diagram.nodes.map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Link type
                <select
                  value={linkKind}
                  onChange={(e) => setLinkKind(e.target.value as EdgeKind)}
                >
                  <option value="flow">Flow</option>
                  <option value="dependency">Dependency</option>
                  <option value="relationship">Relationship</option>
                  <option value="branch">Branch</option>
                </select>
              </label>
              <label>
                Condition / link label
                <input
                  value={linkLabel}
                  maxLength={500}
                  onChange={(e) => setLinkLabel(e.target.value)}
                  placeholder="e.g. payment failed"
                />
              </label>
              <button
                disabled={!linkTarget}
                onClick={() => {
                  commit({
                    ...diagram,
                    edges: [
                      ...diagram.edges,
                      {
                        id: newId(),
                        source: selected,
                        target: linkTarget,
                        kind: linkKind,
                        label: linkLabel,
                      },
                    ],
                  })
                  setLinkLabel('')
                }}
              >
                Add link
              </button>
              <ul>
                {diagram.edges
                  .filter((e) => e.source === selected || e.target === selected)
                  .map((e) => (
                    <li key={e.id}>
                      {e.kind}: {byId.get(e.source)?.label} →{' '}
                      {byId.get(e.target)?.label}
                      {e.label ? ` (${e.label})` : ''}
                      <button
                        aria-label={`Remove ${e.kind} link`}
                        onClick={() =>
                          commit({
                            ...diagram,
                            edges: diagram.edges.filter(
                              (link) => link.id !== e.id,
                            ),
                          })
                        }
                      >
                        Remove
                      </button>
                    </li>
                  ))}
              </ul>
              <h4>Matrix Designer handoff</h4>
              <label>
                Blueprint tier
                <select value={tier} onChange={(e) => setTier(e.target.value)}>
                  <option>minimal</option>
                  <option>standard</option>
                  <option>production</option>
                </select>
              </label>
              <button onClick={() => void handoff()}>
                Generate Design Bundle
              </button>
              {validationReport && (
                <button
                  onClick={() =>
                    download(
                      diagram.title + '-validation-report.json',
                      JSON.stringify(validationReport, null, 2),
                      'application/json',
                    )
                  }
                >
                  Export validation report
                </button>
              )}
              <p>
                Uses the edited graph as reference data. Returns a new
                validation report for review before coding.
              </p>
              {saved && (
                <>
                  <h4>Revision history</h4>
                  <button onClick={() => void loadRevisions()}>
                    Load saved revisions
                  </button>
                  {revisions.map((r) => (
                    <div key={r.revision} className="dmind-rev">
                      <span>
                        r{r.revision} · {r.nodes} topics
                        {r.createdAt ? ' · ' + relativeTime(r.createdAt) : ''}
                      </span>
                      <button
                        onClick={async () => {
                          const doc = await fetchRevision(r.revision)
                          if (!doc) return
                          commit(doc)
                          setMessage(
                            `Revision ${r.revision} restored as a draft. Save to append a new revision.`,
                          )
                        }}
                      >
                        Restore r{r.revision}
                      </button>
                      <button
                        aria-label={`Compare r${r.revision} with the current draft`}
                        onClick={async () => {
                          const doc = await fetchRevision(r.revision)
                          if (doc && diagram)
                            setChanges({
                              revision: r.revision,
                              lines: diffDiagrams(doc, diagram).summary.slice(0, 60),
                            })
                        }}
                      >
                        Compare
                      </button>
                    </div>
                  ))}
                  {revMore !== null && (
                    <button onClick={() => void loadRevisions(true)}>
                      Load older revisions
                    </button>
                  )}
                  {changes && (
                    <>
                      <h5>Changes since r{changes.revision}</h5>
                      {changes.lines.length ? (
                        <ul aria-label="Revision changes">
                          {changes.lines.map((l, i) => (
                            <li key={i}>{l}</li>
                          ))}
                        </ul>
                      ) : (
                        <p>The draft matches r{changes.revision}.</p>
                      )}
                    </>
                  )}
                  <button onClick={() => void save(false, !saved.archived)}>
                    {saved.archived ? 'Unarchive' : 'Archive'} diagram
                  </button>
                </>
              )}
              <p>Undo: Ctrl/⌘ Z · Redo: Ctrl/⌘ Shift Z. Save: Ctrl/⌘ S.</p>
            </aside>
          )}
        </div>
      </fieldset>
      {menu && (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          label="Topic menu"
          items={menuItems(menu.id)}
          onClose={() => {
            setMenu(null)
            focusNode(menu.id)
          }}
        />
      )}
    </section>
  )
}
