#!/usr/bin/env python3
"""Seed a connected Slack workspace and a morning's worth of conversations.

Everything here goes through the real pipeline —
:func:`daypilot_orchestrator.slack_workspace.service.ingest` — rather than
writing rows directly. That matters for a screenshot: the classifications, the
"Draft ready" badges and the provenance chips are produced by the same code the
product runs, so an image can never show a state the product cannot reach.

It also means the restraint is visible. Five conversations arrive; two earn a
draft. "Deployed to staging 👍" gets a row and nothing else, because that is
what the classifier decides — not because the seed data was curated to look
modest.

No credentials are written. Runs against whatever DATABASE_URL is set.
"""
from datetime import datetime, timedelta

from daypilot_knowledge.db import (
    IntegrationConnection,
    Project,
    SlackConversation,
    SlackDraft,
    SlackMessage,
    create_engine_from_settings,
    session_scope,
)
from daypilot_orchestrator.slack_workspace import service, settings

WS = "default"

#: The morning, in the order it happened. `mentioned` and `audience` are the two
#: inputs that change what DayPilot does, so they are stated rather than implied.
MORNING = [
    {
        "channel": "D07JANE", "channelKind": "im", "userName": "Jane Smith",
        "user": "U07JANE", "minutes_ago": 96, "audience": "internal",
        "text": ("Do you think we can deliver the Alpha API changes before Thursday? "
                 "The customer wants to test Friday morning."),
    },
    {
        "channel": "C01PLAT", "channelKind": "channel", "channelName": "#platform",
        "userName": "Marco Bianchi", "user": "U03MARCO", "minutes_ago": 83,
        "memberCount": 38, "mentioned": True, "audience": "internal",
        "text": ("@Ruslan should we move forward with Option B or wait for tomorrow's "
                 "architecture meeting?"),
    },
    {
        "channel": "D09ELENA", "channelKind": "im", "userName": "Elena Garcia",
        "user": "U09ELENA", "minutes_ago": 121, "audience": "internal",
        "text": ("Could you review PR #142 today if you have a moment? It's blocking "
                 "tomorrow's deployment."),
    },
    {
        "channel": "C02ALPHA", "channelKind": "channel", "channelName": "#alpha-project",
        "userName": "Sofia Rinaldi", "user": "U11SOFIA", "minutes_ago": 153,
        "memberCount": 12, "audience": "internal",
        "text": "FYI — posting the EOD update here later. Deployment plan is unchanged.",
    },
    {
        "channel": "D12DAVID", "channelKind": "im", "userName": "David Rossi",
        "user": "U12DAVID", "minutes_ago": 170, "audience": "internal",
        "text": "Deployed to staging 👍",
    },
]


def seed() -> None:
    engine = create_engine_from_settings()
    now = datetime.utcnow()

    with session_scope(engine) as s:
        # Start from nothing so re-running the capture is idempotent.
        for row in s.query(SlackDraft).filter_by(workspace_id=WS).all():
            s.delete(row)
        for model in (SlackMessage, SlackConversation):
            for row in s.query(model).filter_by(workspace_id=WS).all():
                s.delete(row)
        s.flush()

        connection = (
            s.query(IntegrationConnection).filter_by(workspace_id=WS, provider="slack").first()
        )
        if connection is None:
            connection = IntegrationConnection(workspace_id=WS, provider="slack")
            s.add(connection)
        connection.status = "connected"
        connection.auth_type = "oauth"
        connection.capabilities = ["chat.read", "chat.history", "chat.send"]
        connection.detail = "ruslan@example.com"
        connection.last_activity_at = now
        s.flush()

        # Every context source the seeded workspace can actually serve. GitHub
        # and email stay out: nothing is connected to back them, and the panel
        # is more honest showing one source unavailable than all of them on.
        settings.update_preferences(s, WS, {
            "contextSources": ["projects", "tasks", "calendar", "documents"],
            "autoPrepare": True,
        })

        connected = {"slack"}
        for raw in MORNING:
            payload = dict(raw)
            minutes = payload.pop("minutes_ago")
            occurred = now - timedelta(minutes=minutes)
            payload["ts"] = f"{occurred.timestamp():.6f}"
            payload.setdefault("mentioned", False)
            result = service.ingest(s, WS, payload, connected_providers=connected)

            # The ingest path stamps "now"; back-date it so the inbox reads as a
            # morning rather than five messages in the same second.
            message = s.get(SlackMessage, result["messageId"])
            if message is not None:
                message.occurred_at = occurred
                conversation = s.get(SlackConversation, message.conversation_id)
                if conversation is not None:
                    conversation.last_message_at = occurred
            print(f"  {payload['userName']:<14} {result['classification']:<19} {result['status']}")

        s.flush()
        drafted = s.query(SlackDraft).filter_by(workspace_id=WS).count()
        traced = s.query(SlackMessage).filter_by(workspace_id=WS).count()
        projects = s.query(Project).filter_by(workspace_id=WS).count()
        print(f"slack: {traced} traced, {drafted} drafted, {projects} projects for context")


if __name__ == "__main__":
    seed()
