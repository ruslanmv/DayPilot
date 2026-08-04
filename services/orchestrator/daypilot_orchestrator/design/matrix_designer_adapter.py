"""Matrix Designer adapter — DayPilot's planner and design reviewer (batch B8).

Matrix Designer is "the batches guy": given an idea it proposes three candidate
blueprints, and given the one you choose it designs the full proposal as a Design
Bundle with an ordered, dependency-aware batch roadmap. DayPilot drives that whole
chain, ingests the bundle as scheduled work (GitPilot then builds each batch), and
asks Matrix Designer to govern the design before anything is built.

The chain, and the endpoints behind it:

    propose  → POST /design/blueprints  idea            → 3 candidates to choose from
    adjust   → POST /design/refine      + free text     → the same package, adjusted
    design   → POST /design/bundle      + candidate id  → the full Design Bundle
    govern   → POST /design/review      the bundle      → schema + design-rule verdict

Normalization is deliberately tolerant: the bundle normalizer reads both the Design
Bundle schema (``batch_roadmap``, ``framework_decision``, ``acceptance.functional``)
and a flat ``{title, batches}`` shape, so a differently-shaped designer in front of
this adapter still schedules work correctly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_TIMEOUT = 120.0

# Matrix Designer reports rule severities (its governance vocabulary); DayPilot
# reasons in review severities, where "major" and above raise a blocker.
_SEVERITY_MAP = {
    "critical": "critical",
    "high": "major",
    "medium": "minor",
    "low": "info",
    "info": "info",
    "minor": "minor",
    "major": "major",
}


@dataclass
class DesignBatch:
    id: str
    title: str
    description: str = ""
    depends_on: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    estimate_hours: float | None = None
    # The batch's own guardrails, carried through so the coding run that builds it
    # can be scoped to exactly the files the design says it may touch.
    allowed_files: list[str] = field(default_factory=list)
    must_not_change: list[str] = field(default_factory=list)


@dataclass
class DesignBundle:
    bundle_id: str
    title: str
    framework: str = ""
    visual_target: str = ""
    architecture: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    batches: list[DesignBatch] = field(default_factory=list)
    validation_status: str = ""
    # The document exactly as the designer produced it — what a review is run
    # against, and what a build chain downstream consumes.
    document: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class DesignCandidate:
    """One of the plans the user chooses between before anything is designed."""

    id: str
    tier: str
    title: str
    summary: str = ""
    difficulty: str = ""
    estimate: str = ""
    file_count: int = 0
    stack: list[str] = field(default_factory=list)
    recommended: bool = False
    # A preview of what building this plan involves, so the choice is informed.
    batches: list[DesignBatch] = field(default_factory=list)


@dataclass
class DesignProposal:
    candidates: list[DesignCandidate] = field(default_factory=list)
    matrix_rules: list[str] = field(default_factory=list)
    violations: list[dict[str, Any]] = field(default_factory=list)
    reply: str = ""

    @property
    def recommended(self) -> DesignCandidate | None:
        for candidate in self.candidates:
            if candidate.recommended:
                return candidate
        return self.candidates[0] if self.candidates else None


@dataclass
class DesignFinding:
    severity: str  # info | minor | major | critical
    area: str
    note: str


@dataclass
class DesignReview:
    review_id: str
    target: str
    score: int
    grade: str
    status: str = ""
    findings: list[DesignFinding] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def _grade(score: int) -> str:
    return "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D"


class DesignerError(RuntimeError):
    """Matrix Designer refused the request and said why."""


@dataclass
class MatrixDesignerAdapter:
    base_url: str
    api_key: str | None = None
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    timeout: float = DEFAULT_TIMEOUT

    def _client(self) -> httpx.Client:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return httpx.Client(
            base_url=self.base_url.rstrip("/"), headers=headers, timeout=self.timeout,
            transport=self.transport,
        )

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._client() as client:
            response = client.post(path, json=payload)
            response.raise_for_status()
            data = response.json()
        # The designer answers 200 with an "error" for refusals (empty idea, a
        # provider outside the operator's allow-list) rather than a status code.
        if isinstance(data, dict) and data.get("error"):
            raise DesignerError(str(data["error"]))
        return data

    # ── Propose: the plans to choose between ────────────────────────────────

    def generate_blueprints(
        self,
        idea: str,
        references: list[dict[str, str]] | None = None,
        constraints: dict[str, Any] | None = None,
    ) -> DesignProposal:
        """Three candidate plans for an idea, simplest to most complete."""
        payload: dict[str, Any] = {"idea": idea}
        if references:
            payload["references"] = references
        if constraints:
            payload["constraints"] = constraints
        return _normalize_proposal(self._post("/design/blueprints", payload))

    def refine_design(
        self,
        idea: str,
        message: str,
        candidate_id: str = "standard",
        constraints: dict[str, Any] | None = None,
    ) -> DesignProposal:
        """Adjust a candidate from free text ("add SSO", "drop the mobile app")."""
        payload: dict[str, Any] = {"idea": idea, "message": message, "candidate_id": candidate_id}
        if constraints:
            payload["constraints"] = constraints
        return _normalize_proposal(self._post("/design/refine", payload))

    # ── Design: the chosen plan becomes a buildable bundle ───────────────────

    def submit_bundle(self, idea: str, blueprint: str = "", candidate_id: str = "") -> DesignBundle:
        """The full Design Bundle for the chosen plan.

        ``blueprint`` and ``candidate_id`` both name the chosen candidate
        ("minimal" | "standard" | "production"); ``blueprint`` is the older name and
        is still accepted. With neither, the designer's recommended plan is used.
        """
        payload = {"idea": idea, "candidate_id": (candidate_id or blueprint or "").strip()}
        return _normalize_bundle(self._post("/design/bundle", payload))

    # ── Govern: nothing is built from an unreviewed design ───────────────────

    def review_bundle(
        self, bundle: DesignBundle | dict[str, Any], target: str = "", kind: str = "design-bundle"
    ) -> DesignReview:
        """Schema + design-rule verdict on a bundle, as findings a human can act on."""
        document = bundle.document if isinstance(bundle, DesignBundle) else bundle
        if not document:
            raise DesignerError("there is no design bundle to review")
        payload = {"bundle": document, "target": target, "kind": kind}
        return _normalize_review(self._post("/design/review", payload), target)


# ── Normalization ───────────────────────────────────────────────────────────

def _batches(raw_batches: list[dict[str, Any]]) -> list[DesignBatch]:
    batches: list[DesignBatch] = []
    for raw in raw_batches or []:
        batches.append(
            DesignBatch(
                id=str(raw.get("id") or raw.get("key") or len(batches) + 1),
                title=raw.get("title") or raw.get("name") or "Untitled batch",
                description=raw.get("purpose") or raw.get("description") or raw.get("detail") or "",
                depends_on=[str(d) for d in (raw.get("dependsOn") or raw.get("depends_on") or [])],
                acceptance=list(
                    raw.get("acceptance")
                    or raw.get("acceptanceCriteria")
                    or raw.get("acceptance_criteria")
                    or []
                ),
                estimate_hours=raw.get("estimateHours") or raw.get("estimate_hours"),
                allowed_files=list(raw.get("allowedFiles") or raw.get("allowed_files") or []),
                must_not_change=list(raw.get("mustNotChange") or raw.get("must_not_change") or []),
            )
        )
    return batches


def _as_text(value: Any) -> str:
    """Flatten a designer field that may be a string, a list or a nested object."""
    if not value:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ", ".join(_as_text(v) for v in value if v)
    if isinstance(value, dict):
        for key in ("summary", "style", "target", "description", "name"):
            if value.get(key):
                return _as_text(value[key])
        return ", ".join(_as_text(v) for v in value.values() if isinstance(v, str))
    return str(value)


def _bundle_title(data: dict[str, Any]) -> str:
    goal = (data.get("goal_analysis") or {}).get("real_goal") or ""
    for candidate in (data.get("title"), goal, data.get("project"), data.get("slug")):
        text = str(candidate or "").strip()
        if text:
            return text[:120]
    return "Design Bundle"


def _normalize_bundle(data: dict[str, Any]) -> DesignBundle:
    """Read a Design Bundle document (or a flat designer response) into DayPilot's shape."""
    raw_batches = data.get("batch_roadmap") or data.get("batches") or []
    acceptance = data.get("acceptance")
    if isinstance(acceptance, dict):
        criteria = list(acceptance.get("functional") or [])
    else:
        criteria = list(data.get("acceptanceCriteria") or acceptance or [])
    architecture = data.get("architecture")
    if isinstance(architecture, dict):
        architecture_text = _as_text(architecture.get("systems") or architecture)
    else:
        architecture_text = _as_text(architecture)

    framework = data.get("framework") or (data.get("framework_decision") or {}).get("stack")
    return DesignBundle(
        bundle_id=str(data.get("design_id") or data.get("bundleId") or data.get("id") or ""),
        title=_bundle_title(data),
        framework=_as_text(framework),
        visual_target=_as_text(data.get("visual_target") or data.get("visualTarget")),
        architecture=architecture_text,
        acceptance_criteria=criteria,
        batches=_batches(raw_batches),
        validation_status=str((data.get("governance") or {}).get("validation_status") or ""),
        document=data,
    )


