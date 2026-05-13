from __future__ import annotations

import contextvars
import html
from urllib.parse import quote

from app.application.services.export_media import normalize_media_url, src_to_data_url
from app.application.services.plain_text import soft_wrap_long_tokens
from app.domain.entities.manual import Block, Manual

_html_asset_base: contextvars.ContextVar[str | None] = contextvars.ContextVar("html_asset_base", default=None)

OATI_STATIC = {
    "oati_cover",
    "oati_intro",
    "oati_objective",
    "oati_scope",
    "oati_responsible",
    "oati_definitions",
}

OATI_IMAGE_SECTION_ORDER = (
    "oati_intro",
    "oati_objective",
    "oati_scope",
    "oati_responsible",
    "oati_definitions",
)


def _resolve_image_data(data: dict) -> str:
    emb = data.get("imageData") or ""
    if str(emb).strip():
        return str(emb).strip()
    return str(data.get("imageSrc") or "").strip()


def resolve_crest_src(data: dict) -> str:
    """Escudo en portada: archivo incrustado (crestData) o URL (crestUrl)."""
    emb = data.get("crestData") or ""
    if str(emb).strip():
        return str(emb).strip()
    return str(data.get("crestUrl") or "").strip()


def resolve_logo_ud_src(data: dict) -> str:
    emb = data.get("logoUdData") or ""
    if str(emb).strip():
        return str(emb).strip()
    return str(data.get("logoUdUrl") or "").strip()


def resolve_logo_oati_src(data: dict) -> str:
    emb = data.get("logoOatiData") or ""
    if str(emb).strip():
        return str(emb).strip()
    return str(data.get("logoOatiUrl") or "").strip()


def _image_scale_pct(data: dict) -> int:
    try:
        v = int(data.get("imageScalePercent", 100))
    except (TypeError, ValueError):
        return 100
    return max(25, min(100, v))


def _format_figure_caption(num: int | None, user: str) -> str:
    t = (user or "").strip()
    if num is None:
        return t
    base = f"Imagen {num}."
    if not t:
        return base
    return f"{base} {t}"


def oati_image_index_by_block_id(manual: Manual) -> dict[str, int]:
    blocks = sorted(manual.blocks, key=lambda x: x.order)
    smap = {b.type: b for b in blocks if b.type in OATI_STATIC}
    ids: list[str] = []
    for typ in OATI_IMAGE_SECTION_ORDER:
        b = smap.get(typ)
        if b and _resolve_image_data(b.data):
            ids.append(b.id)
    flow = [b for b in blocks if b.type in ("oati_step", "oati_note")]
    for b in flow:
        if b.type == "oati_step" and _resolve_image_data(b.data):
            ids.append(b.id)
    return {bid: i + 1 for i, bid in enumerate(ids)}


def _img_src_for_html(from_resolve: str) -> str:
    """Prefiere data URL generada en servidor para que la vista previa coincida con el PDF."""
    s = str(from_resolve).strip()
    if not s:
        return ""
    base = _html_asset_base.get()
    if s.startswith("data:"):
        return html.escape(s, quote=True)
    inlined = src_to_data_url(s, base)
    if inlined:
        return html.escape(inlined, quote=True)
    normalized = normalize_media_url(s, base)
    return _safe_img_src(normalized)


def _crest_scale_pct(data: dict) -> int:
    try:
        v = int(data.get("crestScalePercent", 100))
    except (TypeError, ValueError):
        return 100
    return max(50, min(150, v))


def _crest_img_style(pct: int) -> str:
    p = max(50, min(150, int(pct)))
    base_h = 56.0
    base_w = 62.0
    mh = base_h * p / 100
    mw = base_w * p / 100
    return f"max-height:{mh:.1f}mm;max-width:{mw:.1f}mm;height:auto;object-fit:contain;"


def _safe_img_src(url: str) -> str:
    u = str(url).strip()
    if u.startswith("data:"):
        return html.escape(u, quote=True)
    if u.startswith("http"):
        return quote(u, safe="/:?=&")
    return _esc(u)


def _img_style_scale(pct: int) -> str:
    p = max(25, min(100, int(pct)))
    return f"max-width:{p}%;height:auto;"


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _nl2br(s: str) -> str:
    return html.escape(s).replace("\n", "<br/>")


def _section_body(raw: str) -> str:
    s = raw or ""
    st = s.strip()
    low = st.lower()
    looks_like_markup = "<" in s and not low.startswith("<!") and "<html" not in low
    if looks_like_markup:
        return f"<div class='body-text body-text--rich'>{s}</div>"
    return f"<div class='body-text'>{_nl2br(soft_wrap_long_tokens(s))}</div>"


