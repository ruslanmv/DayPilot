"""B3 inputs: bounded extraction (text, DOCX, PDF, OCR) and hardened URL fetching."""

import gzip
import io
import socket
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient

from app import dmind_inputs as inputs
from app.main import app
from app.routers import diagram_inputs

HEADERS = {"X-Workspace-Id": "ws-inputs"}
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def client():
    return TestClient(app)


def upload(c, name, data, content_type="application/octet-stream"):
    return c.post("/v1/diagram-inputs/extract", files={"file": (name, data, content_type)}, headers=HEADERS)


# ----------------------------------------------------------------------------- builders


def docx(paragraphs, extra=None, document_xml=None):
    """paragraphs: (text, style, ilvl) tuples."""
    body = ""
    for text, style, ilvl in paragraphs:
        ppr = ""
        if style:
            ppr += f'<w:pStyle w:val="{style}"/>'
        if ilvl is not None:
            ppr += f'<w:numPr><w:ilvl w:val="{ilvl}"/><w:numId w:val="1"/></w:numPr>'
        ppr = f"<w:pPr>{ppr}</w:pPr>" if ppr else ""
        body += f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>"
    xml = document_xml or f'<?xml version="1.0"?><w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", xml)
        for name, content in (extra or {}).items():
            z.writestr(name, content)
    return buf.getvalue()


def pdf(lines):
    """A minimal one-page PDF whose text layer is `lines`."""
    esc = lambda s: s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")  # noqa: E731
    stream = "BT /F1 12 Tf 72 720 Td 14 TL " + " T* ".join(f"({esc(line)}) Tj" for line in lines) + " ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


# ----------------------------------------------------------------------------- text files


def test_text_and_markdown_files():
    c = client()
    raw = "\ufeff- one\n  - two\r\nthree\n".encode()
    r = upload(c, "notes.md", raw)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"] == "- one\n  - two\nthree"
    s = body["source"]
    assert (s["kind"], s["name"], s["extractor"], s["bytes"]) == ("file", "notes.md", "text", len(raw))
    assert s["sha256"].startswith("sha256:") and len(s["sha256"]) == 71


def test_text_refusals_are_specific():
    c = client()
    assert upload(c, "x.txt", b"\xff\xfe\x00bad").status_code == 422
    assert upload(c, "x.txt", b"").status_code == 422
    assert upload(c, "x.txt", b"   \n \n").status_code == 422
    assert upload(c, "x.exe", b"MZ\x90\x00").status_code == 415
    assert upload(c, "x.txt", b"x " * 60_000).status_code == 413  # over 100000 characters: never truncated
    r = upload(c, "big.txt", b"a" * 10_000_001)
    assert r.status_code == 413 and "10 MB" in r.json()["detail"]


def test_long_lines_are_wrapped_not_truncated_and_noted():
    text = " ".join(f"word{i}" for i in range(400))  # one ~2800 character line
    r = upload(client(), "long.txt", text.encode())
    body = r.json()
    lines = body["text"].split("\n")
    assert all(len(line) <= 500 for line in lines)
    assert " ".join(lines) == text  # nothing lost
    assert any("split" in w for w in body["warnings"])


def test_control_characters_are_removed_and_names_are_cleaned():
    r = upload(client(), "..\\..\\evil.txt", b"ok\x00\x07 text")
    assert r.status_code == 200
    assert r.json()["text"] == "ok text"
    assert r.json()["source"]["name"] == "evil.txt"  # a path is never kept
    assert diagram_inputs.clean_name("a/b\\c\x00d\x1f.txt") == "cd.txt"
    assert diagram_inputs.clean_name(None) == "document" and diagram_inputs.clean_name("") == "document"
    assert len(diagram_inputs.clean_name("x" * 500)) == 200


# ----------------------------------------------------------------------------- DOCX


