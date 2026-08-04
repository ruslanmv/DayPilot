/**
 * Your profile — the complete, backend-owned AI-profile editor (Phase 3).
 *
 * Six tabs (Identity, Work style, Goals, Communication, AI context & privacy,
 * Setup checklist) edit the server profile through profileClient. The backend
 * is the source of truth: this panel loads the current revision, guards saves
 * with it (a 409 refetches and asks the user to retry), and shows honest
 * Saving/Saved/Error status announced via aria-live. "What AI sees" renders the
 * exact ProfileContextBuilder projection — never a UI approximation. No secret
 * or provenance source content is ever displayed.
 */
import React, { useEffect, useMemo, useState } from 'react'
import { resetSetup } from '../onboarding/setupState'
import {
  profileClient,
  CONSENT_LABELS,
  USE_CASE_LABELS,
  type AiProfile,
  type ConsentCategory,
  type ContextPreview,
  type Observation,
  type OnboardingView,
  type ProfileGoal,
  type ProfilePatch,
  type UseCase,
} from './profileClient'

type TabId = 'identity' | 'work' | 'goals' | 'communication' | 'privacy' | 'checklist'
const TABS: { id: TabId; label: string }[] = [
  { id: 'identity', label: 'Identity' },
  { id: 'work', label: 'Work style' },
  { id: 'goals', label: 'Goals' },
  { id: 'communication', label: 'Communication' },
  { id: 'privacy', label: 'AI context & privacy' },
  { id: 'checklist', label: 'Setup checklist' },
]

type SaveState = 'idle' | 'saving' | 'saved' | 'error'
const COMMON_TZ = [
  'UTC', 'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Madrid',
  'America/New_York', 'America/Chicago', 'America/Los_Angeles', 'Asia/Tokyo',
  'Asia/Singapore', 'Asia/Kolkata', 'Australia/Sydney',
]
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function browserTimezone(): string {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' } catch { return 'UTC' }
}

