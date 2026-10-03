"""Expert builders: opt-in, pre-checked, and run in a sandbox with no network, files or credentials."""

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.presentations import render, sandbox

from test_presentations import setup_company, story

READY = sandbox.available()["ready"]
needs_sandbox = pytest.mark.skipif(not READY, reason="needs setpriv, unshare, prlimit and node (runs as root in CI containers)")

GOOD = """
export default async function build(deck) {
  const t = deck.addSlide('title')
  t.addText('Weekly review: our process improved', { ...deck.box(0.8, 2.6, 11.7, 1.2), fontFace: deck.fonts.heading, fontSize: 40, bold: true, color: 'FFFFFF' })
  t.addNotes('Opening.')
  const s = deck.addSlide('content')
  s.addText('Delivered per day', { ...deck.box(0.6, 0.5, 12.1, 0.9), fontFace: deck.fonts.heading, fontSize: 28, bold: true, color: deck.color.foreground })
  s.addChart(deck.charts.bar, [{ name: 'Delivered', labels: ['Mon', 'Tue', 'Wed'], values: [4, 5, 6] }], { ...deck.box(0.6, 1.6, 8, 5), chartColors: deck.seriesColors })
  s.addNotes('Source: tracker export.')
}
"""


@pytest.fixture(autouse=True)
def flags(monkeypatch, tmp_path):
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS", "true")
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS_EXPERT", "true")
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS_DIR", str(tmp_path / "store"))


def ws():
    return {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}


def deck(c, h):
    cid, kit = setup_company(c, h)
    r = c.post("/v1/presentations/decks", json={"companyId": cid, "storyline": story()}, headers=h)
    assert r.status_code == 202, r.text
    return r.json()["id"], kit["kit"]


@pytest.mark.parametrize("script,why", [
    ("export default async (deck) => { const fs = await import('node:fs') }", "imports"),
    ("import fs from 'node:fs'\nexport default (deck) => {}", "imports"),
    ("export default (deck) => { require('fs') }", "require"),
    ("export default (deck) => { process.env.TOKEN }", "process"),
    ("export default (deck) => { eval('1') }", "eval"),
    ("export default (deck) => { new Function('return 1')() }", "eval"),
    ("export default async (deck) => { await fetch('https://example.com') }", "network"),
    ("export default (deck) => { globalThis.x = 1 }", "globalThis"),
    ("export default (deck) => { `${process.pid}` }", "process"),
    ("function build(deck) {}", "export default"),
])
def test_precheck_refuses_obvious_escapes(script, why):
    assert any(why in p for p in sandbox.precheck(script))


def test_precheck_allows_plain_words_in_strings_and_comments():
    assert sandbox.precheck(GOOD + "\n// we fetch( nothing; process notes only\n") == []


def test_flag_off_hides_expert(monkeypatch):
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS_EXPERT", "false")
    c, h = TestClient(app), ws()
    assert c.get("/v1/presentations/capabilities").json()["expert"]["enabled"] is False
    assert c.post("/v1/presentations/decks/x/expert", json={"script": GOOD, "expectedRevision": 1}, headers=h).status_code == 404


@needs_sandbox
def test_endpoint_refuses_prechecked_scripts_with_reasons():
    c, h = TestClient(app), ws()
    did, _ = deck(c, h)
    r = c.post(f"/v1/presentations/decks/{did}/expert", json={"script": "export default (deck) => { require('fs') }", "expectedRevision": 1}, headers=h)
    assert r.status_code == 422 and "require" in r.text


