"""Permission-checked, parser-based document ingestion (batch B10).

Ingest only from granted sources, parse to an AI-readable representation without
touching the original, chunk, and persist. The original file is never modified.
"""
from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

from .db import Document, DocumentChunk
from .parsers import parse_document
from .sources import get_registry


class SourceNotPermitted(PermissionError):
    """Raised when ingesting from a path outside any granted scope."""


def _chunk(text: str, size: int = 1200) -> list[str]:
    clean = text.strip()
    return [clean[i : i + size] for i in range(0, len(clean), size)] if clean else []


def ingest_document(
    session: Session,
    path: str,
    content: bytes | str | None = None,
    title: str | None = None,
    project_id: str | None = None,
    source_kind: str = "Local PC",
    enforce_permission: bool = True,
) -> dict[str, Any]:
    registry = get_registry()
    if enforce_permission and content is None and not registry.is_permitted(path):
        raise SourceNotPermitted(
            f"'{path}' is outside any granted source scope. Grant the folder first."
        )

    parsed = parse_document(path, content if content is not None else "")
    text = parsed.text
    digest = hashlib.sha256((text or path).encode("utf-8")).hexdigest()
    chunks = _chunk(text)

    document = Document(
        project_id=project_id,
        source_uri=path,
        title=title or path.split("/")[-1] or path,
        sha256=digest,
        ingest_state="indexed" if not parsed.needs_extra else "needs_parser",
        status="Indexed" if not parsed.needs_extra else "Not Yet Indexed",
        source=source_kind,
    )
    session.add(document)
    session.flush()
    for i, chunk in enumerate(chunks):
        session.add(
            DocumentChunk(document_id=document.id, chunk_index=i, text=chunk,
                          token_count=max(1, len(chunk.split())),
                          metadata_json={"parser": parsed.parser, "fileType": parsed.file_type})
        )
    session.flush()
    return {
        "documentId": document.id,
        "title": document.title,
        "fileType": parsed.file_type,
        "parser": parsed.parser,
        "chunks": len(chunks),
        "needsExtra": parsed.needs_extra,
        "originalPreserved": True,
    }
