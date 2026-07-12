"""Matrix Designer adapter — DayPilot's planner and design reviewer (batch B8).

Matrix Designer is "the batches guy": given an idea and a chosen blueprint, its
agentic crew designs the full proposal as a Design Bundle with an ordered,
dependency-aware batch roadmap. DayPilot submits ideas, ingests the bundle as
scheduled work (GitPilot then builds each batch), and asks Matrix Designer to
review UI/deck/document quality.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

DEFAULT_TIMEOUT = 120.0


@dataclass
class DesignBatch:
    id: str
    title: str
    description: str = ""
    depends_on: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    estimate_hours: float | None = None


@dataclass
class DesignBundle:
    bundle_id: str
    title: str
    framework: str = ""
    visual_target: str = ""
    architecture: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    batches: list[DesignBatch] = field(default_factory=list)


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
    findings: list[DesignFinding] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def _grade(score: int) -> str:
    return "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D"


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

    def submit_bundle(self, idea: str, blueprint: str = "") -> DesignBundle:
        with self._client() as client:
            response = client.post(
                "/v1/design/bundle", json={"idea": idea, "blueprint": blueprint}
            )
            response.raise_for_status()
            data = response.json()
        return _normalize_bundle(data)

    def review_artifact(self, target: str, kind: str = "ui", context: str = "") -> DesignReview:
        with self._client() as client:
            response = client.post(
                "/v1/design/review", json={"target": target, "kind": kind, "context": context}
            )
            response.raise_for_status()
            data = response.json()
        return _normalize_review(data, target)


def _normalize_bundle(data: dict) -> DesignBundle:
    batches = []
    for raw in data.get("batches") or []:
        batches.append(
            DesignBatch(
                id=str(raw.get("id") or raw.get("key") or len(batches) + 1),
                title=raw.get("title") or raw.get("name") or "Untitled batch",
                description=raw.get("description") or raw.get("detail") or "",
                depends_on=[str(d) for d in (raw.get("dependsOn") or raw.get("depends_on") or [])],
                acceptance=list(raw.get("acceptance") or raw.get("acceptanceCriteria") or []),
                estimate_hours=raw.get("estimateHours") or raw.get("estimate_hours"),
            )
        )
    return DesignBundle(
        bundle_id=str(data.get("bundleId") or data.get("id") or ""),
        title=data.get("title") or "Design Bundle",
        framework=data.get("framework") or "",
        visual_target=data.get("visualTarget") or data.get("visual_target") or "",
        architecture=data.get("architecture") or "",
        acceptance_criteria=list(data.get("acceptanceCriteria") or data.get("acceptance") or []),
        batches=batches,
    )


def _normalize_review(data: dict, target: str) -> DesignReview:
    score = int(data.get("score") or 0)
    findings = [
        DesignFinding(
            severity=(f.get("severity") or "info"),
            area=(f.get("area") or "general"),
            note=(f.get("note") or f.get("message") or ""),
        )
        for f in (data.get("findings") or [])
    ]
    return DesignReview(
        review_id=str(data.get("reviewId") or data.get("id") or ""),
        target=data.get("target") or target,
        score=score,
        grade=data.get("grade") or _grade(score),
        findings=findings,
        suggestions=list(data.get("suggestions") or []),
    )


def matrix_designer_from_env(transport: httpx.BaseTransport | None = None) -> MatrixDesignerAdapter:
    return MatrixDesignerAdapter(
        base_url=os.getenv("MATRIX_DESIGNER_URL", "http://localhost:8300"),
        api_key=os.getenv("MATRIX_DESIGNER_API_KEY") or None,
        transport=transport,
    )
