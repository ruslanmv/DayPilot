"""RAG quality evaluation scorecard (batch B14).

Scores retrieval quality on a labeled eval set: context precision (are retrieved
passages relevant?), context recall (did we retrieve the passages we should?),
citation coverage (does the answer cite grounding?), and a faithfulness proxy
(is the answer supported by retrieved text?). Used as a scheduled scorecard and
a CI regression gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from .document_ai import chat
from .retrieval import hybrid_search


@dataclass
class EvalCase:
    query: str
    project_id: str
    relevant_document_ids: list[str]
    expected_terms: list[str]


def evaluate(session: Session, cases: list[EvalCase], k: int = 5) -> dict[str, Any]:
    precisions: list[float] = []
    recalls: list[float] = []
    citation_hits = 0
    faithful_hits = 0

    for case in cases:
        passages = hybrid_search(session, case.query, project_id=case.project_id, limit=k)
        retrieved_ids = [p.document_id for p in passages]
        relevant = set(case.relevant_document_ids)

        if retrieved_ids:
            precision = sum(1 for d in retrieved_ids if d in relevant) / len(retrieved_ids)
        else:
            precision = 0.0
        recall = (
            sum(1 for d in relevant if d in retrieved_ids) / len(relevant) if relevant else 1.0
        )
        precisions.append(precision)
        recalls.append(recall)

        answer = chat(session, case.query, project_id=case.project_id, limit=k)
        if answer.get("citations"):
            citation_hits += 1
        text = answer.get("answer", "").lower()
        if any(term.lower() in text for term in case.expected_terms):
            faithful_hits += 1

    n = max(1, len(cases))
    scorecard = {
        "cases": len(cases),
        "contextPrecision": round(sum(precisions) / n, 3),
        "contextRecall": round(sum(recalls) / n, 3),
        "citationCoverage": round(citation_hits / n, 3),
        "faithfulness": round(faithful_hits / n, 3),
    }
    scorecard["passed"] = (
        scorecard["contextPrecision"] >= 0.5
        and scorecard["contextRecall"] >= 0.5
        and scorecard["citationCoverage"] >= 0.8
    )
    return scorecard