def _oati_header_table(d: dict) -> str:
    logo_ud = resolve_logo_ud_src(d)
    logo_oati = resolve_logo_oati_src(d)
    img_ud = (
        f"<img src='{_img_src_for_html(str(logo_ud))}' class='hdr-logo' alt='UD'/>"
        if logo_ud
        else "<div class='hdr-ph'>Logo<br/>Universidad</div>"
    )
    img_oati = (
        f"<img src='{_img_src_for_html(str(logo_oati))}' class='hdr-logo' alt='OATI'/>"
        if logo_oati
        else "<div class='hdr-ph'>Logo<br/>OATI</div>"
    )
    return (
        "<table class='oati-head' cellspacing='0' cellpadding='0'><tr>"
        f"<td class='hc c1'>{img_ud}</td>"
        "<td class='hc c2'>"
        f"<div class='line strong'>{_esc(str(d.get('moduleHeaderLine','')))}</div>"
        f"<div class='line'>{_esc(str(d.get('macroProcess','')))}</div>"
        f"<div class='line'>{_esc(str(d.get('processLine','')))}</div>"
        "</td><td class='hc c3'>"
        f"<div class='line'><span class='lbl'>Código:</span> {_esc(str(d.get('code','')))}</div>"
        f"<div class='line'><span class='lbl'>Versión:</span> {_esc(str(d.get('version','')))}</div>"
        f"<div class='line'><span class='lbl'>Fecha de Aprobación:</span> {_esc(str(d.get('approvalDate','')))}</div>"
        "</td>"
        f"<td class='hc c4'>{img_oati}</td>"
        "</tr></table>"
    )


def _oati_cover_page(d: dict, hdr: str, total_pages: int) -> str:
    crest = resolve_crest_src(d)
    cscale = _crest_scale_pct(d)
    cstyle = _esc(_crest_img_style(cscale))
    crest_html = (
        f"<div class='crest-wrap'><img src='{_img_src_for_html(crest)}' class='crest' style='{cstyle}' alt='Escudo'/></div>"
        if crest
        else "<div class='crest-ph'>Escudo institucional</div>"
    )
    tp = max(3, int(total_pages))
    return (
        "<section class='sheet cover-sheet'>"
        f"{hdr}"
        "<div class='cover-main'>"
        f"{crest_html}"
        f"<div class='inst-line'>{_esc(str(d.get('institutionLine','')))}</div>"
        f"<div class='central-title'>{_esc(str(d.get('centralTitle','')))}</div>"
        f"<div class='unit-bottom'>{_esc(str(d.get('unitFooterLine','')))}</div>"
        "</div>"
        f"<div class='page-foot'><span>Página 1 de {tp}</span></div></section>"
    )


def _oati_toc_page(hdr: str, total_pages: int) -> str:
    entries = [
        "INTRODUCCIÓN",
        "1. OBJETIVO",
        "2. ALCANCE",
        "3. RESPONSABLES",
        "4. DEFINICIONES Y SIGLAS",
        "5. DESCRIPCIÓN DE CADA PASO (DETALLADO)",
    ]
    tp = max(3, int(total_pages))
    body_first = 3
    body_last = tp
    toc_pages = []
    for i, t in enumerate(entries):
        if i < 5:
            p = "3"
        else:
            p = f"{body_first}–{body_last}" if body_last > body_first else str(body_first)
        toc_pages.append(
            f"<li><span class='toc-t'>{_esc(t)}</span><span class='toc-p'>{p}</span></li>",
        )
    lis = "".join(toc_pages)
    return (
        "<section class='sheet toc-sheet'>"
        f"{hdr}"
        "<h1 class='toc-title'>TABLA DE CONTENIDO</h1>"
        f"<ol class='toc-list'>{lis}</ol>"
        f"<div class='page-foot'><span>Página 2 de {tp}</span></div></section>"
    )


def _oati_section(
    block: Block | None,
    title_html: str,
    img_idx: dict[str, int],
) -> str:
    if not block:
        return ""
    d = block.data
    text = _section_body(str(d.get("text", "")))
    img = _resolve_image_data(d)
    cap_u = str(d.get("imageCaption", ""))
    scale = _image_scale_pct(d)
    num = img_idx.get(block.id)
    cap = _esc(_format_figure_caption(num, cap_u))
    fig = ""
    if img:
        safe = _img_src_for_html(img)
        st = _img_style_scale(scale)
        fig = (
            f"<figure class='evid'><img src='{safe}' alt='' style='{st}'/>"
            f"<figcaption>{cap}</figcaption></figure>"
        )
    return f"<section class='sec-block'><h2 class='sec-h'>{title_html}</h2>{text}{fig}</section>"