def _normalize_proposal(data: dict[str, Any]) -> DesignProposal:
    details = data.get("details") or {}
    candidates: list[DesignCandidate] = []
    for raw in data.get("candidates") or []:
        candidate_id = str(raw.get("id") or "")
        detail = details.get(candidate_id) or {}
        candidates.append(
            DesignCandidate(
                id=candidate_id,
                tier=raw.get("tier") or candidate_id.title(),
                title=raw.get("title") or raw.get("tier") or candidate_id,
                summary=raw.get("summary") or detail.get("overview") or "",
                difficulty=raw.get("difficulty") or "",
                estimate=raw.get("estimate") or "",
                file_count=int(raw.get("file_count") or raw.get("fileCount") or 0),
                stack=list(raw.get("stack") or []),
                recommended=bool(raw.get("recommended")),
                batches=_batches(detail.get("batches") or []),
            )
        )
    return DesignProposal(
        candidates=candidates,
        matrix_rules=list(data.get("matrix_rules") or data.get("matrixRules") or []),
        violations=list(data.get("violations") or []),
        reply=str(data.get("reply") or ""),
    )


def _normalize_review(data: dict[str, Any], target: str) -> DesignReview:
    score = int(data.get("score") or 0)
    findings = [
        DesignFinding(
            severity=_SEVERITY_MAP.get((f.get("severity") or "info").lower(), "minor"),
            area=(f.get("area") or f.get("rule_id") or "general"),
            note=(f.get("note") or f.get("message") or ""),
        )
        for f in (data.get("findings") or [])
    ]
    return DesignReview(
        review_id=str(data.get("review_id") or data.get("reviewId") or data.get("id") or ""),
        target=data.get("target") or target,
        score=score,
        grade=data.get("grade") or _grade(score),
        status=str(data.get("status") or ""),
        findings=findings,
        suggestions=list(data.get("suggestions") or []),
    )


def matrix_designer_from_env(transport: httpx.BaseTransport | None = None) -> MatrixDesignerAdapter:
    return MatrixDesignerAdapter(
        base_url=os.getenv("MATRIX_DESIGNER_URL", "http://localhost:8077"),
        api_key=os.getenv("MATRIX_DESIGNER_API_KEY") or None,
        transport=transport,
    )
