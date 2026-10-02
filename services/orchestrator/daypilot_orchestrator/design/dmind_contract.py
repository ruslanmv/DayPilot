"""dmind/v1 graph contract. Mirrored in DayPilot; no optional dependencies.

Branch edges form a forest. Flow/relationship edges may contain feedback loops.
Input text is data: this module never fetches URLs, evaluates code or mutates input.
"""

from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from typing import Any

SCHEMA_VERSION = "dmind/v1"
MAX_BYTES = 2_000_000
MAX_NODES = 1000
MAX_EDGES = 4000
KINDS = {"mindmap", "flowchart", "system"}
EDGE_KINDS = {"branch", "flow", "dependency", "relationship"}


def validate_diagram(document: Any) -> dict[str, Any]:
    """Validate a bounded graph and return a detached copy, preserving metadata."""
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported diagram schema; expected dmind/v1")
    try:
        encoded = json.dumps(
            document, allow_nan=False, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError) as exc:
        raise ValueError("diagram must contain finite JSON values") from exc
    if len(encoded) > MAX_BYTES:
        raise ValueError("diagram exceeds 2 MB")
    for key, limit in (("id", 100), ("title", 200)):
        if (
            not isinstance(document.get(key), str)
            or not document[key].strip()
            or len(document[key]) > limit
        ):
            raise ValueError(f"invalid diagram {key}")
    if not isinstance(document.get("kind"), str) or document["kind"] not in KINDS:
        raise ValueError("unsupported diagram kind")
    nodes, edges = document.get("nodes"), document.get("edges")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES:
        raise ValueError("diagram needs 1–1000 nodes")
    if not isinstance(edges, list) or len(edges) > MAX_EDGES:
        raise ValueError("diagram supports at most 4000 edges")
    ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError("invalid node")
        nid = node.get("id")
        if not isinstance(nid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", nid) or nid in ids:
            raise ValueError("node IDs must be unique safe identifiers")
        ids.add(nid)
        if (
            not isinstance(node.get("label"), str)
            or not node["label"].strip()
            or len(node["label"]) > 500
        ):
            raise ValueError("node label must contain 1–500 characters")
        if "notes" in node and (not isinstance(node["notes"], str) or len(node["notes"]) > 20000):
            raise ValueError("node notes exceed 20000 characters")
        if "collapsed" in node and not isinstance(node["collapsed"], bool):
            raise ValueError("collapsed must be a boolean")
        if "position" in node:
            p = node["position"]
            if not isinstance(p, dict) or any(
                isinstance(p.get(k), bool)
                or not isinstance(p.get(k), (int, float))
                or not math.isfinite(p[k])
                or abs(p[k]) > 100000
                for k in ("x", "y")
            ):
                raise ValueError("invalid node position")
    if "metadata" in document and not isinstance(document["metadata"], dict):
        raise ValueError("diagram metadata must be an object")
    for node in nodes:
        if "metadata" in node and not isinstance(node["metadata"], dict):
            raise ValueError("node metadata must be an object")
    edge_ids: set[str] = set()
    parents: dict[str, str] = {}
    for edge in edges:
        if not isinstance(edge, dict):
            raise ValueError("invalid edge")
        eid = edge.get("id")
        if (
            not isinstance(eid, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", eid)
            or eid in edge_ids
        ):
            raise ValueError("edge IDs must be unique safe identifiers")
        edge_ids.add(eid)
        if (
            not isinstance(edge.get("source"), str)
            or not isinstance(edge.get("target"), str)
            or edge["source"] not in ids
            or edge["target"] not in ids
        ):
            raise ValueError("edge references a missing node")
        if not isinstance(edge.get("kind"), str) or edge["kind"] not in EDGE_KINDS:
            raise ValueError("invalid edge kind")
        if "label" in edge and (not isinstance(edge["label"], str) or len(edge["label"]) > 500):
            raise ValueError("invalid edge label")
        if edge["kind"] == "branch":
            target = edge["target"]
            if target in parents:
                raise ValueError("branch nodes may have only one parent")
            parents[target] = edge["source"]
    for nid in ids:
        seen: set[str] = set()
        cursor = nid
        while cursor in parents:
            if cursor in seen:
                raise ValueError("branch hierarchy contains a cycle")
            seen.add(cursor)
            cursor = parents[cursor]
    return deepcopy(document)
