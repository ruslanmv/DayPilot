"""Concurrent saves: compare-and-swap lets exactly one writer win, never silently overwrite."""

import json
import threading
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

FIXTURE = Path(__file__).parents[1] / "packages/dmind-contract/order-system.dmind.json"
WRITERS = 8


def test_simultaneous_saves_of_one_revision_yield_one_winner_and_clean_history():
    headers = {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}
    seed = TestClient(app)
    created = seed.post(
        "/v1/diagrams", json={"document": json.loads(FIXTURE.read_text())}, headers=headers
    ).json()
    did, doc = created["id"], created["document"]
    start = threading.Barrier(WRITERS)
    outcomes: dict[int, tuple[int, str]] = {}

    def writer(n: int) -> None:
        edited = {**doc, "title": f"Writer {n}"}
        client = TestClient(app)
        start.wait()
        r = client.put(
            f"/v1/diagrams/{did}",
            json={"document": edited, "expectedRevision": 1},
            headers=headers,
        )
        outcomes[n] = (r.status_code, edited["title"])

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(WRITERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert len(outcomes) == WRITERS
    winners = [title for status, title in outcomes.values() if status == 200]
    assert len(winners) == 1, outcomes
    assert sorted(status for status, _ in outcomes.values()) == [200] + [409] * (WRITERS - 1)

    head = seed.get(f"/v1/diagrams/{did}", headers=headers).json()
    assert head["revision"] == 2 and head["document"]["title"] == winners[0]
    history = seed.get(f"/v1/diagrams/{did}/revisions", headers=headers).json()["items"]
    assert [v["revision"] for v in history] == [2, 1]  # no duplicate or missing snapshot
    assert history[0]["document"] == head["document"] and history[1]["document"] == doc
