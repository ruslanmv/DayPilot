"""SVG logos: an allowlist sanitiser and a rasteriser.

The sanitiser keeps only drawing elements and presentation attributes. Scripts, event handlers,
foreignObject, embedded or external images, stylesheets, animation, external references and any
DOCTYPE/entity declarations are refused or removed. Internal references (``url(#id)``, ``href="#id"``)
are the only links that survive. The cleaned SVG is kept as the original; decks use a PNG rendered
from it, so no SVG ever reaches a slide.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_BYTES = 1_000_000
MAX_ELEMENTS = 10_000
MAX_DEPTH = 50
RASTER_WIDTH = 1200
SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
XML = "http://www.w3.org/XML/1998/namespace"

ELEMENTS = {
    "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan",
    "defs", "linearGradient", "radialGradient", "stop", "clipPath", "mask", "title", "desc", "use", "symbol",
}
PRESENTATION = {
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity", "stroke-linecap",
    "stroke-linejoin", "stroke-miterlimit", "stroke-dasharray", "stroke-dashoffset", "opacity", "clip-path",
    "clip-rule", "mask", "font-family", "font-size", "font-weight", "font-style", "text-anchor",
    "dominant-baseline", "letter-spacing", "stop-color", "stop-opacity", "display", "visibility",
}
ATTRIBUTES = PRESENTATION | {
    "id", "d", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "fx", "fy", "width", "height",
    "viewBox", "preserveAspectRatio", "points", "transform", "gradientUnits", "gradientTransform", "offset",
    "spreadMethod", "clipPathUnits", "maskUnits", "maskContentUnits", "version", "style", "href",
}
DANGEROUS = re.compile(r"javascript:|vbscript:|data:|expression\s*\(|@import|behavior\s*:|-moz-binding", re.I)


class SvgError(ValueError):
    pass


def _local(tag: str) -> tuple[str | None, str]:
    if tag.startswith("{"):
        ns, _, name = tag[1:].partition("}")
        return ns, name
    return None, tag


def _safe_value(value: str) -> bool:
    """No scripts, data URIs, CSS escapes or imports; url() only to an element in this file."""
    if DANGEROUS.search(value) or "\\" in value:
        return False
    calls = re.findall(r"url\s*\(", value, re.I)
    if calls:
        return len(re.findall(r"url\(\s*#[A-Za-z0-9_.:-]+\s*\)", value, re.I)) == len(calls)
    return True


def _clean_style(style: str) -> str:
    kept = []
    for decl in style.split(";"):
        if ":" not in decl:
            continue
        prop, _, val = decl.partition(":")
        prop, val = prop.strip().lower(), val.strip()
        if prop in PRESENTATION and val and _safe_value(val):
            kept.append(f"{prop}:{val}")
    return ";".join(kept)


def _number(v: str | None) -> float | None:
    if not v:
        return None
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*(px)?\s*", v)
    return float(m.group(1)) if m else None


def sanitize(data: bytes) -> tuple[bytes, float, float]:
    """Return (clean SVG bytes, width, height). Raises SvgError for anything unsafe or unreadable."""
    if len(data) > MAX_BYTES:
        raise SvgError("Use an SVG smaller than 1 MB.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SvgError("The SVG must be UTF-8 text.") from exc
    low = text.lower()
    if "<!doctype" in low or "<!entity" in low or "<?xml-stylesheet" in low:
        raise SvgError("SVGs with DOCTYPE, entities or stylesheets are not accepted.")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SvgError("The SVG could not be read.") from exc
    ns, name = _local(root.tag)
    if ns != SVG or name != "svg":
        raise SvgError("The file is not an SVG image.")
    count = 0

    def walk(el: ET.Element, depth: int) -> None:
        nonlocal count
        count += 1
        if count > MAX_ELEMENTS or depth > MAX_DEPTH:
            raise SvgError("The SVG is too complex.")
        for key in list(el.attrib):
            kns, kname = _local(key)
            value = el.attrib[key]
            ok = (
                (kns is None and kname in ATTRIBUTES)
                or (kns == XLINK and kname == "href")
                or (kns == XML and kname == "space")
            )
            if ok and kname == "href":
                ok = bool(re.fullmatch(r"#[A-Za-z0-9_.:-]+", value.strip()))
            if ok and kname == "style":
                cleaned = _clean_style(value)
                if cleaned:
                    el.attrib[key] = cleaned
                    continue
                ok = False
            if not ok or not _safe_value(value) or kname.lower().startswith("on"):
                del el.attrib[key]
        for child in list(el):
            cns, cname = _local(child.tag)
            if cns != SVG or cname not in ELEMENTS:
                el.remove(child)
                continue
            walk(child, depth + 1)
        if el.text and _local(el.tag)[1] not in ("text", "tspan", "title", "desc"):
            el.text = None

    walk(root, 0)
    vb = (root.attrib.get("viewBox") or "").replace(",", " ").split()
    w, h = _number(root.attrib.get("width")), _number(root.attrib.get("height"))
    if len(vb) == 4:
        try:
            vw, vh = float(vb[2]), float(vb[3])
        except ValueError:
            vw = vh = 0
        if vw > 0 and vh > 0:
            w, h = (w or vw), (h or vh)
            if not (root.attrib.get("width") and root.attrib.get("height")):
                w, h = vw, vh
    if not (w and h and w > 0 and h > 0):
        raise SvgError("The SVG needs a viewBox or a width and height.")
    if not 0.05 < w / h < 20:
        raise SvgError("The SVG's proportions are not usable for a logo.")
    ET.register_namespace("", SVG)
    ET.register_namespace("xlink", XLINK)
    return ET.tostring(root, encoding="utf-8"), w, h


def rasterize(clean: bytes, width: float, height: float) -> bytes:
    """Render a sanitised SVG to a transparent PNG about RASTER_WIDTH px wide (LibreOffice Draw)."""
    root = ET.fromstring(clean)
    scale = RASTER_WIDTH / width
    if height * scale > RASTER_WIDTH:
        scale = RASTER_WIDTH / height
    if "viewBox" not in root.attrib:
        root.attrib["viewBox"] = f"0 0 {width:g} {height:g}"
    root.attrib["width"], root.attrib["height"] = f"{round(width * scale)}", f"{round(height * scale)}"
    with tempfile.TemporaryDirectory(prefix="dp-svg-") as tmp:
        work = Path(tmp)
        src = work / "logo.svg"
        src.write_bytes(ET.tostring(root, encoding="utf-8"))
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(work), "SAL_USE_VCLPLUGIN": "svp"}
        subprocess.run(
            ["soffice", f"-env:UserInstallation={(work / 'profile').as_uri()}", "--headless", "--norestore", "--nolockcheck",
             "--convert-to", "png", "--outdir", str(work), str(src)],
            capture_output=True, timeout=120, env=env, check=False,
        )
        out = work / "logo.png"
        if not out.exists():
            raise SvgError("The SVG could not be rendered. Upload a PNG instead.")
        return out.read_bytes()
