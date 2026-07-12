import React, { useEffect, useMemo, useRef, useState } from 'react'

export type PaletteAction = {
  id: string
  label: string
  hint?: string
  keywords?: string
  run: () => void
}

type CommandPaletteProps = {
  open: boolean
  actions: PaletteAction[]
  onClose: () => void
}

/**
 * Keyboard-first command palette (⌘K). A scaffold registry of actions per view;
 * later batches register coding, document, and approval actions here.
 */
export function CommandPalette({ open, actions, onClose }: CommandPaletteProps) {
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return actions
    return actions.filter((a) =>
      (a.label + ' ' + (a.keywords ?? '') + ' ' + (a.hint ?? '')).toLowerCase().includes(q),
    )
  }, [actions, query])

  useEffect(() => {
    if (open) {
      setQuery('')
      setActiveIndex(0)
      inputRef.current?.focus()
    }
  }, [open])

  useEffect(() => {
    setActiveIndex(0)
  }, [query])

  if (!open) return null

  function runAt(index: number) {
    const action = filtered[index]
    if (action) {
      onClose()
      action.run()
    }
  }

  function onKeyDown(event: React.KeyboardEvent) {
    switch (event.key) {
      case 'Escape':
        event.preventDefault()
        onClose()
        break
      case 'ArrowDown':
        event.preventDefault()
        setActiveIndex((i) => Math.min(i + 1, filtered.length - 1))
        break
      case 'ArrowUp':
        event.preventDefault()
        setActiveIndex((i) => Math.max(i - 1, 0))
        break
      case 'Enter':
        event.preventDefault()
        runAt(activeIndex)
        break
      default:
        break
    }
  }

  return (
    <div className="dp-modal-backdrop dp-modal-backdrop--top" onMouseDown={onClose}>
      <div
        className="dp-palette"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <input
          ref={inputRef}
          className="dp-palette__input"
          placeholder="Type a command or search…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Command palette search"
          aria-activedescendant={filtered[activeIndex] ? `dp-palette-opt-${filtered[activeIndex].id}` : undefined}
        />
        <ul className="dp-palette__list" role="listbox" aria-label="Commands">
          {filtered.length === 0 && <li className="dp-palette__empty">No matching commands</li>}
          {filtered.map((action, index) => (
            <li
              key={action.id}
              id={`dp-palette-opt-${action.id}`}
              role="option"
              aria-selected={index === activeIndex}
              className={'dp-palette__item' + (index === activeIndex ? ' is-active' : '')}
              onMouseEnter={() => setActiveIndex(index)}
              onMouseDown={(e) => {
                e.preventDefault()
                runAt(index)
              }}
            >
              <span>{action.label}</span>
              {action.hint && <span className="dp-palette__hint">{action.hint}</span>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
