from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

_LIBRARY_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "library.json"


@dataclass
class LibrarySystemDTO:
    id: UUID
    name: str


@dataclass
class LibraryFolderDTO:
    id: UUID
    name: str
    system_id: UUID


class LibraryStore:
    def __init__(self) -> None:
        self.systems: list[LibrarySystemDTO] = []
        self.folders: list[LibraryFolderDTO] = []
        self._load()

    def _load(self) -> None:
        if not _LIBRARY_FILE.is_file():
            return
        try:
            raw = json.loads(_LIBRARY_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.systems = []
        self.folders = []
        for s in raw.get("systems") or []:
            try:
                self.systems.append(LibrarySystemDTO(id=UUID(str(s["id"])), name=str(s.get("name", ""))))
            except (KeyError, ValueError, TypeError):
                continue
        for f in raw.get("folders") or []:
            try:
                self.folders.append(
                    LibraryFolderDTO(
                        id=UUID(str(f["id"])),
                        name=str(f.get("name", "")),
                        system_id=UUID(str(f["system_id"])),
                    ),
                )
            except (KeyError, ValueError, TypeError):
                continue

    def _persist(self) -> None:
        try:
            _LIBRARY_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "systems": [{"id": str(s.id), "name": s.name} for s in self.systems],
                "folders": [{"id": str(f.id), "name": f.name, "system_id": str(f.system_id)} for f in self.folders],
            }
            _LIBRARY_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def snapshot(self) -> tuple[list[LibrarySystemDTO], list[LibraryFolderDTO]]:
        return list(self.systems), list(self.folders)

    def get_system(self, sid: UUID) -> LibrarySystemDTO | None:
        for s in self.systems:
            if s.id == sid:
                return s
        return None

    def get_folder(self, fid: UUID) -> LibraryFolderDTO | None:
        for f in self.folders:
            if f.id == fid:
                return f
        return None

    def create_system(self, name: str) -> LibrarySystemDTO:
        s = LibrarySystemDTO(id=uuid4(), name=name.strip() or "Sin nombre")
        self.systems.append(s)
        self._persist()
        return s

    def update_system(self, sid: UUID, name: str) -> LibrarySystemDTO | None:
        s = self.get_system(sid)
        if not s:
            return None
        s.name = name.strip() or "Sin nombre"
        self._persist()
        return s

    def delete_system(self, sid: UUID) -> list[UUID]:
        """Elimina el sistema y sus carpetas; devuelve ids de carpetas borradas."""
        removed_folder_ids = [f.id for f in self.folders if f.system_id == sid]
        self.folders = [f for f in self.folders if f.system_id != sid]
        self.systems = [s for s in self.systems if s.id != sid]
        self._persist()
        return removed_folder_ids

    def create_folder(self, name: str, system_id: UUID) -> LibraryFolderDTO | None:
        if self.get_system(system_id) is None:
            return None
        f = LibraryFolderDTO(id=uuid4(), name=name.strip() or "Sin nombre", system_id=system_id)
        self.folders.append(f)
        self._persist()
        return f

    def update_folder(self, fid: UUID, name: str) -> LibraryFolderDTO | None:
        f = self.get_folder(fid)
        if not f:
            return None
        f.name = name.strip() or "Sin nombre"
        self._persist()
        return f

    def delete_folder(self, fid: UUID) -> None:
        self.folders = [f for f in self.folders if f.id != fid]
        self._persist()


_library_singleton: LibraryStore | None = None


def get_library_store() -> LibraryStore:
    global _library_singleton
    if _library_singleton is None:
        _library_singleton = LibraryStore()
    return _library_singleton
