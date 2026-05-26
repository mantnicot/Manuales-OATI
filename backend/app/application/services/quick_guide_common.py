"""Detección consistente de guías rápidas (qg_page) para HTML, PDF y plantillas."""

from __future__ import annotations

from app.domain.entities.manual import Block, Manual


def is_qg_page_block(b: Block) -> bool:
    """True si el bloque es una página de guía rápida (layout con columnas)."""
    t = str(getattr(b, "type", "") or "").strip().lower().replace("-", "_")
    if t == "qg_page":
        return True
    data = b.data if isinstance(getattr(b, "data", None), dict) else {}
    if not data:
        return False
    cols = data.get("columns")
    if not isinstance(cols, list) or len(cols) == 0:
        return False
    theme = str(data.get("theme") or "").strip().lower()
    if theme in ("glossary", "guide"):
        return True
    if data.get("headerTitle") is not None or data.get("header_title") is not None:
        for c in cols:
            if isinstance(c, dict) and isinstance(c.get("component"), dict):
                return True
    return False


def is_quick_guide_manual(manual: Manual) -> bool:
    """True si el manual debe renderizarse como guía rápida (HTML/PDF dedicados)."""
    dk = str(manual.meta.get("document_kind") or "").strip().lower()
    if dk == "quick_guide":
        return True
    return any(is_qg_page_block(b) for b in manual.blocks)