def _split_oati_flow_chunks(flow: list[Block]) -> list[list[Block]]:
    """Una hoja nueva por cada paso (5.x); notas van con el paso anterior."""
    if not flow:
        return []
    chunks: list[list[Block]] = []
    cur: list[Block] = []
    for b in flow:
        if b.type == "oati_step":
            if cur:
                chunks.append(cur)
            cur = [b]
        else:
            cur.append(b)
    if cur:
        chunks.append(cur)
    return chunks


def _render_oati_flow_chunk(
    chunk: list[Block],
    img_idx: dict[str, int],
    step_num_base: int,
) -> tuple[str, int]:
    parts: list[str] = []
    step_num = step_num_base
    for b in chunk:
        if b.type == "oati_step":
            step_num += 1
            d = b.data
            title = _esc(str(d.get("title", "")))
            body = _section_body(str(d.get("description", "")))
            img = _resolve_image_data(d)
            cap_u = str(d.get("imageCaption", ""))
            scale = _image_scale_pct(d)
            num = img_idx.get(b.id)
            cap = _esc(_format_figure_caption(num, cap_u))
            fig = ""
            if img:
                safe = _img_src_for_html(img)
                st = _img_style_scale(scale)
                fig = (
                    f"<figure class='evid'><img src='{safe}' alt='' style='{st}'/>"
                    f"<figcaption>{cap}</figcaption></figure>"
                )
            parts.append(
                "<div class='oati-step'>"
                f"<h3 class='step-title'><span class='step-num'>5.{step_num}</span> {title}</h3>"
                f"{body}{fig}</div>",
            )
        elif b.type == "oati_note":
            body = _esc(soft_wrap_long_tokens(str(b.data.get("body", ""))))
            parts.append(
                "<p class='oati-note'><span class='oati-note-tag'>Nota:</span> "
                f"<span class='oati-note-body'>{body}</span></p>",
            )
    return "".join(parts), step_num


def _oati_flow(flow: list[Block], img_idx: dict[str, int]) -> str:
    """Flujo completo en una sola envoltura (p.ej. exportes legacy)."""
    chunks = _split_oati_flow_chunks(flow)
    if not chunks:
        return (
            "<h2 class='proc-head'>5. DESCRIPCIÓN DE CADA PASO (DETALLADO)</h2><div class='proc-wrap'></div>"
        )
    inner_parts: list[str] = []
    step_base = 0
    for ch in chunks:
        frag, step_base = _render_oati_flow_chunk(ch, img_idx, step_base)
        inner_parts.append(frag)
    return (
        "<h2 class='proc-head'>5. DESCRIPCIÓN DE CADA PASO (DETALLADO)</h2>"
        f"<div class='proc-wrap'>{''.join(inner_parts)}</div>"
    )


