"""HTML/CSS para guías rápidas (bloques qg_page, meta document_kind=quick_guide)."""

from __future__ import annotations

from app.application.services.document_html import _esc, _img_src_for_html, _nl2br
from app.application.services.oati_branding import footer_oati_logo_html
from app.application.services.quick_guide_common import is_qg_page_block
from app.domain.entities.manual import Manual

_FONT_LINK = (
    "<link rel='preconnect' href='https://fonts.googleapis.com'/>"
    "<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin/>"
    "<link href='https://fonts.googleapis.com/css2?family=Open+Sans:ital,wght@0,400;0,600;0,700;0,800;1,400&display=swap' rel='stylesheet'/>"
)


def quick_guide_html(manual: Manual) -> str:
    pages = sorted([b for b in manual.blocks if is_qg_page_block(b)], key=lambda x: x.order)
    if not pages:
        sheets = _empty_sheet()
    else:
        sheets = "".join(
            _render_page(manual, dict(p.data), idx + 1, len(pages)) for idx, p in enumerate(pages)
        )

    css = _css()
    return (
        "<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'/>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
        f"{_FONT_LINK}"
        f"<title>{_esc(manual.title)}</title>"
        f"<style>{css}</style></head><body><div class='qg-doc'>{sheets}</div></body></html>"
    )


def _empty_sheet() -> str:
    return (
        "<section class='qg-sheet qg-theme-guide'>"
        "<header class='qg-head'><div class='qg-head-inner'>"
        "<div class='qg-brand'>UNIVERSIDAD DISTRITAL FRANCISCO JOSÉ DE CALDAS</div>"
        "<div class='qg-head-title'>SIN PÁGINAS</div><div class='qg-head-spacer'></div>"
        "</div></header>"
        "<div class='qg-body'><div class='qg-body-inner'><p class='qg-empty'>Agregue páginas en el editor.</p></div></div>"
        f"{_footer_html(None, 1, 1)}"
        "</section>"
    )


def _footer_html(manual: Manual | None, page_num: int, total_pages: int) -> str:
    logo = footer_oati_logo_html(
        manual,
        img_src_for_html=_img_src_for_html,
        page_suffix=str(page_num),
    )
    return (
        f"<footer class='qg-foot'>"
        f"<span class='qg-foot-text'>OATI — Oficina Asesora de Tecnologías de la Información</span>"
        f"<span class='qg-foot-page'>Página {page_num} / {total_pages}</span>"
        f"{logo}"
        f"</footer>"
    )


def _render_page(manual: Manual, data: dict, page_num: int, total_pages: int) -> str:
    theme = str(data.get("theme") or "guide").strip().lower()
    if theme not in ("glossary", "guide"):
        theme = "guide"
    header_title = str(data.get("headerTitle") or data.get("header_title") or "").strip() or "GUÍA RÁPIDA"
    columns = list(data.get("columns") or [])
    body_inner = _render_placements(columns, theme)
    foot = _footer_html(manual, page_num, total_pages)
    head = _header_bar(header_title)
    return (
        f"<section id='qg-sheet-{page_num}' class='qg-sheet qg-theme-{theme}'>"
        f"{head}"
        f"<div class='qg-body'><div class='qg-body-inner'>{body_inner}</div></div>"
        f"{foot}"
        "</section>"
    )


def _header_bar(title: str) -> str:
    return (
        "<header class='qg-head'><div class='qg-head-inner'>"
        "<div class='qg-brand'>UNIVERSIDAD DISTRITAL FRANCISCO JOSÉ DE CALDAS</div>"
        f"<div class='qg-head-title'>{_esc(title)}</div>"
        "<div class='qg-head-spacer'></div>"
        "</div></header>"
    )


