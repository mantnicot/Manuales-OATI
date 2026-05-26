from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.application.services.document_html import blocks_to_html
from app.application.services.export_docx import manual_to_docx
from app.application.services.export_pdf import manual_to_pdf
from app.application.use_cases.create_manual import CreateManual, DuplicateManual
from app.domain.entities.manual import Block, Manual, ManualStatus
from app.domain.ports.repositories import ManualRepository
from app.infrastructure.persistence.in_memory_manual_repository import InMemoryManualRepository
from app.infrastructure.persistence.library_store import get_library_store

router = APIRouter(prefix="/manuals", tags=["manuals"])

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_PDF_UPLOAD_MAX_BYTES = 45 * 1024 * 1024

_repo_singleton: InMemoryManualRepository | None = None


def _is_pdf_storage_manual(m: Manual) -> bool:
    return str(m.meta.get("storage_kind") or "") == "pdf"


def _pdf_blob_path(m: Manual) -> Path | None:
    rel = m.meta.get("pdf_file")
    if not rel or not isinstance(rel, str):
        return None
    p = (_DATA_DIR / rel).resolve()
    try:
        p.relative_to(_DATA_DIR.resolve())
    except ValueError:
        return None
    return p


def _delete_pdf_blob_if_any(m: Manual) -> None:
    p = _pdf_blob_path(m)
    if p and p.is_file():
        try:
            p.unlink()
        except OSError:
            pass


def get_manual_repo() -> ManualRepository:
    global _repo_singleton
    if _repo_singleton is None:
        _repo_singleton = InMemoryManualRepository()
    return _repo_singleton


class BlockDTO(BaseModel):
    id: str
    type: str
    order: int
    data: dict[str, Any] = Field(default_factory=dict)


class ManualCreateDTO(BaseModel):
    title: str
    code: str
    use_official_template: bool = True
    system_id: UUID | None = None
    folder_id: UUID | None = None
    document_kind: str | None = None


class ManualUpdateDTO(BaseModel):
    title: str | None = None
    code: str | None = None
    status: ManualStatus | None = None
    system_id: UUID | None = None
    folder_id: UUID | None = None
    blocks: list[BlockDTO] | None = None
    meta: dict[str, Any] | None = None
    bump_version: bool = False


class ManualResponseDTO(BaseModel):
    id: UUID
    title: str
    code: str
    system_id: UUID | None
    folder_id: UUID | None
    status: ManualStatus
    blocks: list[BlockDTO]
    meta: dict[str, Any]
    current_version: int
    created_at: str | None = None
    updated_at: str | None = None


def _to_response(m: Manual) -> ManualResponseDTO:
    return ManualResponseDTO(
        id=m.id,
        title=m.title,
        code=m.code,
        system_id=m.system_id,
        folder_id=m.folder_id,
        status=m.status,
        blocks=[BlockDTO(id=b.id, type=b.type, order=b.order, data=b.data) for b in m.blocks],
        meta=m.meta,
        current_version=m.current_version,
        created_at=m.created_at.isoformat() if m.created_at else None,
        updated_at=m.updated_at.isoformat() if m.updated_at else None,
    )


def _domain_blocks_from_payload(items: list[Any]) -> list[Block]:
    """Convierte bloques del PATCH (dicts tras model_dump) o DTOs en entidades de dominio."""
    out: list[Block] = []
    for item in items:
        dto = BlockDTO.model_validate(item)
        out.append(
            Block(
                id=dto.id,
                type=dto.type,
                order=dto.order,
                data=copy.deepcopy(dict(dto.data)),
            )
        )
    return out


@router.get("", response_model=dict)
async def list_manuals(
    repo: Annotated[ManualRepository, Depends(get_manual_repo)],
    q: str | None = Query(None),
    status: ManualStatus | None = None,
    limit: int = 50,
    offset: int = 0,
):
    items, total = await repo.list(
        query=q, system_id=None, status=status, limit=limit, offset=offset
    )
    return {"total": total, "items": [_to_response(m) for m in items]}


@router.post("", response_model=ManualResponseDTO)
async def create_manual(body: ManualCreateDTO, repo: Annotated[ManualRepository, Depends(get_manual_repo)]):
    uc = CreateManual(repo)
    m = await uc.execute(
        title=body.title,
        code=body.code,
        use_official_template=body.use_official_template,
        system_id=body.system_id,
        folder_id=body.folder_id,
        document_kind=body.document_kind,
    )
    return _to_response(m)


