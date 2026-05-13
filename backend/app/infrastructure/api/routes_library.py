from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.domain.ports.repositories import ManualRepository
from app.infrastructure.api.routes_manuals import get_manual_repo
from app.infrastructure.persistence.library_store import (
    LibraryFolderDTO,
    LibraryStore,
    LibrarySystemDTO,
    get_library_store,
)


def _lib_dep() -> LibraryStore:
    return get_library_store()


router = APIRouter(prefix="/library", tags=["library"])


class SystemCreateDTO(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class SystemPatchDTO(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class FolderCreateDTO(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    system_id: UUID


class FolderPatchDTO(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class SystemResponseDTO(BaseModel):
    id: UUID
    name: str


class FolderResponseDTO(BaseModel):
    id: UUID
    name: str
    system_id: UUID


class LibrarySnapshotDTO(BaseModel):
    systems: list[SystemResponseDTO]
    folders: list[FolderResponseDTO]


def _to_sys(s: LibrarySystemDTO) -> SystemResponseDTO:
    return SystemResponseDTO(id=s.id, name=s.name)


def _to_fold(f: LibraryFolderDTO) -> FolderResponseDTO:
    return FolderResponseDTO(id=f.id, name=f.name, system_id=f.system_id)


@router.get("", response_model=LibrarySnapshotDTO)
async def library_snapshot(lib: Annotated[LibraryStore, Depends(_lib_dep)]):
    systems, folders = lib.snapshot()
    return LibrarySnapshotDTO(
        systems=[_to_sys(s) for s in systems],
        folders=[_to_fold(f) for f in folders],
    )


@router.post("/systems", response_model=SystemResponseDTO)
async def create_system(body: SystemCreateDTO, lib: Annotated[LibraryStore, Depends(_lib_dep)]):
    s = lib.create_system(body.name)
    return _to_sys(s)


@router.patch("/systems/{system_id}", response_model=SystemResponseDTO)
async def patch_system(
    system_id: UUID,
    body: SystemPatchDTO,
    lib: Annotated[LibraryStore, Depends(_lib_dep)],
):
    s = lib.update_system(system_id, body.name)
    if s is None:
        raise HTTPException(status_code=404, detail="Sistema no encontrado")
    return _to_sys(s)


@router.delete("/systems/{system_id}", status_code=204)
async def delete_system(
    system_id: UUID,
    lib: Annotated[LibraryStore, Depends(_lib_dep)],
    repo: Annotated[ManualRepository, Depends(get_manual_repo)],
):
    if lib.get_system(system_id) is None:
        raise HTTPException(status_code=404, detail="Sistema no encontrado")
    lib.delete_system(system_id)
    await repo.clear_system_and_folders(system_id)


@router.post("/folders", response_model=FolderResponseDTO)
async def create_folder(body: FolderCreateDTO, lib: Annotated[LibraryStore, Depends(_lib_dep)]):
    f = lib.create_folder(body.name, body.system_id)
    if f is None:
        raise HTTPException(status_code=400, detail="Sistema no válido")
    return _to_fold(f)


@router.patch("/folders/{folder_id}", response_model=FolderResponseDTO)
async def patch_folder(
    folder_id: UUID,
    body: FolderPatchDTO,
    lib: Annotated[LibraryStore, Depends(_lib_dep)],
):
    f = lib.update_folder(folder_id, body.name)
    if f is None:
        raise HTTPException(status_code=404, detail="Carpeta no encontrada")
    return _to_fold(f)


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: UUID,
    lib: Annotated[LibraryStore, Depends(_lib_dep)],
    repo: Annotated[ManualRepository, Depends(get_manual_repo)],
):
    if lib.get_folder(folder_id) is None:
        raise HTTPException(status_code=404, detail="Carpeta no encontrada")
    lib.delete_folder(folder_id)
    await repo.clear_folder_id(folder_id)
