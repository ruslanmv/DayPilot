/**
 * Settings surface configuration.
 *
 * Connected systems (HomePilot, GitPilot, Matrix Designer, Ollabridge, Email,
 * Box) live here in Settings — never in the primary nav — per the DayPilot
 * product rules.
 */
export type SettingsSectionId =
  | 'profile'
  | 'integrations'
  | 'calendar'
  | 'providers'
  | 'mail'
  | 'sources'
  | 'homepilot'
  | 'appearance'
  | 'permissions'
  | 'shortcuts'

// NOTE: The account dropdown is intentionally minimal (profile, Settings, Sign
// out — see shell/AccountMenu.tsx). All sections below are reachable only via
// the full Settings modal's own navigation, never duplicated in a menu.

export type IntegrationRow = {
  name: string
  role: string
  state: 'connected' | 'default' | 'available' | 'disabled'
  detail: string
  /** Granted capabilities (I0), shown on connected integrations. */
  capabilities?: string[]
  /** Last successful activity, shown on connected integrations. */
  lastActivity?: string
  authType?: 'oauth' | 'api_key' | 'mcp'
}

export const INTEGRATIONS: IntegrationRow[] = [
  { name: 'Ollabridge', role: 'Default LLM provider', state: 'default', detail: 'OpenAI-compatible routing for local, hybrid, and cloud models.', capabilities: ['chat.completions', 'models.list'], lastActivity: '2 min ago', authType: 'api_key' },
  { name: 'GitPilot', role: 'Default coding bridge', state: 'connected', detail: 'Retro-compatible runs with Ask/Auto/Plan modes and controlled diffs.', capabilities: ['repo.read', 'branch.create', 'patch.propose'], lastActivity: '1 h ago', authType: 'oauth' },
  { name: 'Slack', role: 'Team messaging', state: 'available', detail: 'Draft replies to mentions and DMs — approval-gated, never auto-sends.', authType: 'oauth' },
  { name: 'GitHub', role: 'Repositories & CI', state: 'connected', detail: 'Read repos, watch checks; writes and PRs require approval.', capabilities: ['repo.read', 'checks.read', 'pr.create'], lastActivity: '12 min ago', authType: 'oauth' },
  { name: 'Google Calendar', role: 'Calendar', state: 'connected', detail: 'Read events and detect conflicts; creates/moves require approval.', capabilities: ['events.read', 'events.write'], lastActivity: '5 min ago', authType: 'oauth' },
  { name: 'Claude Code', role: 'Optional coding executor', state: 'available', detail: 'Enable to route coding blocks through Claude Code.', authType: 'api_key' },
  { name: 'Codex', role: 'Optional coding executor', state: 'available', detail: 'Enable to route coding blocks through Codex.', authType: 'api_key' },
  { name: 'Matrix Designer', role: 'Planner & design reviewer', state: 'connected', detail: 'Turns ideas into Design Bundles and reviews UI/deck quality.', capabilities: ['bundle.create', 'design.review'], lastActivity: '3 h ago', authType: 'mcp' },
  { name: 'Email Sentinel', role: 'Inbox agent', state: 'connected', detail: 'Classifies, drafts, and detects schedule impact. Never sends without approval.', capabilities: ['inbox.read', 'reply.draft'], lastActivity: '20 min ago', authType: 'oauth' },
  { name: 'HomePilot', role: 'Persona portability', state: 'connected', detail: 'Imports .hpersona identities under governed enablement.', capabilities: ['persona.import'], lastActivity: 'yesterday', authType: 'mcp' },
  { name: 'Box', role: 'Document source', state: 'available', detail: 'Scoped folder access, read + index only by default.', authType: 'oauth' },
]

export type ProviderRoute = {
  role: string
  model: string
  tier: 'Local' | 'Hybrid' | 'Cloud'
  latencyMs: number
  status: 'healthy' | 'degraded' | 'offline'
  fallback: string[]
}

