"""Hybrid retrieval + citation assembly (batch B10).

Keyword + token-overlap scoring over document chunks, scoped by project. Returns
ranked passages with citations (document + chunk). A vector backend (Qdrant via
Ollabridge embeddings) can be layered in later; the contract — ranked passages
with citations — stays the same.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Document, DocumentChunk

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass
class Passage:
    chunk_id: str
    document_id: str
    document_title: str
    chunk_index: int
    text: str
    score: float


def hybrid_search(
    session: Session,
    query: str,
    project_id: str | None = None,
    limit: int = 5,
    candidate_pool: int = 2000,
) -> list[Passage]:
    q_tokens = _tokens(query)
    if not q_tokens:
        return []
    q_set = set(q_tokens)

    stmt = select(DocumentChunk, Document).join(Document, DocumentChunk.document_id == Document.id)
    if project_id:
        stmt = stmt.where(Document.project_id == project_id)
    rows = session.execute(stmt.limit(candidate_pool)).all()

    scored: list[Passage] = []
    for chunk, document in rows:
        c_tokens = _tokens(chunk.text)
        if not c_tokens:
            continue
        counts = Counter(c_tokens)
        # Keyword overlap (recall) + term-frequency weighting (precision).
        overlap = len(q_set & set(c_tokens))
        if overlap == 0:
            continue
        tf = sum(counts[t] for t in q_set)
        length_norm = 1.0 / (1.0 + math.log1p(len(c_tokens)))
        score = overlap * 2.0 + tf * length_norm
        scored.append(
            Passage(
                chunk_id=chunk.id,
                document_id=document.id,
                document_title=document.title or document.source_uri,
                chunk_index=chunk.chunk_index,
                text=chunk.text[:600],
                score=round(score, 4),
            )
        )
    scored.sort(key=lambda p: p.score, reverse=True)
    return scored[:limit]


def to_citations(passages: list[Passage]) -> list[dict[str, Any]]:
    return [
        {
            "documentId": p.document_id,
            "documentTitle": p.document_title,
            "chunkIndex": p.chunk_index,
            "score": p.score,
        }
        for p in passages
    ]
