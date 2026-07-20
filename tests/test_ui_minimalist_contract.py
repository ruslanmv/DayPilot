from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_minimalist_ux_spec_contains_required_ascii_views():
    spec = (ROOT / 'docs' / 'ux-space-bridge-minimalist-portal.md').read_text(encoding='utf-8')
    assert 'Strategic Feed' in spec
    assert 'Day Horizon' in spec
    assert 'Week Horizon' in spec
    assert 'Operational Ledger' in spec
    assert 'Context Telemetry' in spec
    assert '┌' in spec and '└' in spec


def test_react_portal_contains_calendar_and_ledger_state_surfaces():
    ui = ROOT / 'packages' / 'ui-bridge' / 'src'
    source = (ui / 'minimalPortal.tsx').read_text(encoding='utf-8')
    assert 'StrategicFeed' in source
    assert 'PlanBlock' in source
    assert 'CalendarCore' in source
    assert 'OperationalLedger' in source
    assert 'DetailDrawer' in source
    assert 'createHumanTask' in source
    assert 'createAiTask' in source

    # The Minute Plan calendar is a real Day/Week timetable with an Outlook-style
    # live current-time indicator and minute-based event positioning.
    assert 'MinutePlanCalendar' in source
    cal = (ui / 'calendar' / 'MinutePlanCalendar.tsx').read_text(encoding='utf-8')
    assert 'DayView' in cal and 'WeekView' in cal
    assert 'dp-now' in cal and 'Now ' in cal  # current-time indicator (day)
    assert 'dp-wnow' in cal  # current-time indicator (week)
    assert 'is-today' in cal and 'All day' in cal  # today highlight + all-day row
    data = (ui / 'calendar' / 'calendarData.ts').read_text(encoding='utf-8')
    assert 'DAY_START_MIN' in data and 'layoutColumns' in data  # minute geometry + overlap
    assert 'weekDates' in data