export function YourProfilePanel({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<TabId>('identity')
  const [profile, setProfile] = useState<AiProfile | null>(null)
  const [onboarding, setOnboarding] = useState<OnboardingView | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [save, setSave] = useState<SaveState>('idle')
  const [saveMsg, setSaveMsg] = useState('')

  async function reload() {
    const [p, o] = await Promise.all([profileClient.getProfile(), profileClient.getOnboarding()])
    if (p.ok) setProfile(p.data); else setLoadError(p.error)
    if (o.ok) setOnboarding(o.data)
  }

  useEffect(() => { void reload() }, [])

  async function persist(patch: ProfilePatch, note = 'Saved') {
    if (!profile) return
    setSave('saving'); setSaveMsg('Saving…')
    const res = await profileClient.saveProfile(profile.revision, patch)
    if (res.ok) {
      setProfile(res.data); setSave('saved'); setSaveMsg(note)
      window.setTimeout(() => setSave('idle'), 1600)
    } else if (res.status === 409) {
      await reload()
      setSave('error'); setSaveMsg('This profile changed elsewhere — your view was refreshed, please re-apply.')
    } else {
      setSave('error'); setSaveMsg(res.error || 'Save failed. Your edits are kept — try again.')
    }
  }

  if (loadError && !profile) {
    return (
      <div className="dp-settings-list">
        <p className="dp-muted">Couldn’t load your profile ({loadError}). It’s safe to retry.</p>
        <button className="dp-ghost-button" type="button" onClick={() => { setLoadError(null); void reload() }}>Retry</button>
      </div>
    )
  }
  if (!profile) return <div className="dp-settings-list"><p className="dp-muted">Loading your profile…</p></div>

  return (
    <div className="dp-settings-list">
      <div role="tablist" aria-label="Profile sections" style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            className={'dp-settings-navitem' + (tab === t.id ? ' is-active' : '')}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <p aria-live="polite" className={'dp-muted' + (save === 'error' ? ' dp-error-text' : '')} style={{ minHeight: 18 }}>
        {save === 'saving' ? 'Saving…' : saveMsg}
      </p>

      {tab === 'identity' && <IdentityTab profile={profile} onSave={persist} />}
      {tab === 'work' && <WorkStyleTab profile={profile} onSave={persist} />}
      {tab === 'goals' && <GoalsTab />}
      {tab === 'communication' && <CommunicationTab profile={profile} onSave={persist} />}
      {tab === 'privacy' && <PrivacyTab profile={profile} onSave={persist} />}
      {tab === 'checklist' && <ChecklistTab onboarding={onboarding} onClose={onClose} onReload={reload} />}
    </div>
  )
}

// --- Identity ----------------------------------------------------------------

function IdentityTab({ profile, onSave }: { profile: AiProfile; onSave: (p: ProfilePatch) => void }) {
  const [name, setName] = useState(profile.preferredName || '')
  const [pronouns, setPronouns] = useState(profile.pronouns || '')
  const [tz, setTz] = useState(profile.timezone || browserTimezone())
  const [locale, setLocale] = useState(profile.locale || '')
  const [useCases, setUseCases] = useState<UseCase[]>(profile.useCases || [])

  function toggle(u: UseCase) {
    setUseCases((prev) => (prev.includes(u) ? prev.filter((x) => x !== u) : [...prev, u]))
  }

  return (
    <form className="dp-settings-list" onSubmit={(e) => { e.preventDefault(); onSave({ preferredName: name, pronouns, timezone: tz, locale: locale || undefined, useCases }) }}>
      <Field label="Preferred name" hint="How the assistant addresses you.">
        <input className="dp-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
      </Field>
      <Field label="Pronouns (optional)">
        <input className="dp-input" value={pronouns} onChange={(e) => setPronouns(e.target.value)} maxLength={40} />
      </Field>
      <Field label="Timezone" hint="Used to avoid scheduling outside your day.">
        <input className="dp-input" list="dp-tz-list" value={tz} onChange={(e) => setTz(e.target.value)} />
        <datalist id="dp-tz-list">{COMMON_TZ.map((z) => <option key={z} value={z} />)}</datalist>
      </Field>
      <Field label="Locale (optional)" hint="BCP 47, e.g. en-US or fr-FR.">
        <input className="dp-input" value={locale} onChange={(e) => setLocale(e.target.value)} placeholder="en-US" />
      </Field>
      <Field label="Primary use cases" hint="Tailors what the assistant leads with.">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {(Object.keys(USE_CASE_LABELS) as UseCase[]).map((u) => (
            <label key={u} className="dp-check">
              <input type="checkbox" checked={useCases.includes(u)} onChange={() => toggle(u)} /> {USE_CASE_LABELS[u]}
            </label>
          ))}
        </div>
      </Field>
      <div className="dp-settings-actions"><button className="dp-primary-button" type="submit">Save identity</button></div>
    </form>
  )
}

// --- Work style --------------------------------------------------------------

function WorkStyleTab({ profile, onSave }: { profile: AiProfile; onSave: (p: ProfilePatch) => void }) {
  const win = profile.schedule.workingWindows?.[0]
  const [days, setDays] = useState<number[]>(win?.days || [1, 2, 3, 4, 5])
  const [start, setStart] = useState(win?.start || '09:00')
  const [end, setEnd] = useState(win?.end || '17:30')
  const [strict, setStrict] = useState(profile.schedule.strictness || 'flexible')
  const [focus, setFocus] = useState(profile.planning.focusMinutes ?? 60)
  const [buffer, setBuffer] = useState(profile.planning.meetingBufferMinutes ?? 10)
  const [horizon, setHorizon] = useState(profile.planning.planningHorizonDays ?? 7)
  const [prioritization, setPrioritization] = useState(profile.planning.prioritization || 'impact')

  function toggleDay(d: number) {
    setDays((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]).sort((a, b) => a - b))
  }

  function submit() {
    onSave({
      schedule: { workingWindows: days.length ? [{ days, start, end }] : [], strictness: strict },
      planning: { focusMinutes: focus, meetingBufferMinutes: buffer, planningHorizonDays: horizon, prioritization },
    })
  }

  return (
    <form className="dp-settings-list" onSubmit={(e) => { e.preventDefault(); submit() }}>
      <Field label="Working days">
        <div style={{ display: 'flex', gap: 6 }}>
          {WEEKDAYS.map((label, i) => (
            <button key={label} type="button" className={'dp-chip' + (days.includes(i + 1) ? ' is-active' : '')} onClick={() => toggleDay(i + 1)}>{label}</button>
          ))}
        </div>
      </Field>
      <Field label="Working hours" hint="The assistant won’t suggest work outside this window.">
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input className="dp-input" type="time" value={start} onChange={(e) => setStart(e.target.value)} />
          <span>to</span>
          <input className="dp-input" type="time" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
      </Field>
      <Field label="Times are">
        <select className="dp-input" value={strict} onChange={(e) => setStrict(e.target.value as 'strict' | 'flexible')}>
          <option value="flexible">Flexible</option>
          <option value="strict">Strict</option>
        </select>
      </Field>
      <Field label="Focus block (minutes)"><input className="dp-input" type="number" min={15} max={480} value={focus} onChange={(e) => setFocus(Number(e.target.value))} /></Field>
      <Field label="Meeting buffer (minutes)"><input className="dp-input" type="number" min={0} max={120} value={buffer} onChange={(e) => setBuffer(Number(e.target.value))} /></Field>
      <Field label="Planning horizon (days)"><input className="dp-input" type="number" min={1} max={90} value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} /></Field>
      <Field label="Prioritize by">
        <select className="dp-input" value={prioritization} onChange={(e) => setPrioritization(e.target.value as 'deadlines' | 'impact' | 'quick_wins' | 'manual')}>
          <option value="impact">Impact</option>
          <option value="deadlines">Deadlines</option>
          <option value="quick_wins">Quick wins</option>
          <option value="manual">Manual</option>
        </select>
      </Field>
      <div className="dp-settings-actions"><button className="dp-primary-button" type="submit">Save work style</button></div>
    </form>
  )
}

