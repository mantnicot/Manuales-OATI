from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class ManualStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


@dataclass
class Block:
    id: str
    type: str
    order: int
    data: dict[str, Any]


@dataclass
class Manual:
    id: UUID
    title: str
    code: str
    system_id: UUID | None
    folder_id: UUID | None
    status: ManualStatus
    blocks: list[Block] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    current_version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @staticmethod
    def create_empty(*, title: str, code: str, template_id: str | None = None) -> Manual:
        meta: dict[str, Any] = {"template_id": template_id} if template_id else {}
        return Manual(
            id=uuid4(),
            title=title,
            code=code,
            system_id=None,
            folder_id=None,
            status=ManualStatus.DRAFT,
            blocks=[],
            meta=meta,
            current_version=1,
        )
