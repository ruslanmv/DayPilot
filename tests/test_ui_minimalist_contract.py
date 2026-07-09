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
    assert 'StrategyBlocks' in source
    assert 'CalendarCore' in source
    assert 'OperationalLedger' in source
    assert 'DetailDrawer' in source
    assert 'createCommanderTask' in source
    assert 'createAgentFollowup' in source


def test_standalone_demo_is_available_without_build_tooling():
    demo = ROOT / 'examples' / 'ui' / 'daypilot-premium-minimalist-portal.html'
    text = demo.read_text(encoding='utf-8')
    assert '<title>DayPilot Premium Minimalist Portal</title>' in text
    assert 'Calendar Core' in text
    assert 'Task Ledger' in text
