import React, { useEffect, useMemo, useState } from 'react'
import type { Diagram } from './dmind'
import { parentOf, reparent, setNodeMeta, toggleMarker, validParents } from './edit'
import { safeHref } from './links'
import { ACCENTS, MARKERS, cleanMarkers } from './style'

/**
 * Appearance, link and placement controls for the selected topics (batch B4). Changes apply to
 * every topic in the selection; a link and a new parent apply to the primary topic.
 */
export const NodeStyleControls = React.memo(function NodeStyleControls({
  diagram,
  ids,
  primary,
  onChange,
  onError,
}: {
  diagram: Diagram
  ids: string[]
  primary: string
  onChange: (next: Diagram, key?: string) => void
  onError: (message: string) => void
}) {
  const node = diagram.nodes.find((n) => n.id === primary)!
  const accent = node.metadata?.accent
  const marks = cleanMarkers(node.metadata?.markers)
  const href = safeHref(node.metadata?.link)
  const [link, setLink] = useState((node.metadata?.link as string) || '')
  const [linkError, setLinkError] = useState('')
  useEffect(() => {
    setLink((node.metadata?.link as string) || '')
    setLinkError('')
  }, [primary, node.metadata?.link])

  function commitLink() {
    const text = link.trim()
    if (!text) {
      setLinkError('')
      if (node.metadata?.link !== undefined) onChange(setNodeMeta(diagram, [primary], 'link', undefined))
      return
    }
    const safe = safeHref(text)
    if (!safe) {
      setLinkError('Only http and https links are allowed, without spaces or credentials.')
      return
    }
    setLinkError('')
    if (safe !== node.metadata?.link) onChange(setNodeMeta(diagram, [primary], 'link', safe))
  }

  const parents = useMemo(() => validParents(diagram, primary), [diagram, primary])
  const current = parentOf(diagram, primary) ?? ''
  const label = (id: string) => diagram.nodes.find((n) => n.id === id)?.label ?? id
  return (
    <div className="dmind-style">
      <h4>Appearance</h4>
      <div role="group" aria-label="Accent colour" className="dmind-swatches">
        {ACCENTS.map((a) => (
          <button
            key={a.id}
            aria-label={`Accent ${a.label}`}
            aria-pressed={accent === a.id}
            style={{ background: a.hex }}
            onClick={() => onChange(setNodeMeta(diagram, ids, 'accent', accent === a.id ? undefined : a.id))}
          />
        ))}
        <button aria-label="No accent" aria-pressed={!accent} onClick={() => onChange(setNodeMeta(diagram, ids, 'accent', undefined))}>
          ∅
        </button>
      </div>
      <div role="group" aria-label="Markers" className="dmind-markers">
        {MARKERS.map((m) => (
          <button
            key={m.id}
            aria-label={m.label}
            title={m.label}
            aria-pressed={marks.includes(m.id)}
            onClick={() => onChange(toggleMarker(diagram, ids, m.id))}
          >
            {m.glyph}
          </button>
        ))}
      </div>
      <label>
        Link
        <input
          value={link}
          maxLength={2048}
          placeholder="https://…"
          aria-invalid={!!linkError}
          onChange={(e) => setLink(e.target.value)}
          onBlur={commitLink}
          onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), commitLink())}
        />
      </label>
      {linkError && (
        <p role="alert" className="dmind-error">
          {linkError}
        </p>
      )}
      {href && (
        <p>
          <a href={href} target="_blank" rel="noopener noreferrer nofollow">
            Open link ↗
          </a>
        </p>
      )}
      <label>
        Move under
        <select
          aria-label="Move under"
          value={current}
          disabled={diagram.kind === 'flowchart'}
          onChange={(e) => {
            const r = reparent(diagram, primary, e.target.value || null)
            if ('error' in r) onError(r.error)
            else if (r.diagram !== diagram) onChange(r.diagram)
          }}
        >
          <option value="">No parent (top level)</option>
          {parents.map((id) => (
            <option key={id} value={id}>
              {label(id)}
            </option>
          ))}
        </select>
      </label>
      {diagram.kind === 'flowchart' && (
        <p className="dmind-hint">Flowcharts are arranged by their flow links, not by branches.</p>
      )}
    </div>
  )
})