@needs_sandbox
def test_expert_build_is_checked_and_downloadable():
    c, h = TestClient(app), ws()
    did, _ = deck(c, h)
    r = c.post(f"/v1/presentations/decks/{did}/expert", json={"script": GOOD, "expectedRevision": 1}, headers=h)
    assert r.status_code == 202, r.text
    head = c.get(f"/v1/presentations/decks/{did}", headers=h).json()["head"]
    assert head["revision"] == 2 and head["author"] == "expert" and head["run"]["status"] == "succeeded", head["run"]["error"]
    assert head["slideCount"] == 2
    if render.capabilities()["ready"]:
        assert head["state"] == "review_ready", head
    f = c.get(f"/v1/presentations/decks/{did}/revisions/2/files/pptx", headers=h)
    assert f.status_code == 200 and f.content[:2] == b"PK"
    # a normal revision afterwards returns to the composed deck
    back = c.post(f"/v1/presentations/decks/{did}/revisions", json={"storyline": story(), "expectedRevision": 2}, headers=h)
    assert back.status_code == 202
    assert c.get(f"/v1/presentations/decks/{did}", headers=h).json()["head"]["slideCount"] == 5


@needs_sandbox
def test_off_slide_geometry_is_a_hard_finding():
    c, h = TestClient(app), ws()
    did, _ = deck(c, h)
    script = "export default (deck) => { const s = deck.addSlide('content'); s.addText('Too wide', { ...deck.box(10, 1, 6, 1), fontFace: deck.fonts.body }); s.addNotes('n') }"
    assert c.post(f"/v1/presentations/decks/{did}/expert", json={"script": script, "expectedRevision": 1}, headers=h).status_code == 202
    head = c.get(f"/v1/presentations/decks/{did}", headers=h).json()["head"]
    assert head["state"] == "failed" and any(f["code"] == "off_slide" for f in head["findings"]), head


def kit_for(c, h):
    _, kit = setup_company(c, h, logo=False)
    return kit["kit"]


# The probes below bypass the pre-check (the sandbox must hold on its own) by calling the runner
# directly with the check disabled.
ESCAPES = {
    "read_secrets": "const fs = await deck.__import('node:fs'); fs.readFileSync('/etc/passwd', 'utf8')",
    "read_env": "const p = deck.__global.process; if (Object.keys(p.env).some((k) => !['PATH', 'HOME', 'NODE_ENV'].includes(k))) throw new Error('LEAK ' + Object.keys(p.env)); throw new Error('clean environment')",
    "spawn": "const cp = await deck.__import('node:child_process'); cp.execSync('id')",
    "network": "await fetch('http://1.1.1.1/')",
    "write_outside": "const fs = await deck.__import('node:fs'); fs.writeFileSync('/tmp/dp-expert-escape', 'x')",
}

EXPECT = {
    "read_secrets": "--allow-fs-read",
    "read_env": "clean environment",
    "spawn": "--allow-child-process",
    "network": "fetch failed",
    "write_outside": "--allow-fs-write",
}

PROBE = """
const G = (0, eval)('this')
export default async function build(deck) {{
  deck = {{ ...deck, __global: G, __import: (m) => import(m) }}
  {body}
}}
"""


@needs_sandbox
@pytest.mark.parametrize("name", sorted(ESCAPES))
def test_sandbox_holds_without_the_precheck(monkeypatch, name):
    c, h = TestClient(app), ws()
    kit = kit_for(c, h)
    monkeypatch.setattr(sandbox, "precheck", lambda script: [])
    with pytest.raises(sandbox.SandboxError) as err:
        sandbox.run(PROBE.format(body=ESCAPES[name]), kit, {})
    assert EXPECT[name] in str(err.value), str(err.value)
    assert not os.path.exists("/tmp/dp-expert-escape")


@needs_sandbox
def test_runaway_builders_are_stopped(monkeypatch):
    c, h = TestClient(app), ws()
    kit = kit_for(c, h)
    monkeypatch.setattr(sandbox, "TIMEOUT", 5)
    with pytest.raises(sandbox.SandboxError, match="longer than"):
        sandbox.run("export default (deck) => { for (;;) {} }", kit, {})


@needs_sandbox
def test_reply_carries_inspection_and_receipt():
    c, h = TestClient(app), ws()
    data, reply = sandbox.run(GOOD, kit_for(c, h), {})
    assert data[:2] == b"PK" and len(reply["inspection"]["slides"]) == 2
    assert reply["receipt"]["findings"] == [] or all(f["severity"] != "hard" for f in reply["receipt"]["findings"]), json.dumps(reply["receipt"])
