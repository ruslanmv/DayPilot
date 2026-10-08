"""Template import: real .pptx/.potx files yield colours, fonts, size, footer and logo candidates;
the original is kept byte-for-byte; hostile packages are refused; a brand made from a template
builds a passing deck."""

import base64
import io
import os
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.presentations import brandkit, engine, render, template_import
from test_presentations import png, story

RENDER = render.capabilities()["ready"]


@pytest.fixture(autouse=True)
def flag(monkeypatch, tmp_path):
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS", "true")
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS_DIR", str(tmp_path / "store"))


@pytest.fixture(scope="module")
def corporate_pptx():
    """A real PowerPoint file in a fictional corporate style, with a logo on its layouts."""
    logo = png(300, 100, (139, 20, 60))
    kit = brandkit.build("acme", "Acme Corp", 1, {"palette": {"primary": "#8B143C", "accent": "#F2A900", "foreground": "#222222"}, "headingFont": "Cambria", "bodyFont": "Arial", "footerText": "Acme Corp · Confidential"},
                         [{"asset_id": "logo", "sha256": "0" * 64, "variant": "universal", "aspect_ratio": 3, "minimum_width_inches": 1.0, "clear_space_ratio": 0.2, "rights": "company_original"}])
    deck = engine.call({"op": "compose", "storyline": story(), "kit": kit, "options": {"deckId": "fixture"}})["deck"]
    with tempfile.TemporaryDirectory() as tmp:
        out = str(Path(tmp) / "t.pptx")
        engine.call({"op": "compile", "deck": deck, "kit": kit, "assets": {"logo": {"media_type": "image/png", "base64": base64.b64encode(logo).decode(), "width": 300, "height": 100}}, "out": out})
        return Path(out).read_bytes()


@pytest.fixture(scope="module")
def corporate_potx(corporate_pptx):
    if not RENDER:
        pytest.skip("needs LibreOffice to make a .potx")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "corp.pptx"
        src.write_bytes(corporate_pptx)
        env = {"PATH": os.environ["PATH"], "HOME": tmp, "SAL_USE_VCLPLUGIN": "svp"}
        subprocess.run(["soffice", f"-env:UserInstallation={(Path(tmp) / 'p').as_uri()}", "--headless", "--convert-to", "potx:Impress Office Open XML Template", "--outdir", tmp, str(src)], env=env, capture_output=True, timeout=120)
        return (Path(tmp) / "corp.potx").read_bytes()


def test_reading_a_real_pptx(corporate_pptx):
    r = template_import.read(corporate_pptx)
    rep = r["report"]
    assert rep["kind"] == "pptx" and rep["slideSize"] == {"width_inches": 13.333, "height_inches": 7.5}
    assert rep["palette"]["accent1"] == "#8B143C" and rep["palette"]["dk1"] == "#222222"
    assert rep["fonts"] == {"heading": "Cambria", "body": "Arial"}
    assert rep["proposal"]["palette"]["primary"] == "#8B143C" and rep["proposal"]["headingFont"] == "Cambria"
    assert any(c["mediaType"] == "image/png" and not c["background"] for c in rep["logoCandidates"])
    assert rep["unsupported"]["slides"] == 5 and any("example slides" in x for x in rep["notKept"])
    assert rep["fidelity"] == "brand_rules_only" and "not reproduced" in rep["fidelityNote"]


def test_reading_a_real_potx(corporate_potx):
    rep = template_import.read(corporate_potx)["report"]
    assert rep["kind"] == "potx" and rep["palette"].get("accent1") == "#8B143C"