// Mirrors the backend routing policy (daypilot_models/routing.py). The live
// values come from GET /v1/providers/health + /routes once data-fetching lands.
export const PROVIDER_ROUTES: ProviderRoute[] = [
  { role: 'Scheduler', model: 'llama3.1', tier: 'Local', latencyMs: 210, status: 'healthy', fallback: ['mistral'] },
  { role: 'Email Sentinel', model: 'llama3.1', tier: 'Local', latencyMs: 240, status: 'healthy', fallback: ['mistral'] },
  { role: 'Document Assistant', model: 'mixtral', tier: 'Hybrid', latencyMs: 680, status: 'healthy', fallback: ['llama3.1'] },
  { role: 'Coding agents', model: 'deepseek-coder', tier: 'Hybrid', latencyMs: 920, status: 'degraded', fallback: ['qwen2.5-coder', 'llama3.1'] },
]

export const PROVIDER_SUMMARY = {
  provider: 'Ollabridge',
  role: 'Default LLM provider',
  detail: 'One OpenAI-compatible endpoint routes local, hybrid, and cloud models. Local-first by default; degrades to mock if unreachable.',
}

export const PROFILE = {
  name: 'Ruslan M.',
  email: 'ruslan@daypilot.local',
  role: 'Principal AI/ML Engineer',
  workspace: 'DayPilot Enterprise',
  mode: 'Local-first · Owner',
}

export type ConfigField = { label: string; value: string; hint?: string; secret?: boolean }
export type ConnState = 'connected' | 'paired' | 'mock' | 'unreachable' | 'available'

/** One Ollabridge deployment target. Local and Cloud are the same
 *  OpenAI-compatible consumer surface (Bearer key + /v1/chat/completions);
 *  Cloud additionally supports TV-style device pairing. */
export type OllabridgeMode = {
  id: 'local' | 'cloud'
  label: string
  endpoint: string
  endpointEnv: string
  keyFormat: string
  status: ConnState
  detail: string
  pairing?: string
}

/** Ollabridge pairing — DayPilot pairs with the local gateway OR Ollabridge
 *  Cloud (switch with OLLABRIDGE_MODE). Binds to OllabridgeConnector /
 *  connector_from_env in services/model-serving. */
export const OLLABRIDGE_PAIRING: {
  activeMode: 'local' | 'cloud'
  modeEnv: string
  detail: string
  modes: OllabridgeMode[]
  fields: ConfigField[]
} = {
  activeMode: 'local',
  modeEnv: 'OLLABRIDGE_MODE',
  detail:
    'Pair DayPilot to Ollabridge. The local gateway and Ollabridge Cloud expose the same OpenAI-compatible endpoint, so pairing works the same way — one base URL plus a Bearer key. Keys are never logged.',
  modes: [
    {
      id: 'local',
      label: 'Local gateway',
      endpoint: 'http://localhost:11435/v1',
      endpointEnv: 'OLLABRIDGE_BASE_URL',
      keyFormat: 'sk-ollabridge-… (printed at startup)',
      status: 'paired',
      detail: 'Runs on your machine. No cloud login, no telemetry — prompts, history, and keys never leave the device.',
    },
    {
      id: 'cloud',
      label: 'Ollabridge Cloud',
      endpoint: 'https://ruslanmv-ollabridge.hf.space/v1',
      endpointEnv: 'OLLABRIDGE_CLOUD_URL',
      keyFormat: 'ob_live_… / ob_test_… (Bearer)',
      status: 'available',
      detail: 'Enterprise relay — reach your models from any device with zero port forwarding, plus premium provider routing and federation.',
      pairing: 'Device pairing: enter the TV-style ABCD-1234 code from your Ollabridge Cloud dashboard, or paste an API key.',
    },
  ],
  fields: [
    { label: 'Default model', value: 'llama3.1', hint: 'OLLABRIDGE_MODEL' },
    { label: 'API key', value: '•••••••••••••••• stored in secret store', hint: 'OLLABRIDGE_API_KEY · never logged', secret: true },
    { label: 'Request timeout', value: '60s' },
  ],
}

