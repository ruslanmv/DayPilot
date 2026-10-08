"""Import an existing company PowerPoint template (.pptx or .potx) as brand rules.

What is taken: theme colours, theme fonts, slide size, layout names and placeholders, footer text
and logo candidates from the masters/layouts. What is not: the template's own master/layout
geometry, background artwork, SmartArt, animations, media and embedded objects. DayPilot does not
claim to reproduce an arbitrary template; it builds new decks from these brand rules in its own
curated layouts, keeps the uploaded file byte-for-byte, and says exactly what it did not carry over.

Reading is strict: bounded ZIP (size, entries, ratio, no traversal, no encryption), no macros, no
external relationships, no DOCTYPE in any XML part.
"""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Any

MAX_FILE = 50_000_000
MAX_ENTRIES = 3000
MAX_ENTRY = 60_000_000
MAX_TOTAL = 300_000_000
MAX_RATIO = 200
EMU = 914_400
NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
}
MAIN_TYPES = {
    "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml": "pptx",
    "application/vnd.openxmlformats-officedocument.presentationml.template.main+xml": "potx",
}
SLOTS = ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink"]
METRIC_FONTS = {"Calibri", "Cambria", "Arial", "Times New Roman", "Courier New"}


class TemplateError(ValueError):
    pass


def _xml(zf: zipfile.ZipFile, name: str) -> ET.Element:
    data = zf.read(name)
    head = data[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in head:
        raise TemplateError(f"{name} declares a DOCTYPE or entities, which is not accepted.")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise TemplateError(f"{name} is not valid XML.") from exc


def _rels(zf: zipfile.ZipFile, part: str) -> list[dict[str, str]]:
    base, name = posixpath.split(part)
    rels = posixpath.join(base, "_rels", name + ".rels")
    if rels not in zf.namelist():
        return []
    out = []
    for r in _xml(zf, rels).findall("rel:Relationship", NS):
        target = r.get("Target", "")
        path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(base, target))
        out.append({"id": r.get("Id", ""), "type": r.get("Type", "").rsplit("/", 1)[-1], "mode": r.get("TargetMode", ""), "path": path})
    return out


def _open(data: bytes) -> zipfile.ZipFile:
    if len(data) > MAX_FILE:
        raise TemplateError("Use a template smaller than 50 MB.")
    if data[:4] != b"PK\x03\x04":
        raise TemplateError("This is not a PowerPoint file (.pptx or .potx).")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise TemplateError("The file is damaged.") from exc
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise TemplateError("The file has too many parts.")
    total, seen = 0, set()
    for i in infos:
        n = i.filename
        if n.startswith("/") or "\\" in n or ".." in n.split("/") or re.match(r"^[A-Za-z]:", n):
            raise TemplateError("The file contains an unsafe part name.")
        if n.lower() in seen:
            raise TemplateError("The file contains duplicate parts.")
        seen.add(n.lower())
        if i.flag_bits & 0x1:
            raise TemplateError("Encrypted files are not supported. Remove the password and try again.")
        if i.file_size > MAX_ENTRY or (i.compress_size and i.file_size / max(i.compress_size, 1) > MAX_RATIO and i.file_size > 1_000_000):
            raise TemplateError("The file looks like a compression bomb and was refused.")
        total += i.file_size
    if total > MAX_TOTAL:
        raise TemplateError("The file expands to more than 300 MB.")
    return zf


def _color(el: ET.Element | None) -> str | None:
    if el is None:
        return None
    srgb = el.find("a:srgbClr", NS)
    if srgb is not None and re.fullmatch(r"[0-9A-Fa-f]{6}", srgb.get("val", "")):
        return "#" + srgb.get("val").upper()
    sys = el.find("a:sysClr", NS)
    if sys is not None and re.fullmatch(r"[0-9A-Fa-f]{6}", sys.get("lastClr", "")):
        return "#" + sys.get("lastClr").upper()
    return None


