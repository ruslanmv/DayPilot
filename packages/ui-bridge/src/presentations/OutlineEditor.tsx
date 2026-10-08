import React from 'react'
import type { Slide, Storyline } from './client'
import { TYPE_LABELS, fieldsFor, newSlide, readField, writeField } from './outline'
import { budget, clock, countWords, fit, wpmOf } from './talk'

const FIT: Record<string, string> = { ok: 'fits its time', short: 'short for its time', long: 'too long for its time', missing: 'no script yet' }

/**
 * The storyline as plain fields: what each slide says, never where things go. Layout, type sizes,
 * colours and logos come from the company's brand kit when the deck is built.
 */
export function OutlineEditor({
  storyline,
  onChange,
  locked = [],
  onRetime,
}: {
  storyline: Storyline
  onChange: (next: Storyline) => void
  locked?: string[]
  /** Re-split the talk's time after slides were added, removed or reordered. */
  onRetime?: () => void
}) {
  const wpm = wpmOf(storyline)
  const timed = !!storyline.talk
  const total = storyline.slides.reduce((n, x) => n + (x.seconds ?? 0), 0)
  const spoken = storyline.slides.reduce((n, x) => n + countWords(x.script), 0)
  const target = (storyline.talk?.minutes ?? 0) * 60
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
      {timed && (
        <div className="pz-talkbar" role="status" aria-label="Talk timing">
          <strong>{clock(target)} talk</strong>
          <span>{storyline.slides.length} slides · ~{wpm} words/min</span>
          <span>Script reads in about {clock((spoken / wpm) * 60)}</span>
          {total !== target && <span className="pz-warn">Slide times add up to {clock(total)}: re-time to fit {clock(target)}.</span>}
          <span className="pz-spacer" />
          {onRetime && <button type="button" onClick={onRetime}>Re-time slides</button>}
        </div>
      )}
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
                {timed && <span className="pz-time" title="Time on this slide">{clock(s.seconds ?? 0)}</span>}
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
                {(timed || s.script) && (() => {
                  const w = countWords(s.script)
                  const goal = budget(s, wpm)
                  const f = fit(w, goal)
                  return (
                    <label className="pz-field pz-script">
                      What to say ({clock(s.seconds ?? 0)})
                      <textarea aria-label={`Script for slide ${i + 1}`} rows={Math.min(10, Math.max(3, Math.ceil(w / 14)))} maxLength={4000} value={s.script ?? ''} onChange={(e) => set(i, { ...s, script: e.target.value })} />
                      <small className={`pz-meter pz-fit-${f}`}>
                        <span className="pz-meter-bar" aria-hidden="true"><i style={{ width: `${Math.min(100, goal ? (w / goal) * 100 : 0)}%` }} /></span>
                        {w} / {goal} words · reads in {clock((w / wpm) * 60)} · {FIT[f]}
                      </small>
                    </label>
                  )
                })()}
                <details>
                  <summary>{timed ? 'Presenter guidance' : 'Speaker notes'}</summary>
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
