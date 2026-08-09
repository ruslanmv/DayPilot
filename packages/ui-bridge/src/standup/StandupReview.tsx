import React from 'react'

import { EvidenceDrawer } from './EvidenceDrawer'
import { StandupPreview } from './StandupPreview'
import {
  draftStatusLabel,
  standupApi,
  type Bullet,
  type StandupDraft,
  type StandupEvidence,
  type StandupWorkflow,
} from './standupClient'

/**
 * The 6:00 PM review — one decision per day.
 *
 * A full-height surface rather than a modal, because the user is checking
 * claims about their own work against evidence, not confirming a yes/no. Three
 * editable sections on the left, the evidence behind whichever line is selected
 * on the right.
 *
 * "Approve for tomorrow" is the single emphasised action and it freezes the
 * exact text server-side. Everything else here (edit, refresh, skip, retry) is
 * deliberately quieter, because they are the exceptions.
 */

function longDate(iso: string): string {
  const d = new Date(`${iso}T12:00:00`)
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' })
}

/**
 * What the approve button promises.
 *
 * "Approve for tomorrow" is a lie on a Friday: the next standup is on Monday,
 * three days away. Naming the actual weekday keeps the button honest about
 * when the update will appear, which matters because the whole feature asks
 * the user to trust a post they will not be present for.
 */
function approveLabel(targetIso: string, sameDay: boolean): string {
  if (sameDay) return 'Approve and post'
  const target = new Date(`${targetIso}T12:00:00`)
  if (Number.isNaN(target.getTime())) return 'Approve'
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  const isTomorrow = target.toDateString() === tomorrow.toDateString()
  return isTomorrow
    ? 'Approve for tomorrow'
    : `Approve for ${target.toLocaleDateString([], { weekday: 'long' })}`
}

function bullets(draft: StandupDraft, key: 'yesterday' | 'today' | 'blockers'): Bullet[] {
  return draft.provenance?.[key] || []
}

export function StandupReview({
  workflow,
  draft: initialDraft,
  onClose,
  onChanged,
}: {
  workflow: StandupWorkflow
  draft: StandupDraft
  onClose?: () => void
  onChanged?: (draft: StandupDraft) => void
}) {
  const [draft, setDraft] = React.useState(initialDraft)
  const [evidence, setEvidence] = React.useState<StandupEvidence[]>([])
  const [highlighted, setHighlighted] = React.useState<string[]>([])
  const [busy, setBusy] = React.useState<string | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [notice, setNotice] = React.useState<string | null>(null)

  const apply = React.useCallback((next: StandupDraft) => {
    setDraft(next)
    onChanged?.(next)
  }, [onChanged])

  const loadEvidence = React.useCallback(async (draftId: string) => {
    const r = await standupApi.evidence(draftId)
    if (r.ok) setEvidence(r.data.evidence)
  }, [])

  React.useEffect(() => { void loadEvidence(draft.id) }, [draft.id, loadEvidence])

  // Edits are debounced to the server rather than saved on every keystroke, and
  // the local text stays authoritative while typing so the caret never jumps.
  const pending = React.useRef<{ yesterday?: string; today?: string; blockers?: string }>({})
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null)

  const flushEdits = React.useCallback(async () => {
    const body = pending.current
    pending.current = {}
    if (!Object.keys(body).length) return
    const r = await standupApi.editDraft(draft.id, body)
    if (r.ok) apply(r.data)
    else setError(r.error)
  }, [draft.id, apply])

  const edit = (key: 'yesterday' | 'today' | 'blockers', value: string) => {
    setDraft((d) => ({ ...d, [key]: value }))
    pending.current[key] = value
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => { void flushEdits() }, 600)
  }

  React.useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label); setError(null); setNotice(null)
    try { await fn() } finally { setBusy(null) }
  }

  const approve = () => run('approve', async () => {
    await flushEdits()
    const r = await standupApi.approve(draft.id)
    if (!r.ok) { setError(r.error); return }
    apply(r.data)
    setNotice(
      workflow.deliveryMode === 'same_day'
        ? 'Approved. Posting to today’s thread.'
        : `Approved. This exact text will reply to the ${longDate(r.data.targetStandupDate)} standup thread once it appears at ${workflow.reminderTime}. Nothing else will be sent.`,
    )
  })

  const refresh = () => run('refresh', async () => {
    const collected = await standupApi.collect(workflow.id, draft.reportingDate)
    if (!collected.ok) { setError(collected.error); return }
    const regenerated = await standupApi.generate(workflow.id, draft.reportingDate)
    if (!regenerated.ok) { setError(regenerated.error); return }
    apply(regenerated.data)
    await loadEvidence(regenerated.data.id)
    setNotice('Rebuilt from the latest activity. Approval was cleared — review it again.')
  })

  const skip = () => run('skip', async () => {
    const r = await standupApi.skip(draft.id, 'Skipped from the review.')
    if (r.ok) { apply(r.data); setNotice('Skipped. Nothing will be posted for this day.') }
    else setError(r.error)
  })

  const sendNow = () => run('send', async () => {
    const r = await standupApi.sendNow(draft.id)
    if (!r.ok) { setError(r.error); return }
    apply(r.data.draft)
    setNotice(r.data.duplicate ? 'Already posted — nothing was sent twice.' : 'Posted to the standup thread.')
  })

  const toggleInclude = (item: StandupEvidence) => run(item.id, async () => {
    const r = item.included
      ? await standupApi.excludeEvidence(draft.id, item.id)
      : await standupApi.includeEvidence(draft.id, item.id)
    if (!r.ok) { setError(r.error); return }
    setEvidence((cur) => cur.map((e) => (e.id === item.id ? r.data : e)))
    setNotice('Evidence updated. Use “Refresh from activity” to rebuild the draft.')
  })

  const addNote = (text: string) => run('note', async () => {
    const r = await standupApi.addNote(workflow.id, text, draft.reportingDate)
    if (!r.ok) { setError(r.error); return }
    setEvidence((cur) => [...cur, r.data])
    setNotice('Note added. Refresh from activity to include it in the draft.')
  })

  const approved = Boolean(draft.approvedAt) && draft.status !== 'NEEDS_REVIEW'
  const failed = draft.status === 'THREAD_NOT_FOUND' || draft.status === 'SEND_FAILED'

  return (
    <div className="dp-standup" role="region" aria-label="Daily standup review">
      <header className="dp-standup__head">
        <div>
          <h2 className="dp-standup__title">Daily Standup Review</h2>
          <p className="dp-standup__subtitle">
            {longDate(draft.reportingDate)}
            {' · '}
            {workflow.deliveryMode === 'same_day'
              ? 'for today’s thread'
              : `for the ${longDate(draft.targetStandupDate)} standup`}
          </p>
        </div>
        <div className="dp-standup__head-right">
          <span className={'dp-standup__status dp-standup__status--' + draft.status.toLowerCase()}>
            {draftStatusLabel(draft.status)}
          </span>
          {onClose && (
            <button type="button" className="dp-standup__close" onClick={onClose} aria-label="Close review">
              ✕
            </button>
          )}
        </div>
      </header>

      {draft.detail && failed && (
        <p className="dp-standup__alert" role="alert">
          {draft.status === 'THREAD_NOT_FOUND'
            ? 'No standup thread was found, so nothing was posted — DayPilot never posts to the channel root.'
            : 'Slack rejected the send.'}{' '}
          {draft.detail}
        </p>
      )}
      {error && <p className="dp-standup__alert" role="alert">{error}</p>}
      {notice && <p className="dp-standup__notice" role="status">{notice}</p>}

      <div className="dp-standup__body">
        <div className="dp-standup__main">
          <p className="dp-standup__preview-label">Slack preview (editable)</p>
          <StandupPreview
            index={1}
            heading="Yesterday"
            question={workflow.deliveryMode === 'same_day'
              ? 'What have you completed since the last standup?'
              : 'What did you work on yesterday?'}
            value={draft.yesterday}
            bullets={bullets(draft, 'yesterday')}
            editable={draft.editable}
            onChange={(v) => edit('yesterday', v)}
            onSelectBullet={setHighlighted}
            selectedEvidenceIds={highlighted}
          />
          <StandupPreview
            index={2}
            heading="Today"
            question="What are you planning to do today?"
            value={draft.today}
            bullets={bullets(draft, 'today')}
            editable={draft.editable}
            onChange={(v) => edit('today', v)}
            onSelectBullet={setHighlighted}
            selectedEvidenceIds={highlighted}
          />
          <StandupPreview
            index={3}
            heading="Blockers"
            question="Do you have any blockers?"
            value={draft.blockers}
            bullets={bullets(draft, 'blockers')}
            editable={draft.editable}
            onChange={(v) => edit('blockers', v)}
            onSelectBullet={setHighlighted}
            selectedEvidenceIds={highlighted}
          />

          {approved && (
            <p className="dp-standup__locked" role="status">
              Approved at {new Date(draft.approvedAt as string).toLocaleTimeString()}. This exact
              text is what will be posted — editing it here asks for a new approval.
            </p>
          )}
        </div>

        <EvidenceDrawer
          evidence={evidence}
          highlightedIds={highlighted}
          busyId={busy}
          onToggleInclude={toggleInclude}
          onAddNote={addNote}
        />
      </div>

      <footer className="dp-standup__actions">
        <button type="button" className="dp-standup__secondary" disabled={!!busy || !draft.editable}
                onClick={refresh}>
          {busy === 'refresh' ? 'Refreshing…' : 'Refresh from activity'}
        </button>
        <button type="button" className="dp-standup__secondary" disabled={!!busy || !draft.editable}
                onClick={skip}>
          Skip today
        </button>
        <span className="dp-standup__actions-spacer" />
        {failed && (
          <button type="button" className="dp-standup__secondary" disabled={!!busy} onClick={sendNow}>
            {busy === 'send' ? 'Retrying…' : 'Retry now'}
          </button>
        )}
        <button
          type="button"
          className="dp-standup__primary"
          disabled={!!busy || draft.status === 'SENT' || draft.status === 'SKIPPED'}
          onClick={approve}
        >
          {busy === 'approve'
            ? 'Approving…'
            : approveLabel(draft.targetStandupDate, workflow.deliveryMode === 'same_day')}
        </button>
      </footer>
    </div>
  )
}
