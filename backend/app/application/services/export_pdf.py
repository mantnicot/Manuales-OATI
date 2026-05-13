from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image as RLImage
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.application.services.document_html import (
    _crest_scale_pct,
    _format_figure_caption,
    _image_scale_pct,
    _resolve_image_data,
    oati_image_index_by_block_id,
    resolve_crest_src,
    resolve_logo_oati_src,
    resolve_logo_ud_src,
)
from app.application.services.export_media import image_bytes_from_src
from app.application.services.plain_text import plain_from_html, soft_wrap_long_tokens
from app.domain.entities.manual import Block, Manual


def _paragraph_lines(text: str, style: ParagraphStyle) -> list[Paragraph]:
    raw = text or ""
    if "<" in raw:
        plain = plain_from_html(raw)
    else:
        plain = soft_wrap_long_tokens(raw.strip())
    body = escape(plain).replace("\n", "<br/>")
    return [Paragraph(body, style)]


def _reportlab_figure_bits(
    src: str,
    caption: str,
    width_pct: int,
    caption_style: ParagraphStyle,
) -> list:
    parts: list = []
    raw = image_bytes_from_src(src)
    pct = max(25, min(100, int(width_pct)))
    usable = A4[0] - 4 * cm
    target_w = usable * pct / 100
    if raw:
        try:
            ir = ImageReader(BytesIO(raw))
            iw, ih = ir.getSize()
            scale = target_w / float(iw)
            parts.append(RLImage(BytesIO(raw), width=target_w, height=ih * scale))
        except Exception:
            parts.append(Paragraph(escape("[Imagen no incluida en PDF]"), caption_style))
    if caption:
        parts.append(Paragraph(escape(soft_wrap_long_tokens(caption)), caption_style))
    return parts


def _rl_logo_flowable(
    src: str,
    max_w: float,
    max_h: float,
    placeholder_html: str,
    ph_style: ParagraphStyle,
) -> RLImage | Paragraph:
    raw_b = image_bytes_from_src(src.strip()) if (src or "").strip() else None
    if raw_b:
        try:
            ir = ImageReader(BytesIO(raw_b))
            iw, ih = ir.getSize()
            scale = min(max_w / float(iw), max_h / float(ih))
            rw, rh = iw * scale, ih * scale
            return RLImage(BytesIO(raw_b), width=rw, height=rh)
        except Exception:
            pass
    return Paragraph(placeholder_html, ph_style)


def _pdf_oati_header_table(d: dict, normal: ParagraphStyle) -> Table:
    """Misma cabecera tabular que la portada, para repetir en páginas siguientes (ReportLab)."""
    hdr_cell = ParagraphStyle(
        name="OatiHdrCellPdfRepeat",
        parent=normal,
        fontSize=9.5,
        leading=12,
        alignment=TA_LEFT,
    )
    ph_style = ParagraphStyle(
        name="OatiLogoPhPdfRepeat",
        parent=normal,
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#6b7280"),
    )
    w_tot = A4[0] - 4 * cm
    col_w = [w_tot * 0.18, w_tot * 0.34, w_tot * 0.28, w_tot * 0.20]
    max_logo_w = max(col_w[0], col_w[3]) - 0.35 * cm
    max_logo_h = 2.8 * cm

    c1 = _rl_logo_flowable(
        resolve_logo_ud_src(d),
        max_logo_w,
        max_logo_h,
        "Logo<br/>Universidad",
        ph_style,
    )
    c4 = _rl_logo_flowable(
        resolve_logo_oati_src(d),
        max_logo_w,
        max_logo_h,
        "Logo<br/>OATI",
        ph_style,
    )
    m_h = escape(str(d.get("moduleHeaderLine", "")))
    mac = escape(str(d.get("macroProcess", "")))
    proc = escape(str(d.get("processLine", "")))
    mid = Paragraph(f"<b>{m_h}</b><br/>{mac}<br/>{proc}", hdr_cell)
    cd = escape(str(d.get("code", "")))
    ver = escape(str(d.get("version", "")))
    apr = escape(str(d.get("approvalDate", "")))
    right = Paragraph(
        f"<b>Código:</b> {cd}<br/><b>Versión:</b> {ver}<br/><b>Fecha de Aprobación:</b> {apr}",
        hdr_cell,
    )
    head_tbl = Table([[c1, mid, right, c4]], colWidths=col_w, hAlign="CENTER")
    head_tbl.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ],
        ),
    )
    return head_tbl


def _draw_pdf_oati_header_repeat(canvas, doc, d_cover: dict, normal: ParagraphStyle) -> None:
    if not d_cover:
        return
    canvas.saveState()
    tbl = _pdf_oati_header_table(d_cover, normal)
    _w, h = tbl.wrap(doc.width, doc.topMargin)
    y = doc.pagesize[1] - doc.topMargin - h
    tbl.drawOn(canvas, doc.leftMargin, y)
    canvas.restoreState()


