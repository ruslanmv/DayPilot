import React, { useCallback, useEffect, useState } from 'react'
import './presentations.css'
import { BrandSetup } from './BrandSetup'
import { presentationsApi, type Capabilities, type Company, type Deck, type Series, type Storyline } from './client'
import { DeckReview } from './DeckReview'
import { useBlobUrl } from './files'
import { NewDeck } from './NewDeck'
import { ScheduleEditor } from './ScheduleEditor'
import { TemplateImport } from './TemplateImport'

type View = { kind: 'library' } | { kind: 'new' } | { kind: 'brand'; companyId: string | null } | { kind: 'deck'; id: string } | { kind: 'weekly'; storyline: Storyline; companyId: string }

const STATE: Record<string, string> = { queued: 'Building', composing: 'Building', review_ready: 'Ready for review', failed: 'Needs fixes', approved: 'Approved' }

function Cover({ deck }: { deck: Deck }) {
  const url = useBlobUrl(deck.head && deck.head.files.slides ? presentationsApi.fileUrl(deck.id, deck.head.revision, 'png', 1) : null)
  return url ? <img src={url} alt="" /> : <span className="pz-thumb-empty" />
}

export function PresentationsWorkspace() {
  const [caps, setCaps] = useState<Capabilities | null>(null)
  const [companies, setCompanies] = useState<Company[]>([])
  const [decks, setDecks] = useState<Deck[]>([])
  const [series, setSeries] = useState<Series[]>([])
  const [view, setView] = useState<View>({ kind: 'library' })
  const [q, setQ] = useState('')
  const [message, setMessage] = useState('')
  const [weeklyName, setWeeklyName] = useState('')
  const [tz, setTz] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC')

  const refresh = useCallback(async () => {
    const [c, d, s] = await Promise.all([presentationsApi.companies(), presentationsApi.decks(q), presentationsApi.series()])
    if (c.ok) setCompanies(c.data.items)
    if (d.ok) setDecks(d.data.items)
    if (s.ok) setSeries(s.data.items)
  }, [q])

  useEffect(() => {
    void presentationsApi.capabilities().then((r) => r.ok && setCaps(r.data))
  }, [])
  useEffect(() => {
    if (view.kind === 'library') void refresh()
  }, [view, refresh])
  useEffect(() => {
    if (view.kind !== 'library' || !decks.some((d) => d.head && (d.head.state === 'queued' || d.head.state === 'composing'))) return
    const t = setInterval(() => void refresh(), 2000)
    return () => clearInterval(t)
  }, [view, decks, refresh])

  if (!caps) return <p role="status">Loading presentations…</p>
  const branded = companies.filter((c) => c.activeBrandVersion)
  const company = (id: string) => companies.find((c) => c.id === id)

  return (
    <div className="pz">
      <header className="pz-top">
        <div>
          <p className="pz-eyebrow">Presentations</p>
          <h2>Branded decks, ready to edit in PowerPoint</h2>
          <p className="pz-muted">Write the story, pick your company brand, and review the real exported file before anyone sees it.</p>
        </div>
        {view.kind === 'library' && (
          <div className="pz-actions">
            <button type="button" onClick={() => setView({ kind: 'brand', companyId: branded[0]?.id ?? null })}>{branded.length ? 'Brand' : 'Set up brand'}</button>
            <button type="button" className="pz-primary" onClick={() => setView(branded.length ? { kind: 'new' } : { kind: 'brand', companyId: null })}>New presentation</button>
          </div>
        )}
      </header>
      {!caps.render.ready && <p className="pz-note">The render worker is not installed on this server, so decks are exported but not visually checked. Install libreoffice-impress and poppler-utils.</p>}
      {message && <p className="pz-note" role="status">{message}</p>}

      {view.kind === 'library' && (
        <>
          {!branded.length && (
            <section className="pz-panel pz-empty">
              <h3>Start with your company brand</h3>
              <p>Add your logo, colours and fonts once; every presentation uses them.</p>
              <button type="button" className="pz-primary" onClick={() => setView({ kind: 'brand', companyId: null })}>Set up brand</button>
            </section>
          )}
          {series.length > 0 && (
            <section className="pz-panel" aria-label="Weekly presentations">
              <h3>Weekly presentations</h3>
              <ul className="pz-series">
                {series.map((s) => (
                  <li key={s.id}>
                    <strong>{s.name}</strong>
                    <span className="pz-muted">{s.nextPeriod?.label} · {s.timezone}{s.paused ? ' · paused' : ''}</span>
                    <span className="pz-spacer" />
                    <button type="button" className="pz-primary" disabled={s.paused} onClick={() => void presentationsApi.prepare(s.id).then((r) => {
                      if (!r.ok) return setMessage(r.error)
                      setMessage(r.data.created ? `Prepared the draft for ${r.data.period.label}.` : `The draft for ${r.data.period.label} already exists; opening it.`)
                      setView({ kind: 'deck', id: r.data.deck.id })
                    })}>Prepare this week</button>
                    <button type="button" onClick={() => void presentationsApi.pause(s.id).then(() => refresh())}>{s.paused ? 'Resume' : 'Pause'}</button>
                    <ScheduleEditor series={s} onSaved={(m) => { setMessage(m); void refresh() }} />
                  </li>
                ))}
              </ul>
            </section>
          )}
          <section className="pz-panel" aria-label="All presentations">
            <div className="pz-row">
              <h3>All presentations</h3>
              <span className="pz-spacer" />
              <input aria-label="Search presentations" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            {decks.length ? (
              <ul className="pz-library">
                {decks.map((d) => (
                  <li key={d.id}>
                    <button type="button" className="pz-card" onClick={() => setView({ kind: 'deck', id: d.id })}>
                      <span className="pz-card-cover"><Cover deck={d} /></span>
                      <strong>{d.title}</strong>
                      <span className="pz-muted">{company(d.companyId)?.name} · r{d.headRevision}{d.periodKey ? ` · ${d.periodKey}` : ''}</span>
                      <span className={`pz-state pz-state-${d.head?.state}`}>{STATE[d.head?.state ?? ''] ?? d.head?.state}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="pz-muted">No presentations yet.</p>
            )}
          </section>
        </>
      )}

      {view.kind === 'brand' && (
        <>
          {companies.length > 1 && (
            <label className="pz-field">
              Company
              <select value={view.companyId ?? ''} onChange={(e) => setView({ kind: 'brand', companyId: e.target.value || null })}>
                {companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                <option value="">+ Another company</option>
              </select>
            </label>
          )}
          {companies.length === 1 && <button type="button" className="pz-link" onClick={() => setView({ kind: 'brand', companyId: null })}>+ Add another company</button>}
          {view.companyId && company(view.companyId) && (
            <TemplateImport
              key={`tpl-${view.companyId}`}
              company={company(view.companyId)!}
              onBrand={(warnings) => {
                setMessage(`Brand created from the template.${warnings.length ? ' Check: ' + warnings.join(' ') : ''}`)
                setView({ kind: 'library' })
              }}
            />
          )}
          <BrandSetup
            key={view.companyId ?? 'new'}
            company={view.companyId ? company(view.companyId) ?? null : null}
            onCancel={() => setView({ kind: 'library' })}
            onDone={(c, warnings) => {
              setMessage(`Brand saved for ${c.name}.${warnings.length ? ' Check: ' + warnings.join(' ') : ''}`)
              setView({ kind: 'library' })
            }}
          />
        </>
      )}

      {view.kind === 'new' && (
        <NewDeck caps={caps} companies={companies} onCancel={() => setView({ kind: 'library' })} onSetupBrand={() => setView({ kind: 'brand', companyId: null })} onCreated={(id) => setView({ kind: 'deck', id })} />
      )}

      {view.kind === 'deck' && <DeckReview deckId={view.id} onBack={() => setView({ kind: 'library' })} onMakeWeekly={(storyline, companyId) => setView({ kind: 'weekly', storyline, companyId })} />}

      {view.kind === 'weekly' && (
        <section className="pz-panel" aria-label="Make it weekly">
          <h3>Make it a weekly presentation</h3>
          <p className="pz-muted">Each week, “Prepare this week” starts from the latest version with the same structure and wording. Numbers are cleared so last week’s figures are never shown as this week’s. Nothing is sent automatically.</p>
          <label className="pz-field">Name<input value={weeklyName} maxLength={120} onChange={(e) => setWeeklyName(e.target.value)} placeholder={view.storyline.title} /></label>
          <label className="pz-field">Time zone<input value={tz} maxLength={60} onChange={(e) => setTz(e.target.value)} /></label>
          <div className="pz-actions">
            <button type="button" onClick={() => setView({ kind: 'library' })}>Cancel</button>
            <button type="button" className="pz-primary" onClick={() => void presentationsApi.createSeries({ companyId: view.companyId, name: weeklyName.trim() || view.storyline.title, timezone: tz, weekStartsOn: 0, rule: 'previous_full_week', storyline: view.storyline }).then((r) => {
              if (!r.ok) return setMessage(r.error)
              setMessage(`Weekly presentation “${r.data.name}” saved. Use “Prepare this week” each week.`)
              setView({ kind: 'library' })
            })}>Save weekly presentation</button>
          </div>
        </section>
      )}
    </div>
  )
}