def oati_v2_html(manual: Manual) -> str:
    blocks = sorted(manual.blocks, key=lambda x: x.order)
    smap = {b.type: b for b in blocks if b.type in OATI_STATIC}
    cov = smap.get("oati_cover")
    d_cover = cov.data if cov else {}
    hdr = _oati_header_table(d_cover)
    flow = [b for b in blocks if b.type in ("oati_step", "oati_note")]
    img_idx = oati_image_index_by_block_id(manual)
    css = (
        ":root{color-scheme:light;}body{margin:0;background:#e5e7eb;font-family:Arial,Helvetica,sans-serif;color:#000;}"
        ".oati-doc{max-width:820px;margin:0 auto;padding:16px;}"
        ".sheet{background:#fff;border:1px solid #cbd5e1;box-shadow:0 1px 3px rgba(0,0,0,.08);"
        "padding:18mm 14mm;margin:0 auto 20px;position:relative;box-sizing:border-box;}"
        ".sheet.cover-sheet{display:flex;flex-direction:column;min-height:260mm;}"
        ".cover-main{flex:1 1 auto;display:flex;flex-direction:column;justify-content:center;align-items:center;"
        "padding:8mm 2mm 22mm;min-height:0;text-align:center;}"
        ".sheet.toc-sheet{min-height:260mm;}"
        ".sheet.body-sheet{min-height:auto;overflow-x:hidden;overflow-wrap:anywhere;}"
        ".body-text,.body-text--rich,.oati-note,.oati-note-body,.sec-block,.oati-step,.proc-wrap,.step-title,.sec-h,.proc-head{"
        "overflow-wrap:anywhere;word-wrap:break-word;word-break:break-word;max-width:100%;}"
        ".body-text--rich *{max-width:100%;overflow-wrap:anywhere;word-break:break-word;}"
        ".oati-head td{overflow-wrap:anywhere;word-break:break-word;}"
        ".evid{max-width:100%;}"
        ".oati-head{width:100%;border-collapse:collapse;border:1px solid #000;table-layout:fixed;margin-bottom:12mm;}"
        ".oati-head td{border:1px solid #000;vertical-align:middle;padding:6px 8px;font-size:10.5pt;}"
        ".hc.c1{width:18%;text-align:center;}.hc.c2{width:34%;}.hc.c3{width:28%;}.hc.c4{width:20%;text-align:center;}"
        ".hdr-logo{max-width:100%;max-height:72px;object-fit:contain;}"
        ".hdr-ph{color:#6b7280;font-size:9pt;text-align:center;line-height:1.2;}"
        ".line{margin:2px 0 4px;}.strong{font-weight:700;text-transform:uppercase;}.lbl{font-weight:600;}"
        ".crest-wrap,.crest-ph{margin:3mm auto 4mm;text-align:center;}.crest{object-fit:contain;}"
        ".crest-ph{border:1px dashed #9ca3af;color:#6b7280;padding:16px;display:inline-block;font-size:10pt;}"
        ".inst-line{text-align:center;font-family:'Times New Roman',Times,serif;font-weight:700;font-size:16pt;margin:5mm 0 2mm;width:100%;}"
        ".central-title{text-align:center;font-weight:700;font-size:14pt;text-transform:uppercase;margin:8mm 0;width:100%;}"
        ".unit-bottom{text-align:center;font-weight:700;font-size:11pt;text-transform:uppercase;margin-top:10mm;width:100%;}"
        ".toc-title{text-align:center;font-weight:700;font-size:12pt;margin:6mm 0 8mm;text-transform:uppercase;}"
        ".toc-list{list-style:none;padding:0;margin:0;}"
        ".toc-list li{display:flex;justify-content:space-between;align-items:baseline;font-weight:700;text-transform:uppercase;"
        "margin:0 0 4mm;font-size:11pt;border-bottom:1px dotted #ccc;}"
        ".toc-p{color:#111827;min-width:24px;text-align:right;}"
        ".sec-h{font-size:11pt;font-weight:700;text-transform:uppercase;margin:8mm 0 3mm;}"
        ".body-text{font-size:11pt;line-height:1.22;}"
        ".evid{margin:4mm 0;text-align:center;}.evid img{border-radius:8px;border:1px solid #e5e7eb;}"
        ".evid figcaption{font-size:10pt;margin-top:2mm;font-weight:700;}"
        ".proc-head{font-size:11pt;font-weight:700;text-transform:uppercase;margin:10mm 0 4mm;}"
        ".proc-wrap-cont{padding-top:10mm;}"
        ".oati-step{margin:5mm 0 6mm;}.step-title{margin:0 0 3mm;font-size:11pt;font-weight:700;text-transform:uppercase;}"
        ".step-num{margin-right:4px;}"
        ".oati-note{margin:5mm 0;font-size:11pt;line-height:1.35;}.oati-note-tag{font-weight:700;font-style:italic;}"
        ".oati-note-body{font-style:italic;text-decoration:underline;}"
        ".page-foot{position:absolute;left:14mm;right:14mm;bottom:10mm;display:flex;justify-content:space-between;"
        "font-size:9pt;color:#6b7280;}.page-foot.wide{align-items:flex-end;}"
        ".attrib{font-size:7pt;color:#9ca3af;max-width:52%;text-align:right;}a{color:#1d4ed8;text-decoration:underline;}"
    )
    chunks = _split_oati_flow_chunks(flow)
    n_body = max(1, len(chunks))
    total_pages = 2 + n_body

    static_blocks = (
        f"{_oati_section(smap.get('oati_intro'), 'INTRODUCCIÓN', img_idx)}"
        f"{_oati_section(smap.get('oati_objective'), '1. OBJETIVO', img_idx)}"
        f"{_oati_section(smap.get('oati_scope'), '2. ALCANCE', img_idx)}"
        f"{_oati_section(smap.get('oati_responsible'), '3. RESPONSABLES', img_idx)}"
        f"{_oati_section(smap.get('oati_definitions'), '4. DEFINICIONES Y SIGLAS', img_idx)}"
    )

    body_sheet_parts: list[str] = []
    step_base = 0
    for i, ch in enumerate(chunks):
        frag, step_base = _render_oati_flow_chunk(ch, img_idx, step_base)
        page_num = 3 + i
        footer = (
            f"<div class='page-foot wide'><span>Página {page_num} de {total_pages}</span>"
            "<span class='attrib'>Desarrollado por Oficina Asesora de Sistemas OATI</span></div>"
        )
        if i == 0:
            inner = (
                f"{static_blocks}<h2 class='proc-head'>5. DESCRIPCIÓN DE CADA PASO (DETALLADO)</h2>"
                f"<div class='proc-wrap'>{frag}</div>{footer}"
            )
        else:
            inner = f"<div class='proc-wrap proc-wrap-cont'>{frag}</div>{footer}"
        body_sheet_parts.append(
            f"<section class='sheet body-sheet'>{hdr}{inner}</section>",
        )

    if not chunks:
        footer = (
            f"<div class='page-foot wide'><span>Página 3 de {total_pages}</span>"
            "<span class='attrib'>Desarrollado por Oficina Asesora de Sistemas OATI</span></div>"
        )
        empty_flow = (
            "<h2 class='proc-head'>5. DESCRIPCIÓN DE CADA PASO (DETALLADO)</h2><div class='proc-wrap'></div>"
        )
        body_sheet_parts.append(
            f"<section class='sheet body-sheet'>{hdr}{static_blocks}{empty_flow}{footer}</section>",
        )

    body_all = "".join(body_sheet_parts)
    body_inner = (
        "<div class='oati-doc'>"
        f"{_oati_cover_page(d_cover, hdr, total_pages)}"
        f"{_oati_toc_page(hdr, total_pages)}"
        f"{body_all}"
        "</div>"
    )
    return (
        "<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'>"
        f"<style>{css}</style></head><body>{body_inner}</body></html>"
    )