// --- Goals -------------------------------------------------------------------

function GoalsTab() {
  const [goals, setGoals] = useState<ProfileGoal[]>([])
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)

  async function load() {
    const res = await profileClient.getGoals()
    if (res.ok) setGoals(res.data.goals)
  }
  useEffect(() => { void load() }, [])

  async function add() {
    if (!title.trim()) return
    setBusy(true)
    const res = await profileClient.createGoal({ title: title.trim() })
    if (res.ok) { setTitle(''); await load() }
    setBusy(false)
  }
  async function setStatus(g: ProfileGoal, status: string) { await profileClient.updateGoal(g.id, { status }); await load() }
  async function remove(g: ProfileGoal) { await profileClient.deleteGoal(g.id); await load() }

  return (
    <div className="dp-settings-list">
      <p className="dp-muted">Up to three current outcomes guide planning. These are profile-level goals, not project tasks.</p>
      <div style={{ display: 'flex', gap: 8 }}>
        <input className="dp-input" style={{ flex: 1 }} placeholder="e.g. Ship the beta by Q3" value={title}
          onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') void add() }} maxLength={200} />
        <button className="dp-primary-button" type="button" disabled={busy} onClick={() => void add()}>Add goal</button>
      </div>
      {goals.length === 0 && <p className="dp-muted">No goals yet.</p>}
      {goals.map((g) => (
        <div key={g.id} className="dp-settings-row dp-settings-row--split">
          <span>{g.title} <span className="dp-pill dp-pill--muted">{g.status}</span></span>
          <span style={{ display: 'flex', gap: 6 }}>
            {g.status !== 'archived'
              ? <button className="dp-ghost-button" type="button" onClick={() => void setStatus(g, 'archived')}>Archive</button>
              : <button className="dp-ghost-button" type="button" onClick={() => void setStatus(g, 'active')}>Reactivate</button>}
            <button className="dp-ghost-button" type="button" onClick={() => void remove(g)} aria-label={`Delete ${g.title}`}>Delete</button>
          </span>
        </div>
      ))}
    </div>
  )
}

// --- Communication -----------------------------------------------------------

