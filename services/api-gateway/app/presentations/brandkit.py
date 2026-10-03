"""Build a full daypilot.brand-kit/v1 from the few choices a person makes. The engine validates it."""

from __future__ import annotations

from typing import Any

SAFE_FONTS = ["Calibri", "Cambria", "Arial", "Times New Roman", "Courier New"]
PALETTE_KEYS = ("background", "foreground", "primary", "accent", "muted", "positive", "warning", "negative")
DEFAULT_PALETTE = {
    "background": "#FFFFFF", "foreground": "#1B2333", "primary": "#1F3A93", "accent": "#0FA3B1",
    "muted": "#5B6474", "positive": "#1E7F4F", "warning": "#9A5B00", "negative": "#B3261E",
}


def build(company_id: str, company_name: str, version: int, choices: dict[str, Any], logos: list[dict[str, Any]]) -> dict[str, Any]:
    palette = {**DEFAULT_PALETTE, **{k: v for k, v in (choices.get("palette") or {}).items() if k in PALETTE_KEYS}}
    head = choices.get("headingFont") or "Calibri"
    body = choices.get("bodyFont") or "Calibri"
    allowed = sorted({head, body, *SAFE_FONTS})

    def role(family: str, lo: int, hi: int) -> dict[str, Any]:
        return {"family": family, "minimum_pt": lo, "preferred_pt": hi, "fallbacks": []}

    series = choices.get("seriesColors") or [palette["primary"], palette["accent"], palette["muted"]]
    footer = (choices.get("footerText") or f"{company_name} · Internal")[:160]
    return {
        "schema_version": "daypilot.brand-kit/v1",
        "id": f"{company_id}_brand",
        "company_id": company_id,
        "company_name": company_name,
        "version": version,
        "slide_size": {"width_inches": 13.333, "height_inches": 7.5},
        "palette": palette,
        "typography": {
            "deck_title": role(head, 36, 44), "slide_title": role(head, 26, 32), "body": role(body, 16, 20),
            "data": role(body, 14, 18), "footnote": role(body, 11, 12),
        },
        "logos": logos,
        "allowed_fonts": allowed,
        "chart_style": {"series_colors": series[:6], "minimum_label_pt": 14, "allow_3d": False},
        "footer": {"text": footer, "required": True, "show_page_number": bool(choices.get("showPageNumber", True))},
        "activation_policy": "sample_review_required",
    }
