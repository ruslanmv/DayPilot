import React from 'react'

import {
  calendarApi,
  relativeTime,
  type CalendarSettings,
  type CalendarStatus,
  type ContextSource,
  type PrepareScope,
  type PrivateMode,
  type SettingsPayload,
} from './calendarClient'

const PROVIDER_MARK: Record<string, string> = {
  microsoft_calendar: 'O',
  google_calendar: '31',
}

const SCOPES: Array<{ id: PrepareScope; label: string }> = [
  { id: 'external', label: 'External/client meetings' },
  { id: 'important', label: 'Important meetings' },
  { id: 'every', label: 'Every meeting' },
]

const PRIVATE_MODES: Array<{ id: PrivateMode; label: string }> = [
  { id: 'metadata_only', label: 'Metadata only' },
  { id: 'full', label: 'Full agenda' },
  { id: 'skip', label: 'Skip entirely' },
]

const MINUTE_CHOICES = [0, 5, 10, 15, 30]

function Toggle({ on, onChange, label, id }: {
  on: boolean; onChange: (v: boolean) => void; label: string; id: string
}) {
  return (
    <button
      type="button" id={id} role="switch" aria-checked={on} aria-label={label}
      className={'dp-switch' + (on ? ' is-on' : '')}
      onClick={() => onChange(!on)}
    >
      <span className="dp-switch__knob" aria-hidden="true" />
    </button>
  )
}

function Hint({ text }: { text: string }) {
  return <span className="dp-cset__hint" title={text} aria-label={text} role="img">ⓘ</span>
}

function MinuteSelect({ value, onChange, label }: {
  value: number; onChange: (v: number) => void; label: string
}) {
  return (
    <select className="dp-cset__select" aria-label={label} value={value}
            onChange={(e) => onChange(Number(e.target.value))}>
      {MINUTE_CHOICES.map((m) => (
        <option key={m} value={m}>{m === 0 ? 'None' : `${m} min`}</option>
      ))}
    </select>
  )
}

/**
 * Settings → Calendar.
 *
 * Four sections, in the order a user thinks about them: what is connected, how
 * DayPilot should prepare you, **what it is allowed to read**, and how it plans
 * around meetings.
 *
 * The third section is the one that matters. Every source here is a permission,
 * so the list is served by the API rather than hardcoded, a source whose
 * integration is not connected renders disabled rather than pretending to be
 * available, and the calendar event itself is always on because a brief that
 * may not read the meeting would be nonsense.
 *
 * There is no "let AI change my calendar without approval" switch. Calendar
 * writes go through the Approval Center, and a toggle that could turn that off
 * would make the guarantee a preference.
 */
