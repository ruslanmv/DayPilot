#!/usr/bin/env python3
"""Seed a demo workspace with HomePilot agents + a Scarlett conversation/tasks so
the agents UI renders like the product design for documentation screenshots.

Runs against whatever DATABASE_URL is set (a throwaway sqlite for shots). Uses
the real models + credential store, so it exercises the same read paths the app
uses — no fake API layer."""
from __future__ import annotations

import io
import os
import urllib.request
import uuid
import zipfile
from datetime import timedelta
from pathlib import Path

from daypilot_knowledge.db import (
    Approval, ChatMessage, ChatSession, HomePilotAgentLink, IntegrationConnection, Task,
    create_engine_from_settings, session_scope,
)
from daypilot_knowledge.db.models import utcnow
from daypilot_orchestrator.homepilot.hpersona import _blueprint_json, _embedded_avatar
from daypilot_orchestrator.integrations.credentials import credential_store

WS = "default"
CONN_ID = "demo-conn"

# Real personas from the HomePilot Community Gallery. The seed pulls each one's
# bundled portrait so the demo directory shows photos (the same path a live sync
# or an offline .hpersona import produces). `gallery` maps a demo agent to a
# gallery persona id; if the network is unavailable the agent falls back to
# initials, so the seed still runs fully offline.
GALLERY_BASE = "https://homepilot-persona-gallery.cloud-data.workers.dev"

AGENTS = [
    ("scarlett", "Scarlett", "Executive Secretary", "available",
     "Manages executive priorities, communications, and schedules.",
     ["Executive Support", "Scheduling", "Communications", "Email Drafting"],
     "scarlett_exec_secretary"),
    ("atlas", "Atlas", "Research Analyst", "busy",
     "Analyzes data, builds reports, and tracks market insights.",
     ["Research", "Reports", "Data"], "atlas_research_assistant"),
    ("nova", "Nova", "Project Coordinator", "working",
     "Keeps projects on track and teams aligned.",
     ["Projects", "Tasks", "Docs"], "felix_project_navigator"),
    ("ethan", "Ethan", "Financial Analyst", "available",
     "Monitors financials, forecasts, and prepares summaries.",
     ["Finance", "Reports", "Analytics"], "luca_calendar_strategist"),
    ("sofia", "Sofia", "Customer Success Manager", "available",
     "Supports clients, tracks health, and drives success.",
     ["Support", "CRM", "Feedback"], "priya_inbox_alchemist"),
    ("luna", "Luna", "Content Strategist", "busy",
     "Creates content plans, briefs, and brand messaging.",
     ["Content", "Strategy", "Docs"], "elena_knowledge_curator"),
    ("marcus", "Marcus", "IT Support Specialist", "working",
     "Resolves tech issues and manages systems.",
     ["IT Support", "Systems", "Security"], "soren_shell_operator"),
    ("iris", "Iris", "HR Coordinator", "available",
     "Handles recruitment, onboarding, and employee support.",
     ["HR", "Onboarding", "Policies"], "diana_office_navigator"),
]


def _package_bytes(persona_id: str) -> bytes | None:
    """A persona's .hpersona bytes — from the local cache dir if present (set
    SEED_PORTRAIT_DIR to a folder of ``<persona_id>.hpersona`` files for a fully
    offline, reproducible seed), else downloaded from the gallery."""
    cache = os.getenv("SEED_PORTRAIT_DIR")
    if cache:
        p = Path(cache) / f"{persona_id}.hpersona"
        if p.is_file():
            return p.read_bytes()
    url = f"{GALLERY_BASE}/p/{persona_id}/1.0.0"
    with urllib.request.urlopen(url, timeout=20) as r:  # noqa: S310 (trusted gallery host)
        return r.read()


def fetch_portrait(persona_id: str) -> str | None:
    """Return a gallery persona's portrait as a data URI, or None if unavailable.
    Reuses the importer's own extraction so the seed and the real import path
    stay in lock-step."""
    try:
        data = _package_bytes(persona_id)
        if not data:
            return None
        zf = zipfile.ZipFile(io.BytesIO(data))
        appearance = _blueprint_json(zf, "persona_appearance.json")
        uri, _ref, _thumb = _embedded_avatar(zf, set(zf.namelist()), appearance)
        return uri
    except Exception as exc:  # network/zip errors — fall back to initials
        print(f"  (portrait for {persona_id} unavailable: {exc})")
        return None


