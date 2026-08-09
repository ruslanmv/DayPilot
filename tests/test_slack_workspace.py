"""The Slack communication workspace.

Most of this file exists to pin behaviour that is easy to regress *upward* —
towards an assistant that answers more, says more, and sends more. In order:

* the classifier's restraint ("thanks 👍" earns no draft),
* the difference between what a draft may read and what a recipient may hear,
* refinement that proposes instead of replacing,
* and the one that matters most: **nothing here can send a Slack message**.

The last one is asserted from several directions on purpose. A single test that
``send`` returns ``approval_required`` would still pass if some other path grew
the ability to post.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from daypilot_knowledge.db import (
    Approval,
    IntegrationConnection,
    Job,
    Project,
    SlackConversation,
    SlackDraft,
    SlackDraftRevision,
    SlackMessage,
    SlackPreferences,
    create_engine_from_settings,
    session_scope,
)
from daypilot_orchestrator.slack_workspace import (
    classify,
    compose,
    context,
    service,
    settings,
    transport,
)

client = TestClient(app)
ENGINE = create_engine_from_settings()
WS = "ws_slack_workspace"


@pytest.fixture()
def ws():
    """A workspace of its own, wiped before each test."""
    with session_scope(ENGINE) as s:
        for row in s.query(SlackDraft).filter_by(workspace_id=WS).all():
            for revision in s.query(SlackDraftRevision).filter_by(draft_id=row.id).all():
                s.delete(revision)
            s.delete(row)
        for model in (SlackMessage, SlackConversation, SlackPreferences,
                      IntegrationConnection, Project, Approval, Job):
            for row in s.query(model).filter_by(workspace_id=WS).all():
                s.delete(row)
    return WS


@pytest.fixture()
def enabled(monkeypatch):
    monkeypatch.setenv(service.FLAG, "1")
    return True


def _connect_slack(session, *, status: str = "connected") -> IntegrationConnection:
    row = IntegrationConnection(
        workspace_id=WS, provider="slack", status=status, auth_type="oauth",
        capabilities=["chat.read", "chat.send"], detail="ruslan@example.com",
    )
    session.add(row)
    session.flush()
    return row


def _ingest(session, text: str, *, kind: str = "im", channel: str = "D001",
            audience: str = "internal", mentioned: bool = False) -> dict:
    return service.ingest(session, WS, {
        "channel": channel, "channelKind": kind, "ts": f"{time.time():.6f}",
        "user": "U123", "userName": "Jane Smith", "text": text,
        "audience": audience, "mentioned": mentioned,
    })


# --- restraint ----------------------------------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("thanks 👍", classify.ACKNOWLEDGEMENT),
    ("Thanks!", classify.ACKNOWLEDGEMENT),
    ("lgtm", classify.ACKNOWLEDGEMENT),
    ("Good morning everyone", classify.SOCIAL),
    ("FYI we shipped the migration last night", classify.FYI),
    ("Can you review PR #142 today?", classify.ACTION_REQUIRED),
    ("Should we go with Option B or wait?", classify.DECISION_REQUESTED),
    ("Do you think we can deliver the Alpha API changes before Thursday?",
     classify.NEEDS_REPLY),
    ("build failed on main", classify.LOW_PRIORITY),
])
def test_classifier_labels(text, expected):
    assert classify.classify(text) == expected


def test_thanks_followed_by_a_request_is_still_a_request():
    """The anchored acknowledgement match is what keeps this from being missed."""
    assert classify.classify("thanks — can you also review the PR?") == classify.ACTION_REQUIRED


def test_only_three_labels_earn_a_draft():
    drafted = {c for c in classify.CLASSIFICATIONS if classify.should_draft(c)}
    assert drafted == {classify.NEEDS_REPLY, classify.ACTION_REQUIRED,
                       classify.DECISION_REQUESTED}


def test_acknowledgements_do_not_earn_a_draft(ws):
    with session_scope(ENGINE) as s:
        result = _ingest(s, "thanks 👍")
    assert result["status"] == "traced"
    assert result["reason"] == "no_reply_needed"
    with session_scope(ENGINE) as s:
        assert s.query(SlackDraft).filter_by(workspace_id=WS).count() == 0


def test_a_real_question_does_earn_a_draft(ws):
    with session_scope(ENGINE) as s:
        result = _ingest(s, "Can you review PR #142 today? It's blocking deployment.")
    assert result["status"] == "drafted"
    with session_scope(ENGINE) as s:
        draft = s.query(SlackDraft).filter_by(workspace_id=WS).one()
        assert draft.status == service.DRAFT
        assert draft.text.strip()


def test_auto_prepare_off_traces_without_drafting(ws):
    with session_scope(ENGINE) as s:
        settings.update_preferences(s, WS, {"autoPrepare": False})
    with session_scope(ENGINE) as s:
        result = _ingest(s, "Can you review PR #142 today?")
    assert result["reason"] == "auto_prepare_off"


def test_busy_channel_messages_are_out_of_drafting_scope_by_default(ws):
    """A channel you are not named in is noise until you say otherwise."""
    with session_scope(ENGINE) as s:
        result = _ingest(s, "Can someone review PR #142 today?",
                         kind="channel", channel="C900")
    assert result["reason"] == "not_in_drafting_scope"

    with session_scope(ENGINE) as s:
        settings.update_preferences(s, WS, {"draftAllChannelMessages": True})
    with session_scope(ENGINE) as s:
        result = _ingest(s, "Can someone review PR #143 today?",
                         kind="channel", channel="C900")
    assert result["status"] == "drafted"


def test_a_message_is_traced_once(ws):
    payload = {
        "channel": "D001", "channelKind": "im", "ts": "1717171717.000100",
        "user": "U123", "userName": "Jane Smith", "text": "Any update?",
    }
    with session_scope(ENGINE) as s:
        first = service.ingest(s, WS, payload)
    with session_scope(ENGINE) as s:
        second = service.ingest(s, WS, payload)
    assert first["status"] == "drafted"
    assert second["status"] == "duplicate"


# --- what may be read vs what may be said -------------------------------------


def _project(session) -> Project:
    row = Project(
        workspace_id=WS, name="Project Alpha", progress=70,
        next_human_action="Approve the API contract",
        blocked=["Security review of the auth change"],
        ai_activity="drafting the migration plan",
    )
    session.add(row)
    session.flush()
    return row


def test_internal_facts_are_withheld_from_an_external_recipient(ws):
    """The recipient filter runs before generation, so the fact never reaches it."""
    with session_scope(ENGINE) as s:
        _project(s)
        conversation = service.upsert_conversation(
            s, WS, channel_id="D-EXT", kind="im",
            counterpart="Customer", audience="external",
        )
        draft = service.prepare_draft(
            s, WS, conversation=conversation,
            instruction="Project Alpha delivery date",
        )
        text = draft.text
        withheld = list(draft.withheld_json)

    assert "drafting the migration plan" not in text
    assert withheld, "an internal fact should have been recorded as withheld"
    # The record says *that* something was withheld and from where, never what —
    # storing the text would put the redacted content straight back on the draft.
    for entry in withheld:
        assert set(entry) == {"source", "audience"}
        assert "migration plan" not in json.dumps(entry)


def test_the_same_facts_survive_for_an_internal_recipient(ws):
    with session_scope(ENGINE) as s:
        _project(s)
        conversation = service.upsert_conversation(
            s, WS, channel_id="D-INT", kind="im",
            counterpart="Elena", audience="internal",
        )
        draft = service.prepare_draft(
            s, WS, conversation=conversation,
            instruction="Project Alpha delivery date",
        )
        assert draft.withheld_json == []
        assert "Project Alpha" in draft.text


def test_recipient_protection_can_be_switched_off_but_is_on_by_default(ws):
    with session_scope(ENGINE) as s:
        assert settings.get_preferences(s, WS).recipient_protection is True


def test_a_source_the_workspace_did_not_grant_is_never_consulted(ws):
    """Not gathered and then dropped — never fetched. The cheapest guarantee."""
    with session_scope(ENGINE) as s:
        project = _project(s)
        sources, resolved = context.assemble(
            s, WS, text="Project Alpha update", allowed_sources={"conversation"},
        )
        assert resolved is None
        assert all(s_.type != "project" for s_ in sources)
        assert project.name not in json.dumps([s_.serialize() for s_ in sources])


def test_a_context_source_needs_its_integration_connected(ws):
    with session_scope(ENGINE) as s:
        settings.update_preferences(s, WS, {
            "contextSources": ["projects", "github", "email"],
        })
        # Intent ∩ connected reality. Granting GitHub context means nothing
        # while GitHub is not connected.
        assert "github" not in settings.allowed_context_sources(s, WS, set())
        assert "github" in settings.allowed_context_sources(s, WS, {"github"})


def test_the_conversation_source_cannot_be_switched_off(ws):
    with session_scope(ENGINE) as s:
        row = settings.update_preferences(s, WS, {"contextSources": []})
        assert "conversation" in row.context_sources


def test_unknown_context_sources_are_dropped_rather_than_stored():
    assert settings.normalize_sources(["projects", "not_a_source"]) == [
        "conversation", "projects",
    ]


def test_an_invalid_access_mode_is_rejected(ws):
    with session_scope(ENGINE) as s:
        with pytest.raises(settings.InvalidSetting):
            settings.update_preferences(s, WS, {"accessMode": "impersonate"})


# --- drafting, refining, undoing ----------------------------------------------


def test_the_destination_changes_the_register(ws):
    """A DM and a 38-person channel are not the same message."""
    with session_scope(ENGINE) as s:
        _project(s)
        dm = service.upsert_conversation(s, WS, channel_id="D-A", kind="im",
                                         counterpart="Jane Smith")
        channel = service.upsert_conversation(s, WS, channel_id="C-A", kind="channel",
                                              name="#platform")
        dm_draft = service.prepare_draft(s, WS, conversation=dm,
                                         instruction="Project Alpha status")
        channel_draft = service.prepare_draft(s, WS, conversation=channel,
                                              instruction="Project Alpha status")
    assert dm_draft.text.startswith("Hi Jane")
    assert channel_draft.text.startswith("Update:")


#: The four quick rewrites, with a sample that each one visibly changes.
_TRANSFORM_CASES = {
    "shorter": ("I think we can ship Friday. The API work is done. Security is pending.",
                lambda out: len(out) < 60),
    "direct": ("I think we can ship Friday. Let me know if you need more detail.",
               lambda out: "I think" not in out),
    "detailed": ("We can ship Friday.",
                 lambda out: "Happy to walk through" in out),
    "friendly": ("We can ship Friday.",
                 lambda out: out.startswith("Hi — ")),
}


def test_the_composer_offers_exactly_four_transforms():
    assert compose.TRANSFORMS == ("shorter", "direct", "detailed", "friendly")


@pytest.mark.parametrize("kind", compose.TRANSFORMS)
def test_each_quick_transform_does_what_its_label_says(kind):
    text, holds = _TRANSFORM_CASES[kind]
    assert holds(compose.transform(text, kind))


def test_a_transform_is_persisted_as_an_undoable_revision(ws):
    with session_scope(ENGINE) as s:
        conversation = service.upsert_conversation(s, WS, channel_id="D-T", kind="im",
                                                   counterpart="Jane Smith")
        draft = service.prepare_draft(s, WS, conversation=conversation)
        service.update_text(s, draft, _TRANSFORM_CASES["direct"][0])
        before = draft.text
        service.apply_transform(s, draft, "direct")
        assert draft.text != before
        service.undo(s, draft)
        assert draft.text == before


def test_an_unknown_transform_is_refused(ws):
    with session_scope(ENGINE) as s:
        conversation = service.upsert_conversation(s, WS, channel_id="D-U", kind="im")
        draft = service.prepare_draft(s, WS, conversation=conversation)
        with pytest.raises(ValueError):
            service.apply_transform(s, draft, "make it rhyme")


def test_refinement_proposes_without_replacing_the_draft(ws):
    """The whole difference between a tool you experiment with and one you watch."""
    with session_scope(ENGINE) as s:
        _project(s)
        conversation = service.upsert_conversation(s, WS, channel_id="D-R", kind="im",
                                                   counterpart="Jane Smith")
        draft = service.prepare_draft(s, WS, conversation=conversation,
                                      instruction="Project Alpha status")
        original = draft.text
        proposal = service.propose_refinement(draft, "make it shorter and more direct")

    assert proposal["proposed"] != original
    assert proposal["current"] == original
    with session_scope(ENGINE) as s:
        assert s.get(SlackDraft, draft.id).text == original


def test_use_this_keeps_the_old_text_so_undo_works(ws):
    with session_scope(ENGINE) as s:
        _project(s)
        conversation = service.upsert_conversation(s, WS, channel_id="D-V", kind="im",
                                                   counterpart="Jane Smith")
        draft = service.prepare_draft(s, WS, conversation=conversation,
                                      instruction="Project Alpha status")
        original = draft.text
        service.accept_refinement(s, draft, "A completely rewritten reply.", "be terse")
        draft_id = draft.id

    with session_scope(ENGINE) as s:
        draft = s.get(SlackDraft, draft_id)
        assert draft.text == "A completely rewritten reply."
        service.undo(s, draft)
        assert draft.text == original


def test_undo_on_an_untouched_draft_is_a_no_op(ws):
    with session_scope(ENGINE) as s:
        conversation = service.upsert_conversation(s, WS, channel_id="D-N", kind="im")
        draft = service.prepare_draft(s, WS, conversation=conversation)
        before = draft.text
        service.undo(s, draft)
        assert draft.text == before


def test_refine_softens_a_commitment_rather_than_deleting_the_answer():
    text = "Hi Jane,\n\nWe will ship on Friday.\n\nLet me know if you need more detail."
    out = compose.refine(text, "don't promise a date")
    assert "We will ship" not in out
    assert "aiming to" in out


def test_a_project_is_found_by_a_distinctive_word_from_its_name(ws):
    """People say "the Alpha API changes", not "Client Alpha"."""
    with session_scope(ENGINE) as s:
        s.add(Project(workspace_id=WS, name="Client Alpha", progress=70))
        s.flush()
        sources, project = context.assemble(
            s, WS, text="Can we deliver the Alpha API changes before Thursday?",
            allowed_sources={"projects"},
        )
        assert project is not None and project.name == "Client Alpha"
        assert any(src.type == "project" for src in sources)


def test_a_generic_mention_does_not_attach_a_project(ws):
    """"Any update on the project?" must not pull one at random."""
    with session_scope(ENGINE) as s:
        s.add(Project(workspace_id=WS, name="Client Alpha", progress=70))
        s.flush()
        _sources, project = context.assemble(
            s, WS, text="Any update on the project?", allowed_sources={"projects"},
        )
        assert project is None


def test_a_draft_presents_evidence_rather_than_answering_what_it_cannot_know(ws):
    """Asked "can we ship by Thursday?", DayPilot does not assert a date.

    It knows what is in flight and what is blocked. It does not know the answer,
    and a draft that confidently supplies one is the failure this whole feature
    is meant to avoid.
    """
    with session_scope(ENGINE) as s:
        _project(s)
        conversation = service.upsert_conversation(
            s, WS, channel_id="D-E1", kind="im", counterpart="Jane Smith")
        draft = service.prepare_draft(
            s, WS, conversation=conversation,
            instruction="Can we deliver the Project Alpha API changes before Thursday?")
        text = draft.text

    assert text.startswith("Hi Jane,")
    assert "Here's where things stand:" in text
    assert "•" in text  # evidence is listed, not welded into a sentence
    assert "I'll confirm" in text
    for promise in ("Yes,", "we can deliver", "achievable"):
        assert promise not in text, promise


def test_a_draft_with_no_facts_says_so_instead_of_inventing_an_answer():
    empty = context.SlackContext(sources=[], withheld=[])
    assert "don't have anything solid" in compose.draft_text(empty)


# --- the invariant: nothing sends ---------------------------------------------


def test_send_opens_an_approval_and_does_not_post(ws):
    with session_scope(ENGINE) as s:
        _connect_slack(s)
        conversation = service.upsert_conversation(s, WS, channel_id="D-S", kind="im",
                                                   counterpart="Jane Smith")
        draft = service.prepare_draft(s, WS, conversation=conversation,
                                      instruction="status")
        result = service.send(s, WS, draft)
        assert result["status"] == "approval_required"
        assert draft.status == service.SENDING
        assert draft.sent_ts is None

    with session_scope(ENGINE) as s:
        approval = s.query(Approval).filter_by(workspace_id=WS).one()
        assert approval.status == "pending"
        assert approval.action == "slack.chat.send"


def test_ingest_never_produces_a_send(ws):
    """Inbound events prepare; they do not reply."""
    with session_scope(ENGINE) as s:
        _connect_slack(s)
        _ingest(s, "Can you review PR #142 today? It's blocking deployment.")
    with session_scope(ENGINE) as s:
        assert s.query(Approval).filter_by(workspace_id=WS).count() == 0
        assert s.query(SlackDraft).filter_by(workspace_id=WS).one().status == service.DRAFT


def test_refinement_and_transforms_never_produce_a_send(ws):
    with session_scope(ENGINE) as s:
        _connect_slack(s)
        conversation = service.upsert_conversation(s, WS, channel_id="D-Q", kind="im")
        draft = service.prepare_draft(s, WS, conversation=conversation, instruction="hi")
        service.apply_transform(s, draft, "shorter")
        service.propose_refinement(draft, "make it friendlier")
        service.accept_refinement(s, draft, "Friendlier text.", "friendlier")
        service.undo(s, draft)
    with session_scope(ENGINE) as s:
        assert s.query(Approval).filter_by(workspace_id=WS).count() == 0


def test_there_is_no_auto_send_setting():
    """A column would imply the invariant could be turned off."""
    columns = set(SlackPreferences.__table__.columns.keys())
    assert not [c for c in columns if "auto_send" in c or "autosend" in c]
    serialized = settings.serialize(SlackPreferences(workspace_id=WS, context_sources=[]))
    assert serialized["neverAutomaticallySend"] is True


def test_sending_without_a_connection_is_refused(ws):
    with session_scope(ENGINE) as s:
        conversation = service.upsert_conversation(s, WS, channel_id="D-X", kind="im")
        draft = service.prepare_draft(s, WS, conversation=conversation, instruction="hi")
        with pytest.raises(service.NotConnected):
            service.send(s, WS, draft)


def test_a_discarded_draft_cannot_be_edited_or_sent(ws):
    with session_scope(ENGINE) as s:
        _connect_slack(s)
        conversation = service.upsert_conversation(s, WS, channel_id="D-D", kind="im")
        draft = service.prepare_draft(s, WS, conversation=conversation, instruction="hi")
        service.discard(s, draft)
        with pytest.raises(service.DraftLocked):
            service.update_text(s, draft, "changed my mind")
        with pytest.raises(service.DraftLocked):
            service.send(s, WS, draft)


def test_an_empty_draft_is_never_sent(ws):
    with session_scope(ENGINE) as s:
        _connect_slack(s)
        conversation = service.upsert_conversation(s, WS, channel_id="D-E", kind="im")
        draft = service.prepare_draft(s, WS, conversation=conversation, instruction="hi")
        service.update_text(s, draft, "   ")
        with pytest.raises(ValueError):
            service.send(s, WS, draft)


# --- transport ----------------------------------------------------------------


def _sign(body: bytes, secret: str, timestamp: str) -> str:
    base = b"v0:" + timestamp.encode() + b":" + body
    return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


def test_a_correctly_signed_event_is_accepted():
    body, secret, ts = b'{"type":"event_callback"}', "s3cr3t", str(int(time.time()))
    transport.verify_signature(
        body,
        {"X-Slack-Signature": _sign(body, secret, ts), "X-Slack-Request-Timestamp": ts},
        secret=secret,
    )


def test_a_forged_signature_is_rejected():
    body, ts = b'{"type":"event_callback"}', str(int(time.time()))
    with pytest.raises(transport.UntrustedEvent):
        transport.verify_signature(
            body,
            {"X-Slack-Signature": _sign(body, "wrong", ts),
             "X-Slack-Request-Timestamp": ts},
            secret="s3cr3t",
        )


def test_a_replayed_event_is_rejected():
    body, secret = b'{"type":"event_callback"}', "s3cr3t"
    ts = str(int(time.time()) - transport.REPLAY_WINDOW_SECONDS - 60)
    with pytest.raises(transport.UntrustedEvent):
        transport.verify_signature(
            body,
            {"X-Slack-Signature": _sign(body, secret, ts),
             "X-Slack-Request-Timestamp": ts},
            secret=secret,
        )


def test_an_unconfigured_signing_secret_refuses_everything():
    """Accepting unsigned events "until it is set up" ships an open relay."""
    with pytest.raises(transport.UntrustedEvent):
        transport.verify_signature(b"{}", {}, secret="")


@pytest.mark.parametrize("event", [
    {"type": "message", "subtype": "channel_join", "channel": "C1", "ts": "1", "text": "x"},
    {"type": "message", "bot_id": "B1", "channel": "C1", "ts": "1", "text": "deployed"},
    {"type": "reaction_added", "channel": "C1", "ts": "1"},
])
def test_channel_bookkeeping_is_not_a_message(event):
    assert transport.normalize({"event": event}) is None


def test_our_own_posts_are_not_traced_as_incoming():
    event = {"type": "message", "channel": "C1", "ts": "1", "user": "UBOT", "text": "hi"}
    assert transport.normalize({"event": event}, bot_user_id="UBOT") is None


def test_a_mention_is_normalized_as_mentioned():
    normalized = transport.normalize({"event": {
        "type": "app_mention", "channel": "C1", "ts": "1.0", "user": "U1",
        "text": "<@UBOT> can you review PR #142?",
    }})
    assert normalized["mentioned"] is True
    assert normalized["channelKind"] == "channel"


# --- the HTTP surface ---------------------------------------------------------


def test_with_the_flag_off_only_status_answers(monkeypatch, ws):
    monkeypatch.delenv(service.FLAG, raising=False)
    status = client.get("/v1/slack/status", params={"workspaceId": WS})
    assert status.status_code == 200
    assert status.json()["enabled"] is False
    for path in ("/v1/slack/inbox", "/v1/slack/settings", "/v1/slack/recipients"):
        response = client.get(path, params={"workspaceId": WS})
        assert response.status_code == 404, path
        assert response.json()["detail"]["error"] == "slack_workspace_disabled"


def test_status_reports_that_sends_require_approval(ws, enabled):
    body = client.get("/v1/slack/status", params={"workspaceId": WS}).json()
    assert body["enabled"] is True
    assert body["sendsRequireApproval"] is True
    assert "transport" in body["delivery"]


def test_settings_ship_the_source_catalogue_with_availability(ws, enabled):
    body = client.get("/v1/slack/settings", params={"workspaceId": WS}).json()
    by_id = {s["id"]: s for s in body["sources"]}
    assert by_id["conversation"]["alwaysOn"] is True
    # Not connected, so not offered as usable — the browser is told, not left to
    # guess from an empty result later.
    assert by_id["github"]["available"] is False
    assert body["settings"]["neverAutomaticallySend"] is True


def test_settings_round_trip_over_http(ws, enabled):
    response = client.put(
        "/v1/slack/settings", params={"workspaceId": WS},
        json={"draftAllChannelMessages": True, "contextSources": ["projects"],
              "accessMode": "personal"},
    )
    assert response.status_code == 200
    stored = response.json()["settings"]
    assert stored["draftAllChannelMessages"] is True
    assert stored["contextSources"] == ["conversation", "projects"]
    assert stored["accessMode"] == "personal"


def test_an_unknown_access_mode_is_a_400(ws, enabled):
    response = client.put("/v1/slack/settings", params={"workspaceId": WS},
                          json={"accessMode": "impersonate"})
    assert response.status_code == 400


def test_the_inbox_groups_and_counts(ws, enabled):
    with session_scope(ENGINE) as s:
        _ingest(s, "Can you review PR #142 today?", channel="D-1")
        _ingest(s, "thanks 👍", channel="D-2")
        _ingest(s, "Should we go with Option B?", channel="D-3")

    body = client.get("/v1/slack/inbox", params={"workspaceId": WS}).json()
    assert body["counts"]["action"] == 2  # action_required + decision_requested
    assert body["counts"]["fyi"] == 1
    assert len(body["items"]) == 3

    only_action = client.get("/v1/slack/inbox",
                             params={"workspaceId": WS, "group": "action"}).json()
    assert {item["group"] for item in only_action["items"]} == {"action"}


def test_marking_a_message_done_is_reversible(ws, enabled):
    with session_scope(ENGINE) as s:
        _ingest(s, "Can you review PR #142 today?", channel="D-1")
        message_id = s.query(SlackMessage).filter_by(workspace_id=WS).one().id

    assert client.post(f"/v1/slack/messages/{message_id}/handled",
                       json={"handled": True}).json()["handled"] is True
    assert client.get("/v1/slack/inbox",
                      params={"workspaceId": WS}).json()["counts"]["done"] == 1
    assert client.post(f"/v1/slack/messages/{message_id}/handled",
                       json={"handled": False}).json()["handled"] is False


def test_compose_a_new_message_over_http(ws, enabled):
    response = client.post("/v1/slack/compose", json={
        "workspaceId": WS, "channelId": "D-NEW", "kind": "im",
        "counterpart": "Elena Garcia", "instruction": "ask about PR #142",
    })
    assert response.status_code == 201
    body = response.json()
    assert body["draft"]["kind"] == "compose"
    assert body["draft"]["sendsRequireApproval"] is True
    assert body["conversation"]["counterpart"] == "Elena Garcia"


def test_compose_without_a_recipient_is_a_400(ws, enabled):
    assert client.post("/v1/slack/compose", json={"workspaceId": WS}).status_code == 400


def test_the_draft_lifecycle_over_http(ws, enabled):
    with session_scope(ENGINE) as s:
        _project(s)
        _connect_slack(s)
        _ingest(s, "Can you review Project Alpha's API contract today?", channel="D-L")
        draft_id = s.query(SlackDraft).filter_by(workspace_id=WS).one().id

    original = client.get(f"/v1/slack/drafts/{draft_id}").json()["text"]

    proposal = client.post(f"/v1/slack/drafts/{draft_id}/refine",
                           json={"instruction": "make it shorter"}).json()
    assert proposal["changed"] is True
    # /refine must not have touched the stored draft.
    assert client.get(f"/v1/slack/drafts/{draft_id}").json()["text"] == original

    accepted = client.post(f"/v1/slack/drafts/{draft_id}/accept",
                           json={"text": proposal["proposed"],
                                 "instruction": "make it shorter"}).json()
    assert accepted["text"] == proposal["proposed"]

    assert client.post(f"/v1/slack/drafts/{draft_id}/undo").json()["text"] == original

    sent = client.post(f"/v1/slack/drafts/{draft_id}/send",
                       json={"workspaceId": WS}).json()
    assert sent["status"] == "approval_required"
    assert sent["approvalId"]

    # And once it is on its way to an approval, editing it is a conflict.
    assert client.post(f"/v1/slack/drafts/{draft_id}/transform",
                       json={"kind": "shorter"}).status_code == 200


def test_a_sent_draft_is_locked(ws, enabled):
    with session_scope(ENGINE) as s:
        conversation = service.upsert_conversation(s, WS, channel_id="D-Z", kind="im")
        draft = service.prepare_draft(s, WS, conversation=conversation, instruction="hi")
        draft.status = service.SENT
        draft_id = draft.id
    assert client.patch(f"/v1/slack/drafts/{draft_id}",
                        json={"text": "late edit"}).status_code == 409


def test_the_events_endpoint_answers_the_url_verification_challenge(ws, enabled,
                                                                    monkeypatch):
    secret = "s3cr3t"
    monkeypatch.setenv("SLACK_SIGNING_SECRET", secret)
    payload = json.dumps({"type": "url_verification", "challenge": "abc123"}).encode()
    ts = str(int(time.time()))
    response = client.post(
        "/v1/slack/events", content=payload,
        headers={"Content-Type": "application/json",
                 "X-Slack-Request-Timestamp": ts,
                 "X-Slack-Signature": _sign(payload, secret, ts)},
    )
    assert response.json() == {"challenge": "abc123"}


def test_an_unsigned_event_is_rejected(ws, enabled, monkeypatch):
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "s3cr3t")
    response = client.post("/v1/slack/events", json={"type": "url_verification"})
    assert response.status_code == 401


def test_a_signed_message_event_is_traced_and_drafted(ws, enabled, monkeypatch):
    secret = "s3cr3t"
    monkeypatch.setenv("SLACK_SIGNING_SECRET", secret)
    payload = json.dumps({
        "workspaceId": WS, "type": "event_callback",
        "event": {"type": "message", "channel_type": "im", "channel": "D-EV",
                  "ts": "1717171717.000200", "user": "U9",
                  "text": "Can you review PR #142 today?"},
    }).encode()
    ts = str(int(time.time()))
    response = client.post(
        "/v1/slack/events", content=payload,
        headers={"Content-Type": "application/json",
                 "X-Slack-Request-Timestamp": ts,
                 "X-Slack-Signature": _sign(payload, secret, ts)},
    )
    assert response.json()["status"] == "drafted"
    with session_scope(ENGINE) as s:
        # Traced and drafted — and still not sent.
        assert s.query(Approval).filter_by(workspace_id=WS).count() == 0
