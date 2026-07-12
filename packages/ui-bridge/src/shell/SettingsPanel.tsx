import React, { useEffect, useRef, useState } from 'react'
import { STATE_LANGUAGE } from '@daypilot/homepilot-theme'
import { IntegrationsPanel } from '../integrations/IntegrationsPanel'
import {
  KNOWLEDGE_SOURCES,
  MAIL_SETTINGS,
  OLLABRIDGE_PAIRING,
  PERMISSION_DEFAULTS,
  PROFILE,
  PROVIDER_ROUTES,
  PROVIDER_SUMMARY,
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

// Order shown in the in-panel navigation rail (mirrors the drop-up menu).
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

function SectionBody({ section }: { section: SettingsSectionId }) {
  if (section === 'integrations') {
    return <IntegrationsPanel />
  }
  if (section === 'providers') {
    return (
      <div className="dp-settings-list">
        {/* Ollabridge pairing — local gateway or Ollabridge Cloud */}
        <div className="dp-settings-row">
          <div className="dp-settings-row__head">
            <StateDot tone="default" />
            <strong>{PROVIDER_SUMMARY.provider} · pairing</strong>
            <span className="dp-pill dp-pill--muted">{OLLABRIDGE_PAIRING.modeEnv}</span>
          </div>
          <p>{OLLABRIDGE_PAIRING.detail}</p>
          <div className="dp-mode-grid">
            {OLLABRIDGE_PAIRING.modes.map((m) => (
              <div key={m.id} className={'dp-mode-card' + (OLLABRIDGE_PAIRING.activeMode === m.id ? ' is-active' : '')}>
                <div className="dp-mode-card__head">
                  <strong>{m.label}</strong>
                  {OLLABRIDGE_PAIRING.activeMode === m.id ? <span className="dp-tag dp-tag--healthy">active</span> : <ConnBadge status={m.status} />}
                </div>
                <p className="dp-mode-card__detail">{m.detail}</p>
                <FieldRows
                  fields={[
                    { label: 'Endpoint', value: m.endpoint, hint: m.endpointEnv },
                    { label: 'API key', value: m.keyFormat, hint: 'Bearer · OLLABRIDGE_API_KEY' },
                  ]}
                />
                {m.pairing && <p className="dp-mode-card__pairing">🔗 {m.pairing}</p>}
              </div>
            ))}
          </div>
          <FieldRows fields={OLLABRIDGE_PAIRING.fields} />
          <div className="dp-settings-actions">
            <button className="dp-ghost-button" type="button">Test connection</button>
            <button className="dp-ghost-button" type="button">Pair with Cloud (device code)</button>
          </div>
        </div>
        <p className="dp-muted">Routing policy per agent role (fallback in order):</p>
        {PROVIDER_ROUTES.map((r) => (
          <div key={r.role} className="dp-settings-row dp-settings-row--grid">
            <strong>{r.role}</strong>
            <span>{r.model}</span>
            <span className="dp-pill dp-pill--muted">{r.tier}</span>
            <span>{r.latencyMs}ms</span>
            <span className={'dp-tag dp-tag--' + r.status}>{r.status}</span>
            <span className="dp-provider-fallback">↳ {r.fallback.join(' · ') || 'none'}</span>
          </div>
        ))}
      </div>
    )
  }
  if (section === 'mail') {
    return (
      <div className="dp-settings-list">
        <div className="dp-settings-row">
          <div className="dp-settings-row__head">
            <StateDot tone="connected" />
            <strong>{MAIL_SETTINGS.provider}</strong>
            <ConnBadge status={MAIL_SETTINGS.status} />
          </div>
          <p>{MAIL_SETTINGS.detail}</p>
          <FieldRows fields={MAIL_SETTINGS.fields} />
          <div className="dp-settings-actions">
            <button className="dp-ghost-button" type="button">Test connection</button>
          </div>
        </div>
      </div>
    )
  }
  if (section === 'sources') {
    return (
      <div className="dp-settings-list">
        <p className="dp-muted">{SOURCES_SUMMARY.detail}</p>
        {KNOWLEDGE_SOURCES.map((s) => (
          <div key={s.label} className="dp-settings-row">
            <div className="dp-settings-row__head">
              <StateDot tone={s.status === 'available' ? 'available' : 'connected'} />
              <strong>{s.label}</strong>
              <span className="dp-pill dp-pill--muted">{s.kind}</span>
              <ConnBadge status={s.status} />
            </div>
            <FieldRows
              fields={[
                { label: 'Scope', value: s.scope },
                { label: 'Permission', value: s.permission },
                { label: 'Projects', value: s.projects },
              ]}
            />
          </div>
        ))}
        <div className="dp-settings-actions">
          <button className="dp-ghost-button" type="button">Add folder</button>
          <button className="dp-ghost-button" type="button">Connect Box</button>
          <button className="dp-ghost-button" type="button">Re-index</button>
        </div>
        <p className="dp-muted">Grant local folders via <code className="dp-code">{SOURCES_SUMMARY.envHint}</code></p>
      </div>
    )
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
    return (
      <div className="dp-settings-list">
        <p className="dp-muted">HomePilot Family theme. Obsidian workspace with accent-as-telemetry.</p>
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
    </div>
  )
}

/**
 * Modal settings surface. A left navigation rail switches between every section
 * (so phones — which have no drop-up menu — can still reach mail, providers,
 * and knowledge sources). Escape closes; focus moves to the dialog on open.
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
            <SectionBody section={active} />
          </div>
        </div>
      </div>
    </div>
  )
}