def main() -> None:
    eng = create_engine_from_settings()
    # A connected HomePilot connection so the workspace shows bridge mode, not degraded.
    credential_store().put(f"homepilot:{CONN_ID}", {
        "base_url": "https://homepilot.ruslanmv.com/api", "api_key": "demo",
        "account_ref": "user:demo", "account_label": "Jane Doe",
        "remote_kind": "cloud", "chat_mode": "bridge", "bridge_version": "1",
    })

    with session_scope(eng) as s:
        s.add(IntegrationConnection(id=CONN_ID, workspace_id=WS, provider="homepilot",
                                    status="connected", auth_type="api_key",
                                    capabilities=["homepilot.persona.chat"]))
        ids: dict[str, str] = {}
        portraits = 0
        for slug, name, role, status, desc, caps, persona_id in AGENTS:
            portrait = fetch_portrait(persona_id)
            portraits += 1 if portrait else 0
            snapshot = {"shared": True, "capabilities": caps}
            if portrait:
                snapshot["avatar_data_uri"] = portrait
            link = HomePilotAgentLink(
                id=slug, workspace_id=WS, connection_id=CONN_ID, account_ref="user:demo",
                homepilot_project_id=slug, homepilot_model_id=f"persona:{slug}",
                name=name, role=role, description=desc, capabilities_json=caps,
                enabled=True, status=status, favorite=(slug == "scarlett"),
                thumbnail_ref=("thumb.webp" if portrait else None),
                snapshot_json=snapshot,
                last_synced_at=utcnow(), last_seen_at=utcnow(),
            )
            s.add(link)
            ids[slug] = slug
        s.flush()

        # Scarlett conversation (mirrors the product design dialog).
        chat = ChatSession(workspace_id=WS, kind="agent", agent_link_id="scarlett",
                           title="Scarlett", remote_session_id=uuid.uuid4().hex,
                           remote_conversation_id="hp-conv-demo", message_count=6)
        s.add(chat)
        s.flush()
        turns = [
            ("assistant", "Good morning, Jane. I've reviewed your calendar and inbox. You have 3 high-priority items and 1 meeting starting at 10:00 AM. How can I help you today?"),
            ("user", "Prepare a client update for Acme Corp and draft a follow-up email. Include progress on the Q2 initiative and risks."),
            ("assistant", "On it. I'll draft the update and a follow-up email for your review. I'll delegate the data pull to Atlas to speed this up. You'll have drafts in your Approvals shortly."),
            ("user", "Also, schedule a check-in with the client for next Tuesday. Morning works best."),
            ("assistant", "Got it. I'll find available times and propose options. You'll see them in your Approvals."),
        ]
        base = utcnow() - timedelta(minutes=30)
        for i, (role, body) in enumerate(turns):
            s.add(ChatMessage(session_id=chat.id, role=role, body=body,
                              created_at=base + timedelta(minutes=i * 4)))

        # Scarlett tasks for the rail: active + waiting-for-approval + completed.
        def task(title, status, prio, pct, ctx="", cap=None, approval=None):
            return Task(workspace_id=WS, title=title, owner="agent", executor="Scarlett",
                        priority=prio, status=status, context=ctx, source="homepilot:Scarlett",
                        assigned_agent_link_id="scarlett", created_by_agent_link_id="scarlett",
                        progress_percent=pct, approval_id=approval,
                        remote_reference={"capability": cap, "lifecycle": (
                            "awaiting" if status == "waiting_for_approval" else
                            "completed" if status == "completed" else "executing")} if cap else {})

        s.add(task("Prepare Client Update for Acme Corp", "active", "high", 60,
                   "Drafting update and follow-up email"))
        s.add(task("Schedule client check-in", "active", "medium", 30, "Find times and propose options"))
        s.add(task("Organize leadership team meeting", "active", "medium", 20, "Agenda, materials, and invites"))

        for title, cap in [("Client Update briefing email", "email.send"),
                           ("Q2 initiative progress update", "document.generate")]:
            appr = Approval(workspace_id=WS, action=cap, summary=title, risk="medium",
                            status="pending", resource_type="task")
            s.add(appr)
            s.flush()
            t = task(title, "waiting_for_approval", "high", 0, "Drafted for your approval", cap, appr.id)
            s.add(t)
            s.flush()
            appr.resource_id = t.id

        s.add(task("Review inbox and flag priorities", "completed", "medium", 100))
        s.add(task("Pull Q2 data and risk summary", "completed", "medium", 100, cap="research"))

    print(f"seeded demo agents + Scarlett workspace ({portraits}/{len(AGENTS)} portraits)")
    # The agents screenshots exist to show portraits. A run that could not reach
    # the gallery still succeeds — but photographing it would replace the checked-in
    # images with initials circles, which is a regression nobody asked for and
    # nobody notices in a diff of PNGs. Say so in a way capture.sh can act on.
    if portraits == 0:
        print("PORTRAITS_UNAVAILABLE")
    return portraits


if __name__ == "__main__":
    main()
