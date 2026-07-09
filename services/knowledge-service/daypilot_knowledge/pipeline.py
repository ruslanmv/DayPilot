from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import select
from starlette.responses import Response

from daypilot_knowledge.db import Base, Document, DocumentChunk, create_engine_from_settings, session_scope

INGESTED_DOCUMENTS = Counter("daypilot_knowledge_documents_ingested_total", "Documents ingested")
SEARCHES = Counter("daypilot_knowledge_searches_total", "Private memory search requests")
INGEST_LATENCY = Histogram("daypilot_knowledge_ingest_seconds", "Ingest pipeline latency")


class IngestRequest(BaseModel):
    path: str = Field(..., description="Local path or source URI to register")
    title: str | None = None
    text: str | None = Field(default=None, description="Optional already-extracted text")


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=50)


def init_database() -> None:
    engine = create_engine_from_settings()
    Base.metadata.create_all(engine)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _chunk_text(text: str, max_chars: int = 1200) -> list[str]:
    clean = text.strip()
    if not clean:
        return []
    return [clean[i : i + max_chars] for i in range(0, len(clean), max_chars)]


@INGEST_LATENCY.time()
def ingest_document(path: str, title: str | None = None, text: str | None = None) -> dict[str, Any]:
    init_database()
    source = Path(path)
    if text is None and source.exists() and source.is_file():
        text = source.read_text(encoding="utf-8", errors="ignore")
    text = text or ""
    digest = _sha256_text(text or path)
    chunks = _chunk_text(text)
    with session_scope() as session:
        document = Document(source_uri=path, title=title or source.name or path, sha256=digest, ingest_state="indexed")
        session.add(document)
        session.flush()
        for index, chunk in enumerate(chunks):
            session.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    text=chunk,
                    token_count=max(1, len(chunk.split())),
                    metadata_json={"engine": os.getenv("QDRANT_URL", "local-sqlite")},
                )
            )
        document_id = document.id
    INGESTED_DOCUMENTS.inc()
    return {
        "status": "indexed",
        "document_id": document_id,
        "path": path,
        "sha256": digest,
        "chunks": len(chunks),
        "vector_backend": os.getenv("QDRANT_URL", "local-sqlite"),
    }


def search_private_memory(query: str, limit: int = 5) -> dict[str, Any]:
    init_database()
    SEARCHES.inc()
    needle = query.lower().strip()
    with session_scope() as session:
        rows = session.scalars(select(DocumentChunk).limit(500)).all()
        matches = [chunk for chunk in rows if needle and needle in chunk.text.lower()]
        results = [
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text[:500],
                "score": 1.0,
            }
            for chunk in matches[:limit]
        ]
    return {"status": "ok", "query": query, "results": results, "count": len(results)}


app = FastAPI(title="DayPilot Knowledge Service", version="0.2.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "daypilot-knowledge-service", "database_url": os.getenv("DATABASE_URL", "sqlite")}


@app.post("/v1/documents/ingest")
def ingest(request: IngestRequest) -> dict[str, Any]:
    return ingest_document(path=request.path, title=request.title, text=request.text)


@app.post("/v1/search")
def search(request: SearchRequest) -> dict[str, Any]:
    return search_private_memory(request.query, request.limit)


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
