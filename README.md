# Manuales-OATI

Aplicación para crear, organizar y exportar manuales con plantilla OATI: **frontend** (Angular) y **API** (FastAPI).

## Estructura

- `frontend/` — Interfaz y editor
- `backend/` — API REST (`/api/v1`)
- `docs/` — Documentación de usuario y técnica
- `scripts/` — Utilidades (proxy, puerto API)

## Requisitos rápidos

- Node.js y npm (para el frontend)
- Python 3.11+ y `pip` (para el backend)

Detalles de arranque: ver `docs/MANUAL_TECNICO.txt` o `Iniciar-Manuales-OATI.bat`.

## PDF de guías rápidas (diseño y estilos)

El PDF maquetado (la misma apariencia que el HTML/CSS del editor) se obtiene con **WeasyPrint** cuando está instalado (típico en Linux/Docker con dependencias de sistema).

Si WeasyPrint falla (muy habitual en **Windows**):

1. La API intenta **Edge o Chrome del sistema** en modo headless con ``--print-to-pdf`` (**no** hace falta ``playwright install chromium`` ni una red que descargue navegadores).
2. Si eso no sirve, puede usarse **Playwright** (``pip install playwright``) con canales `chrome`/`msedge`/`chromium`.

Opcional: variable **`PLAYWRIGHT_PDF_CHANNEL`** = `chrome` | `msedge` | `chromium`.

Si todo lo anterior falla, el API genera un PDF **plano con ReportLab** (sin maquetación). Las respuestas de `GET /api/v1/manuals/{id}/export.pdf` llevan **`X-Manuales-Pdf-Styled: 1`** con HTML/CSS, y **`0`** en modo plano.

## Repositorio

https://github.com/mantnicot/Manuales-OATI