function CommunicationTab({ profile, onSave }: { profile: AiProfile; onSave: (p: ProfilePatch) => void }) {
  const c = profile.communication
  const [tone, setTone] = useState(c.tone || 'neutral')
  const [detail, setDetail] = useState(c.detail || 'balanced')
  const [format, setFormat] = useState(c.format || 'mixed')
  const [languages, setLanguages] = useState((c.languages || []).join(', '))
  const [greeting, setGreeting] = useState(c.draftingGreeting || '')
  const [signoff, setSignoff] = useState(c.draftingSignoff || '')
  const [uncertainty, setUncertainty] = useState(c.uncertainty || 'flag_and_proceed')

  function submit() {
    const langs = languages.split(',').map((s) => s.trim()).filter(Boolean)
    onSave({ communication: { tone, detail, format, languages: langs, draftingGreeting: greeting, draftingSignoff: signoff, uncertainty } })
  }

  return (
    <form className="dp-settings-list" onSubmit={(e) => { e.preventDefault(); submit() }}>
      <p className="dp-muted">Defaults for answers and drafts — always overridable per conversation.</p>
      <Field label="Tone"><select className="dp-input" value={tone} onChange={(e) => setTone(e.target.value as typeof tone)}>
        <option value="friendly">Friendly</option><option value="neutral">Neutral</option><option value="formal">Formal</option><option value="direct">Direct</option>
      </select></Field>
      <Field label="Answer depth"><select className="dp-input" value={detail} onChange={(e) => setDetail(e.target.value as typeof detail)}>
        <option value="concise">Concise</option><option value="balanced">Balanced</option><option value="detailed">Detailed</option>
      </select></Field>
      <Field label="Format"><select className="dp-input" value={format} onChange={(e) => setFormat(e.target.value as typeof format)}>
        <option value="bullets">Bullets</option><option value="prose">Prose</option><option value="mixed">Mixed</option>
      </select></Field>
      <Field label="Languages" hint="Comma-separated BCP 47 tags, e.g. en, fr.">
        <input className="dp-input" value={languages} onChange={(e) => setLanguages(e.target.value)} placeholder="en, fr" />
      </Field>
      <Field label="Drafting greeting (optional)"><input className="dp-input" value={greeting} onChange={(e) => setGreeting(e.target.value)} maxLength={200} /></Field>
      <Field label="Drafting sign-off (optional)"><input className="dp-input" value={signoff} onChange={(e) => setSignoff(e.target.value)} maxLength={200} /></Field>
      <Field label="On uncertainty"><select className="dp-input" value={uncertainty} onChange={(e) => setUncertainty(e.target.value as typeof uncertainty)}>
        <option value="flag_and_proceed">Flag it and proceed</option><option value="ask_first">Ask me first</option>
      </select></Field>
      <div className="dp-settings-actions"><button className="dp-primary-button" type="submit">Save communication</button></div>
    </form>
  )
}

// --- AI context & privacy ----------------------------------------------------

const PREVIEW_PURPOSES = ['planning', 'drafting', 'knowledge', 'agent_delegation', 'assistant']

