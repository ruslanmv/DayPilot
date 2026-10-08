import React, { useEffect, useRef, useState } from 'react'

export type MenuItem = {
  label: string
  onSelect: () => void
  disabled?: boolean
}

/**
 * A keyboard-operable context menu (batch B4): arrows move, Enter or Space chooses, Escape or Tab
 * closes. Opened by right-click or the context-menu key; focus returns to the caller on close.
 */
export function ContextMenu({
  x,
  y,
  label,
  items,
  onClose,
}: {
  x: number
  y: number
  label: string
  items: MenuItem[]
  onClose: () => void
}) {
  const first = Math.max(0, items.findIndex((i) => !i.disabled))
  const [active, setActive] = useState(first)
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const wrap = useRef<HTMLDivElement>(null)

  useEffect(() => {
    refs.current[active]?.focus()
  }, [active])
  useEffect(() => {
    const away = (e: Event) => {
      if (!wrap.current?.contains(e.target as Node)) onClose()
    }
    document.addEventListener('pointerdown', away, true)
    window.addEventListener('resize', onClose)
    window.addEventListener('blur', onClose)
    return () => {
      document.removeEventListener('pointerdown', away, true)
      window.removeEventListener('resize', onClose)
      window.removeEventListener('blur', onClose)
    }
  }, [onClose])

  const step = (from: number, dir: 1 | -1) => {
    for (let n = 1; n <= items.length; n++) {
      const i = (from + dir * n + items.length * n) % items.length
      if (!items[i].disabled) return i
    }
    return from
  }
  function onKeyDown(e: React.KeyboardEvent) {
    e.stopPropagation() // the workspace's own shortcuts must not fire behind the menu
    if (e.key === 'ArrowDown') setActive(step(active, 1))
    else if (e.key === 'ArrowUp') setActive(step(active, -1))
    else if (e.key === 'Home') setActive(first)
    else if (e.key === 'End') setActive(step(items.length, -1))
    else if (e.key === 'Escape' || e.key === 'Tab') onClose()
    else return
    e.preventDefault()
  }

  const left = Math.max(4, Math.min(x, window.innerWidth - 240))
  const top = Math.max(4, Math.min(y, window.innerHeight - items.length * 36 - 16))
  return (
    <div
      ref={wrap}
      role="menu"
      aria-label={label}
      className="dmind-menu"
      style={{ left, top }}
      onKeyDown={onKeyDown}
    >
      {items.map((item, i) => (
        <button
          key={item.label}
          ref={(el) => {
            refs.current[i] = el
          }}
          role="menuitem"
          tabIndex={i === active ? 0 : -1}
          aria-disabled={item.disabled || undefined}
          onMouseEnter={() => !item.disabled && setActive(i)}
          onClick={() => {
            if (item.disabled) return
            onClose()
            item.onSelect()
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
