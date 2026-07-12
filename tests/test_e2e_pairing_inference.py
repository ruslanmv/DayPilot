"""Fast end-to-end check of the real pairing + inference path.

Starts the local OpenAI/Ollama-compatible light-model server and drives it with
the production ``OllabridgeConnector`` over real HTTP — the same code path used
against a live Ollabridge gateway (local or cloud). This locks the wire contract
in CI without downloading a real model. The full five-day workflow lives in
``scripts/e2e_week_simulation.py`` (``make sim``).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from daypilot_models.ollabridge_client import OllabridgeConnector  # noqa: E402
from scripts.sim.light_model_server import MODEL_ID, start_server  # noqa: E402


def test_pairing_and_inference_over_real_http():
    server, base_url = start_server()
    try:
        connector = OllabridgeConnector(base_url=base_url.removesuffix("/v1"), mode="local")

        reachable, latency, models = connector.ping()
        assert reachable is True
        assert latency is not None and latency >= 0
        assert MODEL_ID in models

        planner = connector.generate("Plan my day with prioritized blocks", task="planner")
        assert planner["backend"] == "ollabridge"
        assert "Priorities" in planner["text"]
        assert planner["usage"]["total_tokens"] > 0

        coding = connector.generate("Implement input validation with tests", task="coding")
        assert "change" in coding["text"].lower()

        email = connector.generate("Draft a reply to this inbox item", task="email")
        assert "not sent" in email["text"].lower()
    finally:
        server.shutdown()
