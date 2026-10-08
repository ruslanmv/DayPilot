"""Render the actual exported .pptx: LibreOffice → PDF → slide PNGs, in a private temp profile.

LibreOffice is an operational renderer, not a certificate of PowerPoint fidelity. If any part of
the toolchain is missing the result says so, and the deck is never labelled as checked.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

TIMEOUT = 180
DPI = 120  # 13.333 in × 120 = 1600 px wide, the review target for 16:9


def capabilities() -> dict[str, object]:
    soffice = shutil.which("soffice")
    impress = False
    if soffice:
        prog = Path(os.path.realpath(soffice)).parent
        impress = any(prog.glob("libsdlo.so")) or any(Path("/usr/lib/libreoffice/program").glob("libsdlo.so"))
    fonts = {}
    if shutil.which("fc-match"):
        for office, compatible in (("Calibri", "Carlito"), ("Cambria", "Caladea"), ("Arial", "Liberation Sans")):
            out = subprocess.run(["fc-match", office], capture_output=True, text=True, check=False).stdout
            fonts[office] = compatible in out
    return {
        "soffice": bool(soffice), "impress": impress, "pdftoppm": bool(shutil.which("pdftoppm")),
        "fonts": fonts, "ready": bool(soffice) and impress and bool(shutil.which("pdftoppm")),
    }


class RenderResult:
    def __init__(self, pdf: bytes, pages: list[bytes], blank: list[int]) -> None:
        self.pdf, self.pages, self.blank = pdf, pages, blank


def _pgm_is_blank(path: Path) -> bool:
    """A page whose thumbnail is one flat tone (tiny variance) rendered nothing visible."""
    data = path.read_bytes()
    # P5 header: magic, width, height, maxval separated by whitespace
    parts, i = [], 0
    while len(parts) < 4:
        while data[i:i + 1].isspace():
            i += 1
        j = i
        while not data[j:j + 1].isspace():
            j += 1
        parts.append(data[i:j])
        i = j
    pixels = data[i + 1:]
    if not pixels:
        return True
    mean = sum(pixels) / len(pixels)
    var = sum((p - mean) ** 2 for p in pixels) / len(pixels)
    return var < 2.0


def render(pptx: bytes, suffix: str = ".pptx") -> RenderResult:
    caps = capabilities()
    if not caps["ready"]:
        raise RuntimeError("renderer unavailable: install libreoffice-impress and poppler-utils")
    with tempfile.TemporaryDirectory(prefix="dp-render-") as tmp:
        work = Path(tmp)
        src = work / f"deck{suffix}"
        src.write_bytes(pptx)
        profile = work / "profile"
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(work), "SAL_USE_VCLPLUGIN": "svp"}
        subprocess.run(
            ["soffice", f"-env:UserInstallation={profile.as_uri()}", "--headless", "--norestore", "--nolockcheck",
             "--convert-to", "pdf", "--outdir", str(work), str(src)],
            capture_output=True, timeout=TIMEOUT, env=env, check=False,
        )
        pdf = work / "deck.pdf"
        if not pdf.exists():
            raise RuntimeError("LibreOffice could not render the deck")
        subprocess.run(["pdftoppm", "-png", "-r", str(DPI), str(pdf), str(work / "slide")], capture_output=True, timeout=TIMEOUT, check=True)
        subprocess.run(["pdftoppm", "-gray", "-r", "8", str(pdf), str(work / "thumb")], capture_output=True, timeout=TIMEOUT, check=True)
        pngs = sorted(work.glob("slide-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
        thumbs = sorted(work.glob("thumb-*.pgm"), key=lambda p: int(p.stem.split("-")[-1]))
        blank = [k + 1 for k, t in enumerate(thumbs) if _pgm_is_blank(t)]
        return RenderResult(pdf.read_bytes(), [p.read_bytes() for p in pngs], blank)