def test_docx_headings_and_lists_become_outline_indentation():
    data = docx(
        [
            ("Order process", "Title", None),
            ("Intake", "Heading1", None),
            ("Receive the order", None, None),
            ("Check stock", None, 1),
            ("Billing", "Heading2", None),
            ("Charge the card", None, 0),
            ("Refund rules", "Heading1", None),
            ("", None, None),
            ("Last note", None, None),
        ]
    )
    r = upload(client(), "process.docx", data)
    assert r.status_code == 200, r.text
    lines = r.json()["text"].split("\n")
    assert lines[0] == "Order process" and lines[1] == "Intake"  # Title and Heading 1 are top level
    assert "  Receive the order" in lines and "    Check stock" in lines
    assert "  Billing" in lines and "    Charge the card" in lines  # Heading 2 is one level in
    assert lines[-2:] == ["Refund rules", "  Last note"]
    assert r.json()["source"]["extractor"] == "docx"


def test_docx_text_is_data_not_markup():
    data = docx([('&lt;script&gt;alert(1)&lt;/script&gt; &amp; more', None, None)])
    assert upload(client(), "x.docx", data).json()["text"] == "<script>alert(1)</script> & more"


@pytest.mark.parametrize(
    "xml",
    [
        '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "x">]><w:document xmlns:w="%s"/>' % W,
        '<?xml version="1.0"?><!DOCTYPE d SYSTEM "http://169.254.169.254/x"><w:document xmlns:w="%s"/>' % W,
        '<?xml version="1.0"?><!doctype lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;">]>'
        '<w:document xmlns:w="%s"><w:body><w:p><w:r><w:t>&lol2;</w:t></w:r></w:p></w:body></w:document>' % W,
    ],
)
def test_docx_entity_and_dtd_attacks_are_refused(xml):
    r = upload(client(), "evil.docx", docx([], document_xml=xml))
    assert r.status_code == 422 and "DTD" in r.json()["detail"]


