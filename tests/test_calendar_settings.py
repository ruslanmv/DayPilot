"""Calendar connections, behaviour, and the meeting-context allow-list.

Two of these are policy rather than preference, and both are enforced here
rather than in the browser: the set of sources a meeting brief may read, and
what a calendar entry marked private contributes. The rest of this file covers
the three claims the planner used to make without having earned them.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from daypilot_knowledge.db import (
    CalendarEvent,
    IntegrationConnection,
    create_engine_from_settings,
    session_scope,
)
from daypilot_orchestrator.calendar import connections, settings
from daypilot_orchestrator.calendar.service import conflicts_on
from daypilot_orchestrator.planner.service import _quality_explanation, planner_readiness

client = TestClient(app)
ENGINE = create_engine_from_settings()
WS = "ws_calendar_settings"


@pytest.fixture()
def ws():
    """A workspace of its own, cleaned before each test."""
    with session_scope(ENGINE) as s:
        for row in s.query(IntegrationConnection).filter_by(workspace_id=WS).all():
            s.delete(row)
        for row in s.query(CalendarEvent).filter_by(workspace_id=WS).all():
            s.delete(row)
    return WS


def _connect(session, provider: str, *, account: str = "ruslan@example.com",
             last_sync: datetime | None = None, status: str = "connected") -> str:
    row = IntegrationConnection(
        workspace_id=WS, provider=provider, status=status, auth_type="oauth",
        capabilities=["events.read"], detail=account,
        last_activity_at=last_sync,
    )
    session.add(row)
    session.flush()
    return row.id


# --- the meeting-context allow-list ------------------------------------------

def test_defaults_grant_only_daypilot_s_own_context(ws):
    with session_scope(ENGINE) as s:
        row = settings.get_settings(s, ws)
        assert set(row.context_sources) == {"event", "projects", "tasks", "documents"}
        # Nothing external is granted by simply connecting a calendar.
        assert "slack" not in row.context_sources
        assert "email" not in row.context_sources


def test_private_events_default_to_metadata_only(ws):
    with session_scope(ENGINE) as s:
        assert settings.get_settings(s, ws).private_events == "metadata_only"


def test_an_unknown_source_is_dropped_rather_than_stored(ws):
    # The list is consulted as an allow-list. A typo that persisted would be a
    # permission nobody could look up.
    with session_scope(ENGINE) as s:
        row = settings.update_settings(s, ws, {"contextSources": ["slack", "wikipedia", "tasks"]})
        assert set(row.context_sources) == {"event", "slack", "tasks"}


def test_the_event_itself_cannot_be_switched_off(ws):
    # A brief about a meeting that may not read the meeting is nonsense.
    with session_scope(ENGINE) as s:
        row = settings.update_settings(s, ws, {"contextSources": []})
        assert row.context_sources == ["event"]


def test_a_granted_source_whose_integration_is_gone_is_not_usable(ws):
    with session_scope(ENGINE) as s:
        settings.update_settings(s, ws, {"contextSources": ["tasks", "slack"]})
        # Intent says Slack; reality says Slack is not connected.
        allowed = settings.allowed_context_sources(s, ws, connected_providers=set())
        assert "slack" not in allowed
        assert set(allowed) == {"event", "tasks"}
        with_slack = settings.allowed_context_sources(s, ws, connected_providers={"slack"})
        assert "slack" in with_slack


def test_an_invalid_privacy_mode_is_refused(ws):
    with session_scope(ENGINE) as s:
        with pytest.raises(settings.InvalidSetting):
            settings.update_settings(s, ws, {"privateEvents": "everything"})


def test_an_invalid_prepare_scope_is_refused(ws):
    with session_scope(ENGINE) as s:
        with pytest.raises(settings.InvalidSetting):
            settings.update_settings(s, ws, {"prepareScope": "sometimes"})


def test_buffers_and_prep_time_are_clamped_not_trusted(ws):
    with session_scope(ENGINE) as s:
        row = settings.update_settings(s, ws, {
            "bufferBeforeMinutes": 9999, "bufferAfterMinutes": -5, "prepMinutes": 600,
        })
        assert row.buffer_before_minutes == settings.MAX_BUFFER_MINUTES
        assert row.buffer_after_minutes == 0
        assert row.prep_minutes == settings.MAX_PREP_MINUTES


def test_a_partial_update_leaves_everything_else_alone(ws):
    with session_scope(ENGINE) as s:
        settings.update_settings(s, ws, {"prepareScope": "every", "ignoreDeclined": False})
        row = settings.update_settings(s, ws, {"prepMinutes": 30})
        assert row.prepare_scope == "every"
        assert row.ignore_declined is False
        assert row.prep_minutes == 30


# --- connection status --------------------------------------------------------

def test_no_connection_means_not_connected(ws):
    with session_scope(ENGINE) as s:
        st = connections.status(s, ws)
        assert st["connected"] is False
        assert st["freshness"] == "never"
        assert {a["provider"] for a in st["available"]} == {
            connections.MICROSOFT, connections.GOOGLE,
        }


def test_a_connected_outlook_is_reported_with_its_account_and_freshness(ws):
    with session_scope(ENGINE) as s:
        _connect(s, connections.MICROSOFT, last_sync=datetime.utcnow() - timedelta(minutes=2))
        st = connections.status(s, ws)
    assert st["connected"] is True
    assert st["providers"] == [connections.MICROSOFT]
    assert st["freshness"] == "fresh"
    assert st["connections"][0]["account"] == "ruslan@example.com"
    # The governance model travels with the connection so the UI need not infer it.
    assert st["connections"][0]["writesRequireApproval"] is True


def test_a_connection_that_has_not_synced_in_a_day_is_stale(ws):
    with session_scope(ENGINE) as s:
        _connect(s, connections.MICROSOFT, last_sync=datetime.utcnow() - timedelta(hours=6))
        assert connections.status(s, ws)["freshness"] == "stale"


def test_the_legacy_calendar_provider_id_still_resolves_as_google(ws):
    # `calendar` was the pre-rename registration. Existing rows must keep working.
    with session_scope(ENGINE) as s:
        _connect(s, connections.LEGACY_GOOGLE, last_sync=datetime.utcnow())
        st = connections.status(s, ws)
    assert st["providers"] == [connections.GOOGLE]
    assert st["connections"][0]["label"] == "Google Calendar"


def test_a_broken_connection_does_not_count_as_connected(ws):
    with session_scope(ENGINE) as s:
        _connect(s, connections.MICROSOFT, status="error", last_sync=datetime.utcnow())
        assert connections.status(s, ws)["connected"] is False


# --- the three claims the planner had not earned ------------------------------

def test_calendar_connected_is_no_longer_the_email_flag(ws, monkeypatch):
    # It used to be `calendar_connected = email_enabled()`, so switching the
    # email module on made a workspace with no calendar report one.
    monkeypatch.setenv("DAYPILOT_EMAIL_ENABLED", "true")
    with session_scope(ENGINE) as s:
        r = planner_readiness(s, ws, "2026-08-10")
        assert r["calendarConnected"] is False
        assert r["calendarProviders"] == []
        assert r["calendarFreshness"] == "never"

    with session_scope(ENGINE) as s:
        _connect(s, connections.MICROSOFT, last_sync=datetime.utcnow())
    with session_scope(ENGINE) as s:
        r = planner_readiness(s, ws, "2026-08-10")
        assert r["calendarConnected"] is True
        assert r["calendarProviders"] == [connections.MICROSOFT]


def test_no_calendar_connected_is_stated_not_papered_over():
    q = _quality_explanation({"score": 90, "issues": []}, {"connected": False})
    assert "No calendar conflicts" not in q["strengths"]
    assert any("No calendar connected" in w for w in q["warnings"])


def test_a_clean_check_is_claimed_only_when_one_actually_happened():
    q = _quality_explanation(
        {"score": 90, "issues": []},
        {"connected": True, "freshness": "fresh", "conflicts": 0},
    )
    assert "No calendar conflicts" in q["strengths"]


def test_real_overlaps_are_reported_as_warnings():
    q = _quality_explanation(
        {"score": 90, "issues": []},
        {"connected": True, "freshness": "fresh", "conflicts": 2},
    )
    assert "No calendar conflicts" not in q["strengths"]
    assert any("2 overlapping meetings" in w for w in q["warnings"])


def test_a_stale_calendar_does_not_get_a_clean_bill_of_health():
    q = _quality_explanation(
        {"score": 90, "issues": []},
        {"connected": True, "freshness": "stale", "conflicts": 0},
    )
    assert "No calendar conflicts" not in q["strengths"]
    assert any("not synced recently" in w for w in q["warnings"])


def test_conflicts_are_scoped_to_the_day_being_planned(ws):
    day = datetime(2026, 8, 10, 9, 0)
    with session_scope(ENGINE) as s:
        s.add(CalendarEvent(workspace_id=ws, title="A", start_at=day,
                            end_at=day + timedelta(hours=1)))
        s.add(CalendarEvent(workspace_id=ws, title="B", start_at=day + timedelta(minutes=30),
                            end_at=day + timedelta(hours=2)))
        # An overlap on a different day must not be reported as today's.
        other = day + timedelta(days=3)
        s.add(CalendarEvent(workspace_id=ws, title="C", start_at=other,
                            end_at=other + timedelta(hours=1)))
        s.add(CalendarEvent(workspace_id=ws, title="D", start_at=other,
                            end_at=other + timedelta(hours=1)))
    with session_scope(ENGINE) as s:
        assert len(conflicts_on(s, ws, "2026-08-10")) == 1
        assert len(conflicts_on(s, ws, "2026-08-13")) == 1
        assert conflicts_on(s, ws, "2026-08-11") == []
        assert conflicts_on(s, ws, "not-a-date") == []


# --- API ----------------------------------------------------------------------

def test_the_settings_endpoint_serves_the_source_catalogue(ws):
    r = client.get(f"/v1/calendar/settings?workspaceId={ws}")
    assert r.status_code == 200
    body = r.json()
    ids = {s["id"] for s in body["sources"]}
    assert {"event", "projects", "tasks", "documents", "slack", "email", "github"} == ids
    # The UI must not have to guess which are usable or fixed.
    event = next(s for s in body["sources"] if s["id"] == "event")
    assert event["alwaysOn"] is True
    slack = next(s for s in body["sources"] if s["id"] == "slack")
    assert slack["requires"] == "slack" and slack["available"] is False


def test_the_settings_endpoint_rejects_a_bad_value(ws):
    r = client.put(f"/v1/calendar/settings?workspaceId={ws}", json={"prepareScope": "nope"})
    assert r.status_code == 400


def test_settings_round_trip_through_the_api(ws):
    r = client.put(f"/v1/calendar/settings?workspaceId={ws}", json={
        "prepareScope": "external", "prepMinutes": 30, "autoPrepBlocks": False,
        "contextSources": ["tasks"], "privateEvents": "skip",
    })
    assert r.status_code == 200
    saved = r.json()["settings"]
    assert saved["prepareScope"] == "external"
    assert saved["privateEvents"] == "skip"
    assert set(saved["contextSources"]) == {"event", "tasks"}
    again = client.get(f"/v1/calendar/settings?workspaceId={ws}").json()["settings"]
    assert again == saved


def test_reading_the_calendar_does_not_write(ws):
    # `GET /events` used to call sync_events(), so rendering the calendar
    # performed an upsert and a provider round trip.
    with session_scope(ENGINE) as s:
        before = s.query(CalendarEvent).filter_by(workspace_id=ws).count()
    assert client.get(f"/v1/calendar/events?workspaceId={ws}").status_code == 200
    with session_scope(ENGINE) as s:
        assert s.query(CalendarEvent).filter_by(workspace_id=ws).count() == before


def test_an_unknown_calendar_provider_is_a_404(ws):
    assert client.post(f"/v1/calendar/connect/dropbox?workspaceId={ws}").status_code == 404


def test_connecting_an_unconfigured_provider_says_so_instead_of_dead_ending(ws, monkeypatch):
    monkeypatch.delenv("MS_GRAPH_CLIENT_ID", raising=False)
    monkeypatch.delenv("MICROSOFT_OAUTH_CLIENT_ID", raising=False)
    r = client.post(f"/v1/calendar/connect/microsoft_calendar?workspaceId={ws}")
    assert r.status_code == 200
    assert r.json()["available"] is False
    assert "not configured" in r.json()["reason"]


def test_both_calendars_are_offered_read_only_first(ws):
    body = client.get("/v1/calendar/providers").json()
    assert {i["provider"] for i in body["items"]} == {
        connections.MICROSOFT, connections.GOOGLE,
    }
    for item in body["items"]:
        assert item["readOnly"] is True
        # Least privilege: nothing in the first consent can write a calendar.
        assert not any("ReadWrite" in s or "/calendar\"" in s for s in item["scopes"])


def test_the_calendar_callback_is_not_the_mailbox_callback(monkeypatch):
    """A calendar authorization must come back to the calendar callback.

    Borrowing `mail_oauth._redirect_uri` would send the user to
    `/v1/email/oauth/.../callback`, which looks for a mailbox state it will
    never find — the OAuth *client* is shared, the redirect is not.
    """
    from app import calendar_oauth, mail_oauth

    monkeypatch.setenv("MS_GRAPH_REDIRECT_URI", "https://dp.example.com/v1/email/oauth/microsoft/callback")
    monkeypatch.setenv("MS_GRAPH_CALENDAR_REDIRECT_URI", "https://dp.example.com/v1/calendar/callback")
    assert calendar_oauth.redirect_uri(connections.MICROSOFT).endswith("/v1/calendar/callback")
    assert calendar_oauth.redirect_uri(connections.MICROSOFT) != mail_oauth._redirect_uri("microsoft")

    monkeypatch.setenv("GOOGLE_CALENDAR_REDIRECT_URI", "https://dp.example.com/v1/calendar/callback")
    assert calendar_oauth.redirect_uri(connections.GOOGLE).endswith("/v1/calendar/callback")


def test_the_authorization_url_carries_the_calendar_redirect(monkeypatch):
    monkeypatch.setenv("MS_GRAPH_CLIENT_ID", "test-client")
    monkeypatch.setenv("MS_GRAPH_CALENDAR_REDIRECT_URI", "https://dp.example.com/v1/calendar/callback")
    from app import calendar_oauth

    out = calendar_oauth.build_authorization(WS, connections.MICROSOFT, "https://dp.example.com/#/calendar")
    assert out["available"] is True
    assert "%2Fv1%2Fcalendar%2Fcallback" in out["authorizationUrl"]
    # Read-only first consent.
    assert "Calendars.Read" in out["authorizationUrl"]
    assert "Calendars.ReadWrite" not in out["authorizationUrl"]
