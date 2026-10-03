import React, { useEffect, useState } from 'react'
import { presentationsApi, type Capabilities, type Company, type Storyline } from './client'
import { OutlineEditor } from './OutlineEditor'
import { withIds } from './outline'

const STEPS = ['Purpose', 'Sources', 'Brand', 'Outline']

/**
 * Four short steps: what the deck is for, what it may cite, which brand, and an outline the person
 * approves before anything is built. Numbers on slides come only from the sources step.
 */
export function NewDeck({ caps, companies, onCreated, onCancel, onSetupBrand }: {
  caps: Capabilities
  companies: Company[]
  onCreated: (deckId: string) => void
  onCancel: () => void
  onSetupBrand: () => void
}) {
  const [step, setStep] = useState(0)
  const [genre, setGenre] = useState(caps.genres[0]?.id ?? 'weekly_update')
  const [brief, setBrief] = useState('')
  const [audience, setAudience] = useState('')
  const [count, setCount] = useState(8)
  const [period, setPeriod] = useState('')
  const [sources, setSources] = useState('')
  const [diagramId, setDiagramId] = useState('')
  const [diagrams, setDiagrams] = useState<{ id: string; title: string }[]>([])
  const branded = companies.filter((c) => c.activeBrandVersion)
  const [companyId, setCompanyId] = useState(branded[0]?.id ?? '')
  const [storyline, setStoryline] = useState<Storyline | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    void presentationsApi.diagrams().then((r) => r.ok && setDiagrams(r.data.items ?? []))
  }, [])

  async function draft() {
    setBusy(true)
    setError('')
    const r = await presentationsApi.outline({ genre, brief, audience, slideCount: count, sources, diagramId: diagramId || undefined, periodLabel: period })
    setBusy(false)
    if (!r.ok) return setError(r.error)
    setStoryline(withIds(r.data.storyline))
    const removed = r.data.removedNumbers.length ? ` Removed ${r.data.removedNumbers.length} number(s) not found in your sources: ${r.data.removedNumbers.slice(0, 3).join('; ')}.` : ''
    setNote((r.data.mode === 'model' ? 'Drafted by AI from your brief and sources.' : r.data.message ?? 'Started from the template.') + removed + (r.data.credits ? ` ${r.data.credits.charged} credit(s) used.` : ''))
  }

  async function build() {
    if (!storyline) return
    setBusy(true)
    setError('')
    const r = await presentationsApi.createDeck(companyId, storyline)
    setBusy(false)
    if (!r.ok) return setError(r.error)
    onCreated(r.data.id)
  }

  return (
    <section className="pz-panel" aria-label="New presentation">
      <ol className="pz-steps">
        {STEPS.map((s, i) => (
          <li key={s} aria-current={i === step ? 'step' : undefined} className={i === step ? 'is-current' : i < step ? 'is-done' : ''}>
            {i + 1}. {s}
          </li>
        ))}
      </ol>
      {step === 0 && (
        <div className="pz-grid">
          <fieldset className="pz-genres">
            <legend>What kind of presentation?</legend>
            {caps.genres.map((g) => (
              <label key={g.id} className={genre === g.id ? 'is-selected' : ''}>
                <input type="radio" name="genre" value={g.id} checked={genre === g.id} onChange={() => setGenre(g.id)} />
                {g.name}
              </label>
            ))}
          </fieldset>
          <label className="pz-field">
            What is it about?
            <textarea rows={3} maxLength={3000} value={brief} onChange={(e) => setBrief(e.target.value)} placeholder="e.g. Weekly delivery review for the platform team: what shipped, the API risk, and the decision we need." />
          </label>
          <div className="pz-row">
            <label className="pz-field">
              Audience
              <input value={audience} maxLength={120} onChange={(e) => setAudience(e.target.value)} placeholder="Leadership team" />
            </label>
            <label className="pz-field">
              Slides (including the cover)
              <input type="number" min={3} max={30} value={count} onChange={(e) => setCount(Math.max(3, Math.min(30, Number(e.target.value) || 8)))} />
            </label>
            <label className="pz-field">
              Period (optional)
              <input value={period} maxLength={80} onChange={(e) => setPeriod(e.target.value)} placeholder="Week 40 · 28 Sep – 4 Oct" />
            </label>
          </div>
        </div>
      )}
      {step === 1 && (
        <div className="pz-grid">
          <label className="pz-field">
            Facts and figures to use
            <textarea rows={8} maxLength={20000} value={sources} onChange={(e) => setSources(e.target.value)} placeholder="Paste notes, metrics or a report. Numbers on the slides will come only from here." />
            <small>Anything not found here is left as “—” for you to fill in, never invented.</small>
          </label>
          <label className="pz-field">
            Include a dmind map (optional)
            <select value={diagramId} onChange={(e) => setDiagramId(e.target.value)}>
              <option value="">None</option>
              {diagrams.map((d) => (
                <option key={d.id} value={d.id}>{d.title}</option>
              ))}
            </select>
            <small>The map becomes an editable flow slide. The map itself is not changed.</small>
          </label>
        </div>
      )}
      {step === 2 && (
        <div className="pz-grid">
          {branded.length ? (
            <fieldset className="pz-genres">
              <legend>Which company brand?</legend>
              {branded.map((c) => (
                <label key={c.id} className={companyId === c.id ? 'is-selected' : ''}>
                  <input type="radio" name="company" checked={companyId === c.id} onChange={() => setCompanyId(c.id)} />
                  <span className="pz-swatch" style={{ background: c.activeBrand?.kit.palette.primary }} />
                  {c.name} <small>brand v{c.activeBrandVersion}</small>
                </label>
              ))}
            </fieldset>
          ) : (
            <p>No company brand yet. <button type="button" onClick={onSetupBrand}>Set up a brand</button></p>
          )}
        </div>
      )}
      {step === 3 && (
        <div className="pz-grid">
          {!storyline ? (
            <div className="pz-empty">
              <p>Get an outline you can edit before anything is built.</p>
              <button type="button" className="pz-primary" disabled={busy} onClick={() => void draft()}>{busy ? 'Drafting…' : 'Draft the outline'}</button>
            </div>
          ) : (
            <>
              {note && <p className="pz-note" role="status">{note}</p>}
              <OutlineEditor storyline={storyline} onChange={setStoryline} />
            </>
          )}
        </div>
      )}
      {error && <p role="alert">{error}</p>}
      <div className="pz-actions">
        <button type="button" onClick={step === 0 ? onCancel : () => setStep(step - 1)}>{step === 0 ? 'Cancel' : 'Back'}</button>
        {step < 3 && (
          <button type="button" className="pz-primary" disabled={(step === 0 && !brief.trim()) || (step === 2 && !companyId)} onClick={() => setStep(step + 1)}>
            Next: {STEPS[step + 1]}
          </button>
        )}
        {step === 3 && storyline && (
          <button type="button" className="pz-primary" disabled={busy || !companyId} onClick={() => void build()}>
            {busy ? 'Starting…' : 'Build presentation'}
          </button>
        )}
      </div>
    </section>
  )
}