def _render_placements(columns: list, theme: str) -> str:
    if not columns:
        return "<p class='qg-empty'>Sin módulos.</p>"
    use_free = any(
        isinstance(c, dict) and (c.get("xPct") is not None or c.get("x_pct") is not None)
        for c in columns
    )
    if use_free:
        parts: list[str] = []
        for i, col in enumerate(columns):
            if not isinstance(col, dict):
                continue
            comp = col.get("component") if isinstance(col.get("component"), dict) else {}
            try:
                x = float(col.get("xPct") if col.get("xPct") is not None else col.get("x_pct") or 0)
            except (TypeError, ValueError):
                x = 0.0
            try:
                y = float(col.get("yPct") if col.get("yPct") is not None else col.get("y_pct") or 0)
            except (TypeError, ValueError):
                y = 0.0
            try:
                w = float(col.get("widthPct") if col.get("widthPct") is not None else col.get("width_pct") or 30)
            except (TypeError, ValueError):
                w = 30.0
            try:
                hp = col.get("heightPct")
                if hp is None:
                    hp = col.get("height_pct")
                h = float(hp) if hp is not None and str(hp).strip() != "" else 0.0
            except (TypeError, ValueError):
                h = 0.0
            try:
                z = int(
                    col.get("zIndex")
                    if col.get("zIndex") is not None
                    else col.get("z_index")
                    if col.get("z_index") is not None
                    else i,
                )
            except (TypeError, ValueError):
                z = i
            w = max(8.0, min(100.0, w))
            x = max(0.0, min(100.0 - w, x))
            if h > 0:
                h = max(10.0, min(92.0, h))
                y = max(0.0, min(100.0 - h, y))
                h_style = f"height:{h:.2f}%;"
            else:
                y = max(0.0, min(92.0, y))
                h_style = "height:auto;max-height:92%;"
            inner = _render_component(comp, theme)
            parts.append(
                f"<div class='qg-place' style='left:{x:.2f}%;top:{y:.2f}%;width:{w:.2f}%;"
                f"{h_style}z-index:{z};'>{inner}</div>",
            )
        return f"<div class='qg-canvas'>{''.join(parts)}</div>"
    parts_legacy: list[str] = []
    for col in columns:
        if not isinstance(col, dict):
            continue
        comp = col.get("component") if isinstance(col.get("component"), dict) else {}
        try:
            w = int(col.get("widthPct") or col.get("width_pct") or 100)
        except (TypeError, ValueError):
            w = 100
        w = max(8, min(100, w))
        inner = _render_component(comp, theme)
        parts_legacy.append(f"<div class='qg-col' style='flex:0 0 {w}%;max-width:{w}%;'>{inner}</div>")
    return f"<div class='qg-cols'>{''.join(parts_legacy)}</div>"


def _render_component(comp: dict, theme: str) -> str:
    kind = str(comp.get("kind") or "").strip().lower()
    if kind == "glossary":
        return _glossary_html(comp)
    if kind == "step":
        return _step_html(comp)
    if kind == "comment":
        return _comment_html(comp)
    return f"<div class='qg-unknown'>{_esc(kind or 'vacío')}</div>"


def _glossary_html(comp: dict) -> str:
    entries = list(comp.get("entries") or [])
    blocks: list[str] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        term = str(e.get("term") or "").strip()
        defin = str(e.get("definition") or e.get("text") or "").strip()
        if not term and not defin:
            continue
        inner_line = (
            f"<strong>{_esc(term)}</strong>"
            + (f": <span>{_nl2br(defin)}</span>" if defin else "")
        )
        blocks.append(f"<div class='qg-gloss-entry'><div class='qg-gloss-entry-inner'>{inner_line}</div></div>")
    inner = "".join(blocks) if blocks else "<p class='qg-empty'>(Sin términos)</p>"
    return (
        "<div class='qg-glossary-shell'><div class='qg-glossary-box'><div class='qg-glossary-inner'>"
        f"{inner}</div></div></div>"
    )


def _mini_sep() -> str:
    return (
        "<div class='qg-sep' aria-hidden='true'>"
        "<span class='qg-sep-sq'></span><span class='qg-sep-line'></span><span class='qg-sep-sq'></span>"
        "</div>"
    )


