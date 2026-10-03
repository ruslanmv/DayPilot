"""Logo uploads: PNG or JPEG only, type decided by the bytes, dimensions read from the headers."""

from __future__ import annotations

import struct

MAX_BYTES = 5_000_000
MAX_SIDE = 8000


class ImageError(ValueError):
    pass


def inspect(data: bytes) -> tuple[str, int, int]:
    if len(data) > MAX_BYTES:
        raise ImageError("Use an image smaller than 5 MB.")
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        w, h = struct.unpack(">II", data[16:24])
        kind = "image/png"
    elif data[:3] == b"\xff\xd8\xff":
        w = h = 0
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                break
            i += 2 + length
        kind = "image/jpeg"
    elif data.lstrip()[:5].lower() in (b"<?xml", b"<svg ") or b"<svg" in data[:512].lower():
        raise ImageError("SVG logos are not accepted yet: export the logo as a PNG (transparent background is fine).")
    else:
        raise ImageError("Upload a PNG or JPEG image.")
    if not (0 < w <= MAX_SIDE and 0 < h <= MAX_SIDE):
        raise ImageError("The image dimensions could not be read or are too large.")
    return kind, w, h
