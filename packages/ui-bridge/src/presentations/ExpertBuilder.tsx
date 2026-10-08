import React, { useEffect, useState } from 'react'
import { presentationsApi } from './client'

const EXAMPLE = `export default async function build(deck) {
  const cover = deck.addSlide('title')
  cover.addText('Weekly review', { ...deck.box(0.8, 2.6, 11.7, 1.2), fontFace: deck.fonts.heading, fontSize: 40, bold: true, color: 'FFFFFF' })
  cover.addNotes('Opening: the one decision we need today.')

  const s = deck.addSlide('content')
  s.addText('Delivery rose for the third week', { ...deck.box(0.6, 0.5, 12.1, 0.9), fontFace: deck.fonts.heading, fontSize: 28, bold: true, color: deck.color.foreground })
  s.addChart(deck.charts.bar, [{ name: 'Delivered', labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'], values: [4, 5, 6, 6, 7] }],
    { ...deck.box(0.6, 1.6, 8, 5), chartColors: deck.seriesColors, showLegend: false })
  s.addNotes('Source: tracker export, Friday 17:00.')
}
`

/**
 * Expert mode (opt-in on the server): a JavaScript builder writes slides with the PptxGenJS API on
 * the company's branded layouts. It runs in an isolated sandbox and the file goes through the same
 * render and checks; the deck's outline is kept, so a normal edit afterwards returns to it.
 */
export function ExpertBuilder({ deckId, headRevision, initial, hasLocks, disabled, onStarted }: {
  deckId: string; headRevision: number; initial?: string | null; hasLocks: boolean; disabled: boolean; onStarted: (message: string) => void
}) {
  const [state, setState] = useState<{ enabled: boolean; ready: boolean } | null>(null)
  const [script, setScript] = useState(initial || EXAMPLE)
  const [problems, setProblems] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    void presentationsApi.capabilities().then((r) => r.ok && setState(r.data.expert ?? { enabled: false, ready: false }))
  }, [])
  if (!state?.enabled) return null

  async function run() {
    setBusy(true)
    setProblems([])
    const r = await presentationsApi.expert(deckId, script, headRevision)
    setBusy(false)
    if (!r.ok) return setProblems(r.error.split(/(?<=\.)\s+(?=Not allowed|The builder)/))
    onStarted(`Expert build started as revision ${headRevision + 1}.`)
  }

  return (
    <details className="pz-expert">
      <summary>Expert builder (JavaScript)</summary>
      <p className="pz-muted">
        Write slides directly with the PptxGenJS API on your brand’s layouts: <code>deck.addSlide('title' | 'section' | 'content' | 'quote' | 'closing')</code>,
        <code> deck.box(x, y, w, h)</code> in inches, <code>deck.color</code>, <code>deck.fonts</code>, <code>deck.charts</code>, <code>deck.seriesColors</code>.
        The builder runs isolated (no network, files or credentials) for up to 60 seconds; the file is then rendered and checked like any other revision.
      </p>
      {!state.ready && <p className="pz-note">The sandbox is not available on this server, so expert builds cannot run here.</p>}
      {hasLocks && <p className="pz-note">Unlock all slides first: an expert build replaces every slide.</p>}
      <textarea rows={16} spellCheck={false} value={script} maxLength={200000} onChange={(e) => setScript(e.target.value)} aria-label="Builder script" />
      {problems.length > 0 && (
        <ul role="alert">{problems.map((p) => <li key={p}>{p}</li>)}</ul>
      )}
      <div className="pz-actions">
        <button type="button" onClick={() => setScript(EXAMPLE)}>Reset to example</button>
        <button type="button" className="pz-primary" disabled={busy || disabled || hasLocks || !state.ready} onClick={() => void run()}>Build with script</button>
      </div>
    </details>
  )
}
