"""A tiny, dependency-free OpenAI/Ollama-compatible model server.

It stands in for a local Ollama instance running a light model (e.g.
``qwen2.5:0.5b``) so the DayPilot -> Ollabridge -> model inference path can be
exercised end to end over real HTTP. It is *not* a language model: responses are
deterministic and task-aware so a simulation run reads sensibly and is
reproducible. In a real deployment DayPilot pairs with the actual Ollabridge
gateway in front of Ollama; the wire contract (``/v1/models`` and
``/v1/chat/completions``) is identical.

Run standalone:  python -m scripts.sim.light_model_server  # serves on :11435
"""
from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL_ID = "qwen2.5:0.5b"
MODELS = [MODEL_ID, "qwen2.5-coder:0.5b"]


def _last_user_prompt(messages: list[dict]) -> str:
    for msg in reversed(messages or []):
        if msg.get("role") == "user":
            return str(msg.get("content", ""))
    return ""


def _reply(prompt: str) -> str:
    """Deterministic, task-aware completion keyed off the prompt intent."""
    p = prompt.lower()
    if "plan" in p or "priorit" in p or "schedule" in p or "day" in p:
        return (
            "Priorities for the day, highest-leverage first:\n"
            "1. Ship the blocking work on the critical-path project (deep-work block, morning).\n"
            "2. Review and approve the AI-prepared coding patch before it can merge.\n"
            "3. Clear inbox items that affect today's schedule; defer the rest.\n"
            "Protecting a 90-minute focus block and moving admin to the afternoon."
        )
    if any(k in p for k in ("code", "implement", "patch", "diff", "function", "bug", "refactor")):
        return (
            "Proposed change: add input validation and a typed return, keep the public\n"
            "signature stable, and cover the empty and boundary cases with two unit tests.\n"
            "Risk: low. Suggest running the fast test subset before requesting a write."
        )
    # RAG / grounded-answer intent is checked before the email branch because a
    # retrieved context can itself mention "email".
    if any(k in p for k in ("summar", "context", "document", "rag", "retriev", "based on", "question:", "top risk", "status and")):
        return (
            "Based on the retrieved project context: the serving-platform routing policy is\n"
            "under review and the workspace structure is approved (dark-mode ~76% done). The\n"
            "top risk is the connector authentication boundary; recommend resolving it before\n"
            "the next review gate."
        )
    if any(k in p for k in ("email", "reply", "inbox", "message", "draft")):
        return (
            "Draft reply (for your review — not sent):\n"
            "Thanks for the note. The revised timeline works on our side; I'll confirm the\n"
            "milestone dates by end of week and flag the one open dependency. Happy to sync\n"
            "briefly if useful."
        )
    return (
        "Acknowledged. I can continue a project, prepare a meeting, draft a reply, or show\n"
        "what needs approval — tell me which and I'll take the next step."
    )


def _completion_payload(model: str, prompt: str) -> dict:
    text = _reply(prompt)
    # Rough, stable token estimates (word-ish), enough for reporting.
    in_tok = len(re.findall(r"\S+", prompt))
    out_tok = len(re.findall(r"\S+", text))
    return {
        "id": "chatcmpl-sim",
        "object": "chat.completion",
        "model": model or MODEL_ID,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": in_tok, "completion_tokens": out_tok, "total_tokens": in_tok + out_tok},
    }


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):  # silence access logs
        return

    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/").endswith("/v1/models"):
            self._send(200, {"object": "list", "data": [{"id": m, "object": "model"} for m in MODELS]})
        elif self.path.rstrip("/").endswith("/api/tags"):
            self._send(200, {"models": [{"name": m} for m in MODELS]})
        elif self.path.rstrip("/").endswith("/health"):
            self._send(200, {"status": "ok", "models": MODELS})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            body = {}
        if self.path.endswith("/chat/completions"):
            prompt = _last_user_prompt(body.get("messages", []))
            self._send(200, _completion_payload(body.get("model", MODEL_ID), prompt))
        else:
            self._send(404, {"error": "not found"})


def start_server(host: str = "127.0.0.1", port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """Start the server in a daemon thread. Returns (server, base_url with /v1)."""
    server = ThreadingHTTPServer((host, port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    bound_port = server.server_address[1]
    return server, f"http://{host}:{bound_port}/v1"


if __name__ == "__main__":
    srv, base = start_server(port=11435)
    print(f"light model server ({MODEL_ID}) listening at {base}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