def craft(entries, content_types=None):
    ct = content_types or ('<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                           '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/></Types>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


PRES = '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldSz cx="12192000" cy="6858000"/></p:presentation>'


@pytest.mark.parametrize("make,why", [
    (lambda pp: b"not a zip", "not a PowerPoint"),
    (lambda pp: craft({"ppt/presentation.xml": PRES}, content_types='<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml"/></Types>'), "Macro"),
    (lambda pp: craft({"ppt/presentation.xml": PRES, "ppt/vbaProject.bin": b"x"}), "Macro"),
    (lambda pp: craft({"ppt/presentation.xml": PRES, "ppt/_rels/presentation.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="https://evil.example/x.png" TargetMode="External"/></Relationships>'}), "external"),
    (lambda pp: craft({"../evil.xml": "x", "ppt/presentation.xml": PRES}), "unsafe part"),
    (lambda pp: craft({"ppt/presentation.xml": PRES, "ppt/big.xml": "A" * 40_000_000}), "compression bomb"),
    (lambda pp: craft({"ppt/presentation.xml": '<!DOCTYPE x [<!ENTITY a "b">]>' + PRES}), "DOCTYPE"),
    (lambda pp: craft({"ppt/presentation.xml": PRES}), "no slide master"),
    (lambda pp: craft({"word/document.xml": "<w/>"}, content_types='<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'), "not a PowerPoint presentation"),
    (lambda pp: encrypted(pp), "Encrypted"),
])
def test_hostile_or_wrong_files_are_refused(corporate_pptx, make, why):
    with pytest.raises(template_import.TemplateError, match=why):
        template_import.read(make(corporate_pptx))


def encrypted(data):
    src = zipfile.ZipFile(io.BytesIO(data))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i in src.infolist():
            z.writestr(i, src.read(i.filename))
    raw = bytearray(buf.getvalue())
    i = raw.find(b"PK\x01\x02")  # first central directory entry: set the "encrypted" flag
    raw[i + 8] |= 1
    return bytes(raw)


def test_import_api_keeps_the_original_and_builds_a_brand_from_it(corporate_pptx):
    c, h = TestClient(app), {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}
    co = c.post("/v1/presentations/companies", json={"name": "Acme Corp"}, headers=h).json()
    r = c.post(f"/v1/presentations/companies/{co['id']}/templates", files={"file": ("acme.pptx", corporate_pptx, "application/octet-stream")}, headers=h)
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["report"]["kind"] == "pptx" and "thumbnailKeys" not in t["report"]
    original = c.get(f"/v1/presentations/templates/{t['id']}/file", headers=h)
    assert original.content == corporate_pptx and "attachment" in original.headers["content-disposition"]
    if RENDER:
        assert t["report"]["rendered"] and t["report"]["thumbnails"] == 5
        assert c.get(f"/v1/presentations/templates/{t['id']}/thumbs/1", headers=h).content[:4] == b"\x89PNG"
    logo_index = next(x["index"] for x in t["report"]["logoCandidates"] if x["mediaType"] == "image/png")
    assert c.get(f"/v1/presentations/templates/{t['id']}/logo/{logo_index}", headers=h).content[:4] == b"\x89PNG"
    k = c.post(f"/v1/presentations/companies/{co['id']}/brand-kits", json={"fromTemplateId": t["id"], "templateLogoIndex": logo_index}, headers=h)
    assert k.status_code == 201, k.text
    kit = k.json()["kit"]
    assert kit["palette"]["primary"] == "#8B143C" and kit["typography"]["slide_title"]["family"] == "Cambria" and kit["typography"]["body"]["family"] == "Arial"
    assert kit["footer"]["text"] == "Acme Corp · Confidential" and kit["logos"][0]["aspect_ratio"] == pytest.approx(3, abs=0.02)
    d = c.post("/v1/presentations/decks", json={"companyId": co["id"], "storyline": story()}, headers=h).json()
    head = c.get(f"/v1/presentations/decks/{d['id']}", headers=h).json()["head"]
    assert head["run"]["status"] == "succeeded" and not [f for f in head["findings"] if f["severity"] == "hard"], head["findings"]
    other = {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}
    assert c.get(f"/v1/presentations/templates/{t['id']}", headers=other).status_code == 404
    assert c.get(f"/v1/presentations/templates/{t['id']}/file", headers=other).status_code == 404
    bad = c.post(f"/v1/presentations/companies/{co['id']}/templates", files={"file": ("x.pptm", craft({"ppt/presentation.xml": PRES, "ppt/vbaProject.bin": b"x"}), "application/octet-stream")}, headers=h)
    assert bad.status_code == 422 and "Macro" in bad.json()["detail"]


def test_four_by_three_templates_keep_their_size():
    rep = template_import.propose({"accent1": "#003366", "dk1": "#000000", "lt1": "#FFFFFF"}, {"heading": "Futura", "body": "Helvetica"}, None, 10, 7.5)
    assert rep["slideSize"] == {"width_inches": 10, "height_inches": 7.5}
    assert any("Futura" in w for w in rep["warnings"]) and any("10.00 × 7.50" in w for w in rep["warnings"])
    low = template_import.propose({"accent1": "#FFFF66", "accent2": "#FFEE00", "dk2": "#FFFFAA", "dk1": "#EEEEEE", "lt1": "#FFFFFF"}, {}, None, 13.333, 7.5)
    assert low["palette"]["foreground"] == "#1B2333"  # a near-white text colour is replaced by a readable one
    none_usable = template_import.propose({"accent1": "#777777", "accent2": "#888888", "dk2": "#7A7A7A"}, {}, None, 13.333, 7.5)
    assert none_usable["palette"]["primary"] == "#1F3A93"  # mid-grey reaches 4.5:1 with neither white nor dark text


def test_decks_can_be_built_at_four_by_three(tmp_path):
    kit = brandkit.build("c43", "Old Co", 1, {}, [], {"width_inches": 10, "height_inches": 7.5})
    deck = engine.call({"op": "compose", "storyline": story(), "kit": kit, "options": {"deckId": "d43"}})["deck"]
    out = engine.call({"op": "compile", "deck": deck, "kit": kit, "assets": {}, "out": str(tmp_path / "d.pptx")})
    assert out["receipt"]["hard_failures"] == 0, out["receipt"]["findings"]
    assert shutil.which("node")