def _step_html(comp: dict) -> str:
    title = str(comp.get("title") or "").strip() or "PASO"
    mini = list(comp.get("miniSteps") or comp.get("mini_steps") or [])
    parts: list[str] = [f"<div class='qg-step-title-wrap'><span class='qg-step-title'>{_esc(title)}</span></div>"]
    for i, m in enumerate(mini):
        if not isinstance(m, dict):
            continue
        if i > 0:
            parts.append(_mini_sep())
        txt = str(m.get("text") or "").strip()
        img1 = str(m.get("imageData") or m.get("image_data") or "").strip()
        img2 = str(m.get("imageData2") or m.get("image_data2") or "").strip()
        imgs_html = _mini_images(img1, img2)
        parts.append(
            "<div class='qg-mini'>"
            "<span class='qg-mini-bullet' aria-hidden='true'></span>"
            "<div class='qg-mini-main'>"
            f"<div class='qg-mini-text'>{_nl2br(txt) if txt else ' '}</div>"
            f"{imgs_html}"
            "</div></div>",
        )
    if len(mini) == 0:
        parts.append("<p class='qg-empty-mini'>(Sin mini pasos)</p>")
    return f"<div class='qg-step'>{''.join(parts)}</div>"


def _mini_images(img1: str, img2: str) -> str:
    cells: list[str] = []
    if img1:
        safe = _img_src_for_html(img1)
        cells.append(f'<div class="qg-img-cell"><img src="{safe}" alt=""/></div>')
    if img2:
        safe = _img_src_for_html(img2)
        cells.append(f'<div class="qg-img-cell"><img src="{safe}" alt=""/></div>')
    if not cells:
        return ""
    cls = "qg-imgs qg-imgs-2" if len(cells) > 1 else "qg-imgs qg-imgs-1"
    return f"<div class='{cls}'>{''.join(cells)}</div>"


def _comment_html(comp: dict) -> str:
    txt = str(comp.get("text") or "").strip()
    img = str(comp.get("imageData") or comp.get("image_data") or "").strip()
    img_html = ""
    if img:
        safe = _img_src_for_html(img)
        img_html = f'<div class="qg-comment-img"><img src="{safe}" alt=""/></div>'
    body = _nl2br(txt) if txt else ""
    return f"<div class='qg-comment'><div class='qg-comment-text'>{body}</div>{img_html}</div>"


