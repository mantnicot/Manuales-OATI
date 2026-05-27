"""Logo OATI por defecto y resolución desde meta del manual (guías rápidas, etc.)."""

from __future__ import annotations

import base64
import re
from functools import lru_cache
from pathlib import Path

from app.application.services.document_html import resolve_logo_oati_src
from app.domain.entities.manual import Manual

_OATI_ICON_PATH = (
    Path(__file__).resolve().parents[2] / "static" / "branding" / "oati-icon.svg"
)


@lru_cache(maxsize=1)
def default_oati_logo_src() -> str:
    """Icono OATI embebido (data URL) para PDF/HTML sin depender de red."""
    raw = _OATI_ICON_PATH.read_bytes()
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def oati_icon_svg_inline(*, page_suffix: str = "") -> str:
    """SVG incrustado en el HTML (más fiable que <img>+data URL en iframe/PDF)."""
    raw = _OATI_ICON_PATH.read_text(encoding="utf-8")
    raw = re.sub(r"<\?xml[^>]*\?>", "", raw, flags=re.IGNORECASE).strip()
    if page_suffix:
        token = re.sub(r"[^a-zA-Z0-9]", "", page_suffix) or "p"
        raw = raw.replace("oatiGrad", f"oatiGrad{token}")
    if 'class="qg-foot-oati-icon"' not in raw and "class='qg-foot-oati-icon'" not in raw:
        raw = re.sub(r"<svg\b", '<svg class="qg-foot-oati-icon"', raw, count=1, flags=re.IGNORECASE)
    return raw


def default_oati_icon_svg_inline() -> str:
    return oati_icon_svg_inline()


def footer_oati_logo_html(
    manual: Manual | None,
    *,
    img_src_for_html,
    page_suffix: str = "",
) -> str:
    """Marca OATI en el pie: SVG inline por defecto; <img> si hay logo personalizado."""
    default_src = default_oati_logo_src()
    src = resolve_manual_oati_logo_src(manual) if manual else default_src
    if not src or src == default_src:
        return f"<span class='qg-foot-logo'>{oati_icon_svg_inline(page_suffix=page_suffix)}</span>"
    safe = img_src_for_html(src)
    if not safe:
        return f"<span class='qg-foot-logo'>{oati_icon_svg_inline(page_suffix=page_suffix)}</span>"
    return (
        f"<span class='qg-foot-logo'>"
        f"<img src='{safe}' alt='OATI' class='qg-foot-oati-icon'/>"
        f"</span>"
    )


def resolve_manual_oati_logo_src(manual: Manual) -> str:
    """Logo OATI: meta del manual, portada OATI si existe, o icono institucional por defecto."""
    meta = manual.meta if isinstance(manual.meta, dict) else {}
    for key in ("logoOatiData", "logo_oati_data"):
        v = str(meta.get(key) or "").strip()
        if v:
            return v
    for key in ("logoOatiUrl", "logo_oati_url"):
        v = str(meta.get(key) or "").strip()
        if v:
            return v
    for block in manual.blocks:
        if block.type == "oati_cover" and isinstance(block.data, dict):
            src = resolve_logo_oati_src(block.data)
            if src:
                return src
    return default_oati_logo_src()