export function CalendarPanel() {
  const [payload, setPayload] = React.useState<SettingsPayload | null>(null)
  const [status, setStatus] = React.useState<CalendarStatus | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState<string | null>(null)

  const load = React.useCallback(async () => {
    const [s, st] = await Promise.all([calendarApi.settings(), calendarApi.status()])
    if (s.ok) { setPayload(s.data); setError(null) } else setError(s.error)
    if (st.ok) setStatus(st.data)
  }, [])

  React.useEffect(() => { void load() }, [load])

  // Optimistic, then reconciled: a toggle that waited for a round trip would
  // feel broken, but the server's answer is what ends up on screen.
  const save = React.useCallback(async (patch: Partial<CalendarSettings>) => {
    setPayload((cur) => (cur ? { ...cur, settings: { ...cur.settings, ...patch } } : cur))
    const r = await calendarApi.save(patch)
    if (!r.ok) { setError(r.error); void load(); return }
    setError(null)
    setPayload((cur) => (cur ? { ...cur, settings: r.data } : cur))
  }, [load])

  if (error && !payload) {
    return <p className="dp-standupcard__error" role="alert">Couldn’t load calendar settings: {error}</p>
  }
  if (!payload) return <p className="dp-home__card-empty">Loading calendar settings…</p>

  const s = payload.settings
  const connected = status?.connections.filter((c) => c.status === 'connected') || []
  const missing = (status?.available || []).filter(
    (a) => !connected.some((c) => c.provider === a.provider),
  )

  const toggleSource = (id: string, on: boolean) => {
    const next = on
      ? [...new Set([...s.contextSources, id])]
      : s.contextSources.filter((x) => x !== id)
    void save({ contextSources: next })
  }

  const startConnect = async (provider: string) => {
    setBusy(provider)
    try {
      // A provider with no OAuth client configured says so here rather than
      // sending the user to an identity provider that will reject them.
      const r = await calendarApi.connect(provider)
      if (!r.ok) { setError(r.error); return }
      window.location.assign(r.url)
    } finally { setBusy(null) }
  }

  return (
    <div className="dp-cset">
      {error && <p className="dp-standupcard__error" role="alert">{error}</p>}

      {/* 1 — connections ------------------------------------------------- */}
      <section className="dp-cset__section" aria-labelledby="cset-connections">
        <h5 className="dp-cset__title" id="cset-connections">1. Calendar connections</h5>
        <div className="dp-cset__cards">
          {connected.map((c) => (
            <div key={c.id} className="dp-cset__conn">
              <span className={'dp-cset__mark dp-cset__mark--' + c.provider} aria-hidden="true">
                {PROVIDER_MARK[c.provider] || '📅'}
              </span>
              <div className="dp-cset__conn-body">
                <div className="dp-cset__conn-head">
                  <strong>{c.label}</strong>
                  <span className="dp-cset__ok">Connected ✓</span>
                </div>
                <div className="dp-cset__conn-meta">
                  {[c.account, `Synced ${relativeTime(c.lastSyncAt)}`].filter(Boolean).join(' · ')}
                </div>
              </div>
              <div className="dp-cset__conn-actions">
                <button type="button" className="dp-ghost-button">Manage</button>
                <button type="button" className="dp-send-button" disabled={busy === c.id}
                        onClick={async () => {
                          setBusy(c.id)
                          const r = await calendarApi.sync()
                          if (!r.ok) setError(r.error)
                          await load()
                          setBusy(null)
                        }}>
                  {busy === c.id ? 'Syncing…' : 'Sync now'}
                </button>
              </div>
              <button type="button" className="dp-linkbtn dp-cset__disconnect">Disconnect</button>
            </div>
          ))}
          {missing.map((a) => (
            <div key={a.provider} className="dp-cset__conn dp-cset__conn--empty">
              <span className={'dp-cset__mark dp-cset__mark--' + a.provider} aria-hidden="true">
                {PROVIDER_MARK[a.provider] || '📅'}
              </span>
              <div className="dp-cset__conn-body">
                <div className="dp-cset__conn-head">
                  <strong>{a.label}</strong>
                  <span className="dp-cset__muted">Not connected</span>
                </div>
              </div>
              <div className="dp-cset__conn-actions">
                <button type="button" className="dp-ghost-button" disabled={busy === a.provider}
                        onClick={() => void startConnect(a.provider)}>
                  Connect {a.label.replace('Microsoft ', '')}
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 2 — meeting preparation ----------------------------------------- */}
      <section className="dp-cset__section" aria-labelledby="cset-prep">
        <h5 className="dp-cset__title" id="cset-prep">2. Meeting preparation</h5>
        <div className="dp-cset__row">
          <Toggle id="cset-prep-on" on={s.prepareEnabled} label="Prepare me for important meetings"
                  onChange={(v) => void save({ prepareEnabled: v })} />
          <label htmlFor="cset-prep-on">Prepare me for important meetings</label>
          <Hint text="DayPilot assembles a brief before the meeting starts. It never joins, speaks, or sends anything." />
        </div>

        <div className={'dp-cset__group' + (s.prepareEnabled ? '' : ' is-disabled')}>
          <div className="dp-cset__radios" role="radiogroup" aria-label="Which meetings to prepare">
            {SCOPES.map((scope) => (
              <button
                key={scope.id} type="button" role="radio"
                aria-checked={s.prepareScope === scope.id}
                disabled={!s.prepareEnabled}
                className={'dp-cset__radio' + (s.prepareScope === scope.id ? ' is-on' : '')}
                onClick={() => void save({ prepareScope: scope.id })}
              >
                <span className="dp-cset__dot" aria-hidden="true" />
                {scope.label}
              </button>
            ))}
          </div>

          <div className="dp-cset__field">
            <span>Preparation time</span>
            <select className="dp-cset__select" aria-label="Preparation time"
                    disabled={!s.prepareEnabled} value={s.prepMinutes}
                    onChange={(e) => void save({ prepMinutes: Number(e.target.value) })}>
              {[5, 10, 15, 30].map((m) => <option key={m} value={m}>{m} minutes</option>)}
            </select>
          </div>

          <div className="dp-cset__row">
            <Toggle id="cset-prep-blocks" on={s.autoPrepBlocks} label="Automatically create prep blocks"
                    onChange={(v) => void save({ autoPrepBlocks: v })} />
            <label htmlFor="cset-prep-blocks">Automatically create prep blocks</label>
            <Hint text="A short block is placed before the meeting so the preparation has somewhere to happen." />
          </div>
        </div>
      </section>

      {/* 3 — meeting context (the allow-list) ----------------------------- */}
      <section className="dp-cset__section" aria-labelledby="cset-context">
        <h5 className="dp-cset__title" id="cset-context">3. Meeting context</h5>
        <p className="dp-cset__lede">
          Choose what DayPilot may read when preparing a meeting. Nothing outside this
          list reaches the model, and every brief names the sources it used.
        </p>
        <div className="dp-cset__sources">
          {payload.sources.map((src: ContextSource) => {
            const checked = src.alwaysOn || s.contextSources.includes(src.id)
            return (
              <label
                key={src.id}
                className={'dp-cset__source' + (src.available ? '' : ' is-unavailable')}
                title={src.available ? undefined : `${src.label} — not connected`}
              >
                <input
                  type="checkbox"
                  checked={checked && src.available}
                  disabled={!src.available || src.alwaysOn}
                  onChange={(e) => toggleSource(src.id, e.target.checked)}
                />
                <span className="dp-cset__source-label">{src.label}</span>
                {!src.available && <span className="dp-cset__muted">Not connected</span>}
              </label>
            )
          })}
        </div>
        <div className="dp-cset__field">
          <span>Private calendar events</span>
          <Hint text="Events marked private or confidential. Metadata only means the title, time and attendee count — never the body." />
          <select className="dp-cset__select" aria-label="Private calendar events"
                  value={s.privateEvents}
                  onChange={(e) => void save({ privateEvents: e.target.value as PrivateMode })}>
            {PRIVATE_MODES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
        </div>
      </section>

      {/* 4 — planning ----------------------------------------------------- */}
      <section className="dp-cset__section" aria-labelledby="cset-planning">
        <h5 className="dp-cset__title" id="cset-planning">4. Planning</h5>
        <div className="dp-cset__row">
          <Toggle id="cset-fixed" on={s.acceptedAreFixed} label="Treat accepted meetings as fixed time"
                  onChange={(v) => void save({ acceptedAreFixed: v })} />
          <label htmlFor="cset-fixed">Treat accepted meetings as fixed time</label>
          <Hint text="The planner reserves the meeting first and fits work into what is left. It never moves a meeting on its own." />
        </div>
        <div className="dp-cset__row">
          <Toggle id="cset-declined" on={s.ignoreDeclined} label="Ignore declined meetings"
                  onChange={(v) => void save({ ignoreDeclined: v })} />
          <label htmlFor="cset-declined">Ignore declined meetings</label>
          <Hint text="A meeting you declined does not reserve time in your day." />
        </div>
        <div className="dp-cset__row">
          <Toggle id="cset-tentative" on={s.tentativeBlocks} label="Tentative meetings block planning time"
                  onChange={(v) => void save({ tentativeBlocks: v })} />
          <label htmlFor="cset-tentative">Tentative meetings block planning time</label>
        </div>
        <div className="dp-cset__buffers">
          <div className="dp-cset__field">
            <span>Before meetings</span>
            <MinuteSelect value={s.bufferBeforeMinutes} label="Buffer before meetings"
                          onChange={(v) => void save({ bufferBeforeMinutes: v })} />
          </div>
          <div className="dp-cset__field">
            <span>After meetings</span>
            <MinuteSelect value={s.bufferAfterMinutes} label="Buffer after meetings"
                          onChange={(v) => void save({ bufferAfterMinutes: v })} />
          </div>
        </div>
        <p className="dp-cset__note">
          DayPilot can propose calendar changes. Every change to an external calendar
          is decided by you in the Approval Center — there is no setting that skips it.
        </p>
      </section>
    </div>
  )
}
