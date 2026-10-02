import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { workspaceId } from '../env'
import {
  diagramsApi,
  type DiagramSummary,
  type SavedDiagram,
} from './diagramsClient'
import {
  addTopic,
  commitHistory,
  download,
  fromBundle,
  fromOutline,
  graphAnalysis,
  layout,
  newId,
  redoHistory,
  removeBranch,
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
import './diagrams.css'

type Revision = { revision: number; document: Diagram }
type NodeViewProps = {
  n: DiagramNode
  x: number
  y: number
  selected: boolean
  onSelect: (id: string) => void
  onDragStart: (e: React.PointerEvent<SVGGElement>, n: DiagramNode) => void
}
// Memoised: during a drag only the moved topic receives new props.
const NodeView = React.memo(function NodeView({
  n,
  x,
  y,
  selected,
  onSelect,
  onDragStart,
}: NodeViewProps) {
  return (
    <g
      data-node={n.id}
      transform={`translate(${x},${y})`}
      role="button"
      tabIndex={0}
      aria-label={n.label + (n.collapsed ? ', collapsed' : '')}
      aria-pressed={selected}
      onClick={() => onSelect(n.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect(n.id)
        }
      }}
      onPointerDown={(e) => onDragStart(e, n)}
    >
      <rect
        width="200"
        height="64"
        rx="12"
        className={selected ? 'is-selected' : ''}
      />
      <text x="12" y="37">
        {n.label.length > 23 ? n.label.slice(0, 22) + '…' : n.label}
        {n.collapsed ? ' ⊕' : ''}
      </text>
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
        const a = byId.get(e.source)!.position!,
          b = byId.get(e.target)!.position!
        return (
          <g key={e.id}>
            <path
              d={`M${a.x + 100},${a.y + 32} L${b.x + 100},${b.y + 32}`}
              className={`dmind-edge dmind-edge-${e.kind}`}
              markerEnd={e.kind === 'branch' ? undefined : 'url(#dmind-arrow)'}
            />
            <text x={(a.x + b.x) / 2 + 100} y={(a.y + b.y) / 2 + 24}>
              {e.label}
            </text>
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
  const [items, setItems] = useState<DiagramSummary[]>([]),
    [showArchived, setShowArchived] = useState(false)
  const [history, setHistory] = useState<History | null>(null),
    [saved, setSaved] = useState<SavedDiagram | null>(null)
  const [dirty, setDirty] = useState(false),
    [selected, setSelected] = useState(''),
    [busy, setBusy] = useState(false)
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
  const [revisions, setRevisions] = useState<Revision[]>([]),
    [zoom, setZoom] = useState(1)
  const [validationReport, setValidationReport] = useState<Record<
    string,
    unknown
  > | null>(null)
  const [dragPosition, setDragPosition] = useState<{
    id: string
    x: number
    y: number
  } | null>(null)
  const drag = useRef<{
    id: string
    clientX: number
    clientY: number
    x: number
    y: number
  } | null>(null)
  const pan = useRef<{
    x: number
    y: number
    left: number
    top: number
  } | null>(null)
  const viewport = useRef<HTMLDivElement>(null),
    input = useRef<HTMLInputElement>(null)
  const draftKey = `daypilot.dmind.draft:${workspaceId()}:${accountKey}`
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
      y0 = Math.min(y0, n.position!.y - 30)
      x1 = Math.max(x1, n.position!.x + 240)
      y1 = Math.max(y1, n.position!.y + 100)
    }
    return { minX: x0, minY: y0, width: x1 - x0, height: y1 - y0 }
  }, [visible])

  async function refresh() {
    const result = await diagramsApi.list()
    if (result.ok) setItems(result.data.items)
    else
      setMessage(
        'Saved diagrams unavailable. You can create, edit and export a local draft. ' +
          result.error,
      )
  }
  useEffect(() => {
    let active = true
    diagramsApi.list().then((r) => {
      if (!active) return
      if (r.ok) setItems(r.data.items)
      else
        setMessage(
          'Create a local draft or reconnect to load saved diagrams. ' +
            r.error,
        )
    })
    return () => {
      active = false
    }
  }, [])
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
  useEffect(() => {
    if (!diagram || !dirty) return
    try {
      localStorage.setItem(
        draftKey,
        JSON.stringify({ document: diagram, saved }),
      )
    } catch {
      setMessage(
        'Browser draft cache is full. Export JSON or save to preserve your work.',
      )
    }
  }, [diagram, dirty, draftKey, saved])

  useEffect(() => {
    if (diagram && !diagram.nodes.some((n) => n.id === selected))
      setSelected(diagram.nodes[0].id)
  }, [diagram, selected])

  const startDrag = useCallback(
    (e: React.PointerEvent<SVGGElement>, n: DiagramNode) => {
      if (busy) return
      e.stopPropagation()
      setSelected(n.id)
      drag.current = {
        id: n.id,
        clientX: e.clientX,
        clientY: e.clientY,
        x: n.position!.x,
        y: n.position!.y,
      }
      e.currentTarget.setPointerCapture(e.pointerId)
    },
    [busy],
  )
  function open(
    d: Diagram,
    persisted: SavedDiagram | null = null,
    isDirty = true,
  ) {
    const safe = validateDiagram(d)
    setHistory(startHistory(safe))
    setSaved(persisted)
    setDirty(isDirty)
    setSelected(safe.nodes[0].id)
    setValidationReport(null)
    setWizard(0)
    setRevisions([])
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
  function commit(d: Diagram) {
    try {
      const next = validateDiagram(d)
      setHistory((h) => commitHistory(h, next))
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
      })
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
    const next = removeBranch(diagram, selected)
    if (!next) {
      setMessage('Keep at least one node. Create a new diagram to start again.')
      return
    }
    commit(next)
    setSelected(next.nodes[0].id)
  }
  async function save(copy = false, archive = saved?.archived ?? false) {
    if (!diagram) return
    setBusy(true)
    const result =
      saved && !copy
        ? await diagramsApi.save(saved.id, diagram, saved.revision, archive)
        : await diagramsApi.create(diagram)
    setBusy(false)
    if (result.ok) {
      open(result.data.document, result.data, false)
      try {
        localStorage.removeItem(draftKey)
      } catch {
        /* Browser storage may be blocked; the server save succeeded. */
      }
      setMessage(
        `Saved revision ${result.data.revision}${result.data.archived ? ' · archived' : ''}`,
      )
      await refresh()
    } else
      setMessage(
        result.status === 409
          ? 'This diagram changed elsewhere. Your draft is safe here. Save a copy or reload the latest revision.'
          : result.error,
      )
  }
  async function load(id: string) {
    if (!canLeave()) return
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
      } else d = fromOutline(topic, content, kind)
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
      if (file.size > 2_000_000) throw new Error('Use a file smaller than 2 MB')
      const text = await file.text()
      if (file.name.toLowerCase().endsWith('.json')) {
        const value = JSON.parse(text)
        const d =
          value?.schema_version === 'matrix.designer.bundle/v1'
            ? fromBundle(value)
            : validateDiagram(value)
        setPreview({ ...d, id: newId() })
        setTopic(d.title)
        setWizard(3)
      } else if (/\.(txt|md|markdown)$/i.test(file.name)) {
        if (text.length > 100000)
          throw new Error('Text source exceeds 100000 characters')
        setContent(text)
        if (!topic) setTopic(file.name.replace(/\.[^.]+$/, '').slice(0, 200))
        setMessage(
          'Text loaded. Indentation becomes branches; each line becomes a topic.',
        )
      } else
        throw new Error(
          'Supported attachments: TXT, Markdown, dmind JSON or Matrix Design Bundle JSON. PDF and image extraction are planned.',
        )
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Import failed')
    }
    if (input.current) input.current.value = ''
  }
  function exportAs(format: string) {
    if (!diagram) return
    const name = diagram.title.slice(0, 80)
    if (format === 'json')
      download(
        name + '.dmind.json',
        JSON.stringify(diagram, null, 2),
        'application/json',
      )
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
  function keyDown(e: React.KeyboardEvent) {
    e.stopPropagation() // Keep canvas shortcuts within dmind; shell F opens Focus Mode.
    if (
      busy ||
      wizard ||
      !diagram ||
      (e.target as HTMLElement).matches('input,textarea,select')
    )
      return
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
      e.preventDefault()
      e.shiftKey ? redo() : undo()
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
      e.preventDefault()
      void save()
    }
    if (e.key === 'Insert') {
      e.preventDefault()
      addChild()
    }
    if (e.key === 'Delete') {
      e.preventDefault()
      removeNode()
    }
  }
  return (
    <section
      className="dmind"
      aria-label="dmind diagrams workspace"
      onKeyDown={keyDown}
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
            }
          }}
        >
          New diagram
        </button>
      </header>
      <p className="dmind-status" role="status" aria-live="polite">
        {busy
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
        accept=".txt,.md,.markdown,.json"
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
                  Attach text or import JSON
                </button>
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
                    ? 'Sends the topic and attached text to your configured Matrix Designer provider. Returns batches and dependencies for review.'
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
            <button onClick={() => void refresh()}>Refresh</button>
            <label>
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(e) => setShowArchived(e.target.checked)}
              />{' '}
              Include archived
            </label>
            {items
              .filter((i) => showArchived || !i.archived)
              .map((i) => (
                <button
                  key={i.id}
                  aria-pressed={saved?.id === i.id}
                  onClick={() => void load(i.id)}
                >
                  {i.title}
                  <small>
                    Revision {i.revision}
                    {i.archived ? ' · archived' : ''}
                  </small>
                </button>
              ))}
            {!items.length && <p>Your saved diagrams appear here.</p>}
            <button
              onClick={() => {
                try {
                  const cache = localStorage.getItem(draftKey)
                  if (!cache) {
                    setMessage('No cached draft.')
                    return
                  }
                  if (canLeave()) {
                    const draft = JSON.parse(cache)
                    open(draft.document, draft.saved)
                    setMessage(
                      'Recovered browser draft. Save or export it to preserve it.',
                    )
                  }
                } catch {
                  setMessage(
                    'Cached draft could not be read. Import an exported JSON copy.',
                  )
                }
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
                <button onClick={() => commit(layout(diagram, true))}>
                  Auto-layout
                </button>
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
                  <option value="json">dmind JSON</option>
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
                    setDragPosition({
                      id: a.id,
                      x: a.x + (e.clientX - a.clientX) / zoom,
                      y: a.y + (e.clientY - a.clientY) / zoom,
                    })
                  }}
                  onPointerUp={(e) => {
                    if (!drag.current) return
                    const a = drag.current
                    drag.current = null
                    setDragPosition(null)
                    const position = {
                      x: a.x + (e.clientX - a.clientX) / zoom,
                      y: a.y + (e.clientY - a.clientY) / zoom,
                    }
                    if (
                      Math.abs(e.clientX - a.clientX) +
                        Math.abs(e.clientY - a.clientY) >
                      3
                    )
                      commit({
                        ...diagram,
                        nodes: arranged!.nodes.map((n) =>
                          n.id === a.id ? { ...n, position } : n,
                        ),
                      })
                  }}
                  onPointerCancel={() => {
                    drag.current = null
                    setDragPosition(null)
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
                    const p =
                      dragPosition?.id === n.id ? dragPosition : n.position!
                    return (
                      <NodeView
                        key={n.id}
                        n={n}
                        x={p.x}
                        y={p.y}
                        selected={selected === n.id}
                        onSelect={setSelected}
                        onDragStart={startDrag}
                      />
                    )
                  })}
                </svg>
              </div>
              <details>
                <summary>Outline · keyboard-friendly node selection</summary>
                <ul>
                  {diagram.nodes.map((n) => (
                    <li key={n.id}>
                      <button
                        aria-pressed={selected === n.id}
                        onClick={() => setSelected(n.id)}
                      >
                        {n.label}
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
            </div>
          )}
          {diagram && node && (
            <aside className="dmind-inspector">
              <h3>Topic details</h3>
              <label>
                Label
                <input
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
              <button onClick={() => addChild()}>Add child · Insert</button>
              <button onClick={() => addChild(true)}>Add sibling</button>
              <button
                onClick={() => changeNode({ collapsed: !node.collapsed })}
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
                  <button
                    onClick={async () => {
                      const r = await diagramsApi.revisions(saved.id)
                      if (r.ok) setRevisions(r.data.items)
                      else setMessage(r.error)
                    }}
                  >
                    Load saved revisions
                  </button>
                  {revisions.map((r) => (
                    <button
                      key={r.revision}
                      onClick={() => {
                        commit(r.document)
                        setMessage(
                          `Revision ${r.revision} restored as a draft. Save to append a new revision.`,
                        )
                      }}
                    >
                      Restore r{r.revision}
                    </button>
                  ))}
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
    </section>
  )
}
