"""Daily Standup Copilot — the acceptance criteria, as tests.

The feature posts a summary of a real person's work into a public channel every
day, unattended. Almost every test here is about a way that could go wrong:
claiming work that did not happen, posting text nobody approved, posting twice,
or posting outside the thread and into the channel root.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from daypilot_knowledge.db import (
    Approval,
    Job,
    StandupDraft,
    Task,
    create_engine_from_settings,
    session_scope,
)
from daypilot_orchestrator.standup import compiler, policy, schedule, service
from daypilot_orchestrator.standup.collector import BLOCKED, COMPLETED, PROGRESS
from daypilot_orchestrator.standup.thread_resolver import resolve

client = TestClient(app)


def _ws() -> str:
    return "ws-su-" + uuid.uuid4().hex[:8]


def _workflow(session, workspace_id, **overrides):
    body = {
        "slackChannelId": "C123", "slackChannelName": "daily-standup",
        "slackConnectionId": "conn-1", "timezone": "Europe/Rome",
        **overrides,
    }
    out = service.create_workflow(session, workspace_id, body)
    return service.get_workflow_row(session, workspace_id, out["id"])


class _Ev:
    """A stand-in evidence row for compiler tests — same duck type, no DB."""

    def __init__(self, summary, activity_type=COMPLETED, project_name="", included=True, eid=None):
        self.id = eid or uuid.uuid4().hex
        self.summary = summary
        self.activity_type = activity_type
        self.project_name = project_name
        self.included = included


# ───────────────────────────────────────────────────────────────────────────
# The draft never invents progress
# ───────────────────────────────────────────────────────────────────────────

def test_every_claim_carries_evidence_or_is_flagged():
    out = compiler.compile_draft([
        _Ev("Fixed persona portrait loading across the directory", eid="e1"),
    ])
    observed = [b for b in out.yesterday if b.kind == policy.OBSERVED]
    assert observed and all(b.evidence_ids for b in observed)
    # The placeholder lines that fill empty sections are never dressed up as
    # observations.
    assert all(b.kind != policy.OBSERVED or b.evidence_ids for b in out.today)


def test_an_empty_day_says_so_instead_of_inventing_work():
    out = compiler.compile_draft([], empty_day_policy="honest")
    text = compiler.render_section(out.yesterday)
    assert "No tracked activity" in text
    assert out.yesterday[0].kind == policy.NEEDS_CONFIRMATION
    assert out.yesterday[0].evidence_ids == []


def test_unfinished_work_is_never_reported_as_completed():
    """Rule 4: meaningful movement is 'Continued work on…', not a completion."""
    out = compiler.compile_draft([
        _Ev("Thread-aware Slack delivery", activity_type=PROGRESS, eid="p1"),
    ])
    text = compiler.render_section(out.yesterday)
    assert text.startswith("• Continued work on")
    assert "thread-aware Slack delivery" in text


def test_excluded_evidence_cannot_reach_the_update():
    out = compiler.compile_draft([
        _Ev("Personal side project", included=False, eid="x1"),
        _Ev("Shipped the standup collector", eid="y1"),
    ])
    text = compiler.render_section(out.yesterday)
    assert "Personal side project" not in text
    assert "standup collector" in text


def test_related_evidence_collapses_into_one_outcome():
    """Rule 2: a bullet per commit is a changelog, not a standup."""
    out = compiler.compile_draft([
        _Ev("Fix persona portrait loading in the agents directory", eid="c1"),
        _Ev("Fix persona portrait loading fallback", eid="c2"),
        _Ev("persona portrait loading: correct asset URL", eid="c3"),
    ])
    assert len(out.yesterday) == 1
    assert set(out.yesterday[0].evidence_ids) == {"c1", "c2", "c3"}


def test_blockers_come_only_from_observed_signals():
    empty = compiler.compile_draft([_Ev("Shipped a thing", eid="a")])
    assert compiler.render_section(empty.blockers) == "• None."

    blocked = compiler.compile_draft([
        _Ev("Waiting for approval: post to Slack", activity_type=BLOCKED, eid="b1"),
    ])
    assert "Waiting for approval" in compiler.render_section(blocked.blockers)
    assert blocked.blockers[0].evidence_ids == ["b1"]


def test_sections_are_capped_so_the_update_stays_readable():
    rows = [_Ev(f"Distinct outcome number {n} alpha{n}", eid=f"e{n}") for n in range(10)]
    out = compiler.compile_draft(rows, max_bullets=3)
    assert len(out.yesterday) <= 3


def test_the_rendered_message_mirrors_the_reminder_questions():
    text = compiler.render_slack_message("• a", "• b", "• None.")
    assert "*1️⃣ Yesterday*" in text
    assert "*2️⃣ Today*" in text
    assert "*3️⃣ Blockers*" in text
    assert text.index("Yesterday") < text.index("Today") < text.index("Blockers")


# ───────────────────────────────────────────────────────────────────────────
# Timing: the user's clock, not the server's
# ───────────────────────────────────────────────────────────────────────────

def test_monday_reports_on_friday_not_on_sunday():
    monday = date(2026, 8, 10)
    assert monday.isoweekday() == 1
    assert schedule.previous_working_day(monday, [1, 2, 3, 4, 5]) == date(2026, 8, 7)


def test_the_reporting_window_reaches_back_to_the_previous_workday_evening():
    """Work done after 18:00 belongs to that day, not to nobody."""
    start, end = schedule.reporting_window(
        timezone_name="Europe/Rome", reporting_day=date(2026, 8, 10), days=[1, 2, 3, 4, 5],
    )
    # Friday 18:00 Rome (UTC+2 in August) = Friday 16:00 UTC.
    assert start == datetime(2026, 8, 7, 16, 0)
    assert end > start


def test_the_review_time_holds_across_a_daylight_saving_change():
    """18:00 local must stay 18:00 local, which means the UTC hour moves."""
    summer = schedule.next_occurrence(
        timezone_name="Europe/Rome", at="18:00", days=[1, 2, 3, 4, 5],
        now_utc=datetime(2026, 8, 5, 6, 0),
    )
    winter = schedule.next_occurrence(
        timezone_name="Europe/Rome", at="18:00", days=[1, 2, 3, 4, 5],
        now_utc=datetime(2026, 12, 2, 6, 0),
    )
    assert summer.local.hour == winter.local.hour == 18
    assert summer.utc.hour == 16 and winter.utc.hour == 17


def test_the_next_occurrence_skips_non_working_days():
    friday_evening = datetime(2026, 8, 7, 20, 0)  # after Friday's review, UTC
    nxt = schedule.next_occurrence(
        timezone_name="Europe/Rome", at="18:00", days=[1, 2, 3, 4, 5], now_utc=friday_evening,
    )
    assert nxt.day == date(2026, 8, 10)  # Monday


def test_wednesdays_work_targets_thursdays_thread():
    assert schedule.target_standup_day(
        reporting_day=date(2026, 8, 5), delivery_mode="next_workday", days=[1, 2, 3, 4, 5],
    ) == date(2026, 8, 6)
    # Friday's rolls to Monday, not to Saturday.
    assert schedule.target_standup_day(
        reporting_day=date(2026, 8, 7), delivery_mode="next_workday", days=[1, 2, 3, 4, 5],
    ) == date(2026, 8, 10)
    # Same-day mode posts into today's thread.
    assert schedule.target_standup_day(
        reporting_day=date(2026, 8, 5), delivery_mode="same_day", days=[1, 2, 3, 4, 5],
    ) == date(2026, 8, 5)


def test_an_unreadable_schedule_is_rejected_at_configuration_time():
    with pytest.raises(schedule.ScheduleError):
        schedule.parse_hhmm("six pm")
    with pytest.raises(schedule.ScheduleError):
        schedule.zone("Mars/Olympus_Mons")


# ───────────────────────────────────────────────────────────────────────────
# Thread resolution: reply, or do not post at all
# ───────────────────────────────────────────────────────────────────────────

def _ts(when: datetime) -> str:
    return f"{when.replace(tzinfo=None).timestamp():.6f}"


def _at(local_hhmm: tuple[int, int], day=date(2026, 8, 6)) -> str:
    """A Slack ts for a Rome wall-clock time on ``day``."""
    utc = schedule.to_utc(datetime(day.year, day.month, day.day, *local_hhmm), schedule.zone("Europe/Rome"))
    return f"{utc.replace(tzinfo=None).timestamp():.6f}"


def _resolve(messages, **kwargs):
    return resolve(
        read_history=lambda *_a: messages,
        channel_id="C123",
        standup_day=date(2026, 8, 6),
        timezone_name="Europe/Rome",
        reminder_time="09:00",
        **kwargs,
    )


def test_the_reminder_is_found_by_wording_and_time_together():
    thread = _resolve([
        {"ts": _at((9, 0)), "text": ":sunrise: *Daily Standup Reminder*\nHey team!", "botId": "B1"},
    ])
    assert thread.ts == _at((9, 0))
    assert "signature" in thread.matched_on and "time_window" in thread.matched_on


def test_a_message_that_only_lands_in_the_window_is_not_enough():
    """Time alone would adopt any 9am chatter as the standup thread."""
    with pytest.raises(policy.ThreadNotFound):
        _resolve([{"ts": _at((9, 5)), "text": "morning all", "botId": None}])


def test_the_bot_identity_can_match_a_reworded_reminder():
    thread = _resolve(
        [{"ts": _at((9, 1)), "text": "Standup time!", "botId": "B-workflow"}],
        bot_id="B-workflow",
    )
    assert "bot_identity" in thread.matched_on


def test_a_reply_is_never_mistaken_for_the_thread_root():
    root = _at((9, 0))
    with pytest.raises(policy.ThreadNotFound):
        _resolve([{
            "ts": _at((9, 30)), "threadTs": root,
            "text": "my update for the Daily Standup Reminder", "botId": "B1",
        }])


def test_yesterdays_reminder_is_out_of_the_window():
    yesterday = _at((9, 0), day=date(2026, 8, 5))
    with pytest.raises(policy.ThreadNotFound):
        _resolve([{"ts": yesterday, "text": "Daily Standup Reminder", "botId": "B1"}])


def test_the_later_reminder_wins_when_the_workflow_posted_twice():
    early, late = _at((9, 0)), _at((9, 45))
    thread = _resolve([
        {"ts": early, "text": "Daily Standup Reminder", "botId": "B1"},
        {"ts": late, "text": "Daily Standup Reminder", "botId": "B1"},
    ])
    assert thread.ts == late


# ───────────────────────────────────────────────────────────────────────────
# Approval freezes the text; delivery may send nothing else
# ───────────────────────────────────────────────────────────────────────────

def test_approval_freezes_an_immutable_snapshot():
    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws)
        draft = service.generate_draft(s, wf, date(2026, 8, 5))
        service.edit_draft(s, draft, {"yesterday": "• Shipped the standup collector"})
        service.approve(s, wf, draft, approved_by="u1")

        assert draft.status == policy.WAITING_FOR_THREAD
        assert draft.approved_yesterday == "• Shipped the standup collector"
        assert draft.content_hash == policy.content_hash(
            draft.yesterday_text, draft.today_text, draft.blockers_text,
        )


def test_editing_after_approval_revokes_it():
    """Consent applies to the text consented to. Nothing else may be sent."""
    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws)
        draft = service.generate_draft(s, wf, date(2026, 8, 5))
        service.approve(s, wf, draft)
        assert draft.content_hash is not None

        service.edit_draft(s, draft, {"today": "• Something entirely different"})
        assert draft.content_hash is None
        assert draft.approved_at is None
        assert draft.status == policy.NEEDS_REVIEW

        with pytest.raises(policy.ApprovalRequired):
            service.deliver(s, wf, draft, send=lambda _p: {"ts": "1"},
                            known_thread_ts="1722850800.000100")


def test_delivery_refuses_a_snapshot_that_does_not_match_its_hash():
    """Defence against the frozen copy being altered by anything but approval."""
    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws)
        draft = service.generate_draft(s, wf, date(2026, 8, 5))
        service.approve(s, wf, draft)
        draft.approved_yesterday = "• Text nobody approved"
        s.flush()

        with pytest.raises(policy.ApprovalRequired):
            service.deliver(s, wf, draft, send=lambda _p: {"ts": "1"},
                            known_thread_ts="1722850800.000100")
        assert draft.status == policy.NEEDS_REVIEW


def test_the_approved_text_is_what_reaches_slack():
    ws = _ws()
    eng = create_engine_from_settings()
    sent: list[dict] = []
    with session_scope(eng) as s:
        wf = _workflow(s, ws)
        draft = service.generate_draft(s, wf, date(2026, 8, 5))
        service.edit_draft(s, draft, {"yesterday": "• Approved line"})
        service.approve(s, wf, draft)
        # An edit attempt after approval must not leak into the send.
        draft.yesterday_text = "• Sneaky post-approval edit"
        s.flush()

        service.deliver(s, wf, draft, send=lambda p: sent.append(p) or {"ts": "1.1"},
                        known_thread_ts="1722850800.000100")

    assert "Approved line" in sent[0]["text"]
    assert "Sneaky" not in sent[0]["text"]


# ───────────────────────────────────────────────────────────────────────────
# Delivery: exactly once, always in the thread
# ───────────────────────────────────────────────────────────────────────────

def test_the_update_is_posted_inside_the_thread():
    ws = _ws()
    eng = create_engine_from_settings()
    sent: list[dict] = []
    with session_scope(eng) as s:
        wf = _workflow(s, ws)
        draft = service.generate_draft(s, wf, date(2026, 8, 5))
        service.approve(s, wf, draft)
        service.deliver(s, wf, draft, send=lambda p: sent.append(p) or {"ts": "1.2"},
                        known_thread_ts="1722850800.000100")

    assert sent[0]["threadTs"] == "1722850800.000100"
    assert sent[0]["channel"] == "C123"


def test_a_missing_thread_never_becomes_a_root_message():
    """The failure this whole module exists to prevent."""
    ws = _ws()
    eng = create_engine_from_settings()
    sent: list[dict] = []
    with session_scope(eng) as s:
        wf = _workflow(s, ws)
        draft = service.generate_draft(s, wf, date(2026, 8, 5))
        service.approve(s, wf, draft)

        with pytest.raises(policy.ThreadNotFound):
            service.deliver(s, wf, draft, send=lambda p: sent.append(p) or {"ts": "x"},
                            read_history=lambda *_a: [])

        assert sent == []                       # nothing was posted anywhere
        assert draft.status == policy.THREAD_NOT_FOUND
        assert draft.detail                     # and the failure is visible


def test_the_update_is_posted_exactly_once():
    ws = _ws()
    eng = create_engine_from_settings()
    sent: list[dict] = []
    with session_scope(eng) as s:
        wf = _workflow(s, ws)
        draft = service.generate_draft(s, wf, date(2026, 8, 5))
        service.approve(s, wf, draft)
        first = service.deliver(s, wf, draft, send=lambda p: sent.append(p) or {"ts": "1.3"},
                                known_thread_ts="1722850800.000100")
        # The job runs again after a timeout it never saw the answer to.
        second = service.deliver(s, wf, draft, send=lambda p: sent.append(p) or {"ts": "9.9"},
                                 known_thread_ts="1722850800.000100")

    assert len(sent) == 1
    assert first["duplicate"] is False and second["duplicate"] is True
    assert second["messageTs"] == "1.3"


def test_every_send_carries_an_idempotency_key_for_the_day():
    ws = _ws()
    eng = create_engine_from_settings()
    sent: list[dict] = []
    with session_scope(eng) as s:
        wf = _workflow(s, ws)
        draft = service.generate_draft(s, wf, date(2026, 8, 5))
        service.approve(s, wf, draft)
        service.deliver(s, wf, draft, send=lambda p: sent.append(p) or {"ts": "1.4"},
                        known_thread_ts="1722850800.000100")
        assert sent[0]["clientMessageId"] == policy.delivery_key(wf.id, "2026-08-06")


def test_a_slack_outage_leaves_a_visible_failure_and_can_be_retried():
    ws = _ws()
    eng = create_engine_from_settings()
    attempts: list[int] = []

    def flaky(_payload):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("slack: service_unavailable")
        return {"ts": "2.0"}

    with session_scope(eng) as s:
        wf = _workflow(s, ws)
        draft = service.generate_draft(s, wf, date(2026, 8, 5))
        service.approve(s, wf, draft)

        with pytest.raises(RuntimeError):
            service.deliver(s, wf, draft, send=flaky, known_thread_ts="1722850800.000100")
        assert draft.status == policy.SEND_FAILED
        assert "service_unavailable" in draft.detail

        service.deliver(s, wf, draft, send=flaky, known_thread_ts="1722850800.000100")
        assert draft.status == policy.SENT
        assert draft.attempts == 2


def test_delivery_is_bounded_rather_than_retried_forever():
    """A queued delivery gets bounded attempts, then dead-letters."""
    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws)
        draft = service.generate_draft(s, wf, date(2026, 8, 5))
        service.approve(s, wf, draft)
        job = s.get(Job, draft.delivery_job_id)
        assert job is not None and job.kind == "standup.deliver"
        assert job.max_attempts == 5


def test_an_undelivered_draft_expires_instead_of_posting_stale_news():
    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws)
        draft = service.generate_draft(s, wf, date(2026, 8, 5))
        service.approve(s, wf, draft)
        draft.target_standup_date = "2020-01-02"
        s.flush()

        assert service.expire_stale(s, ws) == 1
        assert draft.status == policy.EXPIRED
        with pytest.raises(policy.DraftLocked):
            service.deliver(s, wf, draft, send=lambda _p: {"ts": "x"},
                            known_thread_ts="1722850800.000100")


def test_a_sent_day_cannot_be_regenerated():
    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws)
        draft = service.generate_draft(s, wf, date(2026, 8, 5))
        service.approve(s, wf, draft)
        service.deliver(s, wf, draft, send=lambda _p: {"ts": "3.0"},
                        known_thread_ts="1722850800.000100")
        with pytest.raises(policy.DraftLocked):
            service.generate_draft(s, wf, date(2026, 8, 5))


# ───────────────────────────────────────────────────────────────────────────
# Scheduling produces durable, deferred work
# ───────────────────────────────────────────────────────────────────────────

def test_creating_a_workflow_schedules_its_next_review_as_a_deferred_job():
    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws)
        assert wf.next_review_at is not None and wf.next_review_at > datetime.utcnow()
        job = s.query(Job).filter_by(workspace_id=ws, kind="standup.review_due").one()
        assert job.state == "queued"
        assert job.run_after == wf.next_review_at   # deferred, not immediate


def test_approval_defers_delivery_until_the_thread_can_exist():
    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws)
        draft = service.generate_draft(s, wf, date.today() + timedelta(days=1))
        service.approve(s, wf, draft)
        job = s.get(Job, draft.delivery_job_id)
        assert job.run_after > datetime.utcnow()  # waits for tomorrow morning


def test_disabling_a_workflow_stops_it_being_scheduled():
    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws)
        service.update_workflow(s, ws, wf.id, {"enabled": False})
        assert wf.next_review_at is None


# ───────────────────────────────────────────────────────────────────────────
# Collection is idempotent and respects the user's exclusions
# ───────────────────────────────────────────────────────────────────────────

def test_collecting_twice_does_not_double_count_the_day():
    ws = _ws()
    eng = create_engine_from_settings()
    today = date.today()
    with session_scope(eng) as s:
        wf = _workflow(s, ws, timezone="UTC")
        s.add(Task(workspace_id=ws, title="Ship the standup collector", status="done"))
        s.flush()

        first = service.collect_evidence(s, wf, today)
        second = service.collect_evidence(s, wf, today)
        assert len(first) == len(second)
        assert len({r.id for r in second}) == len(second)


def test_an_exclusion_survives_a_re_collect():
    """Excluding a personal commit at 17:50 must not be undone at 17:55."""
    ws = _ws()
    eng = create_engine_from_settings()
    today = date.today()
    with session_scope(eng) as s:
        wf = _workflow(s, ws, timezone="UTC")
        s.add(Task(workspace_id=ws, title="A private errand", status="done"))
        s.flush()

        rows = service.collect_evidence(s, wf, today)
        target = next(r for r in rows if "private errand" in r.summary)
        service.set_evidence_included(s, ws, target.id, False)

        service.collect_evidence(s, wf, today)
        s.refresh(target)
        assert target.included is False


def test_a_pending_approval_is_collected_as_a_blocker():
    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws, timezone="UTC")
        s.add(Approval(workspace_id=ws, action="slack.chat.send",
                       summary="Post the standup update", status="pending"))
        s.flush()

        rows = service.collect_evidence(s, wf, date.today())
        blockers = [r for r in rows if r.activity_type == BLOCKED]
        assert any("Post the standup update" in r.summary for r in blockers)


# ───────────────────────────────────────────────────────────────────────────
# Over the API the UI actually calls
# ───────────────────────────────────────────────────────────────────────────

def test_the_full_journey_over_http():
    ws = _ws()
    created = client.post(f"/v1/standup/workflows?workspaceId={ws}", json={
        "slackChannelId": "C777", "slackChannelName": "daily-standup",
        "timezone": "Europe/Rome", "reviewTime": "18:00", "deliveryMode": "next_workday",
    })
    assert created.status_code == 201, created.text
    workflow = created.json()
    assert workflow["reviewTime"] == "18:00"

    wid = workflow["id"]
    assert client.post(f"/v1/standup/workflows/{wid}/collect?workspaceId={ws}").status_code == 200

    note = client.post(f"/v1/standup/workflows/{wid}/notes?workspaceId={ws}",
                       json={"text": "Paired with Ana on the thread resolver"})
    assert note.status_code == 200 and note.json()["source"] == "manual"

    generated = client.post(f"/v1/standup/workflows/{wid}/generate?workspaceId={ws}")
    assert generated.status_code == 200
    draft = generated.json()
    assert draft["status"] == "NEEDS_REVIEW" and draft["editable"] is True
    assert "*1️⃣ Yesterday*" in draft["slackPreview"]

    edited = client.patch(f"/v1/standup/drafts/{draft['id']}?workspaceId={ws}",
                          json={"today": "• Wire the review surface"})
    assert edited.status_code == 200
    assert "Wire the review surface" in edited.json()["slackPreview"]

    approved = client.post(f"/v1/standup/drafts/{draft['id']}/approve?workspaceId={ws}")
    assert approved.status_code == 200
    assert approved.json()["status"] == "WAITING_FOR_THREAD"
    assert approved.json()["contentHash"]

    status = client.get(f"/v1/standup/status?workspaceId={ws}").json()
    assert status["configured"] is True
    assert status["draft"]["status"] == "WAITING_FOR_THREAD"


def test_an_unconfigured_workspace_says_so_rather_than_failing():
    status = client.get(f"/v1/standup/status?workspaceId={_ws()}").json()
    assert status["configured"] is False


def test_a_bad_timezone_is_rejected_with_400_not_500():
    ws = _ws()
    r = client.post(f"/v1/standup/workflows?workspaceId={ws}",
                    json={"timezone": "Mars/Olympus_Mons", "slackChannelId": "C1"})
    assert r.status_code == 400


def test_send_now_refuses_without_an_approved_snapshot():
    ws = _ws()
    created = client.post(f"/v1/standup/workflows?workspaceId={ws}", json={
        "slackChannelId": "C1", "slackConnectionId": "conn-x", "timezone": "UTC",
    }).json()
    draft = client.post(f"/v1/standup/workflows/{created['id']}/generate?workspaceId={ws}").json()
    r = client.post(f"/v1/standup/drafts/{draft['id']}/send-now?workspaceId={ws}")
    assert r.status_code == 409


def test_evidence_can_be_excluded_from_the_review_surface():
    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        s.add(Task(workspace_id=ws, title="Something personal", status="done"))
    created = client.post(f"/v1/standup/workflows?workspaceId={ws}", json={
        "slackChannelId": "C1", "timezone": "UTC",
    }).json()
    client.post(f"/v1/standup/workflows/{created['id']}/collect?workspaceId={ws}")
    draft = client.post(f"/v1/standup/workflows/{created['id']}/generate?workspaceId={ws}").json()

    listed = client.get(f"/v1/standup/drafts/{draft['id']}/evidence?workspaceId={ws}").json()
    item = next(e for e in listed["evidence"] if "Something personal" in e["summary"])

    excluded = client.post(
        f"/v1/standup/drafts/{draft['id']}/evidence/{item['id']}/exclude?workspaceId={ws}")
    assert excluded.status_code == 200 and excluded.json()["included"] is False

    regenerated = client.post(f"/v1/standup/workflows/{created['id']}/generate?workspaceId={ws}").json()
    assert "Something personal" not in regenerated["slackPreview"]


# ───────────────────────────────────────────────────────────────────────────
# The Slack adapter actually replies rather than posting to the channel
# ───────────────────────────────────────────────────────────────────────────

def test_the_slack_adapter_sends_thread_ts():
    import httpx

    from daypilot_orchestrator.integrations.providers.slack.adapter import SlackProvider

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        if request.url.path.endswith("/auth.test"):
            return httpx.Response(200, json={"ok": True})
        seen.update(_json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "ts": "1.5", "channel": "C1"})

    prov = SlackProvider(transport=httpx.MockTransport(handler))
    prov.connect({"bot_token": "xoxb-test"})
    out = prov.execute("chat.send", {
        "channel": "C1", "text": "hello", "threadTs": "1722850800.000100",
        "clientMessageId": "standup:w:2026-08-06",
    })
    assert seen["thread_ts"] == "1722850800.000100"
    assert out["clientMessageId"] == "standup:w:2026-08-06"


def test_a_send_without_a_thread_does_not_invent_one():
    """The adapter stays honest: no threadTs in, no thread_ts out."""
    import httpx

    from daypilot_orchestrator.integrations.providers.slack.adapter import SlackProvider

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        if request.url.path.endswith("/auth.test"):
            return httpx.Response(200, json={"ok": True})
        seen.update(_json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "ts": "1.6"})

    prov = SlackProvider(transport=httpx.MockTransport(handler))
    prov.connect({"bot_token": "xoxb-test"})
    prov.execute("chat.send", {"channel": "C1", "text": "hello"})
    assert "thread_ts" not in seen


def test_channel_history_returns_the_fields_thread_resolution_matches_on():
    import httpx

    from daypilot_orchestrator.integrations.providers.slack.adapter import SlackProvider

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth.test"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json={"ok": True, "messages": [
            {"ts": "1.0", "text": "Daily Standup Reminder", "bot_id": "B1"},
        ]})

    prov = SlackProvider(transport=httpx.MockTransport(handler))
    prov.connect({"bot_token": "xoxb-test"})
    out = prov.execute("chat.history", {"channel": "C1", "oldest": "0", "latest": "9"})
    assert out["messages"][0]["botId"] == "B1"
    assert out["messages"][0]["ts"] == "1.0"


# ───────────────────────────────────────────────────────────────────────────
# Everything is auditable, and the queue can defer
# ───────────────────────────────────────────────────────────────────────────

def test_the_queue_can_defer_a_job_without_a_second_scheduler():
    """A deferred job waits on `run_after` — the same column retries use.

    ``claim_next`` is deliberately not workspace-scoped (one worker drains the
    whole queue), so this asserts on the job itself rather than on "the queue
    is empty", which other tests in this file would falsify.
    """
    from daypilot_orchestrator.jobs import queue

    ws = _ws()
    eng = create_engine_from_settings()
    later = datetime.utcnow() + timedelta(hours=6)
    with session_scope(eng) as s:
        job = queue.enqueue(s, "standup.deliver", {}, workspace_id=ws, run_after=later)
        assert job.run_after == later
        assert job.state == "queued"

        # Drain everything currently due; the deferred job must not be among it.
        claimed: set[str] = set()
        while (nxt := queue.claim_next(s, kinds=["standup.deliver"])) is not None:
            claimed.add(nxt.id)
        assert job.id not in claimed


def test_the_whole_lifecycle_is_audited():
    from daypilot_knowledge.db import AuditLog

    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws)
        draft = service.generate_draft(s, wf, date(2026, 8, 5))
        service.approve(s, wf, draft)
        service.deliver(s, wf, draft, send=lambda _p: {"ts": "4.0"},
                        known_thread_ts="1722850800.000100")

    with session_scope(eng) as s:
        kinds = {row.event_type for row in s.query(AuditLog).all()}
    assert {"standup.workflow.created", "standup.draft.approved", "standup.deliver.sent"} <= kinds


# ───────────────────────────────────────────────────────────────────────────
# The UI is wired to the live API, and says what it does not know
# ───────────────────────────────────────────────────────────────────────────

from pathlib import Path  # noqa: E402

UI = Path(__file__).resolve().parents[1] / "packages" / "ui-bridge" / "src"
SRC = UI / "standup"


def test_the_ui_calls_the_real_endpoints_rather_than_seeded_state():
    source = (SRC / "standupClient.ts").read_text(encoding="utf-8")
    for endpoint in ("/v1/standup/status", "/v1/standup/workflows",
                     "/test-thread-resolution", "/approve", "/send-now",
                     "/evidence/", "/generate", "/collect"):
        assert endpoint in source, f"the UI never calls {endpoint}"


def test_approve_is_the_single_emphasised_action():
    review = (SRC / "StandupReview.tsx").read_text(encoding="utf-8")
    assert review.count("dp-standup__primary") == 1
    assert "Approve for tomorrow" in review and "Approve and post" in review


def test_an_unsupported_bullet_is_labelled_in_the_review():
    preview = (SRC / "StandupPreview.tsx").read_text(encoding="utf-8")
    assert "bulletKindLabel" in preview
    client_src = (SRC / "standupClient.ts").read_text(encoding="utf-8")
    assert "Manual statement" in client_src and "Needs confirmation" in client_src


def test_the_review_explains_a_missing_thread_rather_than_going_quiet():
    review = (SRC / "StandupReview.tsx").read_text(encoding="utf-8")
    assert "never posts to the channel root" in review
    assert "Retry now" in review  # a failure the user can act on


def test_the_setup_screen_explains_the_two_timing_modes():
    setup = (SRC / "StandupSetup.tsx").read_text(encoding="utf-8")
    assert "Reply to tomorrow’s thread" in setup and "Reply to today’s thread" in setup
    assert "completed since the last standup" in setup
    # Confirming a real message is the primary action, not Save.
    assert "Find today’s standup message" in setup
    assert setup.index("dp-standupsetup__primary") < setup.index("dp-standupsetup__secondary")


def test_the_review_and_evidence_surfaces_are_accessible():
    for name, needles in (
        ("StandupReview.tsx", ('role="alert"', 'role="status"', 'aria-label="Daily standup review"')),
        ("EvidenceDrawer.tsx", ('aria-label="Supporting evidence"', 'aria-pressed', "htmlFor")),
        ("StandupPreview.tsx", ("htmlFor", "aria-pressed", "aria-describedby")),
    ):
        source = (SRC / name).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in source, f"{name} is missing {needle}"


def test_the_project_is_named_only_when_the_day_spans_more_than_one():
    """Tagging every line "(DayPilot)" on a single-project day is noise."""
    single = compiler.compile_draft([
        _Ev("Fix portrait loading", project_name="DayPilot", eid="s1"),
        _Ev("Add an initials fallback component", project_name="DayPilot", eid="s2"),
    ])
    assert "(DayPilot)" not in compiler.render_section(single.yesterday)

    spanning = compiler.compile_draft([
        _Ev("Fix portrait loading", project_name="DayPilot", eid="m1"),
        _Ev("Rewrite the deploy script", project_name="GitPilot", eid="m2"),
    ])
    text = compiler.render_section(spanning.yesterday)
    assert "(DayPilot)" in text and "(GitPilot)" in text


# ───────────────────────────────────────────────────────────────────────────
# Details the screenshots caught
# ───────────────────────────────────────────────────────────────────────────

def test_reading_and_editing_a_section_are_exclusive():
    """Rendering the bullets and the textarea together showed every line twice."""
    preview = (SRC / "StandupPreview.tsx").read_text(encoding="utf-8")
    assert "showEditor ? (" in preview
    assert ") : bullets.length > 0 ? (" in preview
    # Reading is the default — most days end with approving unchanged.
    assert "useState(false)" in preview
    # A sent draft must not offer an editor that silently does nothing.
    assert "const showEditor = editing && editable" in preview


def test_the_approve_button_names_the_day_it_will_post():
    """On a Friday the next standup is Monday, so "tomorrow" would be a lie."""
    review = (SRC / "StandupReview.tsx").read_text(encoding="utf-8")
    assert "function approveLabel" in review
    assert "isTomorrow" in review
    assert "weekday: 'long'" in review
    assert "approveLabel(draft.targetStandupDate" in review


def test_the_evidence_line_never_repeats_the_source():
    """A DayPilot project tracked by DayPilot rendered "DayPilot · DayPilot"."""
    drawer = (SRC / "EvidenceDrawer.tsx").read_text(encoding="utf-8")
    assert "item.projectName !== source" in drawer
    assert "meta(item).join(' · ')" in drawer


def test_the_review_is_reachable_at_its_own_address():
    """The 18:00 notification has to link somewhere, in every state."""
    route = (UI / "shell" / "route.ts").read_text(encoding="utf-8")
    assert "'standup'" in route
    workspace = (SRC / "StandupWorkspace.tsx").read_text(encoding="utf-8")
    # Setup when unconfigured, review when a draft exists, an honest prompt
    # when neither.
    assert "status.configured" in workspace
    assert "<StandupSetup" in workspace and "<StandupReview" in workspace
    assert "Prepare today’s draft" in workspace


def test_the_standup_is_mounted_in_the_shell_and_on_home():
    shell = (UI / "minimalPortal.tsx").read_text(encoding="utf-8")
    assert shell.count("<StandupWorkspace />") == 2   # desktop and mobile
    home = (UI / "home" / "HomeWorkspace.tsx").read_text(encoding="utf-8")
    assert "<StandupStatusCard" in home
    # Configured against the live API, not another seeded setting.
    panel = (UI / "integrations" / "IntegrationsPanel.tsx").read_text(encoding="utf-8")
    assert "standupApi.listWorkflows()" in panel


def test_the_review_collapses_to_one_column_on_a_phone():
    css = (SRC / "standup.css").read_text(encoding="utf-8")
    assert "@media (max-width: 900px)" in css
    assert "grid-template-columns: minmax(0, 1fr)" in css
    # The approve action leads on a phone rather than hiding past the fold.
    assert "order: -1" in css


def test_the_home_card_names_the_day_it_will_post_too():
    """Same honesty as the approve button: on a Friday it is not "tomorrow"."""
    card = (SRC / "StandupStatusCard.tsx").read_text(encoding="utf-8")
    assert "function targetDay" in card
    assert "weekday: 'long'" in card
    assert "Replies to ${targetDay(draft)}" in card


# ───────────────────────────────────────────────────────────────────────────
# Unattended operation — the standup runs without anyone clicking
# ───────────────────────────────────────────────────────────────────────────

def _run_due_jobs(session, handlers, *, limit: int = 10) -> list:
    from daypilot_orchestrator.jobs import worker
    from daypilot_orchestrator.standup.handlers import DELIVER, REVIEW_DUE

    ran = []
    for _ in range(limit):
        job = worker.process_once(session, handlers, kinds=[REVIEW_DUE, DELIVER])
        if job is None:
            break
        ran.append(job)
    return ran


def test_the_review_job_builds_the_draft_and_arms_the_next_day():
    """The whole point: at 18:00 a draft exists without anyone clicking."""
    from daypilot_orchestrator.standup import handlers as h

    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws, timezone="UTC")
        s.add(Task(workspace_id=ws, title="Ship the standup worker", status="done"))
        s.flush()
        first_armed = wf.next_review_at

        # The worker can only claim the job once `run_after` has passed, so the
        # handler always runs at or after the review time. Fire it exactly then.
        out = h.handle_review_due(
            s, {"workflowId": wf.id, "reportingDate": date.today().isoformat()},
            now_utc=first_armed,
        )

        assert out["draftId"]
        assert out["signals"] >= 1
        draft = service.get_draft_row(s, ws, out["draftId"])
        assert draft.status == policy.NEEDS_REVIEW
        assert "standup worker" in draft.yesterday_text
        # And the chain continues: the next occurrence is armed and later.
        assert wf.next_review_at is not None and wf.next_review_at > first_armed


def test_a_review_that_fails_still_leaves_tomorrow_scheduled():
    """A workflow that errors once must not stop running forever."""
    from daypilot_orchestrator.standup import handlers as h

    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws, timezone="UTC")
        # Send today's draft so the review job hits DraftLocked mid-handler.
        draft = service.generate_draft(s, wf, date.today())
        service.approve(s, wf, draft)
        service.deliver(s, wf, draft, send=lambda _p: {"ts": "1.1"},
                        known_thread_ts="1722850800.000100")

        out = h.handle_review_due(s, {"workflowId": wf.id,
                                      "reportingDate": date.today().isoformat()})
        assert "skipped" in out
        assert wf.next_review_at is not None and wf.next_review_at > datetime.utcnow()


def test_the_review_job_raises_a_notification_pointing_at_the_review():
    from daypilot_knowledge.db import Event
    from daypilot_orchestrator.standup import handlers as h

    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws, timezone="UTC")
        s.add(Task(workspace_id=ws, title="Something worth reporting", status="done"))
        s.flush()
        h.handle_review_due(s, {"workflowId": wf.id,
                                "reportingDate": date.today().isoformat()})

    with session_scope(eng) as s:
        notes = [e for e in s.query(Event).filter_by(workspace_id=ws).all()
                 if (e.payload_json or {}).get("type") == "standup.review_due"]
    assert notes, "the user is never told the draft is ready"
    assert notes[0].payload_json["link"] == "#/standup"


def test_a_disabled_workflow_stops_scheduling_itself():
    from daypilot_orchestrator.standup import handlers as h

    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws, timezone="UTC")
        service.update_workflow(s, ws, wf.id, {"enabled": False})
        out = h.handle_review_due(s, {"workflowId": wf.id,
                                      "reportingDate": date.today().isoformat()})
        assert out["skipped"] == "workflow_disabled"
        assert wf.next_review_at is None


def test_editing_the_workflow_does_not_leave_two_review_jobs_armed():
    """An afternoon of settings tweaks must not mean several drafts tonight."""
    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws, timezone="UTC")
        service.update_workflow(s, ws, wf.id, {"reviewTime": "17:30"})
        service.update_workflow(s, ws, wf.id, {"reviewTime": "18:30"})

        queued = [j for j in s.query(Job).filter_by(workspace_id=ws,
                                                    kind="standup.review_due").all()
                  if j.state == "queued"]
        assert len(queued) == 1
        assert queued[0].payload_json["workflowId"] == wf.id


def test_a_worker_pass_runs_the_whole_day_end_to_end(monkeypatch):
    """Review job → draft → approval → delivery job → posted, via the worker."""
    from daypilot_orchestrator.standup import handlers as h

    ws = _ws()
    eng = create_engine_from_settings()
    sent: list[dict] = []

    with session_scope(eng) as s:
        wf = _workflow(s, ws, timezone="UTC")
        s.add(Task(workspace_id=ws, title="Wire the standup worker", status="done"))
        s.flush()

        # The 18:00 job is armed for the future; run it as the worker would.
        h.handle_review_due(s, {"workflowId": wf.id,
                                "reportingDate": date.today().isoformat()})
        draft = s.query(StandupDraft).filter_by(workflow_id=wf.id).one()
        service.approve(s, wf, draft)
        assert draft.status == policy.WAITING_FOR_THREAD

        # The next-morning delivery job, executed through the worker's handler
        # map with Slack stubbed at the boundary.
        monkeypatch.setattr(h, "slack_sender",
                            lambda _s, _c: lambda p: sent.append(p) or {"ts": "5.0"})
        # A reminder posted at 09:00 UTC on the standup day the draft targets —
        # a stub outside that window is correctly refused by the resolver.
        reminder_utc = datetime.combine(
            date.fromisoformat(draft.target_standup_date), time(9, 0),
        )
        reminder_ts = f"{reminder_utc.replace(tzinfo=timezone.utc).timestamp():.6f}"
        monkeypatch.setattr(h, "slack_history_reader",
                            lambda _s, _c: (lambda *_a: [
                                {"ts": reminder_ts,
                                 "text": "Daily Standup Reminder", "botId": "B1"},
                            ]))
        handlers = h.build_handlers(s)
        # Make the queued delivery job due now.
        job = s.get(Job, draft.delivery_job_id)
        job.run_after = datetime.utcnow() - timedelta(seconds=1)
        s.flush()

        ran = _run_due_jobs(s, handlers)
        kinds = [j.kind for j in ran]
        assert "standup.deliver" in kinds
        assert all(j.state == "succeeded" for j in ran), [j.last_error for j in ran]

    assert len(sent) == 1
    assert sent[0]["threadTs"] == reminder_ts
    assert "Wire the standup worker" in sent[0]["text"]


def test_a_lapsed_schedule_is_re_armed_at_worker_start():
    """A deployment down over 18:00 would otherwise never schedule again."""
    from daypilot_orchestrator.standup import handlers as h

    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws, timezone="UTC")
        wf.next_review_at = datetime.utcnow() - timedelta(days=3)
        s.flush()

        assert h.bootstrap_schedules(s, workspace_id=ws) == 1
        assert wf.next_review_at > datetime.utcnow()

        # Already-armed workflows are left alone.
        assert h.bootstrap_schedules(s, workspace_id=ws) == 0


def test_the_worker_handles_exactly_the_kinds_the_scheduler_enqueues():
    """A kind with no handler dead-letters silently — the bug this batch fixes."""
    from daypilot_orchestrator.standup import handlers as h

    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        wf = _workflow(s, ws)
        draft = service.generate_draft(s, wf, date(2026, 8, 5))
        service.approve(s, wf, draft)

        enqueued = {j.kind for j in s.query(Job).filter_by(workspace_id=ws).all()}
        assert enqueued <= set(h.build_handlers(s)), (
            f"{enqueued - set(h.build_handlers(s))} would dead-letter"
        )


def test_the_worker_script_loops_and_survives_a_bad_pass():
    script = (Path(__file__).resolve().parents[1] / "scripts" / "standup_worker.py"
              ).read_text(encoding="utf-8")
    assert "--once" in script                    # cron-friendly
    assert "bootstrap_schedules" in script       # re-arms a lapsed schedule
    assert "LOG.exception(\"pass failed; continuing\")" in script
    assert "signal.SIGTERM" in script            # stops cleanly under a supervisor
