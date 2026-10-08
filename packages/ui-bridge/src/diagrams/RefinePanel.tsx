import React, { useMemo, useState } from 'react'
import { analyse } from './analysis'
import type { Diagram } from './dmind'
import { applyPatch, parsePatch, type PatchResult } from './patch'

/**
 * Review and analysis (batch B6). Solver findings are computed here from the document and labelled
 * as such; patch proposals (pasted, or produced by a model elsewhere) are only ever shown as a diff
 * and applied when the person presses Apply, and only to the exact state they were written against.
 */
export function RefinePanel({ diagram, onApply }: { diagram: Diagram; onApply: (next: Diagram) => void }) {
  const [text, setText] = useState('')
  const [review, setReview] = useState<Extract<PatchResult, { ok: true }> | null>(null)
  const [error, setError] = useState('')
  const result = useMemo(() => analyse(diagram), [diagram])
  const label = (id: string) => diagram.nodes.find((n) => n.id === id)?.label ?? id

  async function propose() {
    setError('')
    setReview(null)
    try {
      const outcome = await applyPatch(diagram, parsePatch(JSON.parse(text)))
      if (outcome.ok) setReview(outcome)
      else setError(outcome.message)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'This is not a patch.')
    }
  }

  return (
    <details className="dmind-refine">
      <summary>Check and refine{result.findings.length ? ` · ${result.findings.length} finding(s)` : ''}</summary>
      <section aria-label="Solver checks">
        <h4>Checks from the diagram itself</h4>
        {result.findings.length ? (
          <ul>
            {result.findings.map((f, i) => (
              <li key={i} data-severity={f.severity}>
                {f.message}
              </li>
            ))}
          </ul>
        ) : (
          <p>No problems found.</p>
        )}
        {result.order && result.order.length > 1 && (
          <p>Order: {result.order.slice(0, 12).map(label).join(' → ')}{result.order.length > 12 ? ' …' : ''}</p>
        )}
      </section>
      <section aria-label="Patch proposal">
        <h4>Apply a proposed change</h4>
        <p>Paste a dmind-patch/v1 proposal. You review the differences before anything changes.</p>
        <textarea
          aria-label="Patch proposal"
          maxLength={200000}
          rows={5}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button disabled={!text.trim()} onClick={() => void propose()}>
          Review changes
        </button>
        {error && <p role="alert">{error}</p>}
        {review && (
          <div aria-label="Proposed changes">
            <ul>
              {review.diff.summary.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
            <button
              onClick={() => {
                onApply(review.diagram)
                setReview(null)
                setText('')
              }}
            >
              Apply
            </button>
            <button onClick={() => setReview(null)}>Discard</button>
          </div>
        )}
      </section>
    </details>
  )
}
