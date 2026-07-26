"""Contract tests for the setup + assistant-health fixes.

These lock in the fixes for the two visible failures:
  * `make run` must pass the *resolved* API port to the Vite proxy, so the
    frontend never posts to a stale 8080 and gets HTTP 404.
  * The assistant composer must be gated on a backend health check (down /
    limited / ready), never letting a user send into an unreachable backend.
  * First-run setup completion is an explicit state machine, so "Skip for now"
    cannot permanently hide the wizard.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
UI = REPO / "packages" / "ui-bridge" / "src"


def test_make_run_passes_resolved_port_to_vite() -> None:
    mk = (REPO / "Makefile").read_text(encoding="utf-8")
    run_block = mk.split("run:", 1)[1].split("\nrun-api:", 1)[0]
    # The single run target resolves a free port and hands it to both processes.
    assert "find_free_port.py" in run_block
    assert 'DAYPILOT_API_TARGET="http://localhost:$$port"' in run_block
    assert "uvicorn app.main:app" in run_block and "operator-web dev" in run_block


def test_vite_proxy_reads_api_target_env() -> None:
    vite = (REPO / "apps" / "operator-web" / "vite.config.ts").read_text(encoding="utf-8")
    assert "DAYPILOT_API_TARGET" in vite and "'/api'" in vite


def test_make_run_applies_migrations_before_starting() -> None:
    mk = (REPO / "Makefile").read_text(encoding="utf-8")
    run_block = mk.split("run:", 1)[1].split("\nrun-api:", 1)[0]
    assert "alembic upgrade head" in run_block  # no more "no such table" on first run


def test_make_has_setup_and_start_targets() -> None:
    mk = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "\nsetup:" in mk and "install migrate" in mk  # one-command setup
    start_block = mk.split("\nstart:", 1)[1].split("\n\n", 1)[0]
    assert "operator-web build" in start_block and "uvicorn app.main:app" in start_block


def test_assistant_composer_is_health_gated() -> None:
    avail = (UI / "assistantAvailability.ts").read_text(encoding="utf-8")
    assert "'/health'" in avail and "/v1/providers/status" in avail
    for state in ("down", "limited", "ready", "checking"):
        assert state in avail
    home = (UI / "home" / "HomeWorkspace.tsx").read_text(encoding="utf-8")
    assert "useAssistantAvailability" in home
    assert "DayPilot service is unavailable" in home  # down state blocks the composer
    assert "Limited mode" in home  # provider-less limited state is surfaced
    # Sending is guarded so a message never reaches an unreachable backend.
    assert "availability === 'down'" in home


def test_setup_state_is_explicit_not_a_broad_boolean() -> None:
    setup = (UI / "onboarding" / "setupState.ts").read_text(encoding="utf-8")
    assert "not_started" in setup and "in_progress" in setup and "completed" in setup
    # Skip records in_progress (+ dismissedAt); only completeSetup completes.
    assert "dismissSetup" in setup and "completeSetup" in setup and "resetSetup" in setup
    onb = (UI / "onboarding" / "OnboardingWizard.tsx").read_text(encoding="utf-8")
    assert "dismissSetup" in onb and "completeSetup" in onb
    # The wizard no longer writes the legacy completed-boolean on skip.
    assert "localStorage.setItem(STORAGE_KEY, 'true')" not in onb


def test_settings_profile_can_restart_setup() -> None:
    panel = (UI / "shell" / "SettingsPanel.tsx").read_text(encoding="utf-8")
    assert "resetSetup" in panel and "Restart setup" in panel


def test_sign_out_really_leaves_the_workspace() -> None:
    """Issue 6: after logout the gate lands on the login page directly instead
    of re-resolving into anonymous mode, failures are surfaced, user caches are
    cleared, and mobile has a real Sign out action."""
    gate = (UI / "auth" / "AppGate.tsx").read_text(encoding="utf-8")
    assert "kind: 'unauthenticated'" in gate and "clearUserCaches" in gate
    assert "Sign out failed" in gate  # logout failure is never silent success
    # signOut no longer just resolve()s back into the app.
    sign_out_block = gate.split("async function signOut", 1)[1].split("}", 3)[0]
    assert "resolve()" not in sign_out_block
    portal = (UI / "minimalPortal.tsx").read_text(encoding="utf-8")
    assert "MobilePortal emailEnabled={emailEnabled} user={user} onSignOut={onSignOut}" in portal
    assert "dp-m__navitem--signout" in portal  # mobile drawer Sign out
    env = (REPO / ".env.example").read_text(encoding="utf-8")
    assert "DAYPILOT_REQUIRE_SESSION" in env and "DAYPILOT_COOKIE_SECURE" in env


def test_cloud_web_login_button_is_wired() -> None:
    """AI-setup fix: cloud sign-in offers a real web login page (Google/SSO,
    password reset, create account), and the client carries the deep links +
    a dedicated cloud error helper."""
    client = (UI / "providersClient.ts").read_text(encoding="utf-8")
    assert "cloudLoginUrl" in client and "cloudRegisterUrl" in client
    assert "cloudErrorText" in client and "CLOUD_WEB_LOGIN_URL" in client
    # A reachable-but-key-gated local gateway has its own actionable message.
    assert "key_required" in client
    panel = (UI / "settings" / "AiProvidersPanel.tsx").read_text(encoding="utf-8")
    assert "Log in on the web" in panel and "Create an account" in panel
    onb = (UI / "onboarding" / "OnboardingWizard.tsx").read_text(encoding="utf-8")
    assert "cloudLoginUrl" in onb and "Create an account" in onb
    # The wizard reports cloud failures with cloud-specific text, not local text.
    assert "cloudErrorText(res.ok ? res.data.code : res.error)" in onb


def test_agents_directory_grid_replaces_run_table() -> None:
    """Batch A2: a four-column staff directory (not the old run table). Cards are
    keyboard-openable and open a SEPARATE page — never an inline chat/drawer."""
    landing = (UI / 'agents' / 'AgentsLandingPage.tsx').read_text(encoding='utf-8')
    assert 'Choose an agent to open their workspace' in landing
    assert 'runtime_off' in landing and 'Build your AI staff' in landing  # states
    assert "role=\"status\"" in landing and 'aria-live="polite"' in landing  # live region
    card = (UI / 'agents' / 'AgentCard.tsx').read_text(encoding='utf-8')
    assert "role=\"button\"" in card and 'tabIndex={0}' in card
    assert "e.key === 'Enter'" in card and "e.key === ' '" in card  # keyboard-openable
    assert 'onToggleFavorite' in card
    hook = (UI / 'agents' / 'useAgents.ts').read_text(encoding='utf-8')
    assert 'listProfiles' in hook and 'favorites' in hook  # reads profiles, filter set
    css = (UI / 'agents' / 'agents.css').read_text(encoding='utf-8')
    assert 'repeat(4, 1fr)' in css  # never more than four per row
    portal = (UI / 'minimalPortal.tsx').read_text(encoding='utf-8')
    assert 'AgentsLandingPage' in portal and 'AgentsCore' not in portal  # replaced
    # The agents view renders the directory, not a drawer-opening run table.
    assert "view === 'agents' &&" in portal and '<AgentsLandingPage' in portal


def test_shell_uses_hash_routing_with_agent_deeplinks() -> None:
    """Batch A3: the shell has real, deep-linkable routes. The old `PortalView`
    enum with no URL is replaced by a hash router (`#/agents/:agentId`) shared by
    desktop and mobile, with working browser back / forward and a route-controlled
    open agent (so a refresh keeps you on the agent's page)."""
    route = (UI / 'shell' / 'route.ts').read_text(encoding='utf-8')
    assert 'export function parseHash' in route and 'export function routeToHash' in route
    assert 'export function useRoute' in route
    assert 'hashchange' in route and 'popstate' in route  # browser back / forward
    assert "'#/agents/'" in route or '#/agents/' in route  # agent deep link
    assert 'replaceState' in route  # replace option (no history spam)
    portal = (UI / 'minimalPortal.tsx').read_text(encoding='utf-8')
    # Both shells drive `view` from the router, not from local useState.
    assert "const { route, navigate } = useRoute()" in portal
    assert 'const view = route.view' in portal
    assert "const [view, setView] = useState<PortalView>('home')" not in portal
    # The open agent is carried in the URL, not component state.
    assert 'openAgentId={route.agentId}' in portal
    assert "onOpenAgent={(id) => navigate('agents', { agentId: id })}" in portal
    landing = (UI / 'agents' / 'AgentsLandingPage.tsx').read_text(encoding='utf-8')
    assert 'openAgentId' in landing and 'onOpenAgent' in landing  # route-controlled
    # The OPEN AGENT is route-controlled, not local state.
    assert 'useState<string | null>(null)' not in landing
    assert 'const openId = openAgentId' in landing


def test_agent_workspace_is_a_dedicated_page_with_panels() -> None:
    """Batch A4: /agents/:id is a full page (not a drawer) — header (breadcrumb,
    portrait, status, capability chips), always-on trust card, read-only
    conversation + a three-column task panel (Active/Waiting/Completed with % and
    owner), and Activity/Files/Rules tabs. The A2 placeholder is gone."""
    WS = UI / 'agents' / 'workspace'
    for f in ('AgentWorkspace', 'AgentWorkspaceHeader', 'AgentChatPanel', 'AgentTaskPanel',
              'AgentTrustCard', 'AgentActivityPanel', 'AgentRulesPanel', 'AgentFilesPanel'):
        assert (WS / f'{f}.tsx').exists(), f'missing {f}.tsx'
    ws = (WS / 'AgentWorkspace.tsx').read_text(encoding='utf-8')
    assert 'role="tablist"' in ws and 'role="tabpanel"' in ws  # a11y tabs
    assert "'activity'" in ws and "'files'" in ws and "'rules'" in ws  # three tabs
    tasks = (WS / 'AgentTaskPanel.tsx').read_text(encoding='utf-8')
    assert 'role="progressbar"' in tasks  # Overview completion is a real progressbar
    assert 'Active tasks' in tasks and 'Waiting for approval' in tasks  # the task rail sections
    types = (WS / 'types.ts').read_text(encoding='utf-8')
    assert "'active'" in types and "'waiting'" in types and "'completed'" in types
    trust = (WS / 'AgentTrustCard.tsx').read_text(encoding='utf-8')
    assert 'DayPilot drafts, you approve' in trust
    # The workspace is wired into the directory, replacing the A2 placeholder.
    landing = (UI / 'agents' / 'AgentsLandingPage.tsx').read_text(encoding='utf-8')
    assert 'AgentWorkspace' in landing and 'AgentWorkspacePlaceholder' not in landing


def test_chat_session_has_agent_workspace_fields() -> None:
    """Batch A4: ChatSession gains kind / agent_link_id / remote_session_id /
    remote_conversation_id (additive) so an agent's dedicated conversation can be
    persisted and later resumed against HomePilot's own conversation."""
    models = (REPO / 'services' / 'knowledge-service' / 'daypilot_knowledge' / 'db' / 'models.py').read_text(encoding='utf-8')
    for col in ('kind', 'agent_link_id', 'remote_session_id', 'remote_conversation_id'):
        assert col in models, f'ChatSession missing {col}'
    mig = (REPO / 'alembic' / 'versions' / '0014_chat_session_agent_kind.py').read_text(encoding='utf-8')
    assert 'down_revision = "0013_homepilot_agent_links"' in mig
    for col in ('kind', 'agent_link_id', 'remote_session_id', 'remote_conversation_id'):
        assert f'"{col}"' in mig
    assert 'server_default="assistant"' in mig  # existing rows are the shared assistant


def test_agent_chat_is_live_and_propose_only() -> None:
    """Batch A6: the agent workspace conversation is live — it loads the
    persisted session and sends turns through DayPilot's own endpoints (never
    HomePilot directly), announces replies via aria-live, marks proposals, and
    degrades to a read-only notice when chat is unavailable (404)."""
    client = (UI / 'settings' / 'homepilotClient.ts').read_text(encoding='utf-8')
    assert 'getAgentSession' in client and 'sendTurn' in client
    assert '/session' in client and '/turn' in client
    panel = (UI / 'agents' / 'workspace' / 'AgentChatPanel.tsx').read_text(encoding='utf-8')
    assert 'homepilotApi.getAgentSession' in panel and 'homepilotApi.sendTurn' in panel
    assert 'aria-live="polite"' in panel  # replies announced
    assert "status === 404" in panel and 'unavailable' in panel  # graceful degrade
    assert 'Proposal' in panel  # propose-only work is surfaced, never auto-run
    # The workspace hands the live panel the agent, not a static message list.
    ws = (UI / 'agents' / 'workspace' / 'AgentWorkspace.tsx').read_text(encoding='utf-8')
    assert '<AgentChatPanel agent={agent}' in ws


def test_agent_directive_mapping_schema_and_safety() -> None:
    """Batch A7: Task/AgentRun carry the agent-work fields and migration 0015
    adds them; the mapper's safety invariants are stated in code — a proposal is
    a waiting_for_approval task + pending approval, and a draft is never
    completed."""
    models = (REPO / 'services' / 'knowledge-service' / 'daypilot_knowledge' / 'db' / 'models.py').read_text(encoding='utf-8')
    for col in ('assigned_agent_link_id', 'manager_agent_link_id', 'created_by_agent_link_id',
                'parent_task_id', 'progress_percent', 'remote_reference', 'approval_id'):
        assert col in models, f'Task missing {col}'
    assert 'agent_link_id' in models  # AgentRun too
    mig = (REPO / 'alembic' / 'versions' / '0015_agent_task_mapping.py').read_text(encoding='utf-8')
    assert 'down_revision = "0014_chat_session_agent_kind"' in mig
    for col in ('progress_percent', 'remote_reference', 'approval_id'):
        assert f'"{col}"' in mig
    ORCH = REPO / 'services' / 'orchestrator' / 'daypilot_orchestrator' / 'homepilot'
    directives = (ORCH / 'directives.py').read_text(encoding='utf-8')
    assert 'ALLOWED_DIRECTIVES' in directives and 'CAPABILITIES' in directives
    assert 'MAX_DIRECTIVES_PER_TURN' in directives  # count cap enforced
    mapper = (ORCH / 'task_mapper.py').read_text(encoding='utf-8')
    assert 'waiting_for_approval' in mapper and 'Approval(' in mapper
    assert '_is_draft' in mapper  # a draft is never completed


def test_agent_approval_lifecycle_surfaced_in_workspace() -> None:
    """Batch A8: an approved agent proposal executes via DayPilot's Approval
    Center hook, and the proposal's lifecycle (Awaiting → Executing → Completed /
    Rejected / Failed) is surfaced in the workspace task panel."""
    ORCH = REPO / 'services' / 'orchestrator' / 'daypilot_orchestrator' / 'homepilot'
    actions = (ORCH / 'action_mapping.py').read_text(encoding='utf-8')
    for state in ('AWAITING', 'EXECUTING', 'COMPLETED', 'REJECTED', 'FAILED'):
        assert state in actions
    assert 'def execute_approved' in actions and 'def register_executor' in actions
    approvals = (REPO / 'services' / 'api-gateway' / 'app' / 'routers' / 'approvals.py').read_text(encoding='utf-8')
    assert 'on_approval_decided' in approvals  # reuse the B11 Approval Center
    client = (UI / 'settings' / 'homepilotClient.ts').read_text(encoding='utf-8')
    assert 'getAgentTasks' in client and 'agentLifecycleLabel' in client
    panel = (UI / 'agents' / 'workspace' / 'AgentTaskPanel.tsx').read_text(encoding='utf-8')
    assert 'homepilotApi.getAgentTasks' in panel and 'agentLifecycleLabel' in panel
    assert 'Waiting for approval' in panel and 'dp-tr__state' in panel  # lifecycle surfaced in the rail


def test_homepilot_connections_are_account_scoped() -> None:
    """Security: each connection is bound to a HomePilot account, agents are
    stamped with it, and the panel shows which account (local vs cloud) so one
    user's agents never blend with another's."""
    models = (REPO / 'services' / 'knowledge-service' / 'daypilot_knowledge' / 'db' / 'models.py').read_text(encoding='utf-8')
    assert 'account_ref' in models  # HomePilotAgentLink carries the account
    mig = (REPO / 'alembic' / 'versions' / '0016_agent_account_ref.py').read_text(encoding='utf-8')
    assert 'account_ref' in mig and 'down_revision = "0015_agent_task_mapping"' in mig
    platform = (REPO / 'services' / 'api-gateway' / 'app' / 'homepilot_platform.py').read_text(encoding='utf-8')
    assert 'def _resolve_account' in platform and 'def _remote_kind' in platform
    assert 'account_mismatch' in platform  # chat refuses a foreign-account agent
    sync = (REPO / 'services' / 'orchestrator' / 'daypilot_orchestrator' / 'homepilot' / 'sync.py').read_text(encoding='utf-8')
    assert 'account_ref' in sync and 'wrong_account' in sync  # re-scope on account change
    client = (UI / 'settings' / 'homepilotClient.ts').read_text(encoding='utf-8')
    assert 'accountLabel' in client and 'remoteKind' in client
    panel = (UI / 'settings' / 'HomePilotConnectionPanel.tsx').read_text(encoding='utf-8')
    assert 'accountLabel' in panel and 'Cloud HomePilot' in panel


def test_agent_delegation_chain_and_limits() -> None:
    """Batch A9: manager→worker delegation with a governed chain (You → Scarlett →
    Atlas) and hard safety limits, surfaced in the workspace behind the
    DELEGATION flag."""
    ORCH = REPO / 'services' / 'orchestrator' / 'daypilot_orchestrator' / 'homepilot'
    deleg = (ORCH / 'delegation.py').read_text(encoding='utf-8')
    for guard in ('max_depth', 'max_workers', 'max_child_tasks', 'exceeds_manager', 'no_worker'):
        assert guard in deleg
    assert 'responsibility_chain' in deleg and 'MAX_DELEGATION_DEPTH' in deleg
    assert (ORCH / 'capability_matcher.py').exists()
    mig = (REPO / 'alembic' / 'versions' / '0017_agent_delegations.py').read_text(encoding='utf-8')
    assert 'agent_delegations' in mig and 'down_revision = "0016_agent_account_ref"' in mig
    mapper = (ORCH / 'task_mapper.py').read_text(encoding='utf-8')
    assert '_handle_delegation' in mapper and 'hp_delegation.enabled()' in mapper  # gated
    ev = (UI / 'agents' / 'workspace' / 'DelegationEvent.tsx').read_text(encoding='utf-8')
    assert 'dp-deleg__chain' in ev and 'getAgentDelegations' in ev
    ws = (UI / 'agents' / 'workspace' / 'AgentWorkspace.tsx').read_text(encoding='utf-8')
    assert "'delegations'" in ws and 'DelegationPanel' in ws


def test_add_agent_flow_points_to_homepilot() -> None:
    """Batch A10: 'Add agent' opens a HomePilot-centric flow (Open Gallery /
    Refresh / Manage connection) — it does not import into DayPilot. The local
    .hpersona importer exists only as an offline fallback behind IMPORTS."""
    ORCH = REPO / 'services' / 'orchestrator' / 'daypilot_orchestrator' / 'homepilot'
    hp = (ORCH / 'hpersona.py').read_text(encoding='utf-8')
    assert 'def inspect' in hp and 'def import_local' in hp
    assert 'zipfile' in hp and 'manifest.json' in hp  # reads the .hpersona package
    platform = (REPO / 'services' / 'api-gateway' / 'app' / 'homepilot_platform.py').read_text(encoding='utf-8')
    assert 'def add_info' in platform and 'def _gallery_url' in platform and 'def imports_enabled' in platform
    router = (REPO / 'services' / 'api-gateway' / 'app' / 'routers' / 'homepilot.py').read_text(encoding='utf-8')
    assert '/v1/homepilot/add-info' in router and '/v1/homepilot/hpersona/preview' in router
    assert 'def _require_imports' in router  # importer is gated
    panel = (UI / 'agents' / 'AddAgentPanel.tsx').read_text(encoding='utf-8')
    for action in ('Open HomePilot Gallery', 'Refresh from HomePilot', 'Manage connection'):
        assert action in panel
    assert 'Browse HomePilot Gallery' in panel and 'Import .hpersona file' in panel  # method picker
    assert 'DependencyCheck' in panel and 'hpersonaImport' in panel
    assert 'importsEnabled' in panel  # .hpersona/URL methods gated to the offline fallback
    landing = (UI / 'agents' / 'AgentsLandingPage.tsx').read_text(encoding='utf-8')
    assert "open('add')" in landing and 'AddAgentPanel' in landing


def test_session_continuity_and_failure_matrix() -> None:
    """Batch A11: durable session continuity (stable remote_session_id, captured
    + reused conversation id), a connect-time capability probe (bridge vs legacy
    chat-only), and honest degradation (offline serves local history; timeout
    retains + Retry)."""
    platform = (REPO / 'services' / 'api-gateway' / 'app' / 'homepilot_platform.py').read_text(encoding='utf-8')
    assert 'def _store_chat_mode' in platform and 'chat_mode' in platform  # capability probe
    assert 'remote_conversation_id' in platform  # conversation id captured + reused
    assert '"code": "timeout"' in platform and '"degraded"' in platform    # failure matrix
    router = (REPO / 'services' / 'api-gateway' / 'app' / 'routers' / 'homepilot.py').read_text(encoding='utf-8')
    assert 'homepilot_timeout' in router and 'status_code=504' in router
    panel = (UI / 'agents' / 'workspace' / 'AgentChatPanel.tsx').read_text(encoding='utf-8')
    assert 'retrySend' in panel and 'degraded' in panel and "mode === 'chat_only'" in panel
    assert (REPO / 'docs' / 'homepilot-failure-matrix.md').exists()


def test_a12_hardening_guardrails_observability_mobile_docs() -> None:
    """Batch A12: AI guardrails (strip leaked tool/directive machinery; no
    premature complete), bridge-turn observability, mobile task-rail collapse,
    and the rollout runbook."""
    ORCH = REPO / 'services' / 'orchestrator' / 'daypilot_orchestrator' / 'homepilot'
    guard = (ORCH / 'guardrails.py').read_text(encoding='utf-8')
    assert 'def sanitize_reply' in guard and 'DAYPILOT_DIRECTIVES' in guard
    platform = (REPO / 'services' / 'api-gateway' / 'app' / 'homepilot_platform.py').read_text(encoding='utf-8')
    assert 'guardrails.sanitize_reply' in platform  # applied to visible replies
    assert 'homepilot.bridge.turn' in platform      # observability audit
    css = (UI / 'agents' / 'agents.css').read_text(encoding='utf-8')
    assert '.dp-taskrail { order: 1; }' in css       # rail collapses under chat on mobile
    assert (REPO / 'docs' / 'homepilot-rollout-runbook.md').exists()
    assert (REPO / 'docs' / 'homepilot-failure-matrix.md').exists()


def test_homepilot_connection_panel_wired() -> None:
    """Batch A1: a Settings → HomePilot agents panel connects to a side-by-side
    HomePilot, syncs persona references, and enables agents — the browser only
    ever calls DayPilot's own endpoints, and the runtime-off state is handled."""
    client = (UI / 'settings' / 'homepilotClient.ts').read_text(encoding='utf-8')
    assert '/v1/homepilot/connections' in client and '/v1/agents/profiles' in client
    panel = (UI / 'settings' / 'HomePilotConnectionPanel.tsx').read_text(encoding='utf-8')
    assert 'Refresh agents' in panel and 'runtime_off' in panel
    assert 'without copying their identity' in panel  # the contract promise, surfaced
    sp = (UI / 'shell' / 'SettingsPanel.tsx').read_text(encoding='utf-8')
    assert 'HomePilotConnectionPanel' in sp and "'homepilot'" in sp


def test_planner_readiness_buttons_are_wired() -> None:
    """The 'preparing your first plan' screen must be actionable: each checklist
    row navigates, and the previously-dead 'Connect a source' state offers a real
    Add-your-first-task (POST /v1/tasks) plus connect-email / new-project."""
    board = (UI / 'planning' / 'PlannerBoard.tsx').read_text(encoding='utf-8')
    assert 'onNavigate' in board and 'onAddTask' in board
    assert 'createQuickTask' in board  # inline add-task really creates work
    assert 'dp-pl__ready-action' in board  # every checklist row has an action
    assert 'Add your first task to continue' in board  # dead disabled CTA replaced
    assert "onNavigate('email')" in board and "onNavigate('new-project')" in board
    # recheck re-reads readiness so sufficient flips without a full reload.
    assert 'recheck' in board and 'loadReadiness' in board
    planner_client = (UI / 'plannerClient.ts').read_text(encoding='utf-8')
    assert 'createQuickTask' in planner_client and "'/v1/tasks'" in planner_client
    # The shell maps planner nav targets to real navigation.
    portal = (UI / 'minimalPortal.tsx').read_text(encoding='utf-8')
    assert 'onNavigate={(t) =>' in portal and "setProjectWizardOpen(true)" in portal
    ws = (UI / 'planning' / 'PlanningWorkspace.tsx').read_text(encoding='utf-8')
    assert 'onNavigate' in ws  # threaded through the workspace wrapper


def test_assistant_resyncs_after_provider_connect() -> None:
    """After a provider is connected/activated, the assistant must leave
    'Limited mode' without a reload: provider mutations broadcast a change event
    and the availability hook re-checks on it (and on tab refocus)."""
    client = (UI / "providersClient.ts").read_text(encoding="utf-8")
    assert "PROVIDERS_CHANGED_EVENT" in client and "notifyProvidersChanged" in client
    # The connecting/activating mutations emit the event.
    for fn in ("localConnect", "cloudLogin", "setActive"):
        assert fn in client
    avail = (UI / "assistantAvailability.ts").read_text(encoding="utf-8")
    assert "PROVIDERS_CHANGED_EVENT" in avail
    assert "addEventListener(PROVIDERS_CHANGED_EVENT" in avail
    assert "visibilitychange" in avail


def test_knowledge_source_browse_and_box_are_additive() -> None:
    """Additive knowledge-source pickers: a native folder Browse and a Box
    'Connect' that opens OAuth — with the manual text input preserved as the
    default/fallback (non-destructive)."""
    helper = (UI / "settings" / "workspaceFolder.ts").read_text(encoding="utf-8")
    for fn in ("supportsDirectoryPicker", "slugifyProjectFolder", "suggestProjectPath", "pickWorkspaceFolder"):
        assert fn in helper
    assert "showDirectoryPicker" in helper  # native OS dialog (choose or create)
    onb = (UI / "onboarding" / "OnboardingWizard.tsx").read_text(encoding="utf-8")
    assert "browseFolder" in onb and "Browse…" in onb
    assert "connectBox" in onb and "Connect Box" in onb
    assert "window.open(r.data.authUrl" in onb  # Box opens the web sign-in
    # The manual path/box input is still present (fallback + default preserved).
    assert "set({ source: e.target.value })" in onb
    panel = (UI / "settings" / "KnowledgeSourcesPanel.tsx").read_text(encoding="utf-8")
    assert "browseFolder" in panel and "pickWorkspaceFolder" in panel
    assert "window.open(r.data.authUrl" in panel
    client = (UI / "settings" / "knowledgeSourcesClient.ts").read_text(encoding="utf-8")
    assert "authUrl" in client  # client surfaces the Box authorize URL


def test_skipped_onboarding_is_resumable_from_home() -> None:
    """Best practice: the AI-provider step is skippable, so a resume path must
    exist — a Home banner reopens the wizard without wiping progress."""
    setup = (UI / "onboarding" / "setupState.ts").read_text(encoding="utf-8")
    assert "openSetupWizard" in setup and "setup-open" in setup
    home = (UI / "home" / "HomeWorkspace.tsx").read_text(encoding="utf-8")
    assert "Finish setting up DayPilot" in home and "openSetupWizard" in home
    assert "Continue setup" in home
