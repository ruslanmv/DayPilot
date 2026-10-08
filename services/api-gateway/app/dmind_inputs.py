"""Bounded text extraction for dmind (batch B3).

Everything here treats its input as hostile: file sizes, archive shapes, XML features, page counts,
response sizes, redirects and network targets are all limited before any content is trusted. The
functions are pure (bytes in, text out) apart from the explicit URL fetcher and optional OCR
subprocess, and they never write to disk or touch the database.

Extracted text is *data*: it feeds the outline parser and is never executed or rendered as markup.
"""

from __future__ import annotations

import hashlib
import io
import ipaddress
import re
import shutil
import socket
import subprocess
import time
import zipfile
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import httpx

MAX_FILE_BYTES = 10_000_000
MAX_TEXT_CHARS = 100_000
MAX_LINE_CHARS = 500  # the longest label a dmind topic can hold
MAX_PAGE_BYTES = 1_000_000
MAX_PDF_PAGES = 200
MAX_DOCX_ENTRIES = 1000
MAX_DOCX_EXPANDED = 50_000_000
MAX_DOCX_XML = 20_000_000
MAX_REDIRECTS = 3
FETCH_DEADLINE_SECONDS = 10.0
ALLOWED_PORTS = {80, 443}
FETCH_TYPES = {"text/html", "application/xhtml+xml", "text/plain", "text/markdown"}


class InputError(Exception):
    """A refusal with an HTTP status and a message that says what to do next."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Extraction:
    text: str
    extractor: str
    title: str = ""
    pages: int | None = None
    warnings: list[str] = field(default_factory=list)


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- normalisation


def finish(text: str, extractor: str, **extra: Any) -> Extraction:
    """Clean extracted text, wrap over-long lines (never truncate), and enforce the size limit."""
    warnings: list[str] = list(extra.pop("warnings", []))
    text = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    lines: list[str] = []
    wrapped = 0
    for raw in text.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            if lines and lines[-1] != "":
                lines.append("")
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        room = max(40, MAX_LINE_CHARS - indent)
        while len(body) > room:
            cut = body.rfind(" ", 0, room)
            cut = cut if cut > room // 2 else room
            lines.append(" " * indent + body[:cut].rstrip())
            body = body[cut:].lstrip()
            wrapped += 1
        lines.append(" " * indent + body)
    while lines and lines[-1] == "":
        lines.pop()
    out = "\n".join(lines)
    if wrapped:
        warnings.append(f"{wrapped} long line(s) were split at word boundaries to fit topic labels.")
    if not out.strip():
        raise InputError(
            422,
            "No text was found. A scanned document needs OCR, which is available for images only.",
        )
    if len(out) > MAX_TEXT_CHARS:
        raise InputError(
            413,
            f"The extracted text is {len(out):,} characters; the limit is {MAX_TEXT_CHARS:,}. "
            "Split the document and import the parts you need.",
        )
    return Extraction(text=out, extractor=extractor, warnings=warnings, **extra)


# --------------------------------------------------------------------------- plain text


def text_file(data: bytes) -> Extraction:
    try:
        return finish(data.decode("utf-8-sig"), "text")
    except UnicodeDecodeError as exc:
        raise InputError(422, "The file is not valid UTF-8 text.") from exc


# --------------------------------------------------------------------------- DOCX

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_DTD = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)


def _read_zip_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
    with zf.open(info) as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise InputError(422, "The document's text part is too large to read safely.")
    return data


def docx_text(data: bytes) -> Extraction:
    """Headings and list levels become indentation, so the outline parser sees the structure."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise InputError(422, "This is not a valid DOCX (ZIP) file.") from exc
    infos = zf.infolist()
    if len(infos) > MAX_DOCX_ENTRIES:
        raise InputError(422, "The document contains too many parts to read safely.")
    if sum(i.file_size for i in infos) > MAX_DOCX_EXPANDED:
        raise InputError(422, "The document expands to more than 50 MB and was refused.")
    for i in infos:
        if i.file_size > 1_000_000 and i.file_size > 200 * max(i.compress_size, 1):
            raise InputError(422, "The document looks like a compression bomb and was refused.")
        name = i.filename
        if name.startswith(("/", "\\")) or ".." in name.split("/") or "\\" in name:
            raise InputError(422, "The document contains an unsafe part name and was refused.")
        if i.flag_bits & 0x1:
            raise InputError(422, "Encrypted documents are not supported.")
    try:
        info = zf.getinfo("word/document.xml")
    except KeyError as exc:
        raise InputError(422, "This ZIP file is not a Word document.") from exc
    xml = _read_zip_member(zf, info, MAX_DOCX_XML)
    if _DTD.search(xml):
        raise InputError(422, "The document contains a DTD or entity declaration and was refused.")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise InputError(422, "The document's text could not be parsed.") from exc

    lines: list[str] = []
    heading = 0
    for p in root.iter(f"{W}p"):
        text = []
        for e in p.iter():
            if e.tag == f"{W}t":
                text.append(e.text or "")
            elif e.tag in (f"{W}tab", f"{W}br", f"{W}cr"):
                text.append(" ")
        body = " ".join("".join(text).split())
        if not body:
            continue
        style = p.find(f"{W}pPr/{W}pStyle")
        style_id = (style.get(f"{W}val") if style is not None else "") or ""
        m = re.fullmatch(r"(?i)heading\s*(\d)", style_id)
        level = int(m.group(1)) if m else (1 if style_id.lower() == "title" else 0)
        ilvl = p.find(f"{W}pPr/{W}numPr/{W}ilvl")
        depth = int(ilvl.get(f"{W}val") or 0) if ilvl is not None else 0
        if level:
            heading = min(level, 6)
            lines.append("  " * (heading - 1) + body)
        else:
            lines.append("  " * (heading + min(depth, 6)) + body)
    return finish("\n".join(lines), "docx")


