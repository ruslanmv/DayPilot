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


def test_skipped_onboarding_is_resumable_from_home() -> None:
    """Best practice: the AI-provider step is skippable, so a resume path must
    exist — a Home banner reopens the wizard without wiping progress."""
    setup = (UI / "onboarding" / "setupState.ts").read_text(encoding="utf-8")
    assert "openSetupWizard" in setup and "setup-open" in setup
    home = (UI / "home" / "HomeWorkspace.tsx").read_text(encoding="utf-8")
    assert "Finish setting up DayPilot" in home and "openSetupWizard" in home
    assert "Continue setup" in home
