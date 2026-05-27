from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import tempfile
from xml.sax.saxutils import escape, quoteattr

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
from app.application.services.quick_guide_common import is_qg_page_block, is_quick_guide_manual
from app.domain.entities.manual import Block, Manual

logger = logging.getLogger(__name__)

_RL_DEFAULT_IMG_MAX_HEIGHT_PT = float(min(float(A4[0]), float(A4[1]))) - float(3 * cm)


@dataclass(frozen=True)
class PdfBuildResult:
    content: bytes
    engine: str
    styled: bool


def _paragraph_lines(text: str, style: ParagraphStyle) -> list[Paragraph]:
    raw = text or ""
    if "<" in raw:
        plain = plain_from_html(raw)
    else:
        plain = soft_wrap_long_tokens(raw.strip())
    body = escape(plain).replace("\n", "<br/>")
    return [Paragraph(body, style)]


def _qg_inject_base_href(html_doc: str, base_href: str) -> str:
    """Añade <base href=…> tras <head> para que Chromium resuelva rutas relativas al API."""

    lowered = html_doc.lower()
    key = "<head>"
    idx = lowered.find(key)
    if idx < 0:
        return html_doc
    insert_at = idx + len(key)
    stripped = base_href.strip()
    normalized = stripped.rstrip("/") + "/" if stripped else "/"
    tag = "<base href=" + quoteattr(normalized) + ">"
    return html_doc[:insert_at] + tag + html_doc[insert_at:]


