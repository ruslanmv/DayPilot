import React, { useEffect, useRef, useState } from 'react'
import { STATE_LANGUAGE } from '@daypilot/homepilot-theme'
import { IntegrationsPanel } from '../integrations/IntegrationsPanel'
import { AiProvidersPanel } from '../settings/AiProvidersPanel'
import { CalendarPanel } from '../settings/CalendarPanel'
import { MailSettingsPanel } from '../settings/MailSettingsPanel'
import { KnowledgeSourcesPanel } from '../settings/KnowledgeSourcesPanel'
import { HomePilotConnectionPanel } from '../settings/HomePilotConnectionPanel'
import { YourProfilePanel } from '../settings/YourProfilePanel'
import { getTheme, setTheme, type ThemeMode } from '../theme'
import {
  PERMISSION_DEFAULTS,
  SHORTCUTS,
  type SettingsSectionId,
} from '../settings/settingsData'

type SettingsPanelProps = {
  section: SettingsSectionId
  onClose: () => void
}

const SECTION_TITLES: Record<SettingsSectionId, string> = {
  profile: 'Your profile',
  integrations: 'Integrations',
  calendar: 'Calendar',
  providers: 'AI providers',
  mail: 'Mail settings',
  sources: 'Knowledge sources',
  homepilot: 'HomePilot agents',
  appearance: 'Appearance',
  permissions: 'Permissions & approvals',
  shortcuts: 'Keyboard shortcuts',
}

// Order shown in the in-panel navigation rail — the ONLY place these sections
// are listed; the account dropdown never duplicates them.
const SECTION_ORDER: SettingsSectionId[] = [
  // Calendar sits next to Mail: both are "how DayPilot behaves with a connected
  // account", as opposed to Integrations, which is "what is connected at all".
  'profile', 'integrations', 'calendar', 'mail', 'providers', 'sources', 'homepilot',
  'appearance', 'permissions', 'shortcuts',
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
  if (section === 'calendar') {
    return <CalendarPanel />
  }
  if (section === 'mail') {
    return <MailSettingsPanel />
  }
  if (section === 'sources') {
    return <KnowledgeSourcesPanel />
  }
  if (section === 'homepilot') {
    return <HomePilotConnectionPanel />
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
  // 'profile' → the live, backend-owned AI-profile editor (identity, work style,
  // goals, communication, AI context & privacy, and the setup checklist).
  return <YourProfilePanel onClose={onClose} />
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
