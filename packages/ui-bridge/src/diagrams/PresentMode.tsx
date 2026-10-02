import React, { useEffect, useRef, useState } from 'react'
import type { Diagram } from './dmind'
import { toSlides } from './present'

/** Full-screen walk-through of a map. Keyboard: arrows, space, Home/End, Esc. No network. */
export function PresentMode({ diagram, onClose }: { diagram: Diagram; onClose: () => void }) {
  const slides = React.useMemo(() => toSlides(diagram), [diagram])
  const [i, setI] = useState(0)
  const [showNotes, setShowNotes] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  useEffect(() => {
    root.current?.focus()
  }, [])
  const go = (n: number) => setI(Math.max(0, Math.min(slides.length - 1, n)))
  const slide = slides[i]
  return (
    <div
      ref={root}
      className="dmind-present"
      role="dialog"
      aria-modal="true"
      aria-label={`Presenting ${diagram.title}`}
      tabIndex={-1}
      onKeyDown={(e) => {
        if (e.key === 'Escape') onClose()
        else if (['ArrowRight', 'ArrowDown', 'PageDown', ' '].includes(e.key)) (e.preventDefault(), go(i + 1))
        else if (['ArrowLeft', 'ArrowUp', 'PageUp'].includes(e.key)) (e.preventDefault(), go(i - 1))
        else if (e.key === 'Home') go(0)
        else if (e.key === 'End') go(slides.length - 1)
        else if (e.key.toLowerCase() === 'n') setShowNotes((v) => !v)
      }}
    >
      <div className="dmind-present-slide" aria-live="polite">
        <h1>{slide.title}</h1>
        {i === 0 && slides.length > 1 && <p className="dmind-present-sub">{slides.length - 1} section(s) · press → to begin</p>}
        <ul>
          {slide.bullets.map((b, k) => (
            <li key={k} style={{ marginLeft: b.level * 28 }}>
              {b.text}
            </li>
          ))}
        </ul>
        {showNotes && slide.notes.map((n, k) => <p key={k} className="dmind-present-notes">{n}</p>)}
      </div>
      <div className="dmind-present-bar">
        <button onClick={() => go(i - 1)} disabled={i === 0}>
          Back
        </button>
        <span>
          {i + 1} / {slides.length}
        </span>
        <button onClick={() => go(i + 1)} disabled={i === slides.length - 1}>
          Next
        </button>
        <button aria-pressed={showNotes} onClick={() => setShowNotes(!showNotes)}>
          Notes (N)
        </button>
        <button onClick={onClose}>Exit (Esc)</button>
      </div>
    </div>
  )
}