def _quick_guide_browser_cli_candidates() -> list[tuple[str, str]]:
    """Rutas comunes a Edge/Chrome para ``--print-to-pdf`` (sin Playwright ni descarga de Chromium)."""

    cand: list[tuple[str, str]] = []
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        win_paths: list[tuple[Path, str]] = [
            (Path(local) / r"Microsoft\Edge\Application\msedge.exe", "edge_cli"),
            (Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"), "edge_cli"),
            (Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"), "edge_cli"),
            (Path(local) / r"Google\Chrome\Application\chrome.exe", "chrome_cli"),
            (Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"), "chrome_cli"),
        ]
        for p, label in win_paths:
            if p.is_file():
                cand.append((str(p), label))
    else:
        for name, label in (
            ("google-chrome-stable", "chrome_cli"),
            ("google-chrome", "chrome_cli"),
            ("chromium", "chromium_cli"),
            ("chromium-browser", "chromium_cli"),
        ):
            w = shutil.which(name)
            if w:
                cand.append((w, label))
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for exe, lab in cand:
        if exe not in seen:
            seen.add(exe)
            out.append((exe, lab))
    return out


def _try_quick_guide_headless_cli_pdf(html: str, base_href: str) -> tuple[bytes, str] | None:
    """PDF desde el mismo HTML/CSS usando Chrome o Edge instalados (Chromium ``--print-to-pdf``).

    No usa el paquete Playwright ni descarga binarios; suele ser la vía que mejor replica el
    diseño en Windows cuando WeasyPrint no está disponible.
    """

    candidates = _quick_guide_browser_cli_candidates()
    if not candidates:
        return None

    merged = _qg_inject_base_href(html, base_href)
    tmp_html: Path | None = None
    tmp_pdf: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".html",
            delete=False,
            prefix="manuales-qg-cli-",
        ) as fh:
            fh.write(merged)
            tmp_html = Path(fh.name)
        uri = tmp_html.resolve().as_uri()

        fd, pdf_name = tempfile.mkstemp(suffix=".pdf", prefix="manuales-qg-cli-")
        os.close(fd)
        tmp_pdf = Path(pdf_name)

        run_kw: dict[str, object] = {"capture_output": True, "timeout": 120}
        if sys.platform == "win32":
            cf = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if cf:
                run_kw["creationflags"] = cf

        last_stderr: bytes | None = None
        for exe, engine_label in candidates:
            for head_flag in ("--headless=new", "--headless"):
                tmp_pdf.unlink(missing_ok=True)
                pdf_path = tmp_pdf.resolve()
                cmd = [
                    exe,
                    head_flag,
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-extensions",
                    "--no-pdf-header-footer",
                    "--allow-file-access-from-files",
                    "--virtual-time-budget=12000",
                    f"--print-to-pdf={pdf_path}",
                    uri,
                ]
                proc = subprocess.run(cmd, **run_kw)
                last_stderr = proc.stderr if isinstance(proc.stderr, bytes) else None
                if proc.returncode != 0:
                    logger.info(
                        "PDF CLI %s %s rc=%s: %s",
                        exe,
                        head_flag,
                        proc.returncode,
                        (proc.stderr or b"")[:400].decode("utf-8", "replace"),
                    )
                    continue
                try:
                    data = pdf_path.read_bytes()
                except OSError:
                    continue
                if len(data) < 400 or not data.startswith(b"%PDF"):
                    logger.info(
                        "PDF CLI %s no produjo PDF válido (%s bytes); siguiente.",
                        exe,
                        len(data),
                    )
                    continue

                logger.info("PDF guía rápida generado vía navegador CLI (%s)", engine_label)
                return (data, engine_label)

        if last_stderr:
            logger.info(
                "Último intento PDF CLI stderr: %s",
                last_stderr[:800].decode("utf-8", "replace"),
            )
        return None
    except subprocess.TimeoutExpired:
        logger.warning("PDF headless CLI: tiempo de espera agotado.")
        return None
    except Exception as e:
        logger.warning("PDF headless CLI falló.", exc_info=e)
        return None
    finally:
        if tmp_html is not None:
            try:
                tmp_html.unlink(missing_ok=True)
            except OSError:
                pass
        if tmp_pdf is not None:
            try:
                tmp_pdf.unlink(missing_ok=True)
            except OSError:
                pass


def _try_quick_guide_playwright(html: str, base_href: str) -> tuple[bytes, str] | None:
    """PDF maquetado con HTML+CSS mediante Playwright.

    Por defecto intenta **Google Chrome** y **Microsoft Edge** ya instalados (``channel``),
    sin descargar Chromium desde CDN (útil ante proxies SSL corporativos). Si ambos fallan,
    usa el Chromium empaquetado de Playwright (requiere ``playwright install chromium`` previo).

    Canal forzado: variable de entorno ``PLAYWRIGHT_PDF_CHANNEL`` (``chrome`` | ``msedge`` | ``chromium``).
    """

    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        logger.info("Playwright no está instalado: omitiendo PDF HTML para la guía rápida.")
        return None

    from app.config import get_settings  # noqa: PLC0415

    merged = _qg_inject_base_href(html, base_href)
    tmp_path: Path | None = None

    configured = (get_settings().playwright_pdf_channel or "").strip().lower()
    if configured in ("chromium", "bundled", "builtin"):
        channel_order: list[str | None] = [None]
    elif configured in ("chrome", "msedge"):
        channel_order = [configured]
    elif configured:
        logger.warning(
            "PLAYWRIGHT_PDF_CHANNEL=%r no reconocido (use chrome, msedge o chromium); usando auto.",
            configured,
        )
        channel_order = ["chrome", "msedge", None]
    else:
        # Windows: Chrome o Edge suelen estar sin descargar binarios de Playwright.
        channel_order = ["chrome", "msedge", None]

    last_err: BaseException | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".html",
            delete=False,
            prefix="manuales-qg-",
        ) as fh:
            fh.write(merged)
            tmp_path = Path(fh.name)
        uri = tmp_path.resolve().as_uri()

        launch_kw_base: dict[str, object] = {
            "headless": True,
            "args": ["--disable-dev-shm-usage", "--disable-gpu"],
        }

        for channel in channel_order:
            try:
                with sync_playwright() as pw:
                    if channel is None:
                        browser = pw.chromium.launch(**launch_kw_base)
                        engine_slug = "playwright_chromium_builtin"
                    else:
                        browser = pw.chromium.launch(**launch_kw_base, channel=channel)
                        engine_slug = f"playwright_{channel}"
                    try:
                        page = browser.new_page()
                        page.set_default_navigation_timeout(120_000)
                        # Ancho similar a hoja A4 horizontal (~297mm) para que el maquetado coincida con HTML/PDF.
                        page.set_viewport_size({"width": 1680, "height": 950})
                        page.emulate_media(media="screen")
                        page.goto(uri, wait_until="load")
                        try:
                            page.evaluate(
                                """async () => {
                                  try {
                                    if (document.fonts && document.fonts.ready) await document.fonts.ready;
                                  } catch (e) {}
                                }""",
                            )
                        except Exception:
                            pass
                        pdf_bytes = page.pdf(
                            print_background=True,
                            prefer_css_page_size=True,
                            omit_background=False,
                            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                        )
                        logger.info(
                            "PDF guía rápida generado vía Playwright (%s)",
                            engine_slug.replace("playwright_", ""),
                        )
                        return (pdf_bytes, engine_slug)
                    finally:
                        browser.close()
            except BaseException as e:
                last_err = e
                readable = channel if channel is not None else "chromium_embebido"
                logger.info(
                    "Playwright canal %s no disponible (%s); probando alternativa.",
                    readable,
                    e,
                )

        logger.warning(
            "Playwright no pudo abrir ningún navegador para PDF (instale Chrome o Edge, o ejecute playwright install chromium).",
            exc_info=last_err,
        )
        return None
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _manual_to_html_pdf_inputs(manual: Manual) -> tuple[str, str]:
    from app.application.services.document_html import blocks_to_html  # noqa: PLC0415

    from app.config import get_settings  # noqa: PLC0415

    settings = get_settings()
    base = settings.asset_origin.rstrip("/") + "/"
    html = blocks_to_html(manual, asset_base_url=base)
    return html, base


def _reportlab_figure_bits(
    src: str,
    caption: str,
    width_pct: int,
    caption_style: ParagraphStyle,
    *,
    usable_width_pts: float | None = None,
    max_height_pts: float | None = None,
) -> list:
    """Inserta una imagen en el story de ReportLab, escalándola dentro de un recuadro.

    El ancho base sigue ``width_pct`` sobre ``usable_width_pts`` o, si no se indica, sobre
    ``A4[0]-4cm``. El alto se acota siempre con ``max_height_pts`` o, si es ``None``, con
    ``_RL_DEFAULT_IMG_MAX_HEIGHT_PT`` (lado corto A4 menos márgenes), para evitar el error
    de ReportLab *Flowable … too large* en cabeceras de página estrechas (p. ej. A4 horizontal).
    """
    parts: list = []
    raw = image_bytes_from_src(src)
    pct = max(25, min(100, int(width_pct)))
    default_usable_w = float(A4[0]) - float(4 * cm)
    usable_w = float(usable_width_pts) if usable_width_pts is not None else default_usable_w
    target_w = usable_w * (pct / 100.0)
    # Tope alto razonable en una página A4: lado corto (~595pt) menos márgenes. Evita RL
    # "Flowable … too large" incluso cuando el llamador antiguo no pasa ``max_height_pts``.
    ceiling_h = _RL_DEFAULT_IMG_MAX_HEIGHT_PT if max_height_pts is None else float(max_height_pts)
    if raw:
        try:
            ir = ImageReader(BytesIO(raw))
            iw, ih = ir.getSize()
            if iw <= 0 or ih <= 0:
                raise ValueError("Natural image dimensions not available")
            scale = min(target_w / float(iw), ceiling_h / float(ih))
            rw = float(iw) * scale
            rh = float(ih) * scale
            parts.append(RLImage(BytesIO(raw), width=rw, height=rh))
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
    figure_layout: dict[str, float] | None = None,
) -> None:
    kw = figure_layout or {}
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
            story.extend(_reportlab_figure_bits(src, cap, _image_scale_pct(d), cap_st, **kw))
        story.append(Spacer(1, 0.4 * cm))
        return
    if t == "oati_objective":
        story.append(Paragraph("1. OBJETIVO", h1))
        story.extend(_paragraph_lines(str(d.get("text", "")), normal))
        src = _resolve_image_data(d)
        if src:
            cap = _format_figure_caption(img_idx.get(b.id), str(d.get("imageCaption", "")))
            story.extend(_reportlab_figure_bits(src, cap, _image_scale_pct(d), cap_st, **kw))
        story.append(Spacer(1, 0.4 * cm))
        return
    if t == "oati_scope":
        story.append(Paragraph("2. ALCANCE", h1))
        story.extend(_paragraph_lines(str(d.get("text", "")), normal))
        src = _resolve_image_data(d)
        if src:
            cap = _format_figure_caption(img_idx.get(b.id), str(d.get("imageCaption", "")))
            story.extend(_reportlab_figure_bits(src, cap, _image_scale_pct(d), cap_st, **kw))
        story.append(Spacer(1, 0.4 * cm))
        return
    if t == "oati_responsible":
        story.append(Paragraph("3. RESPONSABLES", h1))
        story.extend(_paragraph_lines(str(d.get("text", "")), normal))
        src = _resolve_image_data(d)
        if src:
            cap = _format_figure_caption(img_idx.get(b.id), str(d.get("imageCaption", "")))
            story.extend(_reportlab_figure_bits(src, cap, _image_scale_pct(d), cap_st, **kw))
        story.append(Spacer(1, 0.4 * cm))
        return
    if t == "oati_definitions":
        story.append(Paragraph("4. DEFINICIONES Y SIGLAS", h1))
        story.extend(_paragraph_lines(str(d.get("text", "")), normal))
        src = _resolve_image_data(d)
        if src:
            cap = _format_figure_caption(img_idx.get(b.id), str(d.get("imageCaption", "")))
            story.extend(_reportlab_figure_bits(src, cap, _image_scale_pct(d), cap_st, **kw))
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
            story.extend(_reportlab_figure_bits(src, cap, _image_scale_pct(d), cap_st, **kw))
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

    rl_figure_layout = {
        "usable_width_pts": float(doc.width),
        "max_height_pts": max(144.0, float(doc.height) - 72.0),
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
            _append_pdf_oati(story, styles_map, b, img_idx, rl_figure_layout)

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


def _manual_to_pdf_quick_guide_reportlab(manual: Manual) -> bytes:
    """Respaldo Windows/sin WeasyPrint: exporta contenido de qg_page con ReportLab (horizontal)."""
    from reportlab.lib.pagesizes import landscape

    buf = BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )
    base = getSampleStyleSheet()
    normal = ParagraphStyle(
        name="QgNormal",
        parent=base["Normal"],
        fontSize=10,
        leading=13,
    )
    h1 = ParagraphStyle(
        name="QgH1",
        parent=base["Heading1"],
        fontSize=14,
        textColor=colors.HexColor("#00668c"),
        spaceAfter=8,
    )
    h2 = ParagraphStyle(
        name="QgH2",
        parent=base["Heading2"],
        fontSize=11,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=6,
    )
    note = ParagraphStyle(
        name="QgNote",
        parent=base["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#64748b"),
    )
    # ReportLab distribuye todo en una sola columna fluida; el alto disponible tras títulos y márgenes
    # puede ser menor que doc.height — reservamos ~1″ para texto alrededor de cada captura.
    qg_img_max_h = max(144.0, min(float(doc.height) - 72.0, _RL_DEFAULT_IMG_MAX_HEIGHT_PT))
    qg_fig_kw = {"usable_width_pts": float(doc.width), "max_height_pts": qg_img_max_h}

    story: list = []
    pages = sorted([b for b in manual.blocks if is_qg_page_block(b)], key=lambda x: x.order)
    if not pages:
        story.append(Paragraph(escape("Sin páginas en la guía rápida."), normal))
        doc.build(story)
        return buf.getvalue()

    def _col_sort_key(ii: tuple[int, object]) -> tuple[int, int]:
        i, c = ii
        if not isinstance(c, dict):
            return (0, i)
        z = c.get("zIndex")
        if z is None:
            z = c.get("z_index")
        if z is None:
            z = i
        try:
            return (int(z), i)
        except (TypeError, ValueError):
            return (0, i)

    for pi, pb in enumerate(pages):
        if pi:
            story.append(PageBreak())
        data = dict(pb.data)
        ht = str(data.get("headerTitle") or "Guía rápida").strip()
        story.append(Paragraph(escape(ht), h1))
        story.append(Spacer(1, 0.2 * cm))
        cols_raw = list(data.get("columns") or [])
        for _, col in sorted(enumerate(cols_raw), key=_col_sort_key):
            if not isinstance(col, dict):
                continue
            comp = col.get("component")
            if not isinstance(comp, dict):
                continue
            kind = str(comp.get("kind") or "").lower()
            if kind == "glossary":
                story.append(Paragraph(escape("Glosario"), h2))
                for e in comp.get("entries") or []:
                    if not isinstance(e, dict):
                        continue
                    term = str(e.get("term") or "").strip()
                    defin = str(e.get("definition") or e.get("text") or "").strip()
                    if not term and not defin:
                        continue
                    line = f"<b>{escape(term)}</b>" + (f": {escape(defin)}" if defin else "")
                    story.append(Paragraph(line.replace("\n", "<br/>"), normal))
                story.append(Spacer(1, 0.25 * cm))
            elif kind == "step":
                title = str(comp.get("title") or "Paso").strip()
                story.append(Paragraph(escape(title), h2))
                for m in comp.get("miniSteps") or comp.get("mini_steps") or []:
                    if not isinstance(m, dict):
                        continue
                    txt = str(m.get("text") or "").strip()
                    if txt:
                        story.extend(_paragraph_lines(txt, normal))
                    for key in ("imageData", "image_data", "imageData2", "image_data2"):
                        src = str(m.get(key) or "").strip()
                        if src:
                            story.extend(_reportlab_figure_bits(src, "", 100, note, **qg_fig_kw))
                story.append(Spacer(1, 0.25 * cm))
            elif kind == "comment":
                txt = str(comp.get("text") or "").strip()
                if txt:
                    body = escape(soft_wrap_long_tokens(txt)).replace("\n", "<br/>")
                    story.append(Paragraph(f"<i>Nota: {body}</i>", normal))
                img = str(comp.get("imageData") or comp.get("image_data") or "").strip()
                if img:
                    story.extend(_reportlab_figure_bits(img, "", 90, note, **qg_fig_kw))
                story.append(Spacer(1, 0.25 * cm))
        story.append(Spacer(1, 0.15 * cm))
        story.append(Paragraph(escape(f"Página {pi + 1} de {len(pages)}"), note))
    doc.build(story)
    return buf.getvalue()