def _lum(hex_: str) -> float:
    def lin(v: float) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contrast(a: str, b: str) -> float:
    x, y = sorted((_lum(a), _lum(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def read(data: bytes) -> dict[str, Any]:
    """Return {kind, report, logos: [(bytes, media_type, placement)]}. Raises TemplateError."""
    zf = _open(data)
    names = set(zf.namelist())
    if "[Content_Types].xml" not in names:
        raise TemplateError("This is not a PowerPoint file (no content types).")
    ct = _xml(zf, "[Content_Types].xml")
    overrides = {o.get("PartName", "").lstrip("/"): o.get("ContentType", "") for o in ct.findall("ct:Override", NS)}
    if any("macroEnabled" in v for v in overrides.values()) or any(n.lower().endswith("vbaproject.bin") for n in names):
        raise TemplateError("Macro-enabled files are not accepted.")
    main = next((p for p, t in overrides.items() if t in MAIN_TYPES), None)
    if not main:
        raise TemplateError("This is not a PowerPoint presentation or template.")
    kind = MAIN_TYPES[overrides[main]]
    for n in names:
        if n.endswith(".rels"):
            body = zf.read(n)
            if b'TargetMode="External"' in body and re.search(rb'Type="[^"]*/(hyperlink)"', body) is None:
                raise TemplateError("The file links to external content, which is not accepted.")
    pres = _xml(zf, main)
    size = pres.find("p:sldSz", NS)
    if size is None:
        raise TemplateError("The presentation has no slide size.")
    w_in, h_in = int(size.get("cx", "0")) / EMU, int(size.get("cy", "0")) / EMU
    prels = _rels(zf, main)
    masters = [r["path"] for r in prels if r["type"] == "slideMaster" and r["path"] in names]
    if not masters:
        raise TemplateError("The file has no slide master.")
    master = masters[0]
    mrels = _rels(zf, master)
    theme_part = next((r["path"] for r in mrels if r["type"] == "theme" and r["path"] in names), None)
    palette: dict[str, str] = {}
    fonts = {"heading": None, "body": None}
    theme_name = None
    if theme_part:
        theme = _xml(zf, theme_part)
        theme_name = theme.get("name")
        scheme = theme.find(".//a:clrScheme", NS)
        if scheme is not None:
            for slot in SLOTS:
                c = _color(scheme.find(f"a:{slot}", NS))
                if c:
                    palette[slot] = c
        major = theme.find(".//a:fontScheme/a:majorFont/a:latin", NS)
        minor = theme.find(".//a:fontScheme/a:minorFont/a:latin", NS)
        fonts = {"heading": major.get("typeface") if major is not None else None, "body": minor.get("typeface") if minor is not None else None}
    layouts = []
    for r in mrels:
        if r["type"] != "slideLayout" or r["path"] not in names:
            continue
        lx = _xml(zf, r["path"])
        csld = lx.find("p:cSld", NS)
        phs = [ph.get("type", "body") for ph in lx.iter(f"{{{NS['p']}}}ph")]
        layouts.append({"name": csld.get("name") if csld is not None else r["path"], "placeholders": phs})
    # Footer text and logo candidates from the master and its layouts.
    footer = None
    candidates = []
    for part in [master] + [r["path"] for r in mrels if r["type"] == "slideLayout" and r["path"] in names]:
        x = _xml(zf, part)
        for sp in x.iter(f"{{{NS['p']}}}sp"):
            ph = sp.find(".//p:nvPr/p:ph", NS)
            text = "".join(t.text or "" for t in sp.iter(f"{{{NS['a']}}}t")).strip()
            if not text or footer:
                continue
            off = sp.find(".//a:xfrm/a:off", NS)
            near_bottom = off is not None and int(off.get("y", "0")) / EMU > 0.85 * h_in
            # A footer placeholder, or plain text sitting in the master's footer band (not a page number field).
            if (ph is not None and ph.get("type") == "ftr") or (ph is None and near_bottom and not re.fullmatch(r"[\d\s‹›<>#]+", text)):
                footer = text[:160]
        rel_by_id = {r["id"]: r for r in _rels(zf, part)}
        for pic in x.iter(f"{{{NS['p']}}}pic"):
            blip = pic.find(".//a:blip", NS)
            ext = pic.find(".//a:xfrm/a:ext", NS)
            off = pic.find(".//a:xfrm/a:off", NS)
            rid = blip.get(f"{{{NS['r']}}}embed") if blip is not None else None
            rel = rel_by_id.get(rid or "")
            if not rel or rel["path"] not in names:
                continue
            w = int(ext.get("cx", "0")) / EMU if ext is not None else 0
            h = int(ext.get("cy", "0")) / EMU if ext is not None else 0
            if w <= 0 or h <= 0:
                continue
            full_bleed = w * h > 0.5 * w_in * h_in
            candidates.append({"part": rel["path"], "on": part, "w": round(w, 2), "h": round(h, 2),
                               "x": round(int(off.get("x", "0")) / EMU, 2) if off is not None else 0, "y": round(int(off.get("y", "0")) / EMU, 2) if off is not None else 0,
                               "background": full_bleed})
    # Same image used several times is one candidate; backgrounds are not logos.
    logos, seen_parts = [], set()
    for c in sorted(candidates, key=lambda c: c["w"] * c["h"]):
        if c["background"] or c["part"] in seen_parts:
            continue
        seen_parts.add(c["part"])
        data_ = zf.read(c["part"])
        ext = c["part"].rsplit(".", 1)[-1].lower()
        media = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "svg": "image/svg+xml"}.get(ext)
        logos.append({**c, "mediaType": media or f"unsupported/{ext}", "bytes": len(data_), "data": data_ if media else None})
    unsupported = {
        "smartArt": sum(1 for n in names if n.startswith("ppt/diagrams/")),
        "charts": sum(1 for n in names if re.match(r"ppt/charts/chart\d+\.xml$", n)),
        "media": sum(1 for n in names if n.startswith("ppt/media/") and n.rsplit(".", 1)[-1].lower() in ("mp4", "mov", "wmv", "avi", "mp3", "wav", "m4a")),
        "embeddedObjects": sum(1 for n in names if n.startswith("ppt/embeddings/")),
        "backgroundImages": sum(1 for c in candidates if c["background"]),
        "slides": sum(1 for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)),
    }
    mapping = propose(palette, fonts, footer, w_in, h_in)
    kept = ["theme colours" if palette else None, "theme fonts" if fonts["heading"] or fonts["body"] else None, "slide size", "footer text" if footer else None,
            f"{len([c for c in logos if c['data']])} logo candidate(s)" if any(c["data"] for c in logos) else None]
    not_kept = ["the template's own master and layout geometry (decks use DayPilot's curated layouts in your colours and fonts)"]
    if unsupported["backgroundImages"]:
        not_kept.append(f"{unsupported['backgroundImages']} background picture(s)")
    for key, label in (("smartArt", "SmartArt parts"), ("charts", "charts in the template"), ("media", "audio/video files"), ("embeddedObjects", "embedded objects"), ("slides", "example slides")):
        if unsupported[key]:
            not_kept.append(f"{unsupported[key]} {label}")
    if any(c["data"] is None for c in logos):
        not_kept.append("pictures in formats other than PNG, JPEG or SVG (for example EMF/WMF)")
    report = {
        "kind": kind, "themeName": theme_name, "slideSize": {"width_inches": round(w_in, 3), "height_inches": round(h_in, 3)},
        "palette": palette, "fonts": fonts, "footer": footer, "layouts": layouts[:40], "unsupported": unsupported,
        "kept": [k for k in kept if k], "notKept": not_kept, "proposal": mapping,
        "logoCandidates": [{k: v for k, v in c.items() if k != "data"} | {"index": i} for i, c in enumerate(logos)],
        "fidelity": "brand_rules_only",
        "fidelityNote": "Decks are built in DayPilot's own layouts using this template's colours, fonts, size, footer and logo. The template's own layouts are not reproduced.",
    }
    return {"kind": kind, "report": report, "logos": logos}


def propose(palette: dict[str, str], fonts: dict[str, str | None], footer: str | None, w: float, h: float) -> dict[str, Any]:
    """Brand choices that keep the template's identity and stay readable."""
    bg = palette.get("lt1", "#FFFFFF")
    fg = palette.get("dk1", "#1B2333")
    if _contrast(fg, bg) < 4.5:
        fg = "#1B2333"
    primary = next((palette[s] for s in ("accent1", "dk2", "accent2") if s in palette and max(_contrast(palette[s], "#FFFFFF"), _contrast(palette[s], fg)) >= 4.5), "#1F3A93")
    accent = next((palette[s] for s in ("accent2", "accent3", "accent4") if s in palette and palette[s] != primary), "#0FA3B1")
    warnings = []
    for role in ("heading", "body"):
        f = fonts.get(role)
        if f and f not in METRIC_FONTS:
            warnings.append(f"Font “{f}” is kept by name; viewers without it see a substitute and text fit is estimated.")
    if abs(w / h - 16 / 9) > 0.02:
        warnings.append(f"The template is {w:.2f} × {h:.2f} in; decks use this size, and DayPilot's layouts are designed for widescreen first.")
    return {
        "palette": {"background": bg, "foreground": fg, "primary": primary, "accent": accent},
        "headingFont": (fonts.get("heading") or "Calibri")[:40], "bodyFont": (fonts.get("body") or "Calibri")[:40],
        "footerText": footer, "slideSize": {"width_inches": round(w, 3), "height_inches": round(h, 3)}, "warnings": warnings,
    }