def test_docx_archive_attacks_are_refused():
    c = client()
    assert upload(c, "x.docx", b"PK\x03\x04 not really a zip").status_code == 422
    assert upload(c, "x.docx", docx([("hi", None, None)], extra={"../evil": "x"})).status_code == 422
    assert upload(c, "x.docx", docx([("hi", None, None)], extra={"/abs": "x"})).status_code == 422
    plain = io.BytesIO()
    with zipfile.ZipFile(plain, "w") as z:
        z.writestr("hello.txt", "hi")
    assert "not a Word document" in upload(c, "x.docx", plain.getvalue()).json()["detail"]
    assert upload(c, "x.zip", plain.getvalue()).status_code == 415
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", "<a/>")
        z.writestr("word/big.bin", b"\0" * 5_000_000)  # compresses ~1000:1
    r = upload(c, "bomb.docx", bomb.getvalue())
    assert r.status_code == 422 and "compression bomb" in r.json()["detail"]
    many = io.BytesIO()
    with zipfile.ZipFile(many, "w") as z:
        z.writestr("word/document.xml", "<a/>")
        for i in range(1100):
            z.writestr(f"p{i}", "")
    assert "too many parts" in upload(c, "many.docx", many.getvalue()).json()["detail"]
    huge = io.BytesIO()
    with zipfile.ZipFile(huge, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", "<a>" + "x" * 100 + "</a>")
        z.writestr("word/a.bin", b"1234567890" * 6_000_000)  # 60 MB expanded
    assert upload(c, "huge.docx", huge.getvalue()).status_code == 422
    assert upload(c, "bad.docx", docx([], document_xml="<w:document")).status_code == 422


# ----------------------------------------------------------------------------- PDF


def test_pdf_text_and_provenance():
    r = upload(client(), "spec.pdf", pdf(["Billing flow", "Retry three times"]))
    assert r.status_code == 200, r.text
    assert r.json()["text"].split("\n") == ["Billing flow", "Retry three times"]
    assert (r.json()["source"]["extractor"], r.json()["source"]["pages"]) == ("pdf", 1)


def test_pdf_refusals():
    from pypdf import PdfWriter

    c = client()
    assert upload(c, "x.pdf", b"%PDF-1.4 garbage").status_code == 422
    locked = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(72, 72)
    writer.encrypt("secret")
    writer.write(locked)
    assert "Password-protected" in upload(c, "locked.pdf", locked.getvalue()).json()["detail"]
    blank = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(72, 72)
    writer.write(blank)
    r = upload(c, "scan.pdf", blank.getvalue())
    assert r.status_code == 422 and "OCR" in r.json()["detail"]  # a scan has no text layer
    many = io.BytesIO()
    writer = PdfWriter()
    for _ in range(inputs.MAX_PDF_PAGES + 1):
        writer.add_blank_page(72, 72)
    writer.write(many)
    assert "limit is 200" in upload(c, "many.pdf", many.getvalue()).json()["detail"]


def test_missing_pdf_library_is_explained(monkeypatch):
    import builtins

    real = builtins.__import__

    def deny(name, *a, **k):
        if name.startswith("pypdf"):
            raise ImportError(name)
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", deny)
    r = upload(client(), "x.pdf", pdf(["hi"]))
    assert r.status_code == 501 and "pypdf" in r.json()["detail"]


# ----------------------------------------------------------------------------- OCR


PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


def test_ocr_unavailable_is_explained(monkeypatch):
    monkeypatch.setattr(inputs.shutil, "which", lambda name: None)
    r = upload(client(), "shot.png", PNG)
    assert r.status_code == 501 and "Tesseract" in r.json()["detail"]
    assert client().get("/v1/diagram-inputs/capabilities", headers=HEADERS).json()["ocr"] is False


def test_ocr_runs_tesseract_with_bounds(monkeypatch):
    calls = {}
    monkeypatch.setattr(inputs.shutil, "which", lambda name: "/usr/bin/tesseract")

    def run(cmd, input, capture_output, timeout, check):
        calls.update(cmd=cmd, size=len(input), timeout=timeout)
        return type("P", (), {"returncode": 0, "stdout": b"Scanned heading\n  Scanned item\n"})()

    monkeypatch.setattr(inputs.subprocess, "run", run)
    r = upload(client(), "shot.png", PNG)
    assert r.status_code == 200 and r.json()["text"] == "Scanned heading\n  Scanned item"
    assert r.json()["source"]["extractor"] == "ocr"
    assert calls["cmd"] == ["/usr/bin/tesseract", "stdin", "stdout", "-l", "eng"] and calls["timeout"] == 30
    for magic in (b"\xff\xd8\xff\xe0", b"GIF89a", b"RIFF\0\0\0\0WEBPVP8 ", b"BM\0\0"):
        assert upload(client(), "i", magic + b"\0" * 20).status_code == 200


def test_ocr_failures(monkeypatch):
    monkeypatch.setattr(inputs.shutil, "which", lambda name: "/usr/bin/tesseract")
    monkeypatch.setattr(
        inputs.subprocess, "run", lambda *a, **k: type("P", (), {"returncode": 1, "stdout": b""})()
    )
    assert upload(client(), "x.png", PNG).status_code == 422

    def slow(*a, **k):
        raise inputs.subprocess.TimeoutExpired("tesseract", 30)

    monkeypatch.setattr(inputs.subprocess, "run", slow)
    assert upload(client(), "x.png", PNG).status_code == 504
    with pytest.raises(inputs.InputError):
        inputs.ocr_text(PNG, language="eng; rm -rf /")  # the language is never passed through unchecked


def test_capabilities_report_limits():
    body = client().get("/v1/diagram-inputs/capabilities", headers=HEADERS).json()
    assert body["docx"] is True and body["pdf"] is True and body["urlFetch"] is False
    assert body["limits"]["textChars"] == 100_000


# ----------------------------------------------------------------------------- HTML text


def test_html_becomes_outline_text_without_markup_or_scripts():
    html = """<!doctype html><html><head><title>Billing &amp; Orders</title>
    <style>.x{}</style><script>alert('x')</script></head><body>
    <nav>Home | About</nav><h1>Billing</h1><p>How we charge.</p>
    <h2>Retries</h2><ul><li>Three attempts</li><li>Then cancel<ul><li>Email the buyer</li></ul></li></ul>
    <iframe src="http://evil"></iframe><noscript>no</noscript><footer>(c)</footer></body></html>"""
    result = inputs.html_text(html)
    assert result.title == "Billing & Orders"
    assert result.text.split("\n") == [
        "Billing",
        "  How we charge.",
        "  Retries",
        "    Three attempts",
        "    Then cancel",
        "      Email the buyer",
    ]
    assert "<" not in result.text and "alert" not in result.text and "Home" not in result.text


# ----------------------------------------------------------------------------- URL fetch


def resolver_for(mapping):
    def resolve(host, port, type=None):
        value = mapping.get(host)
        if value is None:
            raise socket.gaierror("unknown host")
        values = value if isinstance(value, list) else [value]
        return [
            (socket.AF_INET6 if ":" in v else socket.AF_INET, socket.SOCK_STREAM, 6, "", (v, port))
            for v in values
        ]

    return resolve


PUBLIC = {"example.org": "93.184.216.34", "other.example": "151.101.1.1"}


def page(body="<h1>Hello</h1><p>World</p>", ctype="text/html; charset=utf-8", status=200, headers=None):
    return lambda request: httpx.Response(status, content=body, headers={"content-type": ctype, **(headers or {})})


def fetch(url, handler=None, mapping=PUBLIC):
    return inputs.fetch_page(
        url, resolver=resolver_for(mapping), transport=httpx.MockTransport(handler or page())
    )


def test_fetch_returns_outline_text_and_provenance():
    result, source = fetch("https://example.org/docs?a=1")
    assert result.text == "Hello\n  World"
    assert source["kind"] == "url" and source["url"] == "https://example.org/docs?a=1"
    assert source["sha256"].startswith("sha256:") and source["extractor"] == "html"


def test_fetch_connects_to_the_validated_address_with_the_original_host():
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), host=request.headers["host"], sni=request.extensions.get("sni_hostname"),
                    accept_encoding=request.headers["accept-encoding"], cookie=request.headers.get("cookie"),
                    auth=request.headers.get("authorization"))
        return httpx.Response(200, content=b"hi", headers={"content-type": "text/plain"})

    fetch("https://example.org/a b".replace(" ", "%20"), handler)
    assert seen["url"] == "https://93.184.216.34/a%20b"  # never a second DNS lookup
    assert seen["host"] == "example.org" and seen["sni"] == "example.org"
    assert seen["accept_encoding"] == "identity" and seen["cookie"] is None and seen["auth"] is None
    fetch("http://example.org:80/x", handler)
    assert seen["url"] == "http://93.184.216.34/x" and seen["sni"] is None


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/", "http://localhost/", "http://localhost./", "http://10.0.0.5/",
        "http://192.168.1.1/", "http://172.16.0.1/", "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/", "http://0.0.0.0/", "http://[::1]/", "http://[::ffff:127.0.0.1]/",
        "http://[fe80::1]/", "http://[fc00::1]/", "http://[2002:7f00:1::]/", "http://[64:ff9b::7f00:1]/",
        "http://2130706433/", "http://0x7f.0.0.1/", "http://0177.0.0.1/", "http://127.1/",
        "http://224.0.0.1/", "http://240.0.0.1/", "http://metadata.internal/", "http://rebind.example/",
    ],
)
def test_private_and_reserved_targets_are_refused(url):
    mapping = {
        **PUBLIC,
        "localhost": "127.0.0.1", "localhost.": "127.0.0.1", "metadata.internal": "169.254.169.254",
        "2130706433": "127.0.0.1", "0x7f.0.0.1": "127.0.0.1", "0177.0.0.1": "127.0.0.1", "127.1": "127.0.0.1",
        "rebind.example": ["93.184.216.34", "10.0.0.1"],  # one private answer poisons the name
        "127.0.0.1": "127.0.0.1", "10.0.0.5": "10.0.0.5", "192.168.1.1": "192.168.1.1",
        "172.16.0.1": "172.16.0.1", "169.254.169.254": "169.254.169.254", "100.64.0.1": "100.64.0.1",
        "0.0.0.0": "0.0.0.0", "::1": "::1", "::ffff:127.0.0.1": "::ffff:127.0.0.1", "fe80::1": "fe80::1",
        "fc00::1": "fc00::1", "2002:7f00:1::": "2002:7f00:1::", "64:ff9b::7f00:1": "64:ff9b::7f00:1",
        "224.0.0.1": "224.0.0.1", "240.0.0.1": "240.0.0.1",
    }
    contacted = []
    with pytest.raises(inputs.InputError) as raised:
        fetch(url, lambda request: contacted.append(request) or httpx.Response(200), mapping)
    assert raised.value.status == 422 and not contacted, "nothing may be sent to a refused target"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd", "ftp://example.org/x", "gopher://example.org/", "javascript:alert(1)",
        "http://user:pass@example.org/", "http://example.org@evil.example/", "https://:@example.org/",
        "http://example.org:22/", "http://example.org:8080/", "http://example.org:99999/", "http:///x",
        "http://exa mple.org/", "http://example.org/\x00", "", "//example.org/", "example.org",
        "http://" + "a" * 2100,
    ],
)
def test_malformed_and_unsafe_urls_are_refused(url):
    with pytest.raises(inputs.InputError) as raised:
        fetch(url)
    assert raised.value.status == 422


