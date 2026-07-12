"""Tests for the durable job queue, rate limiting, retention, and load (B12)."""
from __future__ import annotations

import time
import uuid

from fastapi.testclient import TestClient

from app.db import _get_sessionmaker
from app.main import app
from daypilot_orchestrator.jobs import queue, worker
from daypilot_orchestrator.scale.rate_limit import RateLimiter

client = TestClient(app)


def _ws() -> str:
    return "ws-" + uuid.uuid4().hex[:8]


# --- Queue lifecycle --------------------------------------------------------

def test_enqueue_claim_complete():
    ws = _ws()
    with _get_sessionmaker()() as s:
        job = queue.enqueue(s, "document.index", {"doc": 1}, ws)
        s.commit()
        jid = job.id
    with _get_sessionmaker()() as s:
        claimed = queue.claim_next(s, kinds=["document.index"])
        assert claimed is not None and claimed.state == "running"
        queue.complete(s, claimed, {"indexed": True})
        s.commit()
    with _get_sessionmaker()() as s:
        from daypilot_knowledge.db import Job
        assert s.get(Job, jid).state == "succeeded"


def test_worker_retries_with_backoff_then_dead_letters():
    ws = _ws()
    with _get_sessionmaker()() as s:
        job = queue.enqueue(s, "flaky", {}, ws, max_attempts=2)
        s.commit()
        jid = job.id

    handlers = {"flaky": lambda payload: (_ for _ in ()).throw(RuntimeError("boom"))}

    with _get_sessionmaker()() as s:
        processed = worker.process_once(s, handlers, kinds=["flaky"])
        s.commit()
        assert processed.state == "queued"  # retry scheduled with backoff
        assert processed.run_after is not None

    # Force it runnable again by clearing run_after, then exhaust attempts.
    with _get_sessionmaker()() as s:
        from daypilot_knowledge.db import Job
        s.get(Job, jid).run_after = None
        s.commit()
    with _get_sessionmaker()() as s:
        processed = worker.process_once(s, handlers, kinds=["flaky"])
        s.commit()
        assert processed.state == "dead_letter"
        assert "boom" in processed.last_error


def test_cancel_job_via_api():
    ws = _ws()
    created = client.post("/v1/jobs", json={"kind": "agent.run", "workspaceId": ws}).json()
    cancelled = client.post(f"/v1/jobs/{created['id']}/cancel").json()
    assert cancelled["state"] == "cancelled"


def test_unknown_kind_fails_gracefully():
    ws = _ws()
    with _get_sessionmaker()() as s:
        queue.enqueue(s, "nope", {}, ws, max_attempts=1)
        s.commit()
    with _get_sessionmaker()() as s:
        job = worker.process_once(s, {}, kinds=["nope"])
        s.commit()
        assert job.state == "dead_letter"


# --- Rate limiting ----------------------------------------------------------

def test_rate_limiter_allows_burst_then_blocks():
    limiter = RateLimiter(rate_per_sec=100.0, burst=3.0)
    key = "persona:x"
    assert [limiter.allow(key) for _ in range(3)] == [True, True, True]
    assert limiter.allow(key) is False
    assert limiter.retry_after(key) > 0
    time.sleep(0.05)
    assert limiter.allow(key) is True  # refilled


# --- Retention --------------------------------------------------------------

def test_retention_sweep_runs():
    body = client.post("/v1/jobs/retention/sweep").json()
    assert set(body.keys()) >= {"eventsDeleted", "jobsDeleted", "auditDeleted", "policy"}


# --- Load: pagination stays correct + fast at volume ------------------------

def test_pagination_at_volume_is_complete_and_bounded():
    ws = _ws()
    # Enqueue a few hundred jobs and page through with cursors.
    with _get_sessionmaker()() as s:
        for i in range(300):
            queue.enqueue(s, "load.test", {"i": i}, ws)
        s.commit()

    seen: set[str] = set()
    cursor = None
    pages = 0
    start = time.perf_counter()
    while pages < 100:
        url = f"/v1/jobs?workspaceId={ws}&limit=50"
        if cursor:
            url += f"&cursor={cursor}"
        body = client.get(url).json()
        for item in body["items"]:
            seen.add(item["id"])
        cursor = body["nextCursor"]
        pages += 1
        if not cursor:
            break
    elapsed = time.perf_counter() - start
    assert len(seen) == 300
    assert pages == 6
    assert elapsed < 5.0  # generous CI budget; keyset stays flat
