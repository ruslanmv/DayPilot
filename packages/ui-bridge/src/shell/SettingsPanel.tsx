import React, { useEffect, useRef, useState } from 'react'
import { STATE_LANGUAGE } from '@daypilot/homepilot-theme'
import { IntegrationsPanel } from '../integrations/IntegrationsPanel'
import { AiProvidersPanel } from '../settings/AiProvidersPanel'
import { MailSettingsPanel } from '../settings/MailSettingsPanel'
import { KnowledgeSourcesPanel } from '../settings/KnowledgeSourcesPanel'
import { resetSetup } from '../onboarding/setupState'
import { getTheme, setTheme, type ThemeMode } from '../theme'
import {
  KNOWLEDGE_SOURCES,
  MAIL_SETTINGS,
  OLLABRIDGE_PAIRING,
  PERMISSION_DEFAULTS,
  PROFILE,
  SOURCES_SUMMARY,
  SHORTCUTS,
  type ConfigField,
  type SettingsSectionId,
} from '../settings/settingsData'

type SettingsPanelProps = {
  section: SettingsSectionId
  onClose: () => void
}

const SECTION_TITLES: Record<SettingsSectionId, string> = {
  profile: 'Profile & workspace',
  integrations: 'Integrations',
  providers: 'AI providers',
  mail: 'Mail settings',
  sources: 'Knowledge sources',
  appearance: 'Appearance',
  permissions: 'Permissions & approvals',
  shortcuts: 'Keyboard shortcuts',
}

// Order shown in the in-panel navigation rail — the ONLY place these sections
// are listed; the account dropdown never duplicates them.
const SECTION_ORDER: SettingsSectionId[] = [
  'profile', 'integrations', 'providers', 'mail', 'sources', 'appearance', 'permissions', 'shortcuts',
]

function StateDot({ tone }: { tone: 'connected' | 'default' | 'available' | 'disabled' }) {
  const map = {
    connected: STATE_LANGUAGE['ai-running'].color,
    default: STATE_LANGUAGE.safe.color,
    available: STATE_LANGUAGE['needs-attention'].color,
    disabled: STATE_LANGUAGE.blocked.color,
  }
  return <span className="dp-dot" style={{ background: map[tone] }} aria-hidden="true" />
}

function ConnBadge({ status }: { status: string }) {
  const healthy = status === 'connected' || status === 'paired' || status === 'indexed'
  const warn = status === 'mock' || status === 'available' || status === 'indexing'
  const cls = healthy ? 'dp-tag--healthy' : warn ? 'dp-tag--degraded' : 'dp-tag--offline'
  return <span className={'dp-tag ' + cls}>{status}</span>
}

function FieldRows({ fields }: { fields: ConfigField[] }) {
  return (
    <div className="dp-settings-fields">
      {fields.map((f) => (
        <div key={f.label} className="dp-settings-field">
          <span className="dp-settings-field__label">{f.label}</span>
          <span className={'dp-settings-field__value' + (f.secret ? ' dp-settings-field__value--secret' : '')}>{f.value}</span>
          {f.hint && <span className="dp-settings-field__hint">{f.hint}</span>}
        </div>
      ))}
    </div>
  )
}

