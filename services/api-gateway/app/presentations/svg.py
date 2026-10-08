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
import shutil
import struct
import subprocess
import tempfile
import zlib
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


def _png_read(data: bytes) -> tuple[int, int, int, bytearray]:
    """Decode an 8-bit, non-interlaced RGB or RGBA PNG (what pdftocairo writes) to raw pixels."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SvgError("The SVG could not be rendered.")
    pos, idat, w = 8, b"", 0
    while pos < len(data):
        (n,) = struct.unpack(">I", data[pos:pos + 4])
        kind, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ctype not in (2, 6) or interlace:
                raise SvgError("The SVG could not be rendered.")
            bpp = 4 if ctype == 6 else 3
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    raw, stride = zlib.decompress(idat), w * bpp
    out, prev = bytearray(), bytearray(stride)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out += line
        prev = line
    return w, h, bpp, out


def _png_write(w: int, h: int, rgba: bytes) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


def _matte(on_white: bytes, on_black: bytes) -> bytes:
    """Recover true transparency from two renders of the same artwork, on white and on black:
    alpha = 255 - (white - black); colour = black render / alpha."""
    w, h, bw, white = _png_read(on_white)
    w2, h2, bb, black = _png_read(on_black)
    if (w, h) != (w2, h2):
        raise SvgError("The SVG could not be rendered.")
    out = bytearray(w * h * 4)
    for p in range(w * h):
        wr, wg, wb = white[p * bw:p * bw + 3]
        kr, kg, kb = black[p * bb:p * bb + 3]
        alpha = 255 - max(0, min(255, max(wr - kr, wg - kg, wb - kb)))
        x, y = p % w, p // w
        if (x < 2 or y < 2 or x >= w - 2 or y >= h - 2) and min(wr, wg, wb) > 250:
            alpha = 0  # the page edge the backdrop did not quite cover after scaling
        o = p * 4
        if alpha:
            out[o], out[o + 1], out[o + 2] = (min(255, kr * 255 // alpha), min(255, kg * 255 // alpha), min(255, kb * 255 // alpha))
        out[o + 3] = alpha
    return _png_write(w, h, bytes(out))


def rasterize(clean: bytes, width: float, height: float) -> bytes:
    """Render a sanitised SVG to a transparent PNG about RASTER_WIDTH px wide.

    LibreOffice Draw renders it to PDF and poppler rasterises that. Both put the artwork on an opaque
    white page, so it is rendered twice (as is, and over a black backdrop added behind it) and the
    transparency is recovered from the difference. Without poppler, an opaque PNG is returned."""
    root = ET.fromstring(clean)
    scale = RASTER_WIDTH / width
    if height * scale > RASTER_WIDTH:
        scale = RASTER_WIDTH / height
    if "viewBox" not in root.attrib:
        root.attrib["viewBox"] = f"0 0 {width:g} {height:g}"
    root.attrib["width"], root.attrib["height"] = f"{round(width * scale)}", f"{round(height * scale)}"
    vb = [float(x) for x in re.split(r"[\s,]+", root.attrib["viewBox"].strip())]
    backed = ET.fromstring(ET.tostring(root))
    backed.insert(0, ET.Element(f"{{{SVG}}}rect", {"x": f"{vb[0]:g}", "y": f"{vb[1]:g}", "width": f"{vb[2]:g}", "height": f"{vb[3]:g}", "fill": "#000000"}))
    with tempfile.TemporaryDirectory(prefix="dp-svg-") as tmp:
        work = Path(tmp)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(work), "SAL_USE_VCLPLUGIN": "svp"}
        office = ["soffice", f"-env:UserInstallation={(work / 'profile').as_uri()}", "--headless", "--norestore", "--nolockcheck"]
        (work / "logo.svg").write_bytes(ET.tostring(root, encoding="utf-8"))
        if shutil.which("pdftocairo"):
            (work / "backed.svg").write_bytes(ET.tostring(backed, encoding="utf-8"))
            subprocess.run([*office, "--convert-to", "pdf", "--outdir", str(work), str(work / "logo.svg"), str(work / "backed.svg")], capture_output=True, timeout=120, env=env, check=False)
            pngs = []
            for name in ("logo", "backed"):
                if (work / f"{name}.pdf").exists():
                    subprocess.run(["pdftocairo", "-png", "-singlefile", "-scale-to-x", str(RASTER_WIDTH), "-scale-to-y", "-1", str(work / f"{name}.pdf"), str(work / f"{name}-r")],
                                   capture_output=True, timeout=60, env=env, check=False)
                pngs.append(work / f"{name}-r.png")
            if all(p.exists() for p in pngs):
                return _matte(pngs[0].read_bytes(), pngs[1].read_bytes())
        subprocess.run([*office, "--convert-to", "png", "--outdir", str(work), str(work / "logo.svg")], capture_output=True, timeout=120, env=env, check=False)
        out = work / "logo.png"
        if not out.exists():
            raise SvgError("The SVG could not be rendered. Upload a PNG instead.")
        return out.read_bytes()
