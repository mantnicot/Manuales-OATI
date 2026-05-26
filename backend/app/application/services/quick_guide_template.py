"""Plantilla inicial para guías rápidas (document_kind=quick_guide)."""

from __future__ import annotations

import copy
from uuid import uuid4

from app.domain.entities.manual import Block


def default_quick_guide_blocks() -> list[Block]:
    def nid() -> str:
        return str(uuid4())

    page_glossary = Block(
        id=nid(),
        type="qg_page",
        order=0,
        data={
            "headerTitle": "GLOSARIO",
            "theme": "glossary",
            "columns": [
                {
                    "xPct": 2,
                    "yPct": 3,
                    "widthPct": 96,
                    "heightPct": 88,
                    "zIndex": 0,
                    "component": {
                        "kind": "glossary",
                        "entries": [
                            {
                                "term": "Vigencia",
                                "definition": "Periodo durante el cual una norma o documento está activo y válido.",
                            },
                            {
                                "term": "Credenciales",
                                "definition": "Datos que permiten identificar y autenticar al usuario en el sistema.",
                            },
                        ],
                    },
                },
            ],
        },
    )

    page_guide = Block(
        id=nid(),
        type="qg_page",
        order=1,
        data={
            "headerTitle": "GUÍA RÁPIDA — EJEMPLO",
            "theme": "guide",
            "columns": [
                {
                    "xPct": 3,
                    "yPct": 8,
                    "widthPct": 30,
                    "heightPct": 78,
                    "zIndex": 1,
                    "component": {
                        "kind": "step",
                        "title": "INGRESO AL SISTEMA",
                        "miniSteps": [
                            {
                                "text": "Abra el enlace institucional e inicie sesión con sus credenciales.",
                                "imageData": "",
                                "imageData2": "",
                            },
                        ],
                    },
                },
                {
                    "xPct": 35,
                    "yPct": 8,
                    "widthPct": 30,
                    "heightPct": 78,
                    "zIndex": 2,
                    "component": {
                        "kind": "step",
                        "title": "PRIMER USO",
                        "miniSteps": [
                            {
                                "text": "Revise el menú lateral y acceda al módulo indicado.",
                                "imageData": "",
                                "imageData2": "",
                            },
                        ],
                    },
                },
                {
                    "xPct": 68,
                    "yPct": 8,
                    "widthPct": 29,
                    "heightPct": 78,
                    "zIndex": 3,
                    "component": {
                        "kind": "comment",
                        "text": "Nota: ajuste títulos, columnas y componentes según su sistema.",
                        "imageData": "",
                    },
                },
            ],
        },
    )

    return [copy.deepcopy(page_glossary), copy.deepcopy(page_guide)]
