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
    source = (ROOT / 'packages' / 'ui-bridge' / 'src' / 'minimalPortal.tsx').read_text(encoding='utf-8')
    assert 'StrategicFeed' in source
    assert 'PlanBlock' in source
    assert 'CalendarCore' in source
    assert 'OperationalLedger' in source
    assert 'DetailDrawer' in source
    assert 'createHumanTask' in source
    assert 'createAiTask' in source


def test_sidebar_nav_and_settings_menu_contract():
    ui = ROOT / 'packages' / 'ui-bridge' / 'src'
    portal = (ui / 'minimalPortal.tsx').read_text(encoding='utf-8')
    # First-class views only; the old text stub must be gone. Command is now Home.
    assert 'SettingsMenu' in portal
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

    menu = (ui / 'shell' / 'SettingsMenu.tsx').read_text(encoding='utf-8')
    # ChatGPT-style drop-up with menu semantics and keyboard support.
    assert 'role="menu"' in menu
    assert 'aria-haspopup="menu"' in menu
    assert 'Escape' in menu and 'ArrowDown' in menu

    settings = (ui / 'settings' / 'settingsData.ts').read_text(encoding='utf-8')
    for label in ('Profile & workspace', 'Integrations', 'AI providers', 'Mail settings',
                  'Knowledge sources', 'Appearance', 'Permissions & approvals',
                  'Keyboard shortcuts', 'Sign out'):
        assert label in settings

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

    panel = (ui / 'shell' / 'SettingsPanel.tsx').read_text(encoding='utf-8')
    assert 'IntegrationsPanel' in panel
    # The panel has an in-panel section nav so phones reach every section.
    assert 'dp-settings-panel__nav' in panel
    for sect in ('mail', 'sources', 'providers'):
        assert f"section === '{sect}'" in panel

    # A minimalist first-run onboarding wizard (identity, mailbox, knowledge
    # source) and a small project-creation wizard exist and are wired in.
    onb = (ui / 'onboarding' / 'OnboardingWizard.tsx').read_text(encoding='utf-8')
    assert 'Connect your mailbox' in onb and 'Add a knowledge source' in onb
    assert 'Skip for now' in onb and 'daypilot.onboarded' in onb
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