def test_sidebar_nav_and_settings_menu_contract():
    ui = ROOT / 'packages' / 'ui-bridge' / 'src'
    portal = (ui / 'minimalPortal.tsx').read_text(encoding='utf-8')
    # First-class views only; the old text stub must be gone. Command is now Home.
    assert 'AccountMenu' in portal
    # No standalone Settings item in the sidebar — Settings is reachable only
    # through the account dropdown (and the command palette / mobile drawer).
    assert 'dp-nav--secondary' not in portal
    assert '>Settings</NavButton>' not in portal
    assert 'CommandPalette' in portal
    assert 'HomeWorkspace' in portal
    assert 'More: Inbox' not in portal
    assert "id: 'command'" not in portal  # renamed to Home
    for view in ('home', 'planning', 'calendar', 'tasks', 'projects', 'documents', 'agents'):
        assert f"id: '{view}'" in portal

    # The Planning tab: multi-agent plan with clickable blocks, replan, and chat.
    planning = (ui / 'planning' / 'PlanningWorkspace.tsx').read_text(encoding='utf-8')
    assert 'Replan' in planning
    assert 'Chat with your plan' in planning or 'Chat with your day plan' in planning
    assert 'dp-plan__popover' in planning  # every block is clickable
    assert 'Start focus' in planning and 'Mark done' in planning

    # Connected Day Planner: state-model-driven (not empty-array), real readiness
    # gate, quality only after a plan, AI assistant shares the plan state.
    board = (ui / 'planning' / 'PlannerBoard.tsx').read_text(encoding='utf-8')
    assert 'PlannerBoard' in planning  # Planning dispatches to it in production
    for state in ('initial_setup_required', 'ready_to_create', 'creating', 'plan_ready'):
        assert state in board
    assert 'loadReadiness' in board and 'Create my plan' in board
    assert 'AI Planning Assistant' in board and 'Why DayPilot scheduled this here' in board
    assert 'We couldn’t update your plan right now' in board  # friendly failure, no backend jargon

    # Smart sync: daily review on open, periodic sync pass, and plan-update
    # notifications with apply / "I'm already on it" discard — never silent.
    assert 'dailyReview' in board and 'syncPlan' in board
    assert 'Suggested plan update' in board
    assert 'Apply update' in board and 'already on it' in board
    pc = (ui / 'plannerClient.ts').read_text(encoding='utf-8')
    assert '/sync' in pc and '/daily-review' in pc
    assert 'discardProposal' in pc and 'applyProposal' in pc

    # API client is content-type-safe: HTML never surfaces as a JSON parse crash.
    ac = (ui / 'apiClient.ts').read_text(encoding='utf-8')
    assert 'gateway_html_response' in ac and 'invalid_json' in ac
    assert 'content-type' in ac.lower()

    # Identity & login (Batch 1): a real logged-out entry — bootstrap + login,
    # cookie sessions (no token in localStorage), identity separate from AI.
    gate = (ui / 'auth' / 'AppGate.tsx').read_text(encoding='utf-8')
    assert 'bootstrap_required' in gate and 'unauthenticated' in gate and 'authenticated' in gate
    login = (ui / 'auth' / 'LoginPage.tsx').read_text(encoding='utf-8')
    # Premium split-screen sign-in with a real first-run bootstrap mode.
    assert 'Welcome back' in login and 'Create your workspace' in login
    assert "mode === 'bootstrap'" in login or "mode==='bootstrap'" in login
    assert 'cloud inference is never activated without your confirmation' in login.lower()
    # Cloud + SSO only render when the backend reports them available.
    assert 'cloudAvailable' in login and 'ssoAvailable' in login
    authc = (ui / 'authClient.ts').read_text(encoding='utf-8')
    assert '/v1/auth/config' in authc and '/v1/auth/local/login' in authc
    assert "credentials: 'include'" in authc and 'X-CSRF-Token' in authc
    assert 'localStorage.setItem' not in authc  # sessions are cookies, never stored

    # Clean product branding only: no "DayPilot Pro" / "Enterprise OS" / Ollabridge
    # environment labels in the main shell.
    assert 'dp-brand__word' in portal and '>DayPilot<' in portal
    assert 'Enterprise OS' not in portal
    assert 'DayPilot Pro' not in portal
    assert 'OLLABRIDGE LIVE' not in portal

    # The single AI conversational input lives in the Home AI panel, not the center.
    home = (ui / 'home' / 'HomeWorkspace.tsx').read_text(encoding='utf-8')
    assert 'AI Assistant' in home
    assert 'Ask anything or give an instruction' in home
    assert 'Next priority' in home and "Today's plan" in home and 'Continue from yesterday' in home
    # The assistant is collapsible and reopenable (ChatGPT / Claude / Gemini style).
    assert 'dp-home--ai-collapsed' in home
    assert 'Open AI' in home and 'Close AI Assistant' in home

    # Phones get a dedicated ChatGPT-style shell (hamburger drawer, single-page
    # views, full-screen AI chat) instead of a squeezed desktop layout.
    assert 'MobilePortal' in portal and 'useIsMobile' in portal
    assert 'dp-m__bar' in portal  # fixed top app bar
    assert 'Recent AI conversations' in portal  # drawer combines nav + AI history
    assert 'Jump to latest' in portal or 'Latest' in portal  # chat scroll affordance

    menu = (ui / 'shell' / 'AccountMenu.tsx').read_text(encoding='utf-8')
    # Compact ChatGPT/Claude-style profile popover with menu semantics and
    # keyboard support: only profile identity, Settings, and Sign out.
    assert 'role="menu"' in menu
    assert 'aria-haspopup="menu"' in menu
    assert 'Escape' in menu and 'ArrowDown' in menu
    assert menu.count('role="menuitem"') == 2
    assert 'Sign out' in menu and 'Settings' in menu
    # It must NOT duplicate the Settings modal's navigation.
    for forbidden in ('Appearance', 'Keyboard shortcuts', 'Integrations', 'AI providers',
                      'Mail settings', 'Knowledge sources', 'Permissions'):
        assert forbidden not in menu

    # Every advanced section lives (only) in the full Settings modal's rail.
    panel = (ui / 'shell' / 'SettingsPanel.tsx').read_text(encoding='utf-8')
    for label in ('Profile & workspace', 'Integrations', 'AI providers', 'Mail settings',
                  'Knowledge sources', 'Appearance', 'Permissions & approvals',
                  'Keyboard shortcuts'):
        assert label in panel

    settings = (ui / 'settings' / 'settingsData.ts').read_text(encoding='utf-8')

    # Ollabridge pairing, IMAP/SMTP mail, and folder/Box RAG sources are all
    # configurable in Settings and bind to real backend config.
    assert 'OLLABRIDGE_PAIRING' in settings and 'OLLABRIDGE_BASE_URL' in settings
    # DayPilot pairs with both the local gateway and Ollabridge Cloud.
    assert 'Local gateway' in settings and 'Ollabridge Cloud' in settings
    assert 'OLLABRIDGE_MODE' in settings and 'ob_live_' in settings
    assert 'MAIL_SETTINGS' in settings and 'IMAP host' in settings and 'SMTP host' in settings
    assert 'KNOWLEDGE_SOURCES' in settings and 'DAYPILOT_LOCAL_SOURCES' in settings
    assert "kind: 'Box'" in settings and "kind: 'Local folder'" in settings

    # The live Integrations page (batch I0): status, capabilities, last activity,
    # Connect/Disconnect.
    integ = (ui / 'integrations' / 'IntegrationsPanel.tsx').read_text(encoding='utf-8')
    assert 'Connect' in integ and 'Disconnect' in integ
    assert 'Last activity' in integ and 'dp-cap-chip' in integ

    # The Email page is production-connected by default: no hard-coded senders,
    # a real onboarding state, safe HTML rendering, and demo gated behind flag.
    email = (ui / 'email' / 'EmailWorkspace.tsx').read_text(encoding='utf-8')
    assert 'ConnectedEmailWorkspace' in email and 'DemoEmailWorkspace' in email
    assert 'isDemoMode()' in email  # demo is opt-in; production connects to the API
    assert 'MailSetupWizard' in email  # onboarding uses the real setup wizard
    assert 'sanitizeEmailHtml' in email  # untrusted email HTML is sanitized
    assert 'emailApi' in email
    # The shared mailbox setup wizard (Batch 3): real probe, honest states, no
    # fabricated connection, and a clear non-destructive guarantee.
    wiz = (ui / 'email' / 'MailSetupWizard.tsx').read_text(encoding='utf-8')
    assert 'Connect your email' in wiz and 'Test connection' in wiz
    assert 'never sends without your approval' in wiz
    assert 'emailApi.test' in wiz and 'emailApi.connect' in wiz
    client_src = (ui / 'email' / 'emailClient.ts').read_text(encoding='utf-8')
    assert '/v1/email/status' in client_src and '/v1/email/messages' in client_src
    assert '/v1/email/test' in client_src and '/v1/email/connect' in client_src
    sani = (ui / 'email' / 'sanitizeEmailHtml.ts').read_text(encoding='utf-8')
    assert 'ALLOWED_TAGS' in sani and 'javascript' in sani and 'allowRemoteImages' in sani

    panel = (ui / 'shell' / 'SettingsPanel.tsx').read_text(encoding='utf-8')
    assert 'IntegrationsPanel' in panel
    assert 'AiProvidersPanel' in panel

    # AI providers → backend-owned (Batch 2): state comes from /v1/providers,
    # local is detected (not assumed), Cloud is authenticated server-side, and
    # no key/token is ever stored client-side.
    aip = (ui / 'settings' / 'AiProvidersPanel.tsx').read_text(encoding='utf-8')
    assert 'providersApi' in aip and 'Sign in with email' in aip
    assert 'Detect again' in aip and 'Not detected' in aip  # local not assumed connected
    assert 'Use Ollabridge Cloud' in aip and 'Use Local Gateway' in aip
    assert 'Sign out of Ollabridge Cloud?' in aip and 'aria-live' in aip
    assert 'localStorage' not in aip  # provider state is server-owned, not stored
    pcl = (ui / 'providersClient.ts').read_text(encoding='utf-8')
    assert '/v1/providers/status' in pcl and '/v1/providers/local/test' in pcl
    assert '/v1/providers/cloud/login' in pcl
    # The panel has an in-panel section nav so phones reach every section.
    assert 'dp-settings-panel__nav' in panel
    for sect in ('mail', 'sources', 'providers'):
        assert f"section === '{sect}'" in panel

    # A minimalist first-run onboarding wizard (identity, mailbox, knowledge
    # source) and a small project-creation wizard exist and are wired in.
    onb = (ui / 'onboarding' / 'OnboardingWizard.tsx').read_text(encoding='utf-8')
    assert 'Connect your mailbox' in onb and 'Add a knowledge source' in onb
    assert 'Skip for now' in onb
    # First-run onboarding requires AI-provider setup before AI is "ready", and
    # really connects the provider (backend localConnect/cloudLogin), not a
    # generic health probe.
    assert 'Connect your AI' in onb and 'Test connection' in onb
    assert 'providersApi.localConnect' in onb and 'setActive' in onb
    assert '/v1/providers/health' not in onb  # no fake "ready" from a health probe
    # Setup completion is an explicit state machine, not a broad boolean, so
    # "Skip for now" can never permanently hide the wizard.
    setup = (ui / 'onboarding' / 'setupState.ts').read_text(encoding='utf-8')
    assert 'not_started' in setup and 'in_progress' in setup and 'completed' in setup
    assert 'dismissSetup' in setup and 'completeSetup' in setup and 'resetSetup' in setup
    assert 'daypilot.onboarded' in setup  # legacy flag migrated, not written on skip

    # Clean-data default: demo/sample content is opt-in behind a flag with a
    # visible badge; the shell no longer imports demo data directly.
    demo = (ui / 'demoData.ts').read_text(encoding='utf-8')
    assert 'VITE_DAYPILOT_DEMO_MODE' in (ui / 'env.ts').read_text(encoding='utf-8')
    assert 'isDemoMode' in demo and 'seedTasks' in demo
    assert 'dp-demo-badge' in portal and 'Demo mode' in portal

    # The assistant is a thin client over the backend orchestrator (Batch 4):
    # the browser sends the message and renders the result; it no longer routes
    # intents or calls planner/integration endpoints itself.
    assistant = (ui / 'assistant.ts').read_text(encoding='utf-8')
    assert 'askAssistant' in assistant and "/v1/assistant/turn" in assistant
    assert 'classifyIntent' not in assistant  # routing moved server-side
    assert 'AssistantTurn' in assistant  # renders the orchestrator's typed result
    chat = (ui / 'chatSessions.ts').read_text(encoding='utf-8')
    assert '/v1/chat/sessions' in chat and 'appendMessage' in chat
    assert 'Conversation history' in home or 'New conversation' in home
    pw = (ui / 'projects' / 'ProjectWizard.tsx').read_text(encoding='utf-8')
    assert 'New project' in pw and 'First milestone' in pw
    assert 'OnboardingWizard' in portal and 'ProjectWizard' in portal
    assert "label: 'New project'" in portal  # command palette action


def test_standalone_demo_is_available_without_build_tooling():
    demo = ROOT / 'examples' / 'ui' / 'daypilot-premium-minimalist-portal.html'
    text = demo.read_text(encoding='utf-8')
    assert '<title>DayPilot Premium Minimalist Portal</title>' in text
    assert 'Calendar Core' in text
    assert 'Task Ledger' in text