function PrivacyTab({ profile, onSave }: { profile: AiProfile; onSave: (p: ProfilePatch, note?: string) => void }) {
  const [purpose, setPurpose] = useState('planning')
  const [preview, setPreview] = useState<ContextPreview | null>(null)
  const [suggestions, setSuggestions] = useState<Observation[]>([])
  const consent = profile.categoryConsent

  useEffect(() => {
    let live = true
    void profileClient.contextPreview(purpose).then((r) => { if (live && r.ok) setPreview(r.data) })
    return () => { live = false }
  }, [purpose, profile.revision])

  async function loadSuggestions() {
    const r = await profileClient.listObservations('suggested')
    if (r.ok) setSuggestions(r.data.observations)
  }
  useEffect(() => { void loadSuggestions() }, [])

  async function decide(o: Observation, confirm: boolean) {
    if (confirm) await profileClient.confirmObservation(o.id)
    else await profileClient.rejectObservation(o.id)
    await loadSuggestions()
  }

  function toggleConsent(cat: ConsentCategory) {
    onSave({ categoryConsent: { [cat]: !consent[cat] } }, 'Consent updated')
  }

  async function doExport() {
    const res = await profileClient.exportProfile()
    if (!res.ok) return
    const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'daypilot-ai-profile.json'; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="dp-settings-list">
      <p className="dp-muted">Choose what the AI may use, and preview exactly what it sees. Turning a category off removes it from every model request.</p>
      {(Object.keys(CONSENT_LABELS) as ConsentCategory[]).map((cat) => (
        <div key={cat} className="dp-settings-row dp-settings-row--split">
          <span>{CONSENT_LABELS[cat]}</span>
          <label className="dp-switch">
            <input type="checkbox" checked={consent[cat] !== false} onChange={() => toggleConsent(cat)} aria-label={`Include ${CONSENT_LABELS[cat]} in AI context`} />
            <span>{consent[cat] !== false ? 'Included' : 'Excluded'}</span>
          </label>
        </div>
      ))}

      <p className="dp-muted" style={{ marginTop: 12 }}>What AI sees</p>
      <Field label="For purpose">
        <select className="dp-input" value={purpose} onChange={(e) => setPurpose(e.target.value)}>
          {PREVIEW_PURPOSES.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </Field>
      <pre className="dp-code" style={{ maxHeight: 220, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
        {preview ? JSON.stringify(preview, null, 2) : 'Loading preview…'}
      </pre>
      {preview && preview.includedCategories.length === 0 && (
        <p className="dp-muted">Nothing would be sent for this purpose yet — add preferences or enable categories above.</p>
      )}

      <p className="dp-muted" style={{ marginTop: 12 }}>Learned suggestions</p>
      {suggestions.length === 0 ? (
        <p className="dp-muted">Nothing to review. DayPilot never uses a learned preference until you confirm it here.</p>
      ) : (
        suggestions.map((o) => (
          <div key={o.id} className="dp-settings-row dp-settings-row--split">
            <span>{CONSENT_LABELS[o.category as ConsentCategory] || o.category}: <code>{JSON.stringify(o.value)}</code></span>
            <span style={{ display: 'flex', gap: 6 }}>
              <button className="dp-ghost-button" type="button" onClick={() => void decide(o, true)}>Confirm</button>
              <button className="dp-ghost-button" type="button" onClick={() => void decide(o, false)}>Dismiss</button>
            </span>
          </div>
        ))
      )}

      <div className="dp-settings-actions" style={{ gap: 8 }}>
        <button className="dp-ghost-button" type="button" onClick={() => void doExport()}>Export my data</button>
        <button className="dp-ghost-button" type="button" onClick={() => { void profileClient.resetLearned().then(() => loadSuggestions()) }}>Reset learned context</button>
      </div>
    </div>
  )
}

// --- Setup checklist ---------------------------------------------------------

function ChecklistTab({ onboarding, onClose, onReload }: { onboarding: OnboardingView | null; onClose: () => void; onReload: () => Promise<void> }) {
  const caps = onboarding?.capabilities
  const rows = useMemo(() => ([
    { key: 'provider', label: 'AI provider', connected: !!caps?.provider.connected },
    { key: 'mail', label: 'Mailbox', connected: !!caps?.mail.connected },
    { key: 'calendar', label: 'Calendar', connected: !!caps?.calendar.connected },
    { key: 'knowledge', label: 'Knowledge sources', connected: !!caps?.knowledge.connected },
  ]), [caps])

  return (
    <div className="dp-settings-list">
      <div className="dp-settings-row dp-settings-row--split">
        <span>Setup status</span>
        <span className={'dp-tag ' + (onboarding?.status === 'completed' ? 'dp-tag--healthy' : 'dp-tag--degraded')}>
          {onboarding?.status === 'completed' ? 'Complete' : onboarding?.status === 'in_progress' ? 'In progress' : 'Not started'}
        </span>
      </div>
      {rows.map((r) => (
        <div key={r.key} className="dp-settings-row dp-settings-row--split">
          <span>{r.label}</span>
          <span className={'dp-tag ' + (r.connected ? 'dp-tag--healthy' : 'dp-tag--muted')}>{r.connected ? 'Connected' : 'Not connected'}</span>
        </div>
      ))}
      <p className="dp-muted">Optional integrations never block completion. Restarting setup reconnects integrations — it does not erase your saved profile.</p>
      <div className="dp-settings-actions" style={{ gap: 8 }}>
        <button className="dp-ghost-button" type="button" onClick={() => { resetSetup(); onClose() }}>Restart setup</button>
        <button className="dp-ghost-button" type="button" onClick={() => void onReload()}>Refresh status</button>
      </div>
    </div>
  )
}

// --- shared ------------------------------------------------------------------

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="dp-settings-row" style={{ display: 'block' }}>
      <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{label}</span>
      {children}
      {hint && <span className="dp-muted" style={{ display: 'block', marginTop: 4, fontSize: 12 }}>{hint}</span>}
    </label>
  )
}
