"""Document parsers (batch B10).

Turn source files into an internal AI-readable text representation without ever
modifying the original. Text-native formats (md, txt, html, csv, tsv, json,
yaml, xml) are parsed directly; office/binary formats (docx, xlsx, pptx, pdf,
images) are parsed when the optional extras are installed and otherwise recorded
as needing a parser — the pipeline degrades rather than failing.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass

TEXT_EXTS = {".txt", ".md", ".markdown", ".rst", ".log"}
HTML_EXTS = {".html", ".htm"}
TABULAR_EXTS = {".csv", ".tsv"}
DATA_EXTS = {".json", ".yaml", ".yml", ".xml"}
OFFICE_EXTS = {".doc", ".docx", ".rtf", ".odt", ".xls", ".xlsx", ".xlsm", ".ods", ".ppt", ".pptx", ".odp", ".pdf"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}


@dataclass
class ParsedDocument:
    text: str
    file_type: str
    parser: str
    needs_extra: bool = False


def _ext(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot >= 0 else ""


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_document(filename: str, content: bytes | str) -> ParsedDocument:
    ext = _ext(filename)
    if isinstance(content, bytes):
        try:
            text_content = content.decode("utf-8")
        except UnicodeDecodeError:
            text_content = content.decode("utf-8", "replace")
    else:
        text_content = content

    if ext in TEXT_EXTS:
        return ParsedDocument(text=text_content.strip(), file_type="text", parser="text")
    if ext in HTML_EXTS:
        return ParsedDocument(text=_strip_html(text_content), file_type="html", parser="html")
    if ext in TABULAR_EXTS:
        delimiter = "\t" if ext == ".tsv" else ","
        rows = list(csv.reader(io.StringIO(text_content), delimiter=delimiter))
        flattened = "\n".join(" | ".join(row) for row in rows[:2000])
        return ParsedDocument(text=flattened, file_type="tabular", parser="csv")
    if ext in DATA_EXTS:
        if ext == ".json":
            try:
                obj = json.loads(text_content)
                return ParsedDocument(text=json.dumps(obj, indent=2)[:200000], file_type="data", parser="json")
            except ValueError:
                pass
        return ParsedDocument(text=text_content.strip(), file_type="data", parser="raw")
    if ext in OFFICE_EXTS:
        extracted = _parse_office(ext, content)
        if extracted is not None:
            return ParsedDocument(text=extracted, file_type="office", parser="office-extra")
        return ParsedDocument(
            text=f"[{ext} document — install RAG extras to extract text]",
            file_type="office", parser="none", needs_extra=True,
        )
    if ext in IMAGE_EXTS:
        return ParsedDocument(
            text=f"[image {filename} — OCR/vision extraction not enabled]",
            file_type="image", parser="none", needs_extra=True,
        )
    # Unknown: treat as best-effort text.
    return ParsedDocument(text=text_content.strip()[:200000], file_type="unknown", parser="fallback")


def _parse_office(ext: str, content: bytes | str) -> str | None:
    """Best-effort office extraction when optional libraries are available."""
    data = content if isinstance(content, bytes) else content.encode("utf-8", "replace")
    try:
        if ext == ".docx":
            import docx  # type: ignore

            document = docx.Document(io.BytesIO(data))
            return "\n".join(p.text for p in document.paragraphs)
        if ext in {".xlsx", ".xlsm"}:
            import openpyxl  # type: ignore

            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            out = []
            for sheet in wb.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    out.append(" | ".join("" if c is None else str(c) for c in row))
            return "\n".join(out)
        if ext == ".pdf":
            import pypdf  # type: ignore

            reader = pypdf.PdfReader(io.BytesIO(data))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:  # pragma: no cover - optional path
        return None
    return None
