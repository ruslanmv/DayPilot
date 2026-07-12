"""Tests for observability + RAG quality gates (B14)."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app
from daypilot_knowledge.rag_eval import EvalCase, evaluate

client = TestClient(app)


def test_request_id_header_present_and_metrics_exposed():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID")
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert b"daypilot_gateway_request_seconds" in metrics.content


def test_client_request_id_is_echoed():
    resp = client.get("/health", headers={"X-Request-ID": "corr-123"})
    assert resp.headers.get("X-Request-ID") == "corr-123"


def test_rag_eval_scorecard_passes_on_relevant_corpus():
    project = "p-" + uuid.uuid4().hex[:8]
    # Ingest a small labeled corpus.
    d1 = client.post("/v1/documents/ingest", json={
        "path": "alpha.md", "projectId": project,
        "content": "The Client Alpha delivery date moved from Friday to Monday.",
    }).json()["documentId"]
    client.post("/v1/documents/ingest", json={
        "path": "beta.md", "projectId": project, "content": "Budget and invoice notes for Q3.",
    })

    from app.db import _get_sessionmaker

    cases = [
        EvalCase(query="Alpha delivery date", project_id=project,
                 relevant_document_ids=[d1], expected_terms=["Monday", "delivery"]),
    ]
    with _get_sessionmaker()() as s:
        scorecard = evaluate(s, cases)

    assert scorecard["cases"] == 1
    assert scorecard["contextRecall"] == 1.0
    assert scorecard["citationCoverage"] == 1.0
    assert scorecard["passed"] is True
