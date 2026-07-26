"""AI-behavior guardrails for agent replies (Batch A12, UX §13).

Defense in depth on the *visible* text a persona returns. HomePilot's propose
instruction already tells the persona not to expose machinery, but a model is
untrusted, so DayPilot strips anything that leaked before persisting/showing it:

  * a directive block that wasn't consumed (``[[DAYPILOT_DIRECTIVES]]…``);
  * raw tool-call / function-call JSON fences;
  * obvious internal system framing.

Model-name redaction is intentionally NOT done by blunt find-replace (it would
mangle legitimate text like "email Claude"); prevention lives in the persona
instruction. The "never say complete before it's complete" rule is enforced
structurally by the task mapper / action mapper (a draft is never completed),
not by scanning prose.
"""
from __future__ import annotations

import re

_DIRECTIVE_BLOCK = re.compile(
    r"`{0,3}\s*\[\[DAYPILOT_DIRECTIVES\]\].*?\[\[/DAYPILOT_DIRECTIVES\]\]\s*`{0,3}",
    re.DOTALL,
)
# A fenced block that is clearly a tool / function call payload (has the tell-tale
# keys). Conservative: only strips fences whose JSON mentions tool/function/name
# + arguments, so ordinary code samples are left alone.
_TOOL_FENCE = re.compile(
    r"```[a-zA-Z_]*\s*\{[^`]*?\"(?:tool|tool_call|function|name)\"\s*:[^`]*?\"(?:arguments|parameters|args)\"[^`]*?\}\s*```",
    re.DOTALL | re.IGNORECASE,
)
_LEAKED_SENTINEL = re.compile(r"\[\[/?DAYPILOT_DIRECTIVES\]\]")


def sanitize_reply(text: str) -> str:
    """Strip leaked machinery from a persona's visible reply. Idempotent."""
    if not text:
        return text
    t = _DIRECTIVE_BLOCK.sub("", text)
    t = _TOOL_FENCE.sub("", t)
    t = _LEAKED_SENTINEL.sub("", t)          # any stray sentinel halves
    t = re.sub(r"\n{3,}", "\n\n", t)          # collapse the gap a strip left behind
    return t.strip()


def was_sanitized(original: str, cleaned: str) -> bool:
    """True when sanitize_reply changed the text (for observability)."""
    return (original or "").strip() != (cleaned or "")
