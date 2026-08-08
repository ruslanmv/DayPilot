"""How the Approval Center presents the queue.

The Approval Center is the product's central governance claim, and two of its
rules are judgement calls rather than plumbing: an unrecognised risk level must
not read as harmless, and the queue must order itself as a to-do list rather
than a log. Both live in
`packages/ui-bridge/src/approvals/approvalsQueue.ts` and are exercised here
against the shipped code, run by node with type stripping.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "packages" / "ui-bridge" / "src" / "approvals" / "approvalsQueue.ts"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


def run(expr: str):
    script = (
        f"import {{ toApprovalRow, orderQueue }} from {json.dumps(str(QUEUE))}\n"
        f"console.log(JSON.stringify({expr}))\n"
    )
    proc = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "--eval", script],
        capture_output=True, text=True, cwd=ROOT,
    )
    if proc.returncode != 0:
        raise AssertionError(f"node failed:\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def row(**kw):
    base = {"id": "a1", "action": "git.write", "summary": "s", "risk": "low",
            "status": "pending", "resourceType": "coding_run"}
    base.update(kw)
    return base


def test_a_server_row_becomes_a_queue_row():
    r = run(f"toApprovalRow({json.dumps(row(createdAt='2026-08-08T09:00:00Z'))})")
    assert r["id"] == "a1"
    assert r["action"] == "git.write"
    assert r["risk"] == "low"
    assert r["status"] == "pending"
    assert r["createdAt"] == "2026-08-08T09:00:00Z"


def test_an_unknown_risk_is_shown_as_high_not_low():
    # The badge exists so a human can trust it at a glance. Defaulting an
    # unrecognised value to "low" would make the safest-looking row the one
    # nobody understood.
    assert run(f"toApprovalRow({json.dumps(row(risk='catastrophic'))})")["risk"] == "high"


def test_an_absent_risk_takes_the_column_default_rather_than_the_unknown_path():
    # Distinct from the case above: the server omitting the field is not a
    # surprise, it is the `risk` column's own default of "low".
    assert run(f"toApprovalRow({json.dumps(row(risk=None))})")["risk"] == "low"


def test_risk_and_status_are_case_insensitive():
    r = run(f"toApprovalRow({json.dumps(row(risk='HIGH', status='Approved'))})")
    assert r["risk"] == "high"
    assert r["status"] == "approved"


def test_an_unknown_status_stays_pending_so_the_item_is_not_silently_dismissed():
    assert run(f"toApprovalRow({json.dumps(row(status='weird'))})")["status"] == "pending"


def test_a_missing_summary_or_resource_type_does_not_crash_the_row():
    r = run('toApprovalRow({ id: "a", action: "x" })')
    assert r["summary"] == ""
    assert r["resourceType"] == ""


def test_pending_items_come_before_decided_ones():
    rows = [row(id="done", status="approved"), row(id="wait", status="pending")]
    ordered = run(f"orderQueue({json.dumps(rows)}.map((r) => ({{ ...r }})))")
    assert [r["id"] for r in ordered] == ["wait", "done"]


def test_riskier_pending_items_come_first():
    rows = [row(id="low", risk="low"), row(id="high", risk="high"), row(id="med", risk="medium")]
    ordered = run(f"orderQueue({json.dumps(rows)})")
    assert [r["id"] for r in ordered] == ["high", "med", "low"]


def test_equal_risk_falls_back_to_most_recent_first():
    rows = [
        row(id="older", createdAt="2026-08-08T09:00:00Z"),
        row(id="newer", createdAt="2026-08-08T17:00:00Z"),
    ]
    ordered = run(f"orderQueue({json.dumps(rows)})")
    assert [r["id"] for r in ordered] == ["newer", "older"]


def test_ordering_does_not_mutate_the_caller_list():
    rows = [row(id="b", risk="low"), row(id="a", risk="high")]
    both = run(
        f"(() => {{ const input = {json.dumps(rows)};"
        " const out = orderQueue(input);"
        " return { input: input.map((r) => r.id), out: out.map((r) => r.id) } })()"
    )
    assert both["input"] == ["b", "a"]
    assert both["out"] == ["a", "b"]
