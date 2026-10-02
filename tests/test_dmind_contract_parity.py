"""dmind/v1 contract parity: the Python validator runs the corpus shared with TypeScript.

``tests/ui/dmind.mjs`` runs the same ``contract-cases.json`` against the editor's validator
and outline parser; Matrix Designer runs it against its validator, outline parser and the
JSON Schema. The pinned digests make drift between the repositories a visible test failure
instead of a silent integration bug.
"""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from daypilot_orchestrator.design.dmind_contract import validate_diagram

CONTRACT = Path(__file__).parents[1] / "packages/dmind-contract"
SCHEMA = CONTRACT / "dmind.schema.json"
FIXTURE = CONTRACT / "order-system.dmind.json"
CASES = CONTRACT / "contract-cases.json"
ARCHIVES = CONTRACT / "archive-cases.json"
PATCHES = CONTRACT / "patch-cases.json"
HANDOFFS = CONTRACT / "handoff-cases.json"

# Canonical-JSON digests of the shared contract. Matrix Designer pins the same values;
# change the schema, fixture or corpus in BOTH repositories together and update both pins.
PINNED = {
    "schema": "a72d842dec9d606474f11acaeb2afcaecb252d88e68ceb1700a8dca3d0778f98",
    "fixture": "be2c8afa7978a29c32693fb7252666563a77d6edd8d2b81934fd45d9b120e095",
    "cases": "bbba4b6458a90b0053a61e8743a37a4a320496d3ec73cfc09e8b4cc2a2d46b50",
    "archives": "7821afee40c47f81788c3703597c07bea277e2142341c408cbd76ab398e6da5d",
    "patches": "870b946b39bd8b2e414659196ac26211ae10ba8182d4b33d98f854ed63c3161a",
    "handoffs": "d9390d6c404356763c8ee8150f176b9b8b4ff65737cc2d436ceb6fa5d2f2594a",
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    canonical = json.dumps(load(path), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve(value):
    if isinstance(value, dict) and "$repeat" in value:
        text, times = value["$repeat"]
        return text * times
    return value


def holder(doc, path):
    *keys, last = path.split(".")
    cur = doc
    for key in keys:
        cur = cur[int(key)] if isinstance(cur, list) else cur[key]
    return cur, (int(last) if isinstance(cur, list) else last)


def apply_ops(doc, ops):
    for op in ops:
        if "set" in op:
            cur, key = holder(doc, op["set"])
            cur[key] = deepcopy(resolve(op["value"]))
        elif "delete" in op:
            cur, key = holder(doc, op["delete"])
            del cur[key]  # list index or dict key
        elif "append" in op:
            cur, key = holder(doc, op["append"])
            cur[key].append(deepcopy(resolve(op["value"])))
        elif "grow" in op:
            items, i = doc[op["grow"]], 0
            while len(items) < op["to"]:
                items.append(
                    {"id": f"g{i}", "label": f"g{i}"}
                    if op["grow"] == "nodes"
                    else {"id": f"g{i}", "source": "root", "target": "root", "kind": "relationship"}
                )
                i += 1
        else:  # pragma: no cover - guards corpus typos
            raise AssertionError(f"unknown op {op}")
    return doc


corpus = load(CASES)


def case_id(case):
    return case["name"]


def test_contract_files_match_the_pinned_digests():
    actual = {"schema": digest(SCHEMA), "fixture": digest(FIXTURE), "cases": digest(CASES),
              "archives": digest(ARCHIVES),
              "patches": digest(PATCHES),
              "handoffs": digest(HANDOFFS)}
    assert actual == PINNED, (
        "dmind/v1 contract changed. Update schema, fixture and corpus in DayPilot AND "
        "Matrix Designer together, then update the pinned digests in both test suites."
    )


def test_golden_fixture_is_valid_and_unchanged_by_validation():
    fixture = load(FIXTURE)
    assert validate_diagram(fixture) == fixture


@pytest.mark.parametrize("case", corpus["valid"], ids=case_id)
def test_valid_cases_are_accepted_with_unknown_fields_retained(case):
    doc = apply_ops(load(FIXTURE), case["ops"])
    assert validate_diagram(doc) == doc


@pytest.mark.parametrize("case", corpus["invalid"], ids=case_id)
def test_invalid_cases_are_rejected(case):
    with pytest.raises(ValueError):
        validate_diagram(apply_ops(load(FIXTURE), case["ops"]))


def test_validation_returns_a_detached_copy():
    fixture = load(FIXTURE)
    checked = validate_diagram(fixture)
    checked["nodes"][0]["label"] = "changed"
    assert fixture["nodes"][0]["label"] == "Order processing"
