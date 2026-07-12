import React, { useEffect } from 'react'
import type { DayPilotTask } from '@daypilot/shared-types'

type FocusModeProps = {
  task: DayPilotTask
  onExit: (outcome: 'done' | 'blocked' | 'hand_to_ai' | 'cancel') => void
}

/**
 * Focus Mode: a first-class Command action that hides all panes except the
 * current block, its context, and the allowed exits (done / blocked / hand to
 * AI). Escape cancels. This is the "What do I do now?" mental mode made real.
 */
export function FocusMode({ task, onExit }: FocusModeProps) {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onExit('cancel')
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onExit])

  return (
    <div className="dp-focus" role="dialog" aria-modal="true" aria-label="Focus Mode">
      <div className="dp-focus__inner">
        <div className="dp-focus__eyebrow">FOCUS · {task.start ?? 'now'}{task.end ? `–${task.end}` : ''}</div>
        <h1 className="dp-focus__title">{task.title}</h1>
        {task.context && <p className="dp-focus__context">{task.context}</p>}
        <div className="dp-focus__meta">
          <span className="dp-pill dp-pill--muted">{task.owner === 'ai' ? 'AI' : 'You'}</span>
          {task.executor && <span className="dp-pill dp-pill--muted">{task.executor}</span>}
          <span className="dp-pill dp-pill--muted">{task.priority}</span>
        </div>
        {task.nextAction && (
          <p className="dp-focus__next"><strong>Next:</strong> {task.nextAction}</p>
        )}
        <div className="dp-focus__actions">
          <button className="dp-send-button" onClick={() => onExit('done')}>Mark done</button>
          <button className="dp-ghost-button" onClick={() => onExit('blocked')}>Blocked</button>
          <button className="dp-ghost-button" onClick={() => onExit('hand_to_ai')}>Hand to AI</button>
          <button className="dp-ghost-button" onClick={() => onExit('cancel')}>Exit focus (Esc)</button>
        </div>
      </div>
    </div>
  )
}
