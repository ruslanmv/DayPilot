"""dmind-patch/v1: bounded patch proposals applied only against the state they were written for.

Python port of the DayPilot reference (diagrams/patch.ts). A patch is all-or-nothing: either every
operation holds and the result is a valid dmind/v1 document, or it is rejected as ``stale`` (the
document moved on) or ``invalid`` (an operation does not hold). Input is data, never mutated.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from .dmind_contract import validate_diagram

PATCH_SCHEMA = "dmind-patch/v1"
MAX_PATCH_OPS = 200
ORIGINS = {"model", "solver", "user"}
NODE_SET = {"label", "notes", "collapsed"}
EDGE_SET = {"source", "target", "kind", "label"}


class PatchError(ValueError):
    """``reason`` is ``stale`` or ``invalid``."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def hash_diagram(document: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON (sorted keys, no spaces). Matches the TypeScript hash for
    documents whose keys are ASCII, which the contract's own field names and ids always are."""
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _only(obj: dict[str, Any], allowed: set[str], where: str) -> None:
    extra = sorted(set(obj) - allowed)
    if extra:
        raise PatchError("invalid", f"{where}: unexpected {', '.join(extra)}")


def _obj(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PatchError("invalid", f"{where}: must be an object")
    return value


def parse_patch(value: Any) -> dict[str, Any]:
    patch = _obj(value, "patch")
    _only(patch, {"schema", "base", "origin", "summary", "ops"}, "patch")
    if patch.get("schema") != PATCH_SCHEMA:
        raise PatchError("invalid", f"patch schema must be {PATCH_SCHEMA}")
    base = patch.get("base")
    h = base.get("hash") if isinstance(base, dict) else None
    if not isinstance(base, dict) or not isinstance(base.get("id"), str) or not (
        isinstance(h, str) and len(h) == 64 and all(c in "0123456789abcdef" for c in h)
    ):
        raise PatchError("invalid", "patch needs base.id and a 64-character base.hash")
    if patch.get("origin") not in ORIGINS:
        raise PatchError("invalid", "patch origin must be model, solver or user")
    if not isinstance(patch.get("summary"), str) or len(patch["summary"]) > 500:
        raise PatchError("invalid", "patch summary must be text up to 500 characters")
    ops = patch.get("ops")
    if not isinstance(ops, list) or not ops:
        raise PatchError("invalid", "patch has no operations")
    if len(ops) > MAX_PATCH_OPS:
        raise PatchError("invalid", f"a patch may hold at most {MAX_PATCH_OPS} operations")
    for i, raw in enumerate(ops, 1):
        w = f"op {i}"
        op = _obj(raw, w)
        kind = op.get("op")
        if kind == "set_title":
            _only(op, {"op", "title"}, w)
            if not isinstance(op.get("title"), str):
                raise PatchError("invalid", f"{w}: title must be text")
        elif kind in ("add_node", "add_edge"):
            _only(op, {"op", "node" if kind == "add_node" else "edge"}, w)
            body = _obj(op.get("node" if kind == "add_node" else "edge"), w)
            _only(body, {"id", "label", "notes"} if kind == "add_node" else {"id", "source", "target", "kind", "label"}, w)
        elif kind in ("update_node", "update_edge"):
            _only(op, {"op", "id", "set"}, w)
            changes = op.get("set")
            if not isinstance(op.get("id"), str) or not isinstance(changes, dict) or not changes:
                raise PatchError("invalid", f"{w}: id and a non-empty set required")
            _only(changes, NODE_SET if kind == "update_node" else EDGE_SET, w)
        elif kind in ("remove_node", "remove_edge"):
            _only(op, {"op", "id"}, w)
            if not isinstance(op.get("id"), str):
                raise PatchError("invalid", f"{w}: id required")
        else:
            raise PatchError("invalid", f"{w}: unknown operation")
    return patch


def _step(d: dict[str, Any], op: dict[str, Any], w: str) -> None:
    node = lambda i: next((n for n in d["nodes"] if n["id"] == i), None)  # noqa: E731
    edge = lambda i: next((e for e in d["edges"] if e["id"] == i), None)  # noqa: E731
    kind = op["op"]
    if kind == "set_title":
        d["title"] = op["title"]
    elif kind == "add_node":
        if node(op["node"].get("id")):
            raise PatchError("invalid", f"{w}: topic {op['node']['id']} already exists")
        d["nodes"].append(dict(op["node"]))
    elif kind == "update_node":
        n = node(op["id"])
        if n is None:
            raise PatchError("invalid", f"{w}: no topic {op['id']}")
        n.update(op["set"])
    elif kind == "remove_node":
        if node(op["id"]) is None:
            raise PatchError("invalid", f"{w}: no topic {op['id']}")
        d["nodes"] = [n for n in d["nodes"] if n["id"] != op["id"]]
        d["edges"] = [e for e in d["edges"] if op["id"] not in (e.get("source"), e.get("target"))]
        if not d["nodes"]:
            raise PatchError("invalid", f"{w}: a diagram needs at least one topic")
    elif kind == "add_edge":
        if edge(op["edge"].get("id")):
            raise PatchError("invalid", f"{w}: link {op['edge']['id']} already exists")
        d["edges"].append(dict(op["edge"]))
    elif kind == "update_edge":
        e = edge(op["id"])
        if e is None:
            raise PatchError("invalid", f"{w}: no link {op['id']}")
        e.update(op["set"])
    elif kind == "remove_edge":
        if edge(op["id"]) is None:
            raise PatchError("invalid", f"{w}: no link {op['id']}")
        d["edges"] = [e for e in d["edges"] if e["id"] != op["id"]]


def apply_patch(current: dict[str, Any], patch: Any) -> dict[str, Any]:
    """Return the patched document or raise ``PatchError``. ``current`` is never modified."""
    patch = parse_patch(patch)
    if patch["base"]["id"] != current.get("id") or patch["base"]["hash"] != hash_diagram(current):
        raise PatchError("stale", "the diagram changed after this proposal was made")
    nxt = deepcopy(current)
    for i, op in enumerate(patch["ops"], 1):
        _step(nxt, op, f"op {i}")
    try:
        return validate_diagram(nxt)
    except ValueError as exc:
        raise PatchError("invalid", str(exc)) from exc
