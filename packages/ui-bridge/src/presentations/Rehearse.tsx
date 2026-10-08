import React, { useCallback, useEffect, useRef, useState } from 'react'
import { presentationsApi, type Slide } from './client'
import { useBlobUrl } from './files'
import { clock } from './talk'

/**
 * Practise the talk against its timing: the rendered slide, the words to say, a clock for this
 * slide and for the whole talk, and whether you are ahead of or behind the plan.
 * Keys: → or Space next, ← back, P pause/resume, Esc close.
 */
export function Rehearse({ deckId, revision, slides, rendered, onClose }: { deckId: string; revision: number; slides: Slide[]; rendered: number; onClose: () => void }) {
  const [i, setI] = useState(0)
  const [running, setRunning] = useState(false)
  const [total, setTotal] = useState(0)
  const [here, setHere] = useState(0)
  const box = useRef<HTMLDivElement>(null)
  const img = useBlobUrl(i < rendered ? presentationsApi.fileUrl(deckId, revision, 'png', i + 1) : null)
  const plan = slides.map((s) => s.seconds ?? 0)
  const planned = plan.reduce((a, b) => a + b, 0)
  const startOf = plan.slice(0, i).reduce((a, b) => a + b, 0)
  const s = slides[i]
  const goal = plan[i] || 0

  useEffect(() => {
    box.current?.focus()
  }, [])
  useEffect(() => {
    if (!running) return
    const t = setInterval(() => {
      setTotal((x) => x + 1)
      setHere((x) => x + 1)
    }, 1000)
    return () => clearInterval(t)
  }, [running])
  const go = useCallback((n: number) => {
    const j = Math.max(0, Math.min(slides.length - 1, n))
    setI(j)
    setHere(0)
    setRunning(true)
  }, [slides.length])
  function onKey(e: React.KeyboardEvent) {
    if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') { e.preventDefault(); go(i + 1) }
    else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); go(i - 1) }
    else if (e.key.toLowerCase() === 'p') setRunning((r) => !r)
    else if (e.key === 'Escape') onClose()
  }
  // Ahead/behind: where the plan says you should be now versus where you are.
  const drift = total - (startOf + Math.min(here, goal))
  const status = !running && total === 0 ? 'Press Start or → to begin' : Math.abs(drift) < 10 ? 'On time' : drift > 0 ? `${clock(drift)} behind plan` : `${clock(-drift)} ahead of plan`
  const over = goal > 0 && here > goal

  return (
    <div className="pz-rehearse" role="dialog" aria-modal="true" aria-label="Rehearse the talk" tabIndex={-1} ref={box} onKeyDown={onKey}>
      <div className="pz-rehearse-top">
        <strong>Slide {i + 1} of {slides.length}</strong>
        <span className={`pz-clock${over ? ' is-over' : ''}`} aria-label="Time on this slide">{clock(here)} / {clock(goal)}</span>
        <span className={`pz-progressbar${over ? ' is-over' : ''}`} aria-hidden="true"><i style={{ width: `${goal ? Math.min(100, (here / goal) * 100) : 0}%` }} /></span>
        <span aria-label="Whole talk">{clock(total)} / {clock(planned)}</span>
        <span role="status">{status}</span>
        <span className="pz-spacer" />
        <button type="button" onClick={() => setRunning((r) => !r)}>{running ? 'Pause' : total ? 'Resume' : 'Start'}</button>
        <button type="button" onClick={() => { setTotal(0); setHere(0); setI(0); setRunning(false) }}>Restart</button>
        <button type="button" onClick={onClose}>Close</button>
      </div>
      <div className="pz-rehearse-body">
        <div>{img ? <img src={img} alt={`Slide ${i + 1}: ${s?.title ?? ''}`} /> : <div className="pz-canvas-empty">{s?.title}</div>}</div>
        <div className="pz-rehearse-script">
          <h4>{s?.title}</h4>
          <p>{(s?.script ?? '').trim() || 'No script for this slide yet.'}</p>
          {s?.notes && <p className="pz-muted">Guidance: {s.notes}</p>}
          {slides[i + 1] && <p className="pz-muted">Next: {slides[i + 1].title}</p>}
        </div>
      </div>
      <div className="pz-actions">
        <button type="button" disabled={i === 0} onClick={() => go(i - 1)}>← Back</button>
        <button type="button" className="pz-primary" disabled={i === slides.length - 1} onClick={() => go(i + 1)}>Next →</button>
      </div>
    </div>
  )
}
