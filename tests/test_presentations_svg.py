"""SVG logos: hostile input is refused or stripped; a clean logo becomes a PNG used by decks."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.presentations import render, svg

SVG = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 300 100"{extra}>{body}</svg>'
GOOD = SVG.format(extra="", body='<defs><linearGradient id="g"><stop offset="0" stop-color="#0B3C5D"/></linearGradient></defs><rect width="90" height="90" fill="url(#g)"/><circle cx="50" cy="50" r="25" style="fill:#E07A1F;stroke:none"/><text x="110" y="62" font-size="36">Northwind</text>')


def clean(body, extra=""):
    out, _, _ = svg.sanitize(SVG.format(extra=extra, body=body).encode())
    return out.decode()


def test_clean_logo_survives_with_internal_references():
    out, w, h = svg.sanitize(GOOD.encode())
    text = out.decode()
    assert (w, h) == (300, 100)
    assert 'fill="url(#g)"' in text and "Northwind" in text and "fill:#E07A1F" in text


@pytest.mark.parametrize("body,forbidden", [
    ('<script>alert(1)</script><rect width="1" height="1"/>', "script"),
    ('<rect width="1" height="1" onload="alert(1)"/>', "onload"),
    ('<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">x</div></foreignObject>', "foreignObject"),
    ('<image href="https://evil.example/x.png" width="1" height="1"/>', "evil.example"),
    ('<image href="data:image/png;base64,AAAA"/>', "data:"),
    ('<use href="https://evil.example/s.svg#a"/>', "evil.example"),
    ('<use xlink:href="javascript:alert(1)"/>', "javascript"),
    ('<a href="javascript:alert(1)"><rect width="1" height="1"/></a>', "javascript"),
    ('<style>@import url(https://evil.example/x.css)</style>', "evil.example"),
    ('<rect width="1" height="1" fill="url(https://evil.example/x)"/>', "evil.example"),
    ('<rect width="1" height="1" style="fill:url(https://evil.example/x);stroke:red"/>', "evil.example"),
    ('<rect width="1" height="1" style="behavior:url(x.htc)"/>', "behavior"),
    ('<rect width="1" height="1" style="fill:\\75 rl(https://evil.example)"/>', "evil.example"),
    ('<animate attributeName="href" to="javascript:alert(1)"/>', "animate"),
    ('<set attributeName="onclick" to="alert(1)"/>', "set"),
    ('<rect xmlns:x="urn:x" x:evil="1" width="1" height="1"/>', "evil"),
    ('<filter id="f"><feImage href="https://evil.example/x"/></filter>', "evil.example"),
])
def test_hostile_content_is_removed(body, forbidden):
    out = clean(body)
    assert forbidden not in out


@pytest.mark.parametrize("data,why", [
    (b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1">&x;</svg>', "DOCTYPE"),
    (b'<!DOCTYPE svg [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;">]><svg xmlns="http://www.w3.org/2000/svg">&b;</svg>', "DOCTYPE"),
    (b'<?xml-stylesheet href="https://evil.example/x.xsl"?><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>', "stylesheets"),
    (b'<html><svg/></html>', "not an SVG"),
    (b'<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>', "viewBox"),
    (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1"/>', "proportions"),
    (b"<svg" + b" " * 1_000_001, "1 MB"),
    (b'\xff\xfe<\x00s\x00', "UTF-8"),
    (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1">' + b"<g>" * 60 + b"</g>" * 60 + b"</svg>", "complex"),
    (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><rect', "could not be read"),
])
def test_unusable_svgs_are_refused(data, why):
    with pytest.raises(svg.SvgError, match=why):
        svg.sanitize(data)


@pytest.mark.skipif(not render.capabilities()["ready"], reason="needs the render worker")
def test_upload_returns_a_png_for_decks_and_keeps_the_sanitised_original(monkeypatch, tmp_path):
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS", "true")
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS_DIR", str(tmp_path))
    c, h = TestClient(app), {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}
    co = c.post("/v1/presentations/companies", json={"name": "Northwind"}, headers=h).json()
    evil = GOOD.replace("</svg>", '<script>alert(1)</script></svg>')
    r = c.post(f"/v1/presentations/companies/{co['id']}/assets", files={"file": ("logo.svg", evil.encode(), "image/svg+xml")}, headers=h)
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["mediaType"] == "image/png" and a["sanitized"] and a["width"] >= 1000 and abs(a["width"] / a["height"] - 3) < 0.05
    original = c.get(f"/v1/presentations/assets/{a['originalId']}", headers=h)
    assert b"<script" not in original.content and "sandbox" in original.headers["content-security-policy"] and "attachment" in original.headers["content-disposition"]
    k = c.post(f"/v1/presentations/companies/{co['id']}/brand-kits", json={"logoAssetId": a["id"]}, headers=h)
    assert k.status_code == 201 and k.json()["kit"]["logos"][0]["aspect_ratio"] == pytest.approx(3, abs=0.05)
    assert c.post(f"/v1/presentations/companies/{co['id']}/brand-kits", json={"logoAssetId": a["originalId"]}, headers=h).status_code == 422
    bad = c.post(f"/v1/presentations/companies/{co['id']}/assets", files={"file": ("x.svg", b'<!DOCTYPE x><svg xmlns="http://www.w3.org/2000/svg"/>', "image/svg+xml")}, headers=h)
    assert bad.status_code == 422 and "DOCTYPE" in bad.json()["detail"]
