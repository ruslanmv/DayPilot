import React from 'react'

import { StandupReview } from './StandupReview'
import { StandupSetup } from './StandupSetup'
import { standupApi, type StandupDraft, type StandupStatus, type StandupWorkflow } from './standupClient'

/**
 * The `#/standup` page.
 *
 * One address that always shows the right thing for where the day is: the
 * setup form when nothing is configured, the review when a draft exists, and
 * an honest "nothing yet" with a way to build one when it does not. That
 * matters because `#/standup` is what the 18:00 notification links to — it has
 * to land somewhere useful whatever state the user arrives in.
 */
export function StandupWorkspace() {
  const [status, setStatus] = React.useState<StandupStatus | null>(null)
  const [draft, setDraft] = React.useState<StandupDraft | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState(false)
  const [editing, setEditing] = React.useState(false)

  const load = React.useCallback(async () => {
    const r = await standupApi.status()
    if (!r.ok) { setError(r.error); return }
    setError(null)
    setStatus(r.data)
    setDraft(r.data.configured ? r.data.draft : null)
  }, [])

  React.useEffect(() => { void load() }, [load])

  if (error) {
    return (
      <section className="dp-standup" aria-label="Daily standup">
        <p className="dp-standup__alert" role="alert">Couldn’t load the standup: {error}</p>
      </section>
    )
  }
  if (!status) return <section className="dp-standup" aria-busy="true" />

  if (!status.configured || editing) {
    const existing: StandupWorkflow | null = status.configured ? status.workflow : null
    return (
      <StandupSetup
        workflow={existing}
        onSaved={() => { setEditing(false); void load() }}
      />
    )
  }

  const { workflow, signals, projects, possibleBlockers } = status

  const prepare = async () => {
    setBusy(true)
    try {
      const collected = await standupApi.collect(workflow.id)
      if (!collected.ok) { setError(collected.error); return }
      const generated = await standupApi.generate(workflow.id)
      if (generated.ok) setDraft(generated.data)
      else setError(generated.error)
    } finally { setBusy(false) }
  }

  if (!draft) {
    return (
      <section className="dp-standup" aria-label="Daily standup">
        <header className="dp-standup__head">
          <div>
            <h2 className="dp-standup__title">Daily Standup</h2>
            <p className="dp-standup__subtitle">
              Review opens at {workflow.reviewTime} · {workflow.timezone}
            </p>
          </div>
          <button type="button" className="dp-standup__secondary" onClick={() => setEditing(true)}>
            Settings
          </button>
        </header>
        <p className="dp-standup__notice" role="status">
          {signals === 0
            ? 'No work signals collected yet today.'
            : `${signals} signal${signals === 1 ? '' : 's'} collected${projects ? ` from ${projects} project${projects === 1 ? '' : 's'}` : ''}`}
          {possibleBlockers > 0 && ` · ${possibleBlockers} possible blocker${possibleBlockers === 1 ? '' : 's'}`}
        </p>
        <div className="dp-standup__actions">
          <span className="dp-standup__actions-spacer" />
          <button type="button" className="dp-standup__primary" disabled={busy} onClick={prepare}>
            {busy ? 'Preparing…' : 'Prepare today’s draft'}
          </button>
        </div>
      </section>
    )
  }

  return (
    <StandupReview
      workflow={workflow}
      draft={draft}
      onChanged={setDraft}
      onClose={() => setEditing(true)}
    />
  )
}
