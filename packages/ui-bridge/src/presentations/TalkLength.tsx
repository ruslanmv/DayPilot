import React from 'react'
import type { Pace } from './client'
import { LENGTHS, PACES } from './talk'

/** Talk length in minutes (common choices first, any other value allowed) and speaking pace. */
export function TalkLength({ minutes, pace, onChange, legend = 'How long will you speak?' }: {
  minutes: number; pace: Pace; onChange: (minutes: number, pace: Pace) => void; legend?: string
}) {
  const custom = !LENGTHS.includes(minutes)
  return (
    <fieldset className="pz-talk">
      <legend>{legend}</legend>
      <div className="pz-chips" role="radiogroup" aria-label="Talk length">
        {LENGTHS.map((m) => (
          <label key={m} className={minutes === m ? 'is-selected' : ''}>
            <input type="radio" name="talk-minutes" checked={minutes === m} onChange={() => onChange(m, pace)} />
            {m} min
          </label>
        ))}
        <label className={custom ? 'is-selected' : ''}>
          <input type="radio" name="talk-minutes" checked={custom} onChange={() => onChange(custom ? minutes : 8, pace)} />
          Other
        </label>
        {custom && (
          <input type="number" min={1} max={120} aria-label="Minutes" className="pz-minutes" value={minutes} onChange={(e) => onChange(Math.max(1, Math.min(120, Number(e.target.value) || 1)), pace)} />
        )}
      </div>
      <label className="pz-field pz-pace">
        Speaking pace
        <select value={pace} onChange={(e) => onChange(minutes, e.target.value as Pace)}>
          {PACES.map((p) => <option key={p.id} value={p.id}>{p.label} (~{p.wpm} words/min)</option>)}
        </select>
      </label>
    </fieldset>
  )
}