def _append_oati_cover_pdf(story: list, d: dict, styles: dict[str, ParagraphStyle]) -> None:
    """Portada con cabecera tabular e imágenes (similar a la vista HTML)."""
    normal = styles["normal"]
    centered = styles["centered"]
    cover_inst = styles["cover_inst"]
    cover_title = styles["cover_title"]
    cover_unit = styles["cover_unit"]
    ph_style = ParagraphStyle(
        name="OatiLogoPhPdf",
        parent=normal,
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#6b7280"),
    )
    w_tot = A4[0] - 4 * cm

    head_tbl = _pdf_oati_header_table(d, normal)
    story.append(head_tbl)
    story.append(Spacer(1, 0.75 * cm))

    crest = resolve_crest_src(d).strip()
    raw_crest = image_bytes_from_src(crest) if crest else None
    c_pct = max(50, min(150, _crest_scale_pct(d))) / 100.0
    if raw_crest:
        try:
            ir = ImageReader(BytesIO(raw_crest))
            iw, ih = ir.getSize()
            max_ch = 5.2 * cm * c_pct
            cw = min(w_tot * 0.42, 4.5 * cm) * c_pct
            scale = min(cw / float(iw), max_ch / float(ih))
            rw, rh = iw * scale, ih * scale
            crest_img = RLImage(BytesIO(raw_crest), width=rw, height=rh)
            crest_wrap = Table([[crest_img]], colWidths=[w_tot], hAlign="CENTER")
            crest_wrap.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
            story.append(crest_wrap)
            story.append(Spacer(1, 0.55 * cm))
        except Exception:
            story.append(Paragraph(escape("[Escudo no disponible]"), ph_style))
            story.append(Spacer(1, 0.35 * cm))
    else:
        story.append(
            Paragraph(escape("Escudo institucional"), ph_style),
        )
        story.append(Spacer(1, 0.45 * cm))

    inst = str(d.get("institutionLine", "")).strip()
    if inst:
        story.extend(_paragraph_lines(inst, cover_inst))
    ct = str(d.get("centralTitle", "")).strip()
    if ct:
        story.extend(_paragraph_lines(ct, cover_title))
    unit = str(d.get("unitFooterLine", "")).strip()
    if unit:
        story.extend(_paragraph_lines(unit, cover_unit))

    story.append(PageBreak())


def _append_pdf_oati(
    story: list,
    styles: dict[str, ParagraphStyle],
    b: Block,
    img_idx: dict[str, int],
) -> None:
    d = b.data
    t = b.type
    normal = styles["normal"]
    h1 = styles["h1"]
    h2 = styles["h2"]
    cap_st = styles["caption"]
    if t == "oati_cover":
        _append_oati_cover_pdf(story, d, styles)
        return
    if t == "oati_intro":
        story.append(Paragraph("INTRODUCCIÓN", h1))
        story.extend(_paragraph_lines(str(d.get("text", "")), normal))
        src = _resolve_image_data(d)
        if src:
            cap = _format_figure_caption(img_idx.get(b.id), str(d.get("imageCaption", "")))
            story.extend(_reportlab_figure_bits(src, cap, _image_scale_pct(d), cap_st))
        story.append(Spacer(1, 0.4 * cm))
        return
    if t == "oati_objective":
        story.append(Paragraph("1. OBJETIVO", h1))
        story.extend(_paragraph_lines(str(d.get("text", "")), normal))
        src = _resolve_image_data(d)
        if src:
            cap = _format_figure_caption(img_idx.get(b.id), str(d.get("imageCaption", "")))
            story.extend(_reportlab_figure_bits(src, cap, _image_scale_pct(d), cap_st))
        story.append(Spacer(1, 0.4 * cm))
        return
    if t == "oati_scope":
        story.append(Paragraph("2. ALCANCE", h1))
        story.extend(_paragraph_lines(str(d.get("text", "")), normal))
        src = _resolve_image_data(d)
        if src:
            cap = _format_figure_caption(img_idx.get(b.id), str(d.get("imageCaption", "")))
            story.extend(_reportlab_figure_bits(src, cap, _image_scale_pct(d), cap_st))
        story.append(Spacer(1, 0.4 * cm))
        return
    if t == "oati_responsible":
        story.append(Paragraph("3. RESPONSABLES", h1))
        story.extend(_paragraph_lines(str(d.get("text", "")), normal))
        src = _resolve_image_data(d)
        if src:
            cap = _format_figure_caption(img_idx.get(b.id), str(d.get("imageCaption", "")))
            story.extend(_reportlab_figure_bits(src, cap, _image_scale_pct(d), cap_st))
        story.append(Spacer(1, 0.4 * cm))
        return
    if t == "oati_definitions":
        story.append(Paragraph("4. DEFINICIONES Y SIGLAS", h1))
        story.extend(_paragraph_lines(str(d.get("text", "")), normal))
        src = _resolve_image_data(d)
        if src:
            cap = _format_figure_caption(img_idx.get(b.id), str(d.get("imageCaption", "")))
            story.extend(_reportlab_figure_bits(src, cap, _image_scale_pct(d), cap_st))
        story.append(Spacer(1, 0.4 * cm))
        return
    if t == "oati_step":
        story.append(
            Paragraph(escape(soft_wrap_long_tokens(str(d.get("title", "Paso")))), h2),
        )
        story.extend(_paragraph_lines(str(d.get("description", "")), normal))
        src = _resolve_image_data(d)
        if src:
            cap = _format_figure_caption(img_idx.get(b.id), str(d.get("imageCaption", "")))
            story.extend(_reportlab_figure_bits(src, cap, _image_scale_pct(d), cap_st))
        story.append(Spacer(1, 0.3 * cm))
        return
    if t == "oati_note":
        body = plain_from_html(str(d.get("body", "")))
        story.extend(_paragraph_lines(f"Nota: {body}", normal))
        story.append(Spacer(1, 0.3 * cm))