@router.post("/actions/upload-pdf", response_model=ManualResponseDTO)
async def upload_pdf_manual(
    repo: Annotated[ManualRepository, Depends(get_manual_repo)],
    file: UploadFile = File(...),
    title: str | None = Form(None),
    code: str | None = Form(None),
    system_id: UUID | None = Form(None),
    folder_id: UUID | None = Form(None),
):
    """Guarda un .pdf tal cual; no es editable en el constructor OATI."""
    raw_name = (file.filename or "").strip()
    if not raw_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se admiten archivos .pdf")
    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="Archivo vacío")
    if len(body) > _PDF_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=400, detail="El archivo supera el tamaño máximo permitido (~45 MB)")

    final_folder_id = folder_id
    final_system_id = system_id
    if final_folder_id is not None:
        fold = get_library_store().get_folder(final_folder_id)
        if fold is None:
            raise HTTPException(status_code=400, detail="Carpeta no encontrada")
        final_system_id = fold.system_id

    title_clean = (title or "").strip()
    code_clean = (code or "").strip()
    stem = Path(raw_name).stem or "documento"
    final_title = title_clean or stem
    final_code = code_clean or f"PDF-{uuid4().hex[:10].upper()}"

    mid = uuid4()
    upload_dir = _DATA_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{mid}.pdf"
    try:
        dest.write_bytes(body)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="No se pudo guardar el archivo") from exc

    m = Manual(
        id=mid,
        title=final_title,
        code=final_code,
        system_id=final_system_id,
        folder_id=final_folder_id,
        status=ManualStatus.DRAFT,
        blocks=[],
        meta={
            "storage_kind": "pdf",
            "original_filename": raw_name,
            "pdf_file": f"uploads/{mid}.pdf",
        },
        current_version=1,
    )
    saved = await repo.save(m)
    return _to_response(saved)


class RenderHtmlDTO(BaseModel):
    """Misma estructura que un manual guardado; genera HTML idéntico a PDF/export.docx."""

    title: str = ""
    code: str = ""
    blocks: list[BlockDTO]
    meta: dict[str, Any] = Field(default_factory=dict)
    current_version: int = 1


@router.post("/actions/render-html")
async def render_html_snap(request: Request, body: RenderHtmlDTO):
    m = Manual(
        id=uuid4(),
        title=body.title,
        code=body.code,
        system_id=None,
        folder_id=None,
        status=ManualStatus.DRAFT,
        blocks=[
            Block(
                id=b.id,
                type=b.type,
                order=b.order,
                data=copy.deepcopy(dict(b.data)),
            )
            for b in body.blocks
        ],
        meta=copy.deepcopy(dict(body.meta)),
        current_version=body.current_version,
    )
    return Response(
        content=blocks_to_html(m, asset_base_url=str(request.base_url)),
        media_type="text/html; charset=utf-8",
    )