def _toc_entries(manual: Manual) -> list[dict]:
    entries: list[dict] = []
    for b in sorted(manual.blocks, key=lambda x: x.order):
        if b.type == "heading1" and b.data.get("text"):
            entries.append({"text": str(b.data["text"]), "level": 1})
        if b.type == "heading2" and b.data.get("text"):
            entries.append({"text": str(b.data["text"]), "level": 2})
    return entries


def blocks_to_html(manual: Manual, asset_base_url: str | None = None) -> str:
    """HTML para vista previa / WeasyPrint; soporta plantilla OATI v2 o legado."""
    from app.config import get_settings

    base_raw = asset_base_url if asset_base_url is not None else get_settings().asset_origin
    base = base_raw.rstrip("/") + "/"
    token = _html_asset_base.set(base)
    try:
        if manual.blocks and any(b.type == "oati_cover" for b in manual.blocks):
            return oati_v2_html(manual)
        parts: list[str] = []
        parts.append(
            "<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'>"
            "<style>"
            "@page { size: A4; margin: 22mm 18mm; }"
            "body{font-family:Arial,Helvetica,sans-serif;font-size:11pt;line-height:1.15;color:#000;}"
            ".cover{text-align:center;margin-top:48mm;}"
            ".cover h1{font-size:20pt;font-weight:700;margin:0 0 8mm;}"
            ".cover .sub{font-size:14pt;color:#434343;margin:4mm 0;}"
            ".cover .meta{font-size:11pt;color:#444;margin-top:18mm;}"
            "h1{font-size:20pt;margin:14mm 0 3mm;font-weight:400;}"
            "h2{font-size:14pt;font-weight:700;margin:8mm 0 2mm;color:#000;}"
            "h3{font-size:14pt;font-weight:400;margin:10mm 0 2mm;color:#434343;}"
            "p{margin:0 0 3mm;}"
            ".toc h2{font-size:14pt;margin-bottom:4mm;}"
            ".toc ul{list-style:none;padding:0;margin:0;}"
            ".toc li{margin:0 0 2mm;}"
            "figure{margin:4mm 0;text-align:center;}"
            "figcaption{font-size:10pt;color:#444;margin-top:2mm;}"
            ".note{border-left:4px solid #2563eb;background:#eff6ff;padding:3mm 4mm;margin:4mm 0;}"
            ".warn{border-left:4px solid #d97706;background:#fffbeb;padding:3mm 4mm;margin:4mm 0;}"
            "table{width:100%;border-collapse:collapse;margin:4mm 0;font-size:10.5pt;}"
            "th,td{border:1px solid #ccc;padding:2mm 3mm;text-align:left;}"
            "th{background:#f3f4f6;font-weight:700;}"
            ".steps{counter-reset:step;}"
            ".step{counter-increment:step;margin:4mm 0;}"
            ".step h3::before{content:counter(step) '. ';font-weight:700;}"
            "hr{border:none;border-top:1px solid #ddd;margin:8mm 0;}"
            ".footer-fixed{font-size:9pt;color:#555;margin-top:12mm;border-top:1px solid #ddd;"
            "padding-top:3mm;display:flex;justify-content:space-between;}"
            "a{color:#0000FF;text-decoration:underline;}"
            "</style></head><body>"
        )

        for b in sorted(manual.blocks, key=lambda x: x.order):
            parts.append(_block_html(b, manual))

        parts.append("</body></html>")
        return "".join(parts)
    finally:
        _html_asset_base.reset(token)


