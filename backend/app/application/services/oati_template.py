from __future__ import annotations

import copy
from uuid import uuid4

from app.domain.entities.manual import Block


def default_oati_blocks() -> list[Block]:
    """Plantilla OATI v2: 6 módulos fijos + 1 paso + 1 nota (arrastrables)."""

    def nid() -> str:
        return str(uuid4())

    blocks: list[Block] = []
    o = 0

    blocks.append(
        Block(
            id=nid(),
            type="oati_cover",
            order=o,
            data={
                "moduleHeaderLine": "MÓDULO — TÍTULO DEL DOCUMENTO",
                "macroProcess": "Macroproceso: Gestión de Recursos",
                "processLine": "Proceso: de Apoyo",
                "code": "",
                "version": "01",
                "approvalDate": "",
                "centralTitle": "TÍTULO CENTRAL DEL MANUAL",
                "institutionLine": "UNIVERSIDAD DISTRITAL FRANCISCO JOSÉ DE CALDAS",
                "unitFooterLine": "OFICINA ASESORA DE TECNOLOGÍAS E INFORMACIÓN",
                "logoUdUrl": "",
                "logoOatiUrl": "",
                "logoUdData": "",
                "logoOatiData": "",
                "crestUrl": "",
                "crestData": "",
                "crestScalePercent": 100,
            },
        )
    )
    o += 1

    sections = [
        ("oati_intro", "Texto de introducción."),
        ("oati_objective", "Describa el objetivo."),
        ("oati_scope", "Indique el alcance."),
        ("oati_responsible", "Responsables OATI y dependencias."),
        ("oati_definitions", "Definiciones y siglas."),
    ]
    for typ, txt in sections:
        blocks.append(
            Block(
                id=nid(),
                type=typ,
                order=o,
                data={
                    "text": txt,
                    "imageSrc": "",
                    "imageData": "",
                    "imageCaption": "",
                    "imageScalePercent": 100,
                },
            )
        )
        o += 1

    blocks.append(
        Block(
            id=nid(),
            type="oati_step",
            order=o,
            data={
                "title": "Ingreso al sistema",
                "description": "Abra el navegador e ingrese al sistema con sus credenciales institucionales.",
                "imageSrc": "",
                "imageData": "",
                "imageCaption": "",
                "imageScalePercent": 100,
            },
        )
    )
    o += 1
    blocks.append(
        Block(
            id=nid(),
            type="oati_note",
            order=o,
            data={"body": "Observaciones o advertencias al usuario."},
        )
    )
    return copy.deepcopy(blocks)