/** Mail settings — IMAP/SMTP mailbox pairing. Binds to ImapSmtpConfig in
 *  services/orchestrator/email/adapters. Reads use BODY.PEEK; never deletes;
 *  sending stays approval-gated. */
export const MAIL_SETTINGS: { provider: string; status: ConnState; detail: string; fields: ConfigField[] } = {
  provider: 'IMAP / SMTP mailbox',
  status: 'connected',
  detail:
    'Universal IMAP/SMTP mailbox — works with Mailu, generic servers, and Gmail / Microsoft 365 via OAuth tokens as the password. Reads use BODY.PEEK (messages are never implicitly marked read); the adapter never deletes or expunges. The Email Sentinel drafts replies but never sends without approval.',
  fields: [
    { label: 'IMAP host', value: 'imap.mailu.local', hint: 'port 993 · TLS' },
    { label: 'SMTP host', value: 'smtp.mailu.local', hint: 'port 587 · STARTTLS' },
    { label: 'Username', value: 'ruslan@daypilot.local' },
    { label: 'Password / OAuth token', value: '•••••••••••••••• stored in secret store', hint: 'never logged', secret: true },
    { label: 'Send policy', value: 'Approval required', hint: 'server-enforced' },
  ],
}

/** Knowledge sources for RAG over projects. Binds to SourceGrant / SourceRegistry
 *  (DAYPILOT_LOCAL_SOURCES) + the knowledge-service ingest pipeline. Local folders
 *  and Box folders are granted, scoped per project, and read + indexed only. */
export type KnowledgeSource = {
  label: string
  kind: 'Local folder' | 'Box' | 'Vault'
  scope: string
  permission: string
  projects: string
  status: 'indexed' | 'indexing' | 'available'
}

export const KNOWLEDGE_SOURCES: KnowledgeSource[] = [
  { label: 'Project workspace', kind: 'Local folder', scope: '/data/projects', permission: 'Read + index', projects: 'DayPilot Portal · GitPilot Connector', status: 'indexed' },
  { label: 'Contracts', kind: 'Local folder', scope: '/data/contracts', permission: 'Read + index', projects: 'Client Alpha', status: 'indexed' },
  { label: 'Box · Consulting Clients', kind: 'Box', scope: 'box://folder/8821', permission: 'Read + index', projects: 'All projects', status: 'available' },
]

export const SOURCES_SUMMARY = {
  detail:
    'Grant folders or Box locations so the AI can run retrieval-augmented answers over your projects. Sources are read + indexed only by default — DayPilot never writes back. Scope grants with DAYPILOT_LOCAL_SOURCES or connect Box in Integrations.',
  envHint: 'DAYPILOT_LOCAL_SOURCES="/data/projects,/data/contracts"',
}

export type ShortcutRow = { keys: string; action: string }

export const SHORTCUTS: ShortcutRow[] = [
  { keys: '⌘K', action: 'Open command palette' },
  { keys: '⌘1–6', action: 'Jump to Home, Calendar, Tasks, Projects, Documents, Agents' },
  { keys: 'F', action: 'Start Focus Mode' },
  { keys: '⌘,', action: 'Open settings' },
  { keys: 'Esc', action: 'Close menu, palette, or drawer' },
]

export const PERMISSION_DEFAULTS = [
  { label: 'Repository writes & PRs', value: 'Approval required', safe: false },
  { label: 'Email send', value: 'Approval required', safe: false },
  { label: 'Calendar create / move', value: 'Approval required', safe: false },
  { label: 'File generation', value: 'New version only', safe: true },
  { label: 'Document folders', value: 'Read + index only', safe: true },
  { label: 'Persona activation', value: 'Policy review', safe: false },
]