# --------------------------------------------------------------------------- PDF


def pdf_text(data: bytes) -> Extraction:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise InputError(
            501, "PDF extraction needs the optional 'pypdf' package: pip install 'daypilot[dmind-extract]'."
        ) from exc
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise InputError(422, "Password-protected PDFs are not supported.")
        pages = list(reader.pages)
    except InputError:
        raise
    except Exception as exc:  # malformed input of every kind surfaces as one clear refusal
        raise InputError(422, "This PDF could not be read; it may be damaged.") from exc
    if len(pages) > MAX_PDF_PAGES:
        raise InputError(422, f"The PDF has {len(pages)} pages; the limit is {MAX_PDF_PAGES}. Split it first.")
    out: list[str] = []
    warnings: list[str] = []
    for n, page in enumerate(pages, 1):
        try:
            out.append(page.extract_text() or "")
        except Exception:
            warnings.append(f"Page {n} could not be read and was skipped.")
    return finish("\n".join(out), "pdf", pages=len(pages), warnings=warnings)


# --------------------------------------------------------------------------- OCR (images)

_IMAGE_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"II*\x00", b"MM\x00*", b"BM")


def is_image(data: bytes) -> bool:
    return data[:8].startswith(_IMAGE_MAGIC) or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def ocr_text(data: bytes, language: str = "eng") -> Extraction:
    exe = shutil.which("tesseract")
    if not exe:
        raise InputError(501, "Image text recognition needs Tesseract OCR installed on the server.")
    if not re.fullmatch(r"[a-z_]{2,12}(\+[a-z_]{2,12}){0,3}", language):
        raise InputError(500, "The configured OCR language is invalid.")
    try:
        proc = subprocess.run(
            [exe, "stdin", "stdout", "-l", language],
            input=data,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise InputError(504, "Reading the image took too long; try a smaller image.") from exc
    if proc.returncode != 0:
        raise InputError(422, "The image could not be read.")
    return finish(proc.stdout.decode("utf-8", errors="replace"), "ocr")


# --------------------------------------------------------------------------- HTML -> outline text

_SKIP = {"script", "style", "noscript", "template", "svg", "iframe", "object", "embed", "head", "nav", "footer", "aside", "form"}
_BLOCK = {"p", "div", "section", "article", "main", "br", "tr", "table", "blockquote", "pre", "ul", "ol", "dl", "dt", "dd", "figure", "figcaption"}


class _HtmlOutline(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.buffer: list[str] = []
        self.skip = 0
        self.heading = 0
        self.depth = 0
        self.indent = 0
        self.title = ""
        self._in_title = False

    def _flush(self) -> None:
        text = " ".join("".join(self.buffer).split())
        self.buffer = []
        if text:
            self.lines.append("  " * self.indent + text)

    def _body_indent(self) -> int:
        """Text sits one level under its heading; nested lists go one level deeper each."""
        return self.heading + min(max(self.depth - 1, 0), 6)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag in _SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self.heading = int(tag[1])
            self.indent = self.heading - 1
        elif tag in ("ul", "ol"):
            self._flush()
            self.depth += 1
            self.indent = self._body_indent()
        elif tag == "li" or tag in _BLOCK:
            self._flush()
            self.indent = self._body_indent()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if re.fullmatch(r"h[1-6]", tag) or tag in _BLOCK or tag == "li":
            self._flush()
        if tag in ("ul", "ol"):
            self.depth = max(0, self.depth - 1)
            self.indent = self._body_indent()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if not self.skip:
            self.buffer.append(data)

    def close(self) -> None:  # type: ignore[override]
        super().close()
        self._flush()


def html_text(html: str) -> Extraction:
    parser = _HtmlOutline()
    parser.feed(html)
    parser.close()
    title = " ".join(unescape(parser.title).split())[:200]
    result = finish("\n".join(parser.lines), "html")
    result.title = title
    return result


# --------------------------------------------------------------------------- dispatch


def extract_text(name: str, data: bytes) -> Extraction:
    """Choose the extractor from the bytes themselves; a file name is only a hint."""
    if len(data) > MAX_FILE_BYTES:
        raise InputError(413, "Use a file smaller than 10 MB.")
    if not data:
        raise InputError(422, "The file is empty.")
    lower = name.lower()
    if data.startswith(b"%PDF-"):
        return pdf_text(data)
    if data.startswith(b"PK\x03\x04"):
        if lower.endswith(".docx") or lower.endswith(".docm") or not lower.rsplit(".", 1)[-1].isalpha():
            return docx_text(data)
        raise InputError(415, "Only DOCX archives are supported.")
    if is_image(data):
        return ocr_text(data)
    if re.search(r"\.(txt|md|markdown|text)$", lower):
        return text_file(data)
    raise InputError(415, "Supported documents: DOCX, PDF, images (OCR), TXT and Markdown.")


# --------------------------------------------------------------------------- URL fetching

Resolver = Callable[..., Any]


def _public_ip(raw: str) -> ipaddress._BaseAddress:
    ip = ipaddress.ip_address(raw.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        elif any(ip in ipaddress.ip_network(n) for n in ("2002::/16", "2001::/32", "64:ff9b::/96", "64:ff9b:1::/48")):
            raise InputError(422, "That address range is not allowed.")  # tunnels can embed private IPv4
    if not ip.is_global or ip.is_multicast:
        raise InputError(422, "Only public internet addresses can be fetched; that address is private or reserved.")
    return ip


def resolve_public(host: str, port: int, resolver: Resolver = socket.getaddrinfo) -> list[ipaddress._BaseAddress]:
    """Every address the name resolves to must be public; one private answer refuses the lot."""
    try:
        infos = resolver(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise InputError(422, "That address could not be resolved.") from exc
    ips = [_public_ip(info[4][0]) for info in infos]
    if not ips:
        raise InputError(422, "That address could not be resolved.")
    return ips


def check_url(url: str) -> tuple[str, str, int, str]:
    """Return (scheme, host, port, path-with-query) for an acceptable URL, else raise."""
    if len(url) > 2048 or any(ord(c) < 33 or ord(c) == 127 for c in url):
        raise InputError(422, "That is not a valid web address.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise InputError(422, "Only http and https addresses can be fetched.")
    if parsed.username is not None or parsed.password is not None or "@" in (parsed.netloc or ""):
        raise InputError(422, "Addresses with embedded credentials are not allowed.")
    host = parsed.hostname
    if not host:
        raise InputError(422, "That is not a valid web address.")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise InputError(422, "That is not a valid web address.") from exc
    if port not in ALLOWED_PORTS:
        raise InputError(422, "Only ports 80 and 443 can be fetched.")
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    return parsed.scheme, host.lower(), port, path


def fetch_page(
    url: str,
    *,
    resolver: Resolver = socket.getaddrinfo,
    transport: httpx.BaseTransport | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[Extraction, dict[str, Any]]:
    """Fetch one public web page as outline text. The caller must have enabled URL fetching."""
    started = clock()
    current = url
    for hop in range(MAX_REDIRECTS + 1):
        scheme, host, port, path = check_url(current)
        ips = resolve_public(host, port, resolver)
        ip = ips[0]  # connect to the address we validated, never to a fresh lookup
        netloc = f"[{ip}]" if ip.version == 6 else str(ip)
        default = 443 if scheme == "https" else 80
        target = f"{scheme}://{netloc}{'' if port == default else f':{port}'}{path}"
        headers = {
            "Host": host if port == default else f"{host}:{port}",
            "User-Agent": "DayPilot-dmind/1 (+text extraction)",
            "Accept": "text/html,text/markdown,text/plain;q=0.9",
            "Accept-Encoding": "identity",
        }
        extensions = {"sni_hostname": host} if scheme == "https" else {}
        client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(5.0),
            follow_redirects=False,
            trust_env=False,  # no ambient proxy, cookie or credential settings
        )
        try:
            with client, client.stream("GET", target, headers=headers, extensions=extensions) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        raise InputError(502, "The page redirected without saying where.")
                    if hop == MAX_REDIRECTS:
                        raise InputError(502, "The page redirected too many times.")
                    current = urljoin(current, location)
                    continue
                if response.status_code != 200:
                    raise InputError(502, f"The page returned HTTP {response.status_code}.")
                ctype = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype not in FETCH_TYPES:
                    raise InputError(415, "Only web pages and text files can be fetched.")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > MAX_PAGE_BYTES:
                        raise InputError(413, "The page is larger than 1 MB. Save the part you need as text instead.")
                    if clock() - started > FETCH_DEADLINE_SECONDS:
                        raise InputError(504, "The page took too long to download.")
                charset = "utf-8"
                m = re.search(r"charset=([\w-]+)", response.headers.get("content-type", ""), re.I)
                if m:
                    charset = m.group(1)
        except httpx.TimeoutException as exc:
            raise InputError(504, "The page took too long to respond.") from exc
        except httpx.HTTPError as exc:
            raise InputError(502, "The page could not be reached.") from exc
        try:
            html = bytes(body).decode(charset, errors="replace")
        except LookupError:
            html = bytes(body).decode("utf-8", errors="replace")
        result = finish(html, "text") if ctype in ("text/plain", "text/markdown") else html_text(html)
        source = {
            "kind": "url",
            "url": current,
            "bytes": len(body),
            "sha256": sha256(bytes(body)),
            "extractor": result.extractor,
            "title": result.title,
        }
        return result, source
    raise InputError(502, "The page redirected too many times.")  # pragma: no cover
