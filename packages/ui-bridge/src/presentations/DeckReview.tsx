import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { presentationsApi, type Deck, type Pace, type Revision, type Slide, type Storyline } from './client'
import { download, useBlobUrl } from './files'
import { ExpertBuilder } from './ExpertBuilder'
import { OutlineEditor } from './OutlineEditor'
import { withIds } from './outline'
import { Rehearse } from './Rehearse'
import { clock, countWords, hasScript } from './talk'
import { TalkLength } from './TalkLength'

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
  const [scripting, setScripting] = useState(false)
  const [rehearsing, setRehearsing] = useState(false)
  const [talkMinutes, setTalkMinutes] = useState(5)
  const [talkPace, setTalkPace] = useState<Pace>('natural')

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

  // An expert revision's slides come from the built file, not the outline.
  const slides = rev?.expert ? (rev.notes ?? []).map((n): Slide => ({ id: n.id, type: 'expert', title: n.title })) : rev?.storyline?.slides ?? []
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

  async function writeScript() {
    if (!rev?.storyline || !deck) return
    setBusy(true)
    setMessage('')
    const r = await presentationsApi.talkScript({ storyline: rev.storyline, minutes: talkMinutes, pace: talkPace, locks })
    setBusy(false)
    if (!r.ok) return setMessage(r.error)
    setScripting(false)
    setEditing(r.data.storyline)
    setMessage(`Timed for ${clock(r.data.plan.totalSeconds)}. Review what to say on each slide, then Save and rebuild.` + (r.data.message ? ' ' + r.data.message : '') + (r.data.plan.advice.length ? ' ' + r.data.plan.advice.join(' ') : '') + (r.data.removedNumbers.length ? ` Removed sentence(s) with numbers not in the deck: ${r.data.removedNumbers.length}.` : '') + (locks.length ? ' Locked slides kept their script.' : ''))
  }
  async function retime() {
    if (!editing?.talk) return
    const r = await presentationsApi.talkPlan(editing, editing.talk.minutes, editing.talk.pace ?? 'natural')
    if (!r.ok) return setMessage(r.error)
    const by = new Map(r.data.slides.map((x) => [x.id, x.seconds]))
    setEditing({ ...editing, slides: editing.slides.map((x) => ({ ...x, seconds: by.get(x.id ?? '') ?? x.seconds })) })
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
            Revision {rev.revision}{rev.expert && ' (expert build)'} · <span className={`pz-state pz-state-${rev.state}`}>{STATE[rev.state] ?? rev.state}</span>
            {rev.quality && ` · ${rev.quality.slides_checked} slides checked, ${rev.quality.hard_failures} problem(s), ${rev.quality.warnings} note(s)`}
            {deck.periodKey && ` · ${deck.periodKey}`}
          </p>
        </div>
        <div className="pz-actions">
          <button type="button" disabled={!rev.files.pptx} onClick={() => void download(presentationsApi.fileUrl(deckId, rev.revision, 'pptx'), `${safeName}-r${rev.revision}.pptx`)}>Download PowerPoint</button>
          <button type="button" disabled={!rev.files.pdf} onClick={() => void download(presentationsApi.fileUrl(deckId, rev.revision, 'pdf'), `${safeName}-r${rev.revision}.pdf`)}>PDF</button>
          <button type="button" disabled={building || !!editing} onClick={() => setEditing(withIds(rev.storyline!))}>Edit content</button>
          {!rev.expert && (
            <button type="button" aria-expanded={scripting} disabled={building || !!editing} onClick={() => { setTalkMinutes(rev.storyline?.talk?.minutes ?? 5); setTalkPace(rev.storyline?.talk?.pace ?? 'natural'); setScripting(!scripting) }}>Script and timing</button>
          )}
          {hasScript(rev.storyline) && !rev.expert && <button type="button" disabled={building} onClick={() => setRehearsing(true)}>Rehearse</button>}
          {hasScript(rev.storyline) && <button type="button" onClick={() => void download(presentationsApi.scriptUrl(deckId, rev.revision), `${safeName}-r${rev.revision}-script.md`)}>Download script</button>}
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

      {scripting && !editing && (
        <section className="pz-panel" aria-label="Script and timing">
          <h4>Speaker script and timing</h4>
          <p className="pz-muted">Pick the talk length. Each slide gets its share of the time and a script sized to it; you review and edit before anything is rebuilt.{locks.length ? ' Locked slides keep their script.' : ''}</p>
          <TalkLength minutes={talkMinutes} pace={talkPace} onChange={(m, p) => { setTalkMinutes(m); setTalkPace(p) }} />
          <div className="pz-actions">
            <button type="button" onClick={() => setScripting(false)}>Cancel</button>
            <button type="button" className="pz-primary" disabled={busy} onClick={() => void writeScript()}>{busy ? 'Writing…' : hasScript(rev.storyline) ? 'Re-time and rewrite script' : 'Write the script'}</button>
          </div>
        </section>
      )}
      {rehearsing && rev.storyline && <Rehearse deckId={deckId} revision={rev.revision} slides={rev.storyline.slides} rendered={rev.files.slides} onClose={() => setRehearsing(false)} />}
      {editing ? (
        <div className="pz-panel">
          <p className="pz-muted">Saving creates revision {deck.headRevision + 1}; revision {rev.revision} and its files stay as they are. Locked slides cannot change.</p>
          <OutlineEditor storyline={editing} onChange={setEditing} locked={locks} onRetime={editing.talk ? () => void retime() : undefined} />
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
            {current?.id && !rev.expert && (
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
            {current?.script ? (
              <>
                <h5>What to say{current.seconds ? ` · ${clock(current.seconds)}` : ''}</h5>
                <p className="pz-script-side">{current.script}</p>
                <p className="pz-muted">{countWords(current.script)} words</p>
              </>
            ) : (
              <>
                <h5>Speaker notes</h5>
                <p className="pz-notes">{notes || '—'}</p>
              </>
            )}
            {current?.id && !rev.expert && !locks.includes(current.id) && (
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
      <ExpertBuilder key={rev.revision} deckId={deckId} headRevision={deck.headRevision} initial={rev.expertScript} hasLocks={locks.length > 0} disabled={building || !!editing}
        onStarted={(m) => { setMessage(m); void load() }} />
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
