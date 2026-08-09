import React from 'react'

import { standupApi, type StandupWorkflow, type ThreadProbe } from './standupClient'

/**
 * Settings → Integrations → Slack → Automations → Daily Standup.
 *
 * The screen has one job beyond collecting fields: making the user confirm,
 * once, against live Slack, that DayPilot has found the right message. A
 * reminder matched by wording alone is a guess, and a wrong guess posts a
 * personal work summary into the wrong place. So the primary action here is
 * **Find today's standup message**, not Save.
 *
 * It also has to explain the timing choice honestly, because the two modes mean
 * different things by the word "Yesterday".
 */

const DAYS = [
  { n: 1, label: 'Mon' }, { n: 2, label: 'Tue' }, { n: 3, label: 'Wed' },
  { n: 4, label: 'Thu' }, { n: 5, label: 'Fri' }, { n: 6, label: 'Sat' }, { n: 7, label: 'Sun' },
]

export function StandupSetup({
  workflow,
  slackConnectionId,
  onSaved,
}: {
  workflow?: StandupWorkflow | null
  slackConnectionId?: string | null
  onSaved?: (w: StandupWorkflow) => void
}) {
  const [draft, setDraft] = React.useState<Partial<StandupWorkflow>>(() => ({
    name: workflow?.name ?? 'Daily Standup',
    enabled: workflow?.enabled ?? true,
    timezone: workflow?.timezone
      ?? Intl.DateTimeFormat().resolvedOptions().timeZone
      ?? 'UTC',
    workingDays: workflow?.workingDays ?? [1, 2, 3, 4, 5],
    reviewTime: workflow?.reviewTime ?? '18:00',
    reminderTime: workflow?.reminderTime ?? '09:00',
    deliveryMode: workflow?.deliveryMode ?? 'next_workday',
    slackChannelId: workflow?.slackChannelId ?? '',
    slackChannelName: workflow?.slackChannelName ?? '',
    reminderSignature: workflow?.reminderSignature ?? 'Daily Standup Reminder',
    emptyDayPolicy: workflow?.emptyDayPolicy ?? 'honest',
    slackConnectionId: workflow?.slackConnectionId ?? slackConnectionId ?? null,
  }))
  const [probe, setProbe] = React.useState<ThreadProbe | null>(null)
  const [busy, setBusy] = React.useState<string | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  const set = <K extends keyof StandupWorkflow>(key: K, value: StandupWorkflow[K]) =>
    setDraft((d) => ({ ...d, [key]: value }))

  const save = async (): Promise<StandupWorkflow | null> => {
    setError(null)
    const r = workflow
      ? await standupApi.updateWorkflow(workflow.id, draft)
      : await standupApi.createWorkflow(draft)
    if (!r.ok) { setError(r.error); return null }
    onSaved?.(r.data)
    return r.data
  }

  const findThread = async () => {
    setBusy('probe')
    try {
      // Save first: resolution runs server-side against the saved channel and
      // signature, so probing an unsaved form would test the wrong thing.
      const saved = await save()
      if (!saved) return
      const r = await standupApi.testThread(saved.id)
      if (r.ok) setProbe(r.data)
      else setError(r.error)
    } finally { setBusy(null) }
  }

  const toggleDay = (n: number) => {
    const cur = new Set(draft.workingDays || [])
    if (cur.has(n)) cur.delete(n); else cur.add(n)
    set('workingDays', Array.from(cur).sort((a, b) => a - b) as StandupWorkflow['workingDays'])
  }

  return (
    <form
      className="dp-standupsetup"
      onSubmit={(e) => { e.preventDefault(); setBusy('save'); void save().finally(() => setBusy(null)) }}
    >
      <h3 className="dp-standupsetup__title">Daily Standup</h3>
      <p className="dp-standupsetup__intro">
        DayPilot collects what you actually worked on, drafts your update before you
        finish for the day, and — once you approve it — replies in the standup thread.
        Nothing is posted without your approval.
      </p>

      <div className="dp-standupsetup__grid">
        <div className="dp-standupsetup__field">
          <label htmlFor="su-channel">Slack channel ID</label>
          <input id="su-channel" value={draft.slackChannelId || ''}
                 onChange={(e) => set('slackChannelId', e.target.value)} placeholder="C0123456789" />
        </div>
        <div className="dp-standupsetup__field">
          <label htmlFor="su-channel-name">Channel name</label>
          <input id="su-channel-name" value={draft.slackChannelName || ''}
                 onChange={(e) => set('slackChannelName', e.target.value)} placeholder="daily-standup" />
        </div>
        <div className="dp-standupsetup__field dp-standupsetup__field--wide">
          <label htmlFor="su-signature">The reminder says</label>
          <input id="su-signature" value={draft.reminderSignature || ''}
                 onChange={(e) => set('reminderSignature', e.target.value)} />
          <p className="dp-standupsetup__hint">
            Used together with who posts it and when — never wording alone.
          </p>
        </div>
        <div className="dp-standupsetup__field">
          <label htmlFor="su-review">Review at</label>
          <input id="su-review" type="time" value={draft.reviewTime || '18:00'}
                 onChange={(e) => set('reviewTime', e.target.value)} />
        </div>
        <div className="dp-standupsetup__field">
          <label htmlFor="su-reminder">Reminder posts at</label>
          <input id="su-reminder" type="time" value={draft.reminderTime || '09:00'}
                 onChange={(e) => set('reminderTime', e.target.value)} />
        </div>
        <div className="dp-standupsetup__field">
          <label htmlFor="su-tz">Timezone</label>
          <input id="su-tz" value={draft.timezone || 'UTC'}
                 onChange={(e) => set('timezone', e.target.value)} />
        </div>
      </div>

      <fieldset className="dp-standupsetup__fieldset">
        <legend>Working days</legend>
        <div className="dp-standupsetup__days">
          {DAYS.map((d) => (
            <label key={d.n} className="dp-standupsetup__day">
              <input
                type="checkbox"
                checked={(draft.workingDays || []).includes(d.n)}
                onChange={() => toggleDay(d.n)}
              />
              {d.label}
            </label>
          ))}
        </div>
        <p className="dp-standupsetup__hint">
          Monday reports on the previous working day, not on Sunday.
        </p>
      </fieldset>

      <fieldset className="dp-standupsetup__fieldset">
        <legend>When to post</legend>
        <label className="dp-standupsetup__radio">
          <input type="radio" name="delivery" checked={draft.deliveryMode === 'next_workday'}
                 onChange={() => set('deliveryMode', 'next_workday')} />
          <span>
            <strong>Reply to tomorrow’s thread</strong> — today’s work becomes tomorrow’s
            “Yesterday”, exactly as the reminder asks. Recommended.
          </span>
        </label>
        <label className="dp-standupsetup__radio">
          <input type="radio" name="delivery" checked={draft.deliveryMode === 'same_day'}
                 onChange={() => set('deliveryMode', 'same_day')} />
          <span>
            <strong>Reply to today’s thread</strong> — posts at review time. The first
            section then means “completed since the last standup”, though the thread
            still labels it “Yesterday”.
          </span>
        </label>
      </fieldset>

      <fieldset className="dp-standupsetup__fieldset">
        <legend>On a day with no tracked work</legend>
        <label className="dp-standupsetup__radio">
          <input type="radio" name="empty" checked={draft.emptyDayPolicy === 'honest'}
                 onChange={() => set('emptyDayPolicy', 'honest')} />
          <span>Post a short, honest update. Never invent activity.</span>
        </label>
        <label className="dp-standupsetup__radio">
          <input type="radio" name="empty" checked={draft.emptyDayPolicy === 'skip'}
                 onChange={() => set('emptyDayPolicy', 'skip')} />
          <span>Leave it blank for me to fill in.</span>
        </label>
      </fieldset>

      {error && <p className="dp-standupsetup__alert" role="alert">{error}</p>}

      {probe && (
        <div className={'dp-standupsetup__probe' + (probe.found ? ' is-found' : ' is-missing')}
             role="status">
          {probe.found ? (
            <>
              <p><strong>{probe.message}</strong></p>
              <p className="dp-standupsetup__probe-preview">“{probe.preview}”</p>
              <p className="dp-standupsetup__hint">Matched on: {probe.matchedOn.join(', ')}</p>
            </>
          ) : (
            <p>
              No standup message found in #{probe.channelName} today. Check the channel and
              the wording — DayPilot will never post to the channel root instead.
            </p>
          )}
        </div>
      )}

      <div className="dp-standupsetup__actions">
        <button type="button" className="dp-standupsetup__primary" disabled={busy !== null}
                onClick={findThread}>
          {busy === 'probe' ? 'Looking…' : 'Find today’s standup message'}
        </button>
        <button type="submit" className="dp-standupsetup__secondary" disabled={busy !== null}>
          {busy === 'save' ? 'Saving…' : 'Save'}
        </button>
      </div>
    </form>
  )
}
