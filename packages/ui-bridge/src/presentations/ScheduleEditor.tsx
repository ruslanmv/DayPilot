import React, { useState } from 'react'
import { presentationsApi, type Series } from './client'

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

/** Opt-in automatic weekly drafts. Drafts are prepared for review; nothing is ever sent. */
export function ScheduleEditor({ series, onSaved }: { series: Series; onSaved: (message: string) => void }) {
  const sc = series.schedule
  const [enabled, setEnabled] = useState(sc?.enabled ?? false)
  const [weekday, setWeekday] = useState(sc?.weekday ?? 0)
  const [time, setTime] = useState(sc?.localTime ?? '08:30')
  const [catchUp, setCatchUp] = useState(sc?.catchUpHours ?? 24)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function save() {
    setBusy(true)
    setError('')
    const r = await presentationsApi.setSchedule(series.id, { enabled, weekday, localTime: time, catchUpHours: catchUp })
    setBusy(false)
    if (!r.ok) return setError(r.error)
    onSaved(enabled ? `“${series.name}” drafts will be prepared every ${DAYS[weekday]} at ${time} (${series.timezone}).` : `Automatic drafts are off for “${series.name}”.`)
  }

  return (
    <details className="pz-schedule">
      <summary>{sc?.enabled ? `Automatic: ${DAYS[sc.weekday ?? 0]} ${sc.localTime}` : 'Automatic drafts: off'}</summary>
      <div className="pz-grid">
        <label className="pz-check">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> Prepare the draft automatically each week
        </label>
        <div className="pz-row">
          <label className="pz-field">Day<select value={weekday} onChange={(e) => setWeekday(Number(e.target.value))}>{DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}</select></label>
          <label className="pz-field">Time ({series.timezone})<input type="time" value={time} onChange={(e) => setTime(e.target.value)} /></label>
          <label className="pz-field">Catch up if missed (hours)<input type="number" min={1} max={168} value={catchUp} onChange={(e) => setCatchUp(Math.max(1, Math.min(168, Number(e.target.value) || 24)))} /></label>
        </div>
        {sc?.policy && <p className="pz-muted">{sc.policy}</p>}
        {sc?.enabled && sc.upcoming.length > 0 && <p className="pz-muted">Next: {sc.upcoming.map((u) => new Date(u).toLocaleString()).join(' · ')}</p>}
        {sc?.lastResult && <p className="pz-muted">Last run: {sc.lastResult}{sc.lastFiredAt ? ` (${new Date(sc.lastFiredAt).toLocaleString()})` : ''}</p>}
        {sc && !sc.schedulerRunning && enabled && <p className="pz-note">The scheduler is not running on this server (DAYPILOT_PRESENTATIONS_SCHEDULER). Drafts are prepared only when someone clicks “Prepare this week”.</p>}
        {error && <p role="alert">{error}</p>}
        <div className="pz-actions">
          <button type="button" className="pz-primary" disabled={busy} onClick={() => void save()}>Save schedule</button>
        </div>
      </div>
    </details>
  )
}
