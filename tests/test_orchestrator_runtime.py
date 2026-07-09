from daypilot_orchestrator.agent_runtime import RunState, apply_approval, plan_agent_run, ApprovalDecision


def test_orchestrator_requires_approval_for_write_tools(monkeypatch):
    monkeypatch.setenv("DAYPILOT_WRITE_ENABLED", "false")
    run = plan_agent_run("atlas", "send a follow-up", tools_requested=["email.send"])
    assert run.state == RunState.WAITING_APPROVAL
    assert run.requires_approval is True
    assert "Risky" in (run.approval_reason or "")

    approved = apply_approval(run.run_id, ApprovalDecision(decision="approve", reason="operator reviewed"))
    assert approved.state == RunState.APPROVED
    assert approved.requires_approval is False