@router.get("/{manual_id}", response_model=ManualResponseDTO)
async def get_manual(manual_id: UUID, repo: Annotated[ManualRepository, Depends(get_manual_repo)]):
    m = await repo.get(manual_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Manual no encontrado")
    return _to_response(m)


@router.patch("/{manual_id}", response_model=ManualResponseDTO)
async def update_manual(
    manual_id: UUID,
    body: ManualUpdateDTO,
    repo: Annotated[ManualRepository, Depends(get_manual_repo)],
):
    m = await repo.get(manual_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Manual no encontrado")
    data = body.model_dump(exclude_unset=True)
    if "folder_id" in data and data["folder_id"] is not None:
        fold = get_library_store().get_folder(data["folder_id"])
        if fold is None:
            raise HTTPException(status_code=400, detail="Carpeta no encontrada")
        data["system_id"] = fold.system_id
    bump = bool(data.pop("bump_version", False))
    if _is_pdf_storage_manual(m):
        data.pop("blocks", None)
        data.pop("meta", None)
    if "blocks" in data:
        raw_blocks = data.pop("blocks")
        m.blocks = _domain_blocks_from_payload(raw_blocks)
    for key in ("title", "code", "status", "system_id", "folder_id", "meta"):
        if key in data:
            setattr(m, key, data[key])
    if bump:
        m.current_version += 1
    m = await repo.save(m)
    return _to_response(m)


@router.post("/{manual_id}/duplicate", response_model=ManualResponseDTO)
async def duplicate_manual(
    manual_id: UUID,
    repo: Annotated[ManualRepository, Depends(get_manual_repo)],
    new_code: str = Query(..., description="Código único para la copia"),
):
    src = await repo.get(manual_id)
    if src is None:
        raise HTTPException(status_code=404, detail="Manual origen no encontrado")
    if _is_pdf_storage_manual(src):
        raise HTTPException(
            status_code=400,
            detail="Los PDF subidos no se pueden duplicar aquí; vuelva a subir el archivo.",
        )
    uc = DuplicateManual(repo)
    clone = await uc.execute(source_id=manual_id, new_code=new_code)
    if clone is None:
        raise HTTPException(status_code=404, detail="Manual origen no encontrado")
    return _to_response(clone)


@router.delete("/{manual_id}", status_code=204)
async def archive_manual(manual_id: UUID, repo: Annotated[ManualRepository, Depends(get_manual_repo)]):
    m = await repo.get(manual_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Manual no encontrado")
    if _is_pdf_storage_manual(m):
        _delete_pdf_blob_if_any(m)
    try:
        await repo.soft_delete(manual_id)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{manual_id}/pdf-file")
async def download_pdf_original(
    manual_id: UUID,
    repo: Annotated[ManualRepository, Depends(get_manual_repo)],
    inline: Annotated[
        bool,
        Query(description="Si es true, Content-Disposition inline (ver en el navegador)."),
    ] = False,
):
    m = await repo.get(manual_id)
    if m is None or not _is_pdf_storage_manual(m):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    path = _pdf_blob_path(m)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado en disco")
    fname = str(m.meta.get("original_filename") or f"{m.code}.pdf")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=fname,
        content_disposition_type="inline" if inline else "attachment",
    )


def _inject_preview_pdf_toolbar(html: str, manual_id: UUID) -> str:
    """Barra fija con descarga PDF (solo pestaña de vista previa guardada)."""
    mid = str(manual_id)
    pdf_href = f"/api/v1/manuals/{mid}/export.pdf?inline=1"
    bar = (
        '<div id="oati-preview-toolbar" style="position:fixed;z-index:2147483647;top:0;left:0;right:0;'
        "background:#0f172a;color:#f8fafc;padding:12px 16px;font-family:system-ui,Segoe UI,sans-serif;"
        'font-size:15px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;box-shadow:0 2px 8px rgba(0,0,0,.25);">'
        "<strong>Vista previa — OATI</strong>"
        '<span style="opacity:.9;font-size:13px;max-width:min(520px,90vw);">Última versión guardada. Use el botón para generar y descargar el PDF.</span>'
        f'<a href="{pdf_href}" '
        'style="margin-left:auto;background:#22c55e;color:#0f172a;padding:10px 18px;border-radius:8px;'
        'font-weight:700;text-decoration:none;white-space:nowrap;">Descargar PDF</a>'
        "</div>"
        "<style>html{scroll-padding-top:64px;}body{padding-top:64px !important;margin:0;}</style>"
    )
    out, n = re.subn(r"(<body[^>]*>)", r"\1" + bar, html, count=1, flags=re.IGNORECASE)
    if n:
        return out
    if "</head>" in html:
        return html.replace("</head>", bar + "</head>", 1)
    return bar + html


@router.get("/{manual_id}/preview")
async def preview_html(
    request: Request,
    manual_id: UUID,
    repo: Annotated[ManualRepository, Depends(get_manual_repo)],
):
    m = await repo.get(manual_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Manual no encontrado")
    if _is_pdf_storage_manual(m):
        raise HTTPException(
            status_code=400,
            detail="Este documento es un PDF almacenado; ábralo con «ver» o «descargar» desde la biblioteca.",
        )
    html_out = _inject_preview_pdf_toolbar(blocks_to_html(m, asset_base_url=str(request.base_url)), manual_id)
    return Response(content=html_out, media_type="text/html; charset=utf-8")


@router.get("/{manual_id}/export.docx")
async def export_docx(manual_id: UUID, repo: Annotated[ManualRepository, Depends(get_manual_repo)]):
    m = await repo.get(manual_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Manual no encontrado")
    if _is_pdf_storage_manual(m):
        raise HTTPException(
            status_code=400,
            detail="Use la ruta del PDF almacenado (/pdf-file) para este documento.",
        )
    data = manual_to_docx(m)
    filename = f"{m.code}-v{m.current_version}.docx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{manual_id}/export.pdf")
async def export_pdf(
    manual_id: UUID,
    repo: Annotated[ManualRepository, Depends(get_manual_repo)],
    inline: Annotated[
        bool,
        Query(description="Si es true, Content-Disposition inline (ver en navegador / iframe)."),
    ] = False,
):
    m = await repo.get(manual_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Manual no encontrado")
    if _is_pdf_storage_manual(m):
        raise HTTPException(
            status_code=400,
            detail="Este documento es el PDF subido; no se genera otro PDF desde la plantilla OATI.",
        )
    try:
        result = manual_to_pdf(m)
    except Exception as e:
        raise HTTPException(status_code=501, detail=f"No se pudo generar el PDF: {e!s}") from e
    filename = f"{m.code}-v{m.current_version}.pdf"
    return Response(
        content=result.content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{filename}"',
            "Cache-Control": "no-store, max-age=0",
            "X-Manuales-Pdf-Engine": result.engine,
            "X-Manuales-Pdf-Styled": "1" if result.styled else "0",
        },
    )