def _manual_to_pdf_reportlab(manual: Manual) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    base = getSampleStyleSheet()
    styles_map = {
        "normal": base["Normal"],
        "h1": ParagraphStyle(
            name="PdfH1",
            parent=base["Heading1"],
            spaceAfter=12,
            textColor=colors.HexColor("#1d4ed8"),
        ),
        "h2": ParagraphStyle(
            name="PdfH2",
            parent=base["Heading2"],
            spaceAfter=10,
            textColor=colors.HexColor("#1d4ed8"),
        ),
        "centered": ParagraphStyle(
            name="PdfCenter",
            parent=base["Normal"],
            alignment=TA_CENTER,
            spaceAfter=6,
        ),
        "cover_inst": ParagraphStyle(
            name="PdfCoverInst",
            parent=base["Normal"],
            alignment=TA_CENTER,
            fontName="Times-Bold",
            fontSize=14,
            leading=18,
            spaceAfter=10,
        ),
        "cover_title": ParagraphStyle(
            name="PdfCoverTitle",
            parent=base["Normal"],
            alignment=TA_CENTER,
            fontSize=13,
            fontName="Helvetica-Bold",
            spaceAfter=14,
        ),
        "cover_unit": ParagraphStyle(
            name="PdfCoverUnit",
            parent=base["Normal"],
            alignment=TA_CENTER,
            fontSize=11,
            fontName="Helvetica-Bold",
            spaceAfter=8,
        ),
        "caption": ParagraphStyle(
            name="PdfFigCap",
            parent=base["Normal"],
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            fontSize=10,
            spaceBefore=4,
            spaceAfter=8,
        ),
    }

    story: list = []
    ordered = sorted(manual.blocks, key=lambda x: x.order)
    d_cover: dict = {}
    for b in ordered:
        if b.type == "oati_cover":
            d_cover = dict(b.data)
            break

    if not ordered:
        story.append(Paragraph(escape("Sin contenido en el manual."), styles_map["normal"]))
        doc.build(story)
    elif any(b.type == "oati_cover" for b in manual.blocks):
        img_idx = oati_image_index_by_block_id(manual)
        for b in ordered:
            _append_pdf_oati(story, styles_map, b, img_idx)

        def _on_first(_canv, _doc) -> None:
            return

        def _on_later(canv, doc) -> None:
            _draw_pdf_oati_header_repeat(canv, doc, d_cover, styles_map["normal"])

        doc.build(story, onFirstPage=_on_first, onLaterPages=_on_later)
    else:
        story.append(
            Paragraph(
                escape("Estructura no OATI: use la plantilla oficial o exporte a Word."),
                styles_map["normal"],
            ),
        )
        doc.build(story)
    return buf.getvalue()


def manual_to_pdf(manual: Manual) -> bytes:
    try:
        from app.application.services.document_html import blocks_to_html  # noqa: PLC0415

        from app.config import get_settings  # noqa: PLC0415

        settings = get_settings()
        base = settings.asset_origin.rstrip("/") + "/"
        html = blocks_to_html(manual, asset_base_url=base)
        from weasyprint import HTML  # type: ignore[import-not-found]

        return HTML(string=html, base_url=base).write_pdf()
    except Exception:
        return _manual_to_pdf_reportlab(manual)
