"""Risk scoring for coding runs (batch B6).

Turns a diff + test results into a low/medium/high risk signal so the reviewer
knows where to look first. Signals: change surface (files, lines), test pass
rate, and whether sensitive paths were touched.
"""
from __future__ import annotations

from .interface import DiffSummary, TestResults

# Paths whose changes carry outsized blast radius.
SENSITIVE_PATTERNS = (
    "migration",
    "alembic",
    "auth",
    "security",
    "secret",
    "infra/",
    "deploy",
    "dockerfile",
    ".github/",
    "requirements",
    "pyproject",
    "package.json",
)


def _touches_sensitive(diff: DiffSummary) -> list[str]:
    hits = []
    for change in diff.files:
        lowered = change.path.lower()
        if any(pattern in lowered for pattern in SENSITIVE_PATTERNS):
            hits.append(change.path)
    return hits


def score_risk(diff: DiffSummary, tests: TestResults) -> tuple[str, int, list[str]]:
    """Return (level, score 0-100, reasons)."""
    score = 0
    reasons: list[str] = []

    files = diff.files_changed
    if files > 20:
        score += 40
        reasons.append(f"large change surface ({files} files)")
    elif files > 8:
        score += 25
        reasons.append(f"moderate change surface ({files} files)")
    elif files > 0:
        score += 10

    lines = diff.total_lines
    if lines > 600:
        score += 25
        reasons.append(f"large diff ({lines} lines)")
    elif lines > 200:
        score += 12

    rate = tests.pass_rate
    if rate is None:
        score += 20
        reasons.append("no test results")
    elif rate < 1.0:
        score += int((1.0 - rate) * 40)
        reasons.append(f"tests not fully green ({int(rate * 100)}% passing)")

    sensitive = _touches_sensitive(diff)
    if sensitive:
        score += 25
        reasons.append(f"touches sensitive paths: {', '.join(sensitive[:3])}")

    score = min(score, 100)
    level = "high" if score >= 60 else "medium" if score >= 30 else "low"
    return level, score, reasons
