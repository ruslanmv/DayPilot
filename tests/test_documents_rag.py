"""Tests for the documents/RAG pipeline (B10): parsers, permissions, hybrid
retrieval with citations, version-safe generation, and Document AI chat."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app
from daypilot_knowledge.parsers import parse_document
from daypilot_knowledge.sources import SourceRegistry

client = TestClient(app)


def _ws() -> str:
    return "ws-" + uuid.uuid4().hex[:8]


# --- Parsers ----------------------------------------------------------------

def test_parse_markdown_and_html_and_csv():
    md = parse_document("notes.md", "# Title\nBody text")
    assert md.file_type == "text" and "Body text" in md.text
    html = parse_document("page.html", "<h1>Hi</h1><script>x()</script><p>World</p>")
    assert "World" in html.text and "x()" not in html.text
    csv_doc = parse_document("data.csv", "a,b\n1,2")
    assert "a | b" in csv_doc.text


def test_binary_office_degrades_without_extra():
    parsed = parse_document("proposal.docx", b"\x50\x4b\x03\x04binarybytes")
    assert parsed.needs_extra is True
    assert parsed.file_type == "office"


# --- Source permissions -----------------------------------------------------

def test_ingest_outside_granted_scope_is_forbidden(monkeypatch):
    monkeypatch.delenv("DAYPILOT_LOCAL_SOURCES", raising=False)
    resp = client.post("/v1/documents/ingest", json={"path": "/etc/secret.txt"})
    assert resp.status_code == 403


def test_vault_is_always_permitted():
    reg = SourceRegistry()
    assert reg.is_permitted("vault://generated/x") is True
    assert reg.can_generate("vault://generated/x") is True


# --- Ingest + retrieval + chat with citations -------------------------------

def _ingest_inline(project_id: str, path: str, content: str) -> str:
    # content provided inline bypasses the filesystem permission check.
    resp = client.post(
        "/v1/documents/ingest",
        json={"path": path, "content": content, "projectId": project_id, "title": path},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["documentId"]


def test_chat_returns_grounded_answer_with_citations():
    project = "p-" + uuid.uuid4().hex[:8]
    _ingest_inline(project, "alpha.md", "The Client Alpha delivery date moved from Friday to Monday.")
    _ingest_inline(project, "beta.md", "Unrelated content about budgets and invoices.")

    resp = client.post(
        "/v1/documents/chat",
        json={"query": "When is the Alpha delivery date?", "projectId": project},
    ).json()
    assert resp["grounded"] is True
    assert resp["citations"]
    assert "Monday" in resp["answer"] or "delivery" in resp["answer"].lower()


def test_chat_without_grounding_is_honest():
    resp = client.post(
        "/v1/documents/chat",
        json={"query": "zzzznomatch", "projectId": "p-" + uuid.uuid4().hex[:8]},
    ).json()
    assert resp["grounded"] is False
    assert resp["citations"] == []


# --- Version-safe generation ------------------------------------------------

def test_generate_output_creates_new_version_and_preserves_original():
    project = "p-" + uuid.uuid4().hex[:8]
    source_id = _ingest_inline(project, "contract.md", "Original contract text.")
    gen = client.post(
        f"/v1/documents/{source_id}/generate",
        json={"title": "contract-summary", "content": "AI summary of the contract.", "kind": "summary"},
    )
    assert gen.status_code == 201
    body = gen.json()
    assert body["originalPreserved"] is True
    assert body["version"] == 2
    assert body["generatedDocumentId"] != source_id


def test_generate_missing_source_404():
    assert client.post("/v1/documents/nope/generate",
                       json={"title": "x", "content": "y"}).status_code == 404


# --- Project status rules ---------------------------------------------------

def test_project_status_from_tasks(monkeypatch):
    ws = _ws()
    # Create a project via design intake path is heavy; use a direct project.
    from app.db import _get_sessionmaker
    from daypilot_knowledge.db import Project, Task

    with _get_sessionmaker()() as s:
        project = Project(workspace_id=ws, name="Status test", risk="low")
        s.add(project)
        s.flush()
        pid = project.id
        for st in ("done", "done", "active", "blocked"):
            s.add(Task(workspace_id=ws, title="t", status=st, project_id=pid))
        s.commit()

    body = client.get(f"/v1/documents/project-status/{pid}").json()
    assert body["tasksTotal"] == 4
    assert body["tasksDone"] == 2
    assert body["progress"] == 50
    assert body["blockers"]
