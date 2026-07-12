"""Prompt-injection detection for untrusted content (batch B11).

Documents and emails are untrusted input. Retrieved content that tries to
override instructions, exfiltrate data, or grant itself tool permissions is
detected, scored, and — above a threshold — quarantined and surfaced in the
Approval Center. Injected content can never silently grant permissions: this
guard runs before content reaches an agent's instruction context.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Instruction-override / exfiltration / permission-grant patterns.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("instruction_override", re.compile(r"ignore\s+(?:\w+\s+){0,4}(instructions|prompts|rules)", re.I)),
    ("instruction_override", re.compile(r"disregard (the|all|previous)\s+", re.I)),
    ("role_hijack", re.compile(r"you are now|from now on,? you|act as (an?|the) (admin|root|system)", re.I)),
    ("permission_grant", re.compile(r"(enable|grant|allow)\s+(all\s+)?(tools?|permissions?|write access|admin)", re.I)),
    ("exfiltration", re.compile(r"(send|email|post|upload|leak)\s+.{0,30}(secret|password|token|api[_ ]?key|credential)", re.I)),
    ("system_prompt_leak", re.compile(r"(reveal|print|show)\s+.{0,20}(system prompt|instructions|hidden)", re.I)),
    ("tool_directive", re.compile(r"\b(call|invoke|execute)\s+the\s+\w+\s+tool\b", re.I)),
]

QUARANTINE_THRESHOLD = 1


@dataclass
class InjectionReport:
    flagged: bool
    score: int
    categories: list[str] = field(default_factory=list)
    quarantined: bool = False
    excerpt: str = ""


def scan(content: str, source: str = "unknown") -> InjectionReport:
    categories: list[str] = []
    first_hit = ""
    for category, pattern in _PATTERNS:
        match = pattern.search(content)
        if match:
            categories.append(category)
            if not first_hit:
                start = max(0, match.start() - 20)
                first_hit = content[start : match.end() + 20]
    score = len(categories)
    flagged = score > 0
    return InjectionReport(
        flagged=flagged,
        score=score,
        categories=sorted(set(categories)),
        quarantined=score >= QUARANTINE_THRESHOLD,
        excerpt=first_hit.strip(),
    )


def sanitize_for_context(content: str, source: str = "unknown") -> tuple[str, InjectionReport]:
    """Return content tagged with untrusted provenance, plus the scan report.

    The provenance wrapper makes clear to any downstream agent that this text is
    data, not instructions — it must never be executed as a directive.
    """
    report = scan(content, source)
    wrapped = (
        f"<untrusted_external_data source=\"{source}\" injection_flagged=\"{report.flagged}\">\n"
        f"{content}\n</untrusted_external_data>"
    )
    return wrapped, report
