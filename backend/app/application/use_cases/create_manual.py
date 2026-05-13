from __future__ import annotations

import copy
from uuid import UUID

from app.domain.entities.manual import Manual, ManualStatus
from app.domain.ports.repositories import ManualRepository
from app.application.services.oati_template import default_oati_blocks


class CreateManual:
    def __init__(self, manuals: ManualRepository) -> None:
        self._manuals = manuals

    async def execute(
        self,
        *,
        title: str,
        code: str,
        use_official_template: bool = True,
        system_id: UUID | None = None,
        folder_id: UUID | None = None,
    ) -> Manual:
        manual = Manual.create_empty(
            title=title,
            code=code,
            template_id="oati-v1" if use_official_template else None,
        )
        manual.system_id = system_id
        manual.folder_id = folder_id
        if use_official_template:
            manual.blocks = default_oati_blocks()
            manual.meta["structure"] = [
                "portada",
                "tabla_contenido",
                "introduccion",
                "objetivo",
                "alcance",
                "responsables",
                "definiciones",
                "procedimiento",
            ]
        return await self._manuals.save(manual)


class DuplicateManual:
    def __init__(self, manuals: ManualRepository) -> None:
        self._manuals = manuals

    async def execute(self, *, source_id: UUID, new_code: str) -> Manual | None:
        src = await self._manuals.get(source_id)
        if src is None:
            return None
        clone = Manual.create_empty(title=f"{src.title} (copia)", code=new_code)
        clone.blocks = [copy.deepcopy(b) for b in src.blocks]
        clone.system_id = src.system_id
        clone.folder_id = src.folder_id
        clone.meta = dict(src.meta)
        clone.status = ManualStatus.DRAFT
        return await self._manuals.save(clone)
