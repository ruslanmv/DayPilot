import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { presentationsApi, type Deck, type Revision, type Storyline } from './client'
import { download, useBlobUrl } from './files'
import { OutlineEditor } from './OutlineEditor'
import { withIds } from './outline'

const STATE: Record<string, string> = {
  queued: 'Waiting to build', composing: 'Building', review_ready: 'Ready for review', failed: 'Needs fixes', approved: 'Approved',
}
const PHASE: Record<string, string> = { queued: 'Queued', compose: 'Laying out slides', export: 'Writing PowerPoint', render: 'Rendering the actual file', publish: 'Checking and saving', done: 'Done' }

function Thumb({ path, label, selected, onClick }: { path: string; label: string; selected: boolean; onClick: () => void }) {
  const url = useBlobUrl(path)
  return (
    <button type="button" className={`pz-thumb${selected ? ' is-selected' : ''}`} aria-label={label} aria-pressed={selected} onClick={onClick}>
      {url ? <img src={url} alt="" /> : <span className="pz-thumb-empty" />}
    </button>
  )
}

/**
 * Review uses the real exported file: every image here is a page of the rendered PowerPoint.
 */
export function DeckReview({ deckId, onBack, onMakeWeekly }: { deckId: string; onBack: () => void; onMakeWeekly: (storyline: Storyline, companyId: string) => void }) {
  const [deck, setDeck] = useState<Deck | null>(null)
  const [rev, setRev] = useState<Revision | null>(null)
  const [slide, setSlide] = useState(1)
  const [editing, setEditing] = useState<Storyline | null>(null)
  const [instruction, setInstruction] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const d = await presentationsApi.deck(deckId)
    if (!d.ok) return setMessage(d.error)
    setDeck(d.data)
    const r = await presentationsApi.revision(deckId, d.data.headRevision)
    if (r.ok) setRev(r.data)
  }, [deckId])

  useEffect(() => {
    void load()
  }, [load])
  const building = !!rev && (rev.state === 'queued' || rev.state === 'composing')
  useEffect(() => {
    if (!building) return
    const t = setInterval(() => void load(), 1500)
    return () => clearInterval(t)
  }, [building, load])

  const slides = rev?.storyline?.slides ?? []
  const current = slides[slide - 1]
  const findings = useMemo(() => (rev?.findings ?? []).filter((f) => f.slide === current?.id || f.slide === null), [rev, current])
  const notes = rev?.notes?.find((n) => n.id === current?.id)?.notes
  const locks = rev?.locks ?? []
  const big = useBlobUrl(rev && rev.files.slides >= slide ? presentationsApi.fileUrl(deckId, rev.revision, 'png', slide) : null)

  async function act<T>(fn: () => Promise<{ ok: true; data: T } | { ok: false; error: string }>, done?: string) {
    setBusy(true)
    setMessage('')
    const r = await fn()
    setBusy(false)
    if (!r.ok) return setMessage(r.error)
    if (done) setMessage(done)
    await load()
  }

  if (!deck || !rev) return <p role="status">{message || 'Loading presentation…'}</p>
  const safeName = deck.title.replace(/[^A-Za-z0-9._-]+/g, '-').slice(0, 60) || 'presentation'
  const toggleLock = () =>
    current?.id && act(() => presentationsApi.locks(deckId, locks.includes(current.id!) ? locks.filter((x) => x !== current.id) : [...locks, current.id!], deck.headRevision))

  return (
    <section className="pz-review" aria-label={`Presentation ${deck.title}`}>
      <header className="pz-review-head">
        <button type="button" onClick={onBack}>← All presentations</button>
        <div>
          <h3>{deck.title}</h3>
          <p className="pz-muted">
            Revision {rev.revision} · <span className={`pz-state pz-state-${rev.state}`}>{STATE[rev.state] ?? rev.state}</span>
            {rev.quality && ` · ${rev.quality.slides_checked} slides checked, ${rev.quality.hard_failures} problem(s), ${rev.quality.warnings} note(s)`}
            {deck.periodKey && ` · ${deck.periodKey}`}
          </p>
        </div>
        <div className="pz-actions">
          <button type="button" disabled={!rev.files.pptx} onClick={() => void download(presentationsApi.fileUrl(deckId, rev.revision, 'pptx'), `${safeName}-r${rev.revision}.pptx`)}>Download PowerPoint</button>
          <button type="button" disabled={!rev.files.pdf} onClick={() => void download(presentationsApi.fileUrl(deckId, rev.revision, 'pdf'), `${safeName}-r${rev.revision}.pdf`)}>PDF</button>
          <button type="button" disabled={building || !!editing} onClick={() => setEditing(withIds(rev.storyline!))}>Edit content</button>
          {!deck.seriesId && <button type="button" disabled={building} onClick={() => onMakeWeekly(rev.storyline!, deck.companyId)}>Make it weekly</button>}
          {rev.state === 'review_ready' && (
            <button type="button" className="pz-primary" disabled={busy} onClick={() => void act(() => presentationsApi.approve(deckId, rev.revision, rev.pptxSha256!), 'Approved. This exact file is now the approved version.')}>Approve</button>
          )}
        </div>
      </header>
      {building && (
        <div className="pz-progress" role="status">
          <span>{PHASE[rev.run?.phase ?? 'queued'] ?? 'Building'}…</span>
          <progress max={4} value={['queued', 'compose', 'export', 'render', 'publish'].indexOf(rev.run?.phase ?? 'queued')} />
        </div>
      )}
      {rev.state === 'failed' && rev.error && <p role="alert">{rev.error}</p>}
      {message && <p role="status" className="pz-note">{message}</p>}

      {editing ? (
        <div className="pz-panel">
          <p className="pz-muted">Saving creates revision {deck.headRevision + 1}; revision {rev.revision} and its files stay as they are. Locked slides cannot change.</p>
          <OutlineEditor storyline={editing} onChange={setEditing} locked={locks} />
          <div className="pz-actions">
            <button type="button" onClick={() => setEditing(null)}>Discard changes</button>
            <button type="button" className="pz-primary" disabled={busy} onClick={() => void act(async () => { const r = await presentationsApi.revise(deckId, editing, deck.headRevision, locks); if (r.ok) setEditing(null); return r }, 'Saved. Building the new revision…')}>Save and rebuild</button>
          </div>
        </div>
      ) : (
        <div className="pz-stage">
          <nav className="pz-filmstrip" aria-label="Slides">
            {slides.map((s, i) => (
              <Thumb key={`${rev.revision}-${i}`} path={rev.files.slides > i ? presentationsApi.fileUrl(deckId, rev.revision, 'png', i + 1) : ''} label={`Slide ${i + 1}: ${s.title}${locks.includes(s.id ?? '') ? ' (locked)' : ''}`} selected={slide === i + 1} onClick={() => setSlide(i + 1)} />
            ))}
          </nav>
          <div className="pz-canvas">
            {big ? <img src={big} alt={`Slide ${slide}: ${current?.title ?? ''} (rendered from the PowerPoint file)`} /> : <div className="pz-canvas-empty">{building ? 'Rendering…' : rev.files.pptx ? 'This revision was exported but not rendered here. Download the PowerPoint to view it.' : 'No preview.'}</div>}
          </div>
          <aside className="pz-side" aria-label="Slide details">
            <h4>Slide {slide}{current ? `: ${current.title}` : ''}</h4>
            {current?.id && (
              <button type="button" aria-pressed={locks.includes(current.id)} disabled={busy || building} onClick={() => void toggleLock()}>
                {locks.includes(current.id) ? 'Unlock slide' : 'Lock slide'}
              </button>
            )}
            <h5>Checks</h5>
            {findings.length ? (
              <ul className="pz-findings">
                {findings.map((f, i) => (
                  <li key={i} data-severity={f.severity}>{f.message}</li>
                ))}
              </ul>
            ) : (
              <p className="pz-muted">{rev.quality ? 'No problems on this slide.' : '—'}</p>
            )}
            <h5>Speaker notes</h5>
            <p className="pz-notes">{notes || '—'}</p>
            {current?.id && !locks.includes(current.id) && (
              <div className="pz-rewrite">
                <h5>Rewrite this slide with AI</h5>
                <textarea rows={2} maxLength={1500} value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="e.g. make the title a finding; shorter points" aria-label="Instruction for the AI" />
                <button type="button" disabled={busy || building} onClick={() => void act(async () => {
                  const r = await presentationsApi.regenerate(deckId, [current.id!], instruction, deck.headRevision)
                  if (r.ok && r.data.removedNumbers?.length) setTimeout(() => setMessage(`Removed number(s) the AI could not source: ${r.data.removedNumbers!.join('; ')}`), 0)
                  return r
                }, 'Rewriting… a new revision is being built.')}>Rewrite</button>
              </div>
            )}
          </aside>
        </div>
      )}
      <details className="pz-history">
        <summary>Revisions ({deck.revisions?.length ?? 0})</summary>
        <ul>
          {(deck.revisions ?? []).map((r) => (
            <li key={r.revision}>
              Revision {r.revision} · {STATE[r.state] ?? r.state} · by {r.author}
              {r.createdAt && ` · ${new Date(r.createdAt).toLocaleString()}`}
              {r.revision !== deck.headRevision && (
                <button type="button" disabled={busy || building} onClick={() => void act(() => presentationsApi.restore(deckId, r.revision, deck.headRevision), `Restoring revision ${r.revision} as a new revision…`)}>Restore</button>
              )}
              {r.files.pptx && (
                <button type="button" onClick={() => void download(presentationsApi.fileUrl(deckId, r.revision, 'pptx'), `${safeName}-r${r.revision}.pptx`)}>Download</button>
              )}
            </li>
          ))}
        </ul>
      </details>
    </section>
  )
}
