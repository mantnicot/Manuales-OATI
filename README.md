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

El PDF maquetado (la misma apariencia que el HTML/CSS del editor) se obtiene sobre todo con **WeasyPrint** (Linux/Docker con sus dependencias instaladas).

En **Windows**, si WeasyPrint no está disponible, el backend usa **Playwright** apoyándose primero en **Chrome o Edge que ya estén instalados** (no descarga Chromium por CDN). Solo hace falta el paquete Python:

```bash
cd backend
pip install playwright
```

Solo necesitarías `python -m playwright install chromium` si quieres forzar el binario integrado (`PLAYWRIGHT_PDF_CHANNEL=chromium`), p. ej. en un servidor sin Chrome/Edge pero con red para descargar.

Variable opcional **`PLAYWRIGHT_PDF_CHANNEL`**: `chrome` | `msedge` | `chromium`.

Si Playwright también falla, el API puede generar un PDF plano con **ReportLab**. Las respuestas de `GET /api/v1/manuals/{id}/export.pdf` incluyen **`X-Manuales-Pdf-Styled: 1`** cuando lleva HTML/CSS maquetado, y **`0`** en modo simple.

## Repositorio

https://github.com/mantnicot/Manuales-OATI
