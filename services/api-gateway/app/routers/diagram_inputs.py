"""dmind input extraction (batch B3): turn a document or a web page into reviewable outline text.

Nothing here saves anything. The browser shows the extracted text and its provenance, and the
person decides whether to use it. URL fetching is off unless the operator enables it, because a
server that fetches arbitrary addresses is a network-access decision.
"""

from __future__ import annotations

import os
import re
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from .. import dmind_inputs as inputs
from .diagrams import access

router = APIRouter(prefix="/v1/diagram-inputs", tags=["diagrams"])
URL_FETCH_ENV = "DAYPILOT_DMIND_URL_FETCH"


def url_fetch_enabled() -> bool:
    return os.getenv(URL_FETCH_ENV, "false").lower() == "true"


def refuse(exc: inputs.InputError) -> HTTPException:
    return HTTPException(exc.status, exc.message)


def clean_name(name: str | None) -> str:
    base = re.split(r"[\\/]", name or "document")[-1]
    return re.sub(r"[\x00-\x1f\x7f]", "", base)[:200] or "document"


class FetchIn(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)


def payload(result: inputs.Extraction, source: dict[str, Any]) -> dict[str, Any]:
    source = {**source, "extractor": result.extractor, "chars": len(result.text)}
    if result.pages is not None:
        source["pages"] = result.pages
    if result.title:
        source["title"] = result.title
    return {"text": result.text, "source": source, "warnings": result.warnings}


@router.get("/capabilities")
def capabilities(workspace: str = Depends(access)) -> dict[str, Any]:
    try:
        import pypdf  # noqa: F401

        pdf = True
    except ImportError:
        pdf = False
    return {
        "text": True,
        "docx": True,
        "pdf": pdf,
        "ocr": inputs.ocr_available(),
        "urlFetch": url_fetch_enabled(),
        "limits": {
            "fileBytes": inputs.MAX_FILE_BYTES,
            "textChars": inputs.MAX_TEXT_CHARS,
            "pdfPages": inputs.MAX_PDF_PAGES,
            "pageBytes": inputs.MAX_PAGE_BYTES,
        },
    }


@router.post("/extract")
async def extract(
    request: Request, file: UploadFile = File(...), workspace: str = Depends(access)
) -> dict[str, Any]:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > inputs.MAX_FILE_BYTES + 100_000:
        raise HTTPException(413, "Use a file smaller than 10 MB.")
    data = await file.read(inputs.MAX_FILE_BYTES + 1)
    name = clean_name(file.filename)
    try:
        result = inputs.extract_text(name, data)
    except inputs.InputError as exc:
        raise refuse(exc) from exc
    return payload(
        result,
        {"kind": "file", "name": name, "bytes": len(data), "sha256": inputs.sha256(data)},
    )


@router.post("/fetch-url")
def fetch_url(body: FetchIn, workspace: str = Depends(access)) -> dict[str, Any]:
    if not url_fetch_enabled():
        raise HTTPException(
            403,
            f"Fetching web pages is turned off on this server. An administrator can enable it with {URL_FETCH_ENV}=true.",
        )
    try:
        result, source = inputs.fetch_page(body.url.strip())
    except inputs.InputError as exc:
        raise refuse(exc) from exc
    return payload(result, source)