function AppearanceSection() {
  const [theme, setThemeState] = useState<ThemeMode>(() => getTheme())
  function choose(mode: ThemeMode) { setThemeState(mode); setTheme(mode) }
  return (
    <div className="dp-settings-list">
      <p className="dp-muted">Appearance. DayPilot is dark by default; switch to light if you prefer.</p>
      <div className="dp-theme-toggle" role="radiogroup" aria-label="Theme">
        {(['dark', 'light'] as ThemeMode[]).map((mode) => (
          <button
            key={mode}
            role="radio"
            aria-checked={theme === mode}
            className={'dp-theme-opt dp-theme-opt--' + mode + (theme === mode ? ' is-active' : '')}
            onClick={() => choose(mode)}
          >
            <span className="dp-theme-opt__swatch" aria-hidden="true" />
            <span className="dp-theme-opt__label">{mode === 'dark' ? '🌙 Dark' : '☀ Light'}{theme === mode ? ' · Active' : ''}</span>
          </button>
        ))}
      </div>
      <p className="dp-muted" style={{ marginTop: '0.75rem' }}>Accent-as-telemetry — colors signal state, never decoration.</p>
      <div className="dp-swatches">
        {Object.entries(STATE_LANGUAGE).map(([key, s]) => (
          <div key={key} className="dp-swatch">
            <span className="dp-dot" style={{ background: s.color }} aria-hidden="true" />
            <span>{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function SectionBody({ section, onClose }: { section: SettingsSectionId; onClose: () => void }) {
  if (section === 'integrations') {
    return <IntegrationsPanel />
  }
  if (section === 'providers') {
    return <AiProvidersPanel />
  }
  if (section === 'mail') {
    return <MailSettingsPanel />
  }
  if (section === 'sources') {
    return <KnowledgeSourcesPanel />
  }
  if (section === 'permissions') {
    return (
      <div className="dp-settings-list">
        <p className="dp-muted">Safe by default. Sensitive actions are approval-gated and audited.</p>
        {PERMISSION_DEFAULTS.map((p) => (
          <div key={p.label} className="dp-settings-row dp-settings-row--split">
            <span>{p.label}</span>
            <span className={'dp-tag ' + (p.safe ? 'dp-tag--healthy' : 'dp-tag--degraded')}>{p.value}</span>
          </div>
        ))}
      </div>
    )
  }
  if (section === 'shortcuts') {
    return (
      <div className="dp-settings-list">
        {SHORTCUTS.map((s) => (
          <div key={s.action} className="dp-settings-row dp-settings-row--split">
            <span>{s.action}</span>
            <kbd className="dp-kbd">{s.keys}</kbd>
          </div>
        ))}
      </div>
    )
  }
  if (section === 'appearance') {
    return <AppearanceSection />
  }
  return (
    <div className="dp-settings-list">
      <div className="dp-settings-row">
        <div className="dp-settings-row__head">
          <strong>{PROFILE.name}</strong>
          <span className="dp-pill dp-pill--muted">{PROFILE.role}</span>
        </div>
        <FieldRows
          fields={[
            { label: 'Email', value: PROFILE.email },
            { label: 'Workspace', value: PROFILE.workspace },
            { label: 'Mode', value: PROFILE.mode },
          ]}
        />
      </div>
      <p className="dp-muted">Connected essentials</p>
      <div className="dp-settings-row dp-settings-row--split">
        <span>Mailbox</span>
        <span className="dp-tag dp-tag--healthy">{MAIL_SETTINGS.fields[2].value}</span>
      </div>
      <div className="dp-settings-row dp-settings-row--split">
        <span>Knowledge sources</span>
        <span className="dp-tag dp-tag--healthy">{KNOWLEDGE_SOURCES.length} granted</span>
      </div>
      <div className="dp-settings-row dp-settings-row--split">
        <span>AI provider</span>
        <span className="dp-tag dp-tag--healthy">{OLLABRIDGE_PAIRING.modes.find((m) => m.id === OLLABRIDGE_PAIRING.activeMode)?.label}</span>
      </div>
      <p className="dp-muted">Setup</p>
      <div className="dp-settings-row">
        <p>Re-run the first-run setup wizard to reconnect your AI provider, mailbox, and knowledge sources.</p>
        <div className="dp-settings-actions">
          <button className="dp-ghost-button" type="button" onClick={() => { resetSetup(); onClose() }}>Restart setup</button>
        </div>
      </div>
    </div>
  )
}

/**
 * Modal settings surface — the single home for every advanced section. A left
 * navigation rail (chip row on phones) switches between sections; the account
 * dropdown only links here. Escape closes; focus moves to the dialog on open.
 */
export function SettingsPanel({ section, onClose }: SettingsPanelProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const [active, setActive] = useState<SettingsSectionId>(section)

  useEffect(() => setActive(section), [section])

  useEffect(() => {
    dialogRef.current?.focus()
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="dp-modal-backdrop" onMouseDown={onClose}>
      <div
        ref={dialogRef}
        className="dp-settings-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        tabIndex={-1}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="dp-settings-panel__head">
          <h3>Settings</h3>
          <button className="dp-icon-button" aria-label="Close settings" onClick={onClose}>✕</button>
        </header>
        <div className="dp-settings-panel__layout">
          <nav className="dp-settings-panel__nav" aria-label="Settings sections">
            {SECTION_ORDER.map((id) => (
              <button
                key={id}
                type="button"
                className={'dp-settings-navitem' + (active === id ? ' is-active' : '')}
                aria-current={active === id ? 'page' : undefined}
                onClick={() => setActive(id)}
              >
                {SECTION_TITLES[id]}
              </button>
            ))}
          </nav>
          <div className="dp-settings-panel__body">
            <h4 className="dp-settings-panel__section-title">{SECTION_TITLES[active]}</h4>
            <SectionBody section={active} onClose={onClose} />
          </div>
        </div>
      </div>
    </div>
  )
}
