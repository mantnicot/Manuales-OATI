from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from app.domain.entities.manual import Block, Manual, ManualStatus
from app.domain.ports.repositories import ManualRepository

_DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "manuals.json"


def _serialize_manual(m: Manual) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "title": m.title,
        "code": m.code,
        "system_id": str(m.system_id) if m.system_id else None,
        "folder_id": str(m.folder_id) if m.folder_id else None,
        "status": m.status.value,
        "blocks": [{"id": b.id, "type": b.type, "order": b.order, "data": b.data} for b in m.blocks],
        "meta": m.meta,
        "current_version": m.current_version,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _deserialize_manual(d: dict[str, Any]) -> Manual:
    blocks = [
        Block(id=str(b["id"]), type=str(b["type"]), order=int(b["order"]), data=dict(b.get("data") or {}))
        for b in d.get("blocks") or []
    ]
    return Manual(
        id=UUID(str(d["id"])),
        title=str(d.get("title", "")),
        code=str(d.get("code", "")),
        system_id=UUID(str(d["system_id"])) if d.get("system_id") else None,
        folder_id=UUID(str(d["folder_id"])) if d.get("folder_id") else None,
        status=ManualStatus(str(d.get("status", "draft"))),
        blocks=blocks,
        meta=dict(d.get("meta") or {}),
        current_version=int(d.get("current_version") or 1),
        created_at=_parse_dt(d.get("created_at")),
        updated_at=_parse_dt(d.get("updated_at")),
    )


def _iter_manuals_from_raw(raw: dict[str, Any]) -> tuple[list[Manual], bool]:
    """Lee entradas del JSON; omite legacy Word. skipped_legacy_word=True si hubo que ignorar alguna."""
    skipped_legacy_word = False
    out: list[Manual] = []
    for item in raw.get("manuals") or []:
        try:
            meta = item.get("meta") or {}
            if str(meta.get("storage_kind") or "") == "word":
                skipped_legacy_word = True
                continue
            out.append(_deserialize_manual(item))
        except (KeyError, ValueError, TypeError):
            continue
    return out, skipped_legacy_word


class InMemoryManualRepository(ManualRepository):
    def __init__(self) -> None:
        self._store: dict[UUID, Manual] = {}
        self._hydrate_store_from_disk()

    def _read_raw_from_disk(self) -> dict[str, Any] | None:
        if not _DATA_FILE.is_file():
            return None
        try:
            return json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _manuals_from_disk(self) -> list[Manual]:
        raw = self._read_raw_from_disk()
        if not raw:
            return []
        manuals, _ = _iter_manuals_from_raw(raw)
        return manuals

    def _hydrate_store_from_disk(self) -> None:
        self._store.clear()
        raw = self._read_raw_from_disk()
        if not raw:
            return
        manuals, skipped_legacy_word = _iter_manuals_from_raw(raw)
        for m in manuals:
            self._store[m.id] = m
        if skipped_legacy_word:
            self._persist_to_disk()

    def _persist_to_disk(self) -> None:
        try:
            _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {"manuals": [_serialize_manual(m) for m in self._store.values()]}
            _DATA_FILE.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            raise RuntimeError(
                f"No se pudo escribir {_DATA_FILE}: {exc}. Compruebe permisos y que el archivo no esté abierto en otro programa."
            ) from exc

    async def get(self, manual_id: UUID) -> Manual | None:
        for m in self._manuals_from_disk():
            if m.id == manual_id:
                return copy.deepcopy(m)
        return None

    async def list(
        self,
        *,
        query: str | None,
        system_id: UUID | None,
        status: ManualStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Manual], int]:
        items = self._manuals_from_disk()
        if status:
            items = [m for m in items if m.status == status]
        else:
            items = [m for m in items if m.status != ManualStatus.ARCHIVED]
        if system_id:
            items = [m for m in items if m.system_id == system_id]
        if query:
            q = query.lower()
            items = [m for m in items if q in m.title.lower() or q in m.code.lower()]

        def _ts(m: Manual) -> datetime:
            return m.updated_at or m.created_at or datetime.min.replace(tzinfo=timezone.utc)

        items.sort(key=_ts, reverse=True)
        total = len(items)
        return [copy.deepcopy(m) for m in items[offset : offset + limit]], total

    async def save(self, manual: Manual) -> Manual:
        now = datetime.now(timezone.utc)
        if manual.created_at is None:
            manual.created_at = now
        manual.updated_at = now
        self._hydrate_store_from_disk()
        self._store[manual.id] = copy.deepcopy(manual)
        self._persist_to_disk()
        return copy.deepcopy(manual)

    async def soft_delete(self, manual_id: UUID) -> None:
        self._hydrate_store_from_disk()
        self._store.pop(manual_id, None)
        self._persist_to_disk()

    async def clear_folder_id(self, folder_id: UUID) -> None:
        self._hydrate_store_from_disk()
        for m in self._store.values():
            if m.folder_id == folder_id:
                m.folder_id = None
                self._touch_manual(m)
        self._persist_to_disk()

    async def clear_system_and_folders(self, system_id: UUID) -> None:
        self._hydrate_store_from_disk()
        for m in self._store.values():
            if m.system_id == system_id:
                m.system_id = None
                m.folder_id = None
                self._touch_manual(m)
        self._persist_to_disk()

    def _touch_manual(self, m: Manual) -> None:
        m.updated_at = datetime.now(timezone.utc)