def _block_html(b: Block, manual: Manual) -> str:
    d = b.data
    t = b.type
    if t == "cover":
        return (
            f"<section class='cover'><div class='sub'>{_esc(d.get('institution',''))}</div>"
            f"<div class='sub'>{_esc(d.get('unit',''))}</div>"
            f"<h1>{_esc(d.get('manualTitle',''))}</h1>"
            f"<div class='sub'>{_esc(d.get('moduleName',''))}</div>"
            f"<div class='meta'>Versión {_esc(str(d.get('version','')))} &nbsp;·&nbsp; "
            f"{_esc(str(d.get('date','')))}</div></section>"
        )
    if t == "toc":
        entries = list(d.get("entries") or [])
        if d.get("auto") and not entries:
            entries = _toc_entries(manual)
        if entries:
            lis = "".join(
                f"<li style='margin-left:{(int(e.get('level',1))-1)*6}mm'>{_esc(e.get('text',''))}</li>"
                for e in entries
            )
        else:
            lis = "<li>Índice automático: agregue títulos en el manual.</li>"
        return f"<section class='toc'><h2>{_esc(d.get('title','Tabla de contenido'))}</h2><ul>{lis}</ul></section>"
    if t == "heading1":
        return f"<h1>{_esc(str(d.get('text','')))}</h1>"
    if t == "heading2":
        return f"<h2>{_esc(str(d.get('text','')))}</h2>"
    if t == "heading3":
        return f"<h3>{_esc(str(d.get('text','')))}</h3>"
    if t == "rich_text":
        return f"<div class='rt'>{d.get('html','')}</div>"
    if t == "image":
        src = d.get("src") or ""
        cap = d.get("caption") or ""
        safe_src = _img_src_for_html(str(src))
        return (
            f"<figure><img src='{safe_src}' style='max-width:100%' alt=''/><figcaption>{_esc(cap)}</figcaption></figure>"
        )
    if t == "steps":
        items = d.get("items") or []
        body = "".join(
            f"<div class='step'><h3>{_esc(it.get('title',''))}</h3><p>{_esc(it.get('body',''))}</p></div>" for it in items
        )
        return f"<section class='steps'>{body}</section>"
    if t == "table":
        rows = d.get("rows") or []
        if not rows:
            return ""
        head = rows[0]
        h = "".join(f"<th>{_esc(c)}</th>" for c in head)
        rbody = ""
        for row in rows[1:]:
            rbody += "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>"
        return f"<table><thead><tr>{h}</tr></thead><tbody>{rbody}</tbody></table>"
    if t == "note":
        cls = "warn" if d.get("variant") == "warning" else "note"
        inner = d.get("html") or _esc(str(d.get("text", "")))
        return f"<div class='{_esc(cls)}'>{inner}</div>"
    if t == "separator":
        return "<hr/>"
    if t == "link":
        return f"<p><a href='{_esc(d.get('href',''))}'>{_esc(d.get('label',''))}</a></p>"
    if t == "footer":
        return (
            "<footer class='footer-fixed'>"
            f"<span>{_esc(d.get('left',''))}</span>"
            f"<span>{_esc(d.get('center',''))}</span>"
            f"<span>{_esc(d.get('right',''))}</span>"
            "</footer>"
        )
    return f"<div><!-- bloque desconocido: {_esc(t)} --></div>"
