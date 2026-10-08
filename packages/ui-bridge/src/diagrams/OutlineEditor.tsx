import React, { useEffect, useMemo, useState } from 'react'
import type { Diagram } from './dmind'
import { patchNodes } from './edit'
import { indentNode, moveSibling, outdentNode, outlineRows, type OutlineRow } from './outline'

const WINDOW = 300 // long outlines show their first rows until the person asks for all of them

type Handlers = {
  onSelect: (id: string) => void
  onChange: (next: Diagram, key?: string) => void
  onAddSibling: (id: string) => void
}

const Row = React.memo(function Row({
  row,
  number,
  diagram,
  isGroup,
  isCurrent,
  handlers,
}: {
  row: OutlineRow
  number: number
  diagram: Diagram
  isGroup: boolean
  isCurrent: boolean
  handlers: Handlers
}) {
  const { onSelect, onChange, onAddSibling } = handlers
  const id = row.id
  function key(e: React.KeyboardEvent<HTMLInputElement>) {
    e.stopPropagation() // typing here is not a canvas shortcut
    const run = (next: Diagram | null) => {
      if (next) onChange(next)
      e.preventDefault()
    }
    if (e.altKey && e.key === 'ArrowRight') return run(indentNode(diagram, id))
    if (e.altKey && e.key === 'ArrowLeft') return run(outdentNode(diagram, id))
    if (e.altKey && e.key === 'ArrowUp') return run(moveSibling(diagram, id, -1))
    if (e.altKey && e.key === 'ArrowDown') return run(moveSibling(diagram, id, 1))
    if (e.key === 'Enter') {
      e.preventDefault()
      onAddSibling(id)
    } else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      const li = e.currentTarget.closest('li')
      const next = (e.key === 'ArrowUp' ? li?.previousElementSibling : li?.nextElementSibling)?.querySelector('input')
      if (next) {
        e.preventDefault()
        next.focus()
      }
    }
  }
  return (
    <li
      role="treeitem"
      aria-level={row.depth + 1}
      aria-selected={isGroup}
      aria-expanded={row.hasChildren ? !row.collapsed : undefined}
      style={{ paddingLeft: Math.min(row.depth, 12) * 16 }}
    >
      {row.hasChildren ? (
        <button
          className="dmind-fold"
          aria-label={`${row.collapsed ? 'Expand' : 'Collapse'} ${row.label}`}
          onClick={() => onChange(patchNodes(diagram, [id], { collapsed: !row.collapsed }))}
        >
          {row.collapsed ? '▸' : '▾'}
        </button>
      ) : (
        <span className="dmind-fold" aria-hidden="true" />
      )}
      <input
        data-outline={id}
        aria-label={`Topic ${number}, level ${row.depth + 1}`}
        aria-current={isCurrent ? 'true' : undefined}
        aria-keyshortcuts="Alt+ArrowLeft Alt+ArrowRight Alt+ArrowUp Alt+ArrowDown"
        value={row.label}
        maxLength={500}
        onFocus={() => onSelect(id)}
        onKeyDown={key}
        onChange={(e) => onChange(patchNodes(diagram, [id], { label: e.target.value }), 'label:' + id)}
      />
      <span className="dmind-rowtools">
        <button aria-label={`Outdent ${row.label}`} disabled={!row.canOutdent} onClick={() => onChange(outdentNode(diagram, id)!)}>
          ←
        </button>
        <button aria-label={`Indent ${row.label}`} disabled={!row.canIndent} onClick={() => onChange(indentNode(diagram, id)!)}>
          →
        </button>
        <button aria-label={`Move ${row.label} up`} disabled={!row.canMoveUp} onClick={() => onChange(moveSibling(diagram, id, -1)!)}>
          ↑
        </button>
        <button aria-label={`Move ${row.label} down`} disabled={!row.canMoveDown} onClick={() => onChange(moveSibling(diagram, id, 1)!)}>
          ↓
        </button>
      </span>
    </li>
  )
})

/**
 * The branch hierarchy as an editable, keyboard-friendly outline (batch B4). It edits the same
 * document as the canvas, so a change here appears there at once and the reverse.
 *
 * In a topic's field: Enter adds a sibling below; Alt+Left/Right outdent and indent; Alt+Up/Down
 * move among siblings; Up/Down move to the neighbouring topic.
 *
 * Memoised, with memoised rows: dragging on the canvas re-renders the workspace many times a
 * second, and none of that may touch a long outline.
 */
export const OutlineEditor = React.memo(function OutlineEditor({
  diagram,
  selected,
  group,
  focusId,
  handlers,
  onFocused,
}: {
  diagram: Diagram
  selected: string
  group: Set<string>
  focusId: string
  handlers: Handlers
  onFocused: () => void
}) {
  const rows = useMemo(() => outlineRows(diagram), [diagram])
  const [all, setAll] = useState(false)
  const limited = !all && rows.length > WINDOW
  const target = rows.findIndex((r) => r.id === focusId)
  const shown = limited ? rows.slice(0, Math.max(WINDOW, target + 1)) : rows

  useEffect(() => {
    if (!focusId) return
    const el = document.querySelector<HTMLInputElement>(`[data-outline="${CSS.escape(focusId)}"]`)
    if (el) {
      el.focus()
      el.select()
      onFocused()
    }
  }, [focusId, shown.length, onFocused])

  return (
    <details className="dmind-outline" open>
      <summary>Outline · edit topics and structure</summary>
      <p className="dmind-hint">Enter adds a sibling. Alt+← / → outdent or indent; Alt+↑ / ↓ reorder.</p>
      <ul role="tree" aria-label="Topic outline">
        {shown.map((r, i) => (
          <Row
            key={r.id}
            row={r}
            number={i + 1}
            diagram={diagram}
            isGroup={group.has(r.id)}
            isCurrent={selected === r.id}
            handlers={handlers}
          />
        ))}
      </ul>
      {limited && shown.length < rows.length && (
        <button onClick={() => setAll(true)}>Show all {rows.length} topics</button>
      )}
    </details>
  )
})