def test_unresolvable_host_is_refused():
    with pytest.raises(inputs.InputError, match="resolved"):
        fetch("http://nope.example/")


def test_redirects_are_followed_and_revalidated():
    hops = []

    def handler(request):
        hops.append(request.headers["host"])
        if request.headers["host"] == "example.org":
            return httpx.Response(302, headers={"location": "https://other.example/final"})
        return httpx.Response(200, content=b"<p>Final</p>", headers={"content-type": "text/html"})

    result, source = fetch("http://example.org/start", handler)
    assert result.text == "Final" and hops == ["example.org", "other.example"]
    assert source["url"] == "https://other.example/final"
    # A redirect into the private network is refused before anything is sent to it.
    sent = []

    def sneaky(request):
        sent.append(request.headers["host"])
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    with pytest.raises(inputs.InputError, match="private"):
        fetch("http://example.org/", sneaky, {**PUBLIC, "169.254.169.254": "169.254.169.254"})
    assert sent == ["example.org"]
    for bad in ("file:///etc/passwd", "http://user@example.org/", "http://localhost/"):
        with pytest.raises(inputs.InputError):
            fetch("http://example.org/", lambda r, b=bad: httpx.Response(302, headers={"location": b}),
                  {**PUBLIC, "localhost": "127.0.0.1"})


