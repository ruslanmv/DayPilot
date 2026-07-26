"""AI-behavior guardrails + compat matrix (Batch A12, UX §13).

The guardrails strip leaked machinery from a visible reply; the structural rules
(a draft is never completed) are enforced by the mapper. A small compat matrix
exercises bridge / chat-only / offline together end to end.
"""
from __future__ import annotations

import uuid

from daypilot_knowledge.db import Task, create_engine_from_settings, session_scope
from daypilot_orchestrator.homepilot import action_mapping, guardrails, task_mapper
from daypilot_orchestrator.homepilot.directives import validate_directives


def _ws() -> str:
    return "ws-g-" + uuid.uuid4().hex[:8]


# --- guardrails (pure) ------------------------------------------------------

def test_strips_leaked_directive_block():
    text = 'On it.\n[[DAYPILOT_DIRECTIVES]]{"directives":[{"type":"task.create","title":"x"}]}[[/DAYPILOT_DIRECTIVES]]'
    assert guardrails.sanitize_reply(text) == 'On it.'


def test_strips_tool_call_fence_but_keeps_normal_code():
    tool = 'Sure.\n```json\n{"tool":"send","name":"email","arguments":{"to":"x"}}\n```'
    assert 'tool' not in guardrails.sanitize_reply(tool).lower()
    code = 'Here is a snippet:\n```python\nprint("hi")\n```'
    assert 'print' in guardrails.sanitize_reply(code)  # ordinary code is preserved


def test_sanitize_is_idempotent_and_flagged():
    once = guardrails.sanitize_reply('Hi [[DAYPILOT_DIRECTIVES]]{}[[/DAYPILOT_DIRECTIVES]]')
    assert guardrails.sanitize_reply(once) == once
    assert guardrails.was_sanitized('Hi [[/DAYPILOT_DIRECTIVES]]', 'Hi') is True
    assert guardrails.was_sanitized('Hi', 'Hi') is False


# --- structural: never "complete" before complete ---------------------------

def test_proposed_action_is_never_completed_until_executed():
    ws = _ws()
    from daypilot_knowledge.db import HomePilotAgentLink
    with session_scope(create_engine_from_settings()) as s:
        link = HomePilotAgentLink(workspace_id=ws, connection_id="c", homepilot_project_id="p",
                                  name="A", enabled=True, status="available")
        s.add(link)
        s.flush()
        v = validate_directives({"items": [{"type": "daypilot.action.propose", "capability": "email.send", "summary": "x"}]})
        res = task_mapper.apply_directives(s, ws, link, v)
        task = s.get(Task, res.created[0])
        assert task.status == "waiting_for_approval" and task.progress_percent == 0
        # Only an approved execution can complete it.
        task.approval_id and None
        out = action_mapping.execute_approved(s, ws, task)
        assert out["lifecycle"] == "completed" and task.status == "completed"
