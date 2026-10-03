import React from 'react'
import type { Slide, Storyline } from './client'
import { TYPE_LABELS, fieldsFor, newSlide, readField, writeField } from './outline'

/**
 * The storyline as plain fields: what each slide says, never where things go. Layout, type sizes,
 * colours and logos come from the company's brand kit when the deck is built.
 */
export function OutlineEditor({
  storyline,
  onChange,
  locked = [],
}: {
  storyline: Storyline
  onChange: (next: Storyline) => void
  locked?: string[]
}) {
  const slides = storyline.slides
  const set = (i: number, s: Slide) => onChange({ ...storyline, slides: slides.map((x, k) => (k === i ? s : x)) })
  const move = (i: number, d: number) => {
    const j = i + d
    if (j < 0 || j >= slides.length) return
    const next = slides.slice()
    ;[next[i], next[j]] = [next[j], next[i]]
    onChange({ ...storyline, slides: next })
  }
  return (
    <div className="pz-outline">
      <label className="pz-field">
        Presentation title
        <input value={storyline.title} maxLength={200} onChange={(e) => onChange({ ...storyline, title: e.target.value })} />
      </label>
      <ol className="pz-slides">
        {slides.map((s, i) => {
          const isLocked = !!s.id && locked.includes(s.id)
          return (
            <li key={s.id ?? i} className="pz-slide-card" aria-label={`Slide ${i + 1}: ${s.title}`}>
              <div className="pz-slide-head">
                <span className="pz-num">{i + 1}</span>
                <span className="pz-type">{TYPE_LABELS[s.type] ?? s.type}</span>
                {isLocked && <span className="pz-badge">Locked</span>}
                <span className="pz-spacer" />
                <button type="button" aria-label={`Move slide ${i + 1} up`} disabled={i === 0 || isLocked} onClick={() => move(i, -1)}>↑</button>
                <button type="button" aria-label={`Move slide ${i + 1} down`} disabled={i === slides.length - 1 || isLocked} onClick={() => move(i, 1)}>↓</button>
                <button type="button" aria-label={`Remove slide ${i + 1}`} disabled={slides.length <= 1 || isLocked} onClick={() => onChange({ ...storyline, slides: slides.filter((_, k) => k !== i) })}>Remove</button>
              </div>
              <fieldset disabled={isLocked} className="pz-slide-body">
                <label className="pz-field">
                  Title
                  <input value={s.title} maxLength={160} onChange={(e) => set(i, { ...s, title: e.target.value })} />
                </label>
                {fieldsFor(s.type).map((f) => (
                  <label key={f.key} className="pz-field">
                    {f.label}
                    {f.multiline ? (
                      <textarea rows={Math.min(8, Math.max(2, readField(s, f.key).split('\n').length + 1))} value={readField(s, f.key)} onChange={(e) => set(i, writeField(s, f.key, e.target.value))} />
                    ) : (
                      <input value={readField(s, f.key)} onChange={(e) => set(i, writeField(s, f.key, e.target.value))} />
                    )}
                    {f.hint && <small>{f.hint}</small>}
                  </label>
                ))}
                <details>
                  <summary>Speaker notes</summary>
                  <textarea aria-label={`Speaker notes for slide ${i + 1}`} rows={3} maxLength={4000} value={s.notes ?? ''} onChange={(e) => set(i, { ...s, notes: e.target.value })} />
                </details>
              </fieldset>
            </li>
          )
        })}
      </ol>
      <label className="pz-field pz-add">
        Add a slide
        <select
          value=""
          disabled={slides.length >= 50}
          onChange={(e) => e.target.value && onChange({ ...storyline, slides: [...slides, newSlide(e.target.value, slides)] })}
        >
          <option value="">Choose a slide type…</option>
          {Object.entries(TYPE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </label>
    </div>
  )
}