def test_redirect_loops_and_missing_locations_stop():
    with pytest.raises(inputs.InputError, match="too many"):
        fetch("http://example.org/", lambda r: httpx.Response(302, headers={"location": "/again"}))
    with pytest.raises(inputs.InputError, match="without saying where"):
        fetch("http://example.org/", lambda r: httpx.Response(301))


def test_response_limits_types_and_failures():
    with pytest.raises(inputs.InputError) as big:
        fetch("http://example.org/", page(b"x" * (inputs.MAX_PAGE_BYTES + 1), "text/plain"))
    assert big.value.status == 413
    for ctype in ("application/pdf", "application/octet-stream", "image/png", "application/json", ""):
        with pytest.raises(inputs.InputError) as bad:
            fetch("http://example.org/", page(b"x", ctype))
        assert bad.value.status == 415
    with pytest.raises(inputs.InputError) as missing:
        fetch("http://example.org/", page(status=404))
    assert missing.value.status == 502 and "404" in missing.value.message
    with pytest.raises(inputs.InputError) as slow:
        fetch("http://example.org/", lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=r)))
    assert slow.value.status == 504
    with pytest.raises(inputs.InputError) as down:
        fetch("http://example.org/", lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused", request=r)))
    assert down.value.status == 502
    assert fetch("http://example.org/", page("plain *text*", "text/markdown"))[0].text == "plain *text*"


def test_compressed_responses_cannot_expand_past_the_limit():
    bomb = gzip.compress(b"a" * 20_000_000)
    assert len(bomb) < 100_000
    with pytest.raises(inputs.InputError) as raised:
        fetch("http://example.org/", page(bomb, "text/plain", headers={"content-encoding": "gzip"}))
    assert raised.value.status == 413


def test_total_download_time_is_bounded():
    ticks = iter(range(0, 1000, 12))  # each clock read is twelve seconds later
    with pytest.raises(inputs.InputError) as raised:
        inputs.fetch_page(
            "http://example.org/",
            resolver=resolver_for(PUBLIC),
            transport=httpx.MockTransport(page(b"x" * 10, "text/plain")),
            clock=lambda: next(ticks),
        )
    assert raised.value.status == 504


def test_charset_is_honoured_and_unknown_charsets_fall_back():
    latin = "caf\xe9".encode("latin-1")
    assert fetch("http://example.org/", page(latin, "text/plain; charset=latin-1"))[0].text == "café"
    assert fetch("http://example.org/", page("é".encode(), "text/plain; charset=nonsense"))[0].text == "é"


# ----------------------------------------------------------------------------- endpoint policy


def test_url_fetch_is_off_by_default_and_never_reaches_the_network(monkeypatch):
    called = []
    monkeypatch.setattr(inputs, "fetch_page", lambda *a, **k: called.append(a))
    r = client().post("/v1/diagram-inputs/fetch-url", json={"url": "http://example.org/"}, headers=HEADERS)
    assert r.status_code == 403 and "DAYPILOT_DMIND_URL_FETCH" in r.json()["detail"] and not called


def test_url_fetch_when_enabled(monkeypatch):
    monkeypatch.setenv("DAYPILOT_DMIND_URL_FETCH", "true")
    real = inputs.fetch_page
    monkeypatch.setattr(
        diagram_inputs.inputs, "fetch_page",
        lambda url: real(url, resolver=resolver_for(PUBLIC), transport=httpx.MockTransport(page())),
    )
    c = client()
    assert c.get("/v1/diagram-inputs/capabilities", headers=HEADERS).json()["urlFetch"] is True
    r = c.post("/v1/diagram-inputs/fetch-url", json={"url": "https://example.org/x"}, headers=HEADERS)
    assert r.status_code == 200 and r.json()["text"] == "Hello\n  World"
    assert r.json()["source"]["url"] == "https://example.org/x"
    bad = c.post("/v1/diagram-inputs/fetch-url", json={"url": "http://127.0.0.1/"}, headers=HEADERS)
    assert bad.status_code == 422 and "resolved" in bad.json()["detail"]
    assert c.post("/v1/diagram-inputs/fetch-url", json={"url": ""}, headers=HEADERS).status_code == 422


def test_real_resolver_refuses_loopback_without_any_connection(monkeypatch):
    monkeypatch.setenv("DAYPILOT_DMIND_URL_FETCH", "true")
    for url in ("http://127.0.0.1/", "http://localhost/", "http://[::1]/", "http://2130706433/"):
        r = client().post("/v1/diagram-inputs/fetch-url", json={"url": url}, headers=HEADERS)
        assert r.status_code == 422, (url, r.text)


def test_endpoints_follow_diagram_access_rules(monkeypatch):
    monkeypatch.setenv("DAYPILOT_AUTH_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_AUTH_TOKENS", "read:read_only,write:operator")
    c = client()
    files = {"file": ("a.txt", b"hello", "text/plain")}
    assert c.post("/v1/diagram-inputs/extract", files=files).status_code == 401
    assert c.post("/v1/diagram-inputs/extract", files=files, headers={"Authorization": "Bearer read"}).status_code == 403
    assert c.get("/v1/diagram-inputs/capabilities", headers={"Authorization": "Bearer read"}).status_code == 200
    ok = c.post("/v1/diagram-inputs/extract", files=files, headers={"Authorization": "Bearer write"})
    assert ok.status_code == 200 and ok.json()["text"] == "hello"
    other = {"Authorization": "Bearer write", "X-Workspace-Id": "someone-elses"}
    assert c.post("/v1/diagram-inputs/extract", files=files, headers=other).status_code == 403