def manual_to_pdf(manual: Manual) -> PdfBuildResult:
    if is_quick_guide_manual(manual):
        html, base = _manual_to_html_pdf_inputs(manual)
        try:
            from weasyprint import HTML  # type: ignore[import-not-found]

            pdf = HTML(string=html, base_url=base).write_pdf()
            return PdfBuildResult(content=pdf, engine="weasyprint", styled=True)
        except Exception as e_wp:
            logger.warning(
                "Guía rápida: WeasyPrint no disponible o falló; intentando Chrome/Edge (CLI) u otro navegador.",
                exc_info=e_wp,
            )
            cli_out = _try_quick_guide_headless_cli_pdf(html, base)
            if cli_out is not None:
                pdf_body, cli_engine = cli_out
                return PdfBuildResult(content=pdf_body, engine=cli_engine, styled=True)
            pw_out = _try_quick_guide_playwright(html, base)
            if pw_out is not None:
                pdf_body, pw_engine = pw_out
                return PdfBuildResult(content=pdf_body, engine=pw_engine, styled=True)
            logger.warning(
                "Guía rápida: usando respaldo ReportLab (texto plano, sin CSS ni posiciones de módulos)."
            )
            return PdfBuildResult(
                content=_manual_to_pdf_quick_guide_reportlab(manual),
                engine="reportlab_quick_guide_plain",
                styled=False,
            )

    html, base = _manual_to_html_pdf_inputs(manual)
    try:
        from weasyprint import HTML  # type: ignore[import-not-found]

        pdf = HTML(string=html, base_url=base).write_pdf()
        return PdfBuildResult(content=pdf, engine="weasyprint", styled=True)
    except Exception as e:
        logger.warning("WeasyPrint falló para el manual OATI; usando ReportLab.", exc_info=e)
        return PdfBuildResult(
            content=_manual_to_pdf_reportlab(manual),
            engine="reportlab_oati_fallback",
            styled=False,
        )
