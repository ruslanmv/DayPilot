"""What a Slack draft is allowed to know, and what it is allowed to say.

Two separate questions, and conflating them is the mistake this module exists to
prevent:

1. **May DayPilot read this?** — the workspace's context allow-list. Answered by
   :func:`assemble`.
2. **May this recipient be told it?** — answered by :func:`redact_for_recipient`.

They are not the same question. An internal email may say *"legal says don't
tell the customer until contract review finishes"*. DayPilot should read that —
it is exactly what stops the draft promising a date. But it must never appear in
a message to that customer. A model given the sentence and told "don't repeat
this" will eventually repeat it, so the sentence does not reach the model when
the recipient is external. The guarantee is structural, not instructional.

Facts therefore carry provenance **and** an audience. The filter runs before
generation, and what it removed is recorded on the draft so the redaction is
auditable rather than invisible.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import CodingRun, Document, Project, Task

#: Audience a fact may be shown to. `internal` facts never reach an external
#: recipient; `restricted` facts never reach anyone but the user.
AUDIENCE_ANYONE = "anyone"
AUDIENCE_INTERNAL = "internal"
AUDIENCE_RESTRICTED = "restricted"

_AUDIENCE_RANK = {AUDIENCE_ANYONE: 0, AUDIENCE_INTERNAL: 1, AUDIENCE_RESTRICTED: 2}

#: What the conversation's own audience permits.
_RECIPIENT_LIMIT = {
    "external": AUDIENCE_ANYONE,
    "internal": AUDIENCE_INTERNAL,
    "self": AUDIENCE_RESTRICTED,
}


@dataclass
class Fact:
    """One retrievable statement, with where it came from and who may hear it."""

    text: str
    audience: str = AUDIENCE_INTERNAL


@dataclass
class Source:
    """A place facts came from — what the UI shows as a provenance chip."""

    type: str
    label: str
    id: str = ""
    facts: list[Fact] = field(default_factory=list)

    def serialize(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "label": self.label,
            "facts": [f.text for f in self.facts],
        }


@dataclass
class SlackContext:
    """Everything a draft may use, already filtered for the recipient."""

    sources: list[Source] = field(default_factory=list)
    withheld: list[dict[str, str]] = field(default_factory=list)

    def serialize_sources(self) -> list[dict[str, Any]]:
        return [s.serialize() for s in self.sources if s.facts]

    def facts(self) -> list[str]:
        return [f.text for s in self.sources for f in s.facts]


def _mentions(text: str, needle: str) -> bool:
    return bool(needle) and needle.lower() in (text or "").lower()


#: Words that name no project on their own. A message mentioning "the project"
#: must not attach a project's facts to a reply about to be sent to someone.
_WEAK_TOKENS = frozenset({
    "project", "client", "team", "the", "and", "for", "with", "internal",
    "external", "new", "phase", "release", "platform", "service", "app",
})


def _project_for(session: Session, workspace_id: str, text: str) -> Project | None:
    """The project this conversation is about.

    A full-name match wins. Failing that, one distinctive word from the name is
    enough — people say "the Alpha API changes", not "Client Alpha". A word is
    distinctive if it is long enough and is not the kind of word every project
    name contains.

    Deliberately conservative past that point: guessing the wrong project would
    attach the wrong facts to a message about to be sent to a colleague, which is
    worse than attaching none. A tie is broken by the longer name, and a token
    match never beats a full-name match.
    """
    rows = session.execute(
        select(Project).where(Project.workspace_id == workspace_id)
    ).scalars().all()

    best: Project | None = None
    for row in rows:
        if _mentions(text, row.name) and (best is None or len(row.name) > len(best.name)):
            best = row
    if best is not None:
        return best

    for row in rows:
        tokens = [t for t in re.split(r"\W+", row.name or "")
                  if len(t) >= 5 and t.lower() not in _WEAK_TOKENS]
        if any(_mentions(text, token) for token in tokens):
            if best is None or len(row.name) > len(best.name):
                best = row
    return best


def _project_source(project: Project) -> Source:
    facts = [Fact(f"{project.name} is {project.progress}% complete")]
    if project.next_human_action:
        facts.append(Fact(f"Next action on {project.name}: {project.next_human_action}"))
    for blocker in list(project.blocked or [])[:2]:
        facts.append(Fact(f"{project.name} is blocked on {blocker}"))
    if project.ai_activity:
        # What an agent is doing right now is internal working state.
        facts.append(Fact(f"DayPilot is currently {project.ai_activity}", AUDIENCE_INTERNAL))
    return Source("project", project.name, project.id, facts)


def _relevant(title: str, text: str) -> bool:
    """Whether this record has anything to do with what was said.

    One distinctive word in common is the bar. Deliberately the same rule as
    project matching, and deliberately not "any word": *the* and *review* appear
    in everything.
    """
    tokens = [t for t in re.split(r"\W+", title or "")
              if len(t) >= 5 and t.lower() not in _WEAK_TOKENS]
    return any(_mentions(text, token) for token in tokens)


def _task_source(
    session: Session, workspace_id: str, project: Project | None, text: str = ""
) -> Source:
    """Open work, scoped to the conversation.

    With a project resolved, its tasks are the answer. Without one, only tasks
    the message actually names get in — an earlier version listed the four most
    recently touched tasks in the workspace, which put "Deep work · API gateway"
    into a draft reply about an architecture decision. Irrelevant evidence in a
    message you are about to post to thirty-eight people is worse than none.
    """
    stmt = select(Task).where(
        Task.workspace_id == workspace_id,
        Task.status.in_(("active", "running", "scheduled", "blocked", "needs_approval")),
    )
    if project is not None:
        stmt = stmt.where(Task.project_id == project.id)
    rows = session.execute(stmt.order_by(Task.updated_at.desc()).limit(8)).scalars().all()
    if project is None:
        rows = [r for r in rows if _relevant(r.title or "", text)]
    rows = rows[:4]

    facts = []
    for row in rows:
        title = (row.title or "").strip().rstrip(".")
        if not title:
            continue
        if row.status == "blocked":
            facts.append(Fact(f"{title} is blocked"))
        else:
            facts.append(Fact(f"{title} is in progress"))
    return Source("tasks", "Tasks", "", facts)


def _github_source(
    session: Session, workspace_id: str, project: Project | None, text: str = ""
) -> Source:
    stmt = select(CodingRun).where(CodingRun.workspace_id == workspace_id)
    if project is not None:
        stmt = stmt.where(CodingRun.project_id == project.id)
    row = session.execute(stmt.order_by(CodingRun.updated_at.desc()).limit(1)).scalars().first()
    if row is None:
        return Source("github", "GitHub", "", [])
    label = f"{row.repo} · {row.branch}" if row.branch else row.repo
    facts = [Fact(f"A change on {label} is {row.status.replace('_', ' ')}")]
    if row.diff_summary:
        facts.append(Fact(f"That change covers {row.diff_summary}", AUDIENCE_INTERNAL))
    return Source("github", label or "GitHub", row.id, facts)


def _document_source(
    session: Session, workspace_id: str, project: Project | None, text: str = ""
) -> Source:
    """Indexed documents, scoped the same way as tasks — see :func:`_task_source`."""
    stmt = select(Document).where(Document.status == "Indexed")
    if project is not None:
        stmt = stmt.where(Document.project_id == project.id)
    rows = [r for r in session.execute(stmt.limit(8)).scalars().all() if r.title]
    if project is None:
        rows = [r for r in rows if _relevant(r.title, text)]
    facts = [Fact(f"{r.title} is the reference document", AUDIENCE_INTERNAL)
             for r in rows[:3]]
    return Source("documents", "Documents", "", facts)


def _thread_source(recent: list[Any]) -> Source:
    """The conversation itself — always available, never a permission."""
    facts = [
        Fact(f"{m.author_name or 'They'} said: {m.text[:180]}", AUDIENCE_ANYONE)
        for m in recent[:3]
    ]
    return Source("conversation", "This Slack conversation", "", facts)


def _email_source(
    session: Session, workspace_id: str, project: Project | None, text: str = ""
) -> Source:
    """Email context is the sharpest example of read-but-do-not-repeat.

    DayPilot has no message store for mail yet, so this contributes the fact that
    a constraint exists rather than its wording — which is the behaviour we want
    even once it does.
    """
    if project is None or not (project.blocked or []):
        return Source("email", "Related email", "", [])
    return Source("email", "Related email", "", [
        Fact("A related email thread constrains what can be promised here",
             AUDIENCE_RESTRICTED),
    ])


#: source id -> builder. Ids match the allow-list stored in SlackPreferences.
BUILDERS = {
    "conversation": None,   # always on; built from the traced messages
    "projects": None,       # handled inline (needs the resolved project)
    "tasks": _task_source,
    "documents": _document_source,
    "github": _github_source,
    "email": _email_source,
}


def assemble(
    session: Session,
    workspace_id: str,
    *,
    text: str,
    recent_messages: list[Any] | None = None,
    allowed_sources: set[str] | None = None,
) -> tuple[list[Source], Project | None]:
    """Gather facts from the permitted sources only.

    A source the workspace has not granted is not consulted — it is not gathered
    and then dropped later, because the cheapest way to guarantee something never
    leaks is to never fetch it.
    """
    allowed = allowed_sources if allowed_sources is not None else set(BUILDERS)
    sources: list[Source] = [_thread_source(recent_messages or [])]

    project = _project_for(session, workspace_id, text) if "projects" in allowed else None
    if project is not None:
        sources.append(_project_source(project))

    for source_id, builder in BUILDERS.items():
        if builder is None or source_id not in allowed:
            continue
        sources.append(builder(session, workspace_id, project, text))

    return [s for s in sources if s.facts], project


def redact_for_recipient(
    sources: list[Source], audience: str, *, enabled: bool = True
) -> SlackContext:
    """Drop facts this recipient must not be told.

    Runs **before** generation. A fact removed here never reaches the model, so
    no amount of prompting or prompt injection can surface it — the alternative,
    handing the model everything with an instruction to be discreet, is a request
    rather than a guarantee.
    """
    limit = _AUDIENCE_RANK[_RECIPIENT_LIMIT.get(audience, AUDIENCE_INTERNAL)]
    kept: list[Source] = []
    withheld: list[dict[str, str]] = []
    for source in sources:
        allowed_facts, removed = [], []
        for fact in source.facts:
            if not enabled or _AUDIENCE_RANK.get(fact.audience, 1) <= limit:
                allowed_facts.append(fact)
            else:
                removed.append(fact)
        if allowed_facts:
            kept.append(Source(source.type, source.label, source.id, allowed_facts))
        for fact in removed:
            # Record that something was withheld and from where — never the text,
            # which would put the redacted content back into the draft record.
            withheld.append({"source": source.label, "audience": fact.audience})
    return SlackContext(sources=kept, withheld=withheld)


def freshness_window(hours: int = 48) -> datetime:
    """How far back "recent" reaches when pulling conversation history."""
    return datetime.utcnow() - timedelta(hours=hours)