def _css() -> str:
    return """
@page {
  size: A4 landscape;
  /* Márgenes físicos del PDF: más aire lateral (más «cuadrado», alineado con la vista HTML). */
  margin: 9mm 18mm;
}
@media print {
  html, body {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
}
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; padding: 0; }
body {
  margin: 0;
  font-family: "Open Sans", Arial, Helvetica, sans-serif;
  font-size: 12pt;
  line-height: 1.4;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

.qg-doc { display: flex; flex-direction: column; gap: 0; }

/* Altura fija por hoja: sin ella, solo hay hijos absolutos en el cuerpo y el flex colapsa
   (los % de .qg-place quedan sobre altura 0 → módulos invisibles en vista previa/PDF). */
.qg-sheet {
  page-break-after: always;
  display: flex;
  flex-direction: column;
  position: relative;
  height: 194mm;
  min-height: 194mm;
  max-height: 194mm;
  overflow: hidden;
}
.qg-sheet:last-child { page-break-after: auto; }

.qg-head {
  color: #fff;
  flex: 0 0 auto;
}
.qg-theme-glossary .qg-head {
  background: #4b5563;
}
.qg-theme-guide .qg-head {
  background: #00668c;
}
.qg-head-inner {
  display: flex;
  align-items: center;
  min-height: 16mm;
  padding: 2.5mm 5mm;
  gap: 4mm;
}
.qg-brand {
  flex: 0 0 26%;
  font-size: 8pt;
  font-weight: 800;
  line-height: 1.2;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.qg-head-title {
  flex: 1 1 auto;
  text-align: center;
  font-size: 17pt;
  font-weight: 800;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  line-height: 1.1;
}
.qg-head-spacer { flex: 0 0 26%; }

.qg-body {
  flex: 1 1 0;
  min-height: 0;
  /* Más margen izquierdo/derecho respecto al borde de las franjas (contenido centrado). */
  padding: 5mm 16mm 6mm;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.qg-theme-glossary .qg-body {
  /* Franjas ~3× más anchas que antes (13mm→39mm por banda) para fondo más simple. */
  background: repeating-linear-gradient(90deg, #f0f0f2 0 39mm, #e0e0e6 39mm 78mm);
}
.qg-theme-guide .qg-body {
  /* Mismo criterio: bandas pastel más amplias (15mm→45mm). */
  background: repeating-linear-gradient(90deg, #f8e8ec 0 45mm, #ece4f0 45mm 90mm);
}

.qg-body-inner {
  flex: 1 1 0;
  min-height: 0;
  width: 100%;
  max-width: 100%;
  position: relative;
  overflow: hidden;
}

.qg-canvas {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  bottom: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
}
.qg-place {
  position: absolute;
  min-width: 0;
  box-sizing: border-box;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.qg-cols {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: flex-start;
  gap: 3mm;
  width: 100%;
}
.qg-col { min-width: 0; }

.qg-foot {
  flex: 0 0 auto;
  display: flex;
  flex-wrap: nowrap;
  justify-content: flex-start;
  align-items: center;
  gap: 4mm;
  font-size: 8pt;
  color: #4b5563;
  padding: 2mm 5mm 3mm;
  border-top: 1px solid #d1d5db;
  background: #f9fafb;
}
.qg-foot-text {
  flex: 1 1 auto;
  min-width: 0;
}
.qg-foot-page {
  flex: 0 0 auto;
  white-space: nowrap;
}
.qg-foot-logo {
  flex: 0 0 auto;
  margin-left: auto;
  align-self: center;
}
.qg-foot-oati-icon {
  display: block;
  height: 10mm;
  width: 10mm;
  flex-shrink: 0;
  object-fit: contain;
}
.qg-foot-logo .qg-foot-oati-icon {
  vertical-align: middle;
}
.qg-theme-glossary .qg-foot { background: #f3f4f6; }

/* Vista previa en pantalla (iframe del editor): hoja completa + pie visibles sin depender del scroll. */
@media screen {
  html, body {
    background: #e5e7eb;
  }
  .qg-doc {
    zoom: 0.72;
    transform-origin: top center;
    padding: 8px 0 16px;
  }
  .qg-foot {
    flex-shrink: 0;
    min-height: 12mm;
  }
  .qg-foot-oati-icon,
  .qg-foot-logo svg.qg-foot-oati-icon {
    height: 32px;
    width: 32px;
  }
}

.qg-empty, .qg-empty-mini { color: #6b7280; font-size: 10pt; margin: 2mm; }

/* Tarjeta blanca + caja teal centrada y más estrecha (referencia diseño glosario). */
.qg-theme-glossary .qg-glossary-shell {
  background: #fff;
  border-radius: 4.5mm;
  padding: 4mm;
  box-shadow: 0 2px 8px rgba(0,0,0,.12);
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  width: 88%;
  max-width: min(246mm, 100%);
  margin-left: auto;
  margin-right: auto;
}
.qg-theme-guide .qg-glossary-shell {
  background: #fff;
  border-radius: 4mm;
  padding: 3.5mm;
  box-shadow: 0 2px 6px rgba(0,0,0,.1);
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.qg-theme-glossary .qg-glossary-box {
  flex: 1;
  min-height: 0;
  background: transparent;
  border-radius: 3mm;
  padding: 0;
}
.qg-glossary-inner {
  background: linear-gradient(165deg, #006688 0%, #007a99 45%, #005a78 100%);
  border: 1px solid rgba(15, 23, 42, 0.25);
  border-radius: 5mm;
  box-shadow: 0 1mm 4mm rgba(0, 40, 60, 0.15);
  color: #fff;
  padding: 4mm 5mm;
  font-size: 12pt;
  line-height: 1.45;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.qg-gloss-entry {
  margin: 0 0 3mm;
}
.qg-gloss-entry-inner {
  border: 1px solid rgba(255,255,255,.75);
  border-radius: 2.5mm;
  padding: 2mm 2.75mm;
}
.qg-gloss-entry-inner strong { font-weight: 800; font-size: 12.5pt; }

.qg-step {
  background: linear-gradient(160deg, #0a7aa3 0%, #00668c 40%, #055a7a 100%);
  border: 1px solid rgba(255, 255, 255, 0.35);
  border-radius: 7mm;
  box-shadow: 0 1.5mm 5mm rgba(0, 50, 80, 0.22);
  color: #fff;
  padding: 3mm 4mm 4mm;
  height: 100%;
  min-height: 0;
  font-size: 11.5pt;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.qg-step-title-wrap {
  text-align: center;
  margin-bottom: 2.5mm;
  padding-bottom: 0;
  flex: 0 0 auto;
}
.qg-step-title {
  display: inline-block;
  font-weight: 800;
  font-size: 11.5pt;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border: 1px solid rgba(255,255,255,.55);
  padding: 1.5mm 3.5mm;
  border-radius: 4mm;
  background: rgba(255, 255, 255, 0.08);
}
.qg-mini {
  display: flex;
  flex-direction: row;
  align-items: stretch;
  gap: 2.5mm;
  margin-top: 2mm;
  flex: 1 1 0;
  min-height: 0;
}
.qg-mini-bullet {
  flex: 0 0 5mm;
  width: 5mm;
  height: 5mm;
  background: #fff;
  margin-top: 2mm;
  flex-shrink: 0;
  align-self: flex-start;
}
.qg-mini:has(.qg-imgs) .qg-mini-bullet {
  display: none;
}
.qg-mini:has(.qg-imgs) {
  gap: 2mm;
}
.qg-mini-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  padding: 0 2mm 0 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.qg-mini-text {
  text-align: center;
  font-size: 11.5pt;
  line-height: 1.4;
  padding: 0 1.5mm;
  flex: 0 1 auto;
  min-height: 0;
  max-height: 45%;
  overflow: hidden;
}
.qg-sep {
  display: flex;
  flex-direction: row;
  align-items: center;
  margin: 2.5mm 3mm 1.5mm;
  flex-shrink: 0;
}
.qg-sep-sq { width: 5px; height: 5px; background: #cbd5e1; flex-shrink: 0; }
.qg-sep-line { flex: 1; height: 1px; background: #94a3b8; margin: 0 4px; }

.qg-imgs {
  margin-top: 2.5mm;
  width: 100%;
  padding: 0 3mm 1mm;
  flex: 1 1 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.qg-imgs-1 { justify-content: center; }
.qg-imgs-1 .qg-img-cell {
  max-width: 94%;
  max-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.qg-imgs-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2.5mm;
  width: 100%;
  max-height: 100%;
  align-content: center;
}
.qg-img-cell {
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.qg-img-cell img {
  display: block;
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
  object-fit: contain;
  border: 1px solid rgba(15, 23, 42, 0.2);
  border-radius: 2mm;
}

.qg-comment {
  background: #fff;
  border: 1px solid #d1d5db;
  border-radius: 5mm;
  box-shadow: 0 1mm 3mm rgba(15, 23, 42, 0.08);
  color: #111;
  padding: 3mm 3.5mm;
  font-size: 11.5pt;
  line-height: 1.42;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.qg-comment-text {
  text-align: left;
  flex: 0 1 auto;
  min-height: 0;
  max-height: 55%;
  overflow: hidden;
}
.qg-comment-img {
  flex: 1 1 0;
  min-height: 0;
  margin-top: 3mm;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.qg-comment-img img {
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
  object-fit: contain;
  border: 1px solid #cbd5e1;
}

.qg-unknown { border: 1px dashed #999; padding: 3mm; font-size: 10pt; color: #444; }
"""
