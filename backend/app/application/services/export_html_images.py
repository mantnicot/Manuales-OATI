"""Reemplaza imágenes data: URL en HTML por archivos temporales (p. ej. para HtmlToDocx)."""

from __future__ import annotations

import os
import tempfile

from bs4 import BeautifulSoup

from app.application.services.export_media import image_bytes_from_src


def materialize_data_images_in_html(html: str) -> tuple[str, list[str]]:
    """Devuelve HTML modificado y rutas temporales a borrar tras el uso."""
    soup = BeautifulSoup(html, "html.parser")
    temps: list[str] = []
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src.startswith("data:"):
            continue
        raw = image_bytes_from_src(src)
        if not raw:
            continue
        low = src.lower()
        if "png" in low[:40]:
            ext = "png"
        elif "gif" in low[:40]:
            ext = "gif"
        elif "webp" in low[:40]:
            ext = "webp"
        else:
            ext = "jpg"
        fd, path = tempfile.mkstemp(suffix=f".{ext}")
        try:
            os.write(fd, raw)
        finally:
            os.close(fd)
        temps.append(path)
        img["src"] = os.path.abspath(path)
    return str(soup), temps


def cleanup_temp_paths(paths: list[str]) -> None:
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass
