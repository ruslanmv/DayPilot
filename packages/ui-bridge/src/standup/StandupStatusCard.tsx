import React from 'react'

import { draftStatusLabel, standupApi, type StandupDraft, type StandupStatus } from './standupClient'

/**
 * Which day the update actually lands on.
 *
 * "tomorrow" is wrong on a Friday — the next standup is Monday. Saying the
 * weekday keeps the card honest about a post the user will not be present for,
 * which is the whole thing they are being asked to trust.
 */
function targetDay(draft: StandupDraft | null): string {
  if (!draft) return 'the next workday'
  const target = new Date(`${draft.targetStandupDate}T12:00:00`)
  if (Number.isNaN(target.getTime())) return 'the next workday'
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  return target.toDateString() === tomorrow.toDateString()
    ? 'tomorrow'
    : target.toLocaleDateString([], { weekday: 'long' })
}

/**
 * The Home dashboard card.
 *
 * Its job is to make the 6:00 PM review a non-event: by the time the user gets
 * there they already know how much was collected and whether anything looks
 * blocked. Counts come from real evidence rows — a card that says "12 signals"
 * when nothing was collected would be the first lie in a feature whose whole
 * value is not lying.
 */
export function StandupStatusCard({ onReview }: { onReview?: (status: StandupStatus) => void }) {
  const [status, setStatus] = React.useState<StandupStatus | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState(false)

  const load = React.useCallback(async () => {
    const r = await standupApi.status()
    if (r.ok) { setStatus(r.data); setError(null) } else setError(r.error)
  }, [])

  React.useEffect(() => { void load() }, [load])

  if (error) {
    return (
      <section className="dp-standupcard" aria-label="Daily standup">
        <p className="dp-standupcard__error" role="alert">Couldn’t load the standup: {error}</p>
      </section>
    )
  }
  if (!status) return <section className="dp-standupcard dp-standupcard--loading" aria-busy="true" />

  if (!status.configured) {
    return (
      <section className="dp-standupcard" aria-label="Daily standup">
        <h3 className="dp-standupcard__title">Daily Standup</h3>
        <p className="dp-standupcard__body">
          Let DayPilot prepare your standup update from the day’s work and post it
          to your Slack thread — after you review it.
        </p>
        <button type="button" className="dp-standupcard__primary" onClick={() => onReview?.(status)}>
          Set up
        </button>
      </section>
    )
  }

  const { workflow, draft, signals, projects, possibleBlockers } = status
  const ready = draft && ['DRAFT', 'NEEDS_REVIEW'].includes(draft.status)

  const prepare = async () => {
    setBusy(true)
    try {
      await standupApi.collect(workflow.id)
      const g = await standupApi.generate(workflow.id)
      if (g.ok) { await load(); onReview?.({ ...status, draft: g.data }) }
      else setError(g.error)
    } finally { setBusy(false) }
  }

  return (
    <section className="dp-standupcard" aria-label="Daily standup">
      <div className="dp-standupcard__head">
        <h3 className="dp-standupcard__title">Daily Standup</h3>
        {draft && (
          <span className={'dp-standupcard__badge dp-standupcard__badge--' + draft.status.toLowerCase()}>
            {draftStatusLabel(draft.status)}
          </span>
        )}
      </div>

      <p className="dp-standupcard__body">
        {ready
          ? 'Your daily update is ready to review.'
          : draft?.status === 'SENT'
            ? 'Today’s update has been posted to Slack.'
            : `Draft opens at ${workflow.reviewTime}.`}
      </p>

      <ul className="dp-standupcard__facts">
        <li>
          {signals === 0
            ? 'No work signals collected yet'
            : `Collected ${signals} signal${signals === 1 ? '' : 's'}${projects ? ` from ${projects} project${projects === 1 ? '' : 's'}` : ''}`}
        </li>
        {possibleBlockers > 0 && (
          <li className="dp-standupcard__fact--warn">
            {possibleBlockers} possible blocker{possibleBlockers === 1 ? '' : 's'} detected
          </li>
        )}
      </ul>

      <p className="dp-standupcard__meta">
        {workflow.deliveryMode === 'same_day'
          ? `Posts to today’s #${workflow.slackChannelName || 'standup'} thread`
          : `Replies to ${targetDay(draft)}’s #${workflow.slackChannelName || 'standup'} thread at ${workflow.reminderTime}`}
      </p>

      <div className="dp-standupcard__actions">
        <button
          type="button"
          className="dp-standupcard__primary"
          disabled={busy}
          onClick={() => (draft ? onReview?.(status) : void prepare())}
        >
          {busy ? 'Preparing…' : draft ? 'Review now' : 'Prepare draft now'}
        </button>
      </div>
    </section>
  )
}
