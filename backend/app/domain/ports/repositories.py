from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.domain.entities.manual import Manual, ManualStatus


class ManualRepository(Protocol):
    async def get(self, manual_id: UUID) -> Manual | None: ...

    async def list(
        self,
        *,
        query: str | None,
        system_id: UUID | None,
        status: ManualStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Manual], int]: ...

    async def save(self, manual: Manual) -> Manual: ...

    async def soft_delete(self, manual_id: UUID) -> None: ...

    async def clear_folder_id(self, folder_id: UUID) -> None: ...

    async def clear_system_and_folders(self, system_id: UUID) -> None: ...
