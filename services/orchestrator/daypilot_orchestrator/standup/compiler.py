"""Turn evidence into the three sections, without inventing anything.

The compiler is deterministic and has no model call in it. That is deliberate:
a standup is a factual report about a specific person's day, posted publicly
under their name, and a generated sentence that overstates progress is worse
than a plain one that does not. Everything here is a rule over observed rows.

The rules it enforces, in order of importance:

1. A bullet exists only if evidence supports it (or the user wrote it).
2. "Completed" is only said when the source says completed. Anything still
   moving is "Continued work on …".
3. Blockers come from observable signals — a blocked task, a failed run, a
   pending approval — never from a guess about what might be hard.
4. Related evidence collapses into one outcome instead of one bullet per commit.
5. An empty day says so.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from . import policy
from .collector import BLOCKED, COMPLETED, MEETING, PLANNED, PROGRESS


@dataclass
class Bullet:
    """One line of the update, with the evidence that justifies it."""

    text: str
    evidence_ids: list[str] = field(default_factory=list)
    kind: str = policy.OBSERVED

    def as_dict(self) -> dict[str, Any]:
        return {"text": self.text, "evidenceIds": list(self.evidence_ids), "kind": self.kind}


@dataclass
class CompiledDraft:
    yesterday: list[Bullet]
    today: list[Bullet]
    blockers: list[Bullet]

    def provenance(self) -> dict[str, Any]:
        return {
            "yesterday": [b.as_dict() for b in self.yesterday],
            "today": [b.as_dict() for b in self.today],
            "blockers": [b.as_dict() for b in self.blockers],
        }


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with", "fix",
    "add", "update", "make", "use", "into", "from", "by", "at", "is", "be",
}


def _topic(summary: str) -> frozenset[str]:
    """The distinctive words of a summary, used to spot related work.

    Deliberately crude — this only has to notice that three commits and a task
    are about the same thing, not to understand them. Preserving the original
    words matters more than clever normalisation: the reader recognises their
    own project vocabulary.
    """
    words = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}", (summary or "").lower())
    return frozenset(w for w in words if w not in _STOPWORDS)


def _related(a: frozenset[str], b: frozenset[str]) -> bool:
    if not a or not b:
        return False
    overlap = len(a & b)
    return overlap >= 2 or (overlap == 1 and min(len(a), len(b)) <= 2)


def _group(rows: list[Any]) -> list[list[Any]]:
    """Cluster evidence about the same outcome, richest description first."""
    groups: list[tuple[frozenset[str], list[Any]]] = []
    for row in sorted(rows, key=lambda r: len(r.summary or ""), reverse=True):
        topic = _topic(row.summary)
        for existing_topic, members in groups:
            if _related(topic, existing_topic):
                members.append(row)
                break
        else:
            groups.append((topic, [row]))
    return [members for _, members in groups]


def _headline(members: list[Any]) -> str:
    """The sentence a group is reported as.

    The longest summary wins, because a task title ("Fix persona portrait
    loading across the directory and workspace") says more than the commit
    message that implemented part of it.
    """
    best = max(members, key=lambda r: len(r.summary or ""))
    return (best.summary or "").strip().rstrip(".")


def _projects(members: list[Any]) -> str:
    names = {m.project_name for m in members if m.project_name}
    return ", ".join(sorted(names))


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _completed_bullets(rows: list[Any], limit: int, *, name_projects: bool) -> list[Bullet]:
    out: list[Bullet] = []
    for members in _group([r for r in rows if r.activity_type == COMPLETED]):
        text = _headline(members)
        if not text:
            continue
        # The project only earns a mention when the day spans more than one:
        # tagging every line "(DayPilot)" on a single-project day is noise the
        # reader has to skip past three times.
        project = _projects(members) if name_projects else ""
        if project and project.lower() not in text.lower():
            text = f"{text} ({project})"
        out.append(Bullet(text=text, evidence_ids=[m.id for m in members]))
        if len(out) >= limit:
            break
    return out


def _progress_bullets(rows: list[Any], limit: int, *, exclude: set[str]) -> list[Bullet]:
    """Unfinished but meaningful movement.

    Phrased "Continued work on …" so it can never be read as a completion —
    rule 4 of the draft-generation rules, and the difference between an honest
    standup and one that quietly over-reports.
    """
    out: list[Bullet] = []
    candidates = [r for r in rows if r.activity_type == PROGRESS and r.id not in exclude]
    for members in _group(candidates):
        text = _headline(members)
        if not text:
            continue
        out.append(Bullet(text=f"Continued work on {text[0].lower()}{text[1:]}",
                          evidence_ids=[m.id for m in members]))
        if len(out) >= limit:
            break
    return out


def _blocker_bullets(rows: list[Any], limit: int) -> list[Bullet]:
    out: list[Bullet] = []
    for members in _group([r for r in rows if r.activity_type == BLOCKED]):
        text = _headline(members)
        if not text:
            continue
        out.append(Bullet(text=text, evidence_ids=[m.id for m in members]))
        if len(out) >= limit:
            break
    return out


def _today_bullets(
    planned: list[Any], carried: list[Any], meetings: list[Any], limit: int,
) -> list[Bullet]:
    """What the next workday holds.

    Built from the approved plan and from work that is genuinely still open —
    never from a guess. When there is neither, the section says so rather than
    filling the space.
    """
    out: list[Bullet] = []
    for row in planned:
        out.append(Bullet(text=(row.summary or "").strip(), evidence_ids=[row.id]))
        if len(out) >= limit:
            return out
    for members in _group(carried):
        text = _headline(members)
        if text:
            out.append(Bullet(text=text, evidence_ids=[m.id for m in members]))
        if len(out) >= limit:
            return out
    for row in meetings:
        out.append(Bullet(text=f"Meeting: {row.summary}", evidence_ids=[row.id]))
        if len(out) >= limit:
            return out
    return out


def compile_draft(
    evidence: Iterable[Any],
    *,
    empty_day_policy: str = "honest",
    max_bullets: int = policy.MAX_BULLETS,
) -> CompiledDraft:
    """Build the three sections from the day's included evidence."""
    rows = [r for r in evidence if getattr(r, "included", True)]
    spans_projects = len({r.project_name for r in rows if r.project_name}) > 1

    completed = _completed_bullets(rows, max_bullets, name_projects=spans_projects)
    used = {eid for b in completed for eid in b.evidence_ids}
    remaining = max_bullets - len(completed)
    if remaining > 0:
        completed += _progress_bullets(rows, remaining, exclude=used)

    blockers = _blocker_bullets(rows, max_bullets)

    planned = [r for r in rows if r.activity_type == PLANNED]
    meetings = [r for r in rows if r.activity_type == MEETING]
    still_open = [
        r for r in rows
        if r.activity_type == PROGRESS
        and r.id not in {eid for b in completed for eid in b.evidence_ids}
    ]
    today = _today_bullets(planned, still_open, meetings, max_bullets)

    if not completed:
        text = policy.empty_day_text(empty_day_policy)
        if text:
            completed = [Bullet(text=text.lstrip("• "), evidence_ids=[],
                                kind=policy.NEEDS_CONFIRMATION)]
    if not today:
        today = [Bullet(text="No plan recorded yet for the next workday.",
                        evidence_ids=[], kind=policy.NEEDS_CONFIRMATION)]
    if not blockers:
        blockers = [Bullet(text="None.", evidence_ids=[], kind=policy.OBSERVED)]

    return CompiledDraft(yesterday=completed, today=today, blockers=blockers)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_section(bullets: list[Bullet]) -> str:
    return "\n".join(f"• {b.text}" for b in bullets)


def render_slack_message(
    yesterday: str, today: str, blockers: str, *, reporting_label: str = "",
) -> str:
    """The exact text posted as a thread reply.

    Mirrors the reminder's own numbering and headings so a reader scanning the
    thread sees the same three questions answered in the same order.
    """
    parts = [
        "*1️⃣ Yesterday*",
        yesterday.strip() or "• —",
        "",
        "*2️⃣ Today*",
        today.strip() or "• —",
        "",
        "*3️⃣ Blockers*",
        blockers.strip() or "• None.",
    ]
    if reporting_label:
        parts.append("")
        parts.append(f"_{reporting_label}_")
    return "\n".join(parts)


def reporting_label(reporting_day: date) -> str:
    return f"Reporting on {reporting_day.strftime('%A, %d %B %Y')}"
