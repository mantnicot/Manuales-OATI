from __future__ import annotations

import base64
import re
from urllib.parse import urljoin, urlparse


def normalize_media_url(src: str, base_url: str | None) -> str:
    """abs://, rutas relativas y //protocol-relative → URL absoluta para httpx."""
    s = (src or "").strip()
    if not s or s.startswith("data:"):
        return s
    if s.startswith("//"):
        return "https:" + s
    low = s.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return s
    if not base_url:
        return s
    base = base_url.rstrip("/") + "/"
    if s.startswith("/"):
        parsed = urlparse(base_url if "://" in base_url else base)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return urljoin(origin + "/", s.lstrip("/"))
    return urljoin(base, s)


def sniff_image_mime(data: bytes) -> str:
    """MIME mínimo por firmas de archivo (sin dependencias)."""
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 2 and data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if len(data) >= 6 and data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def src_to_data_url(src: str, base_url: str | None = None) -> str | None:
    """Devuelve data URL con bytes resueltos en servidor (misma lógica que PDF)."""
    s = (src or "").strip()
    if not s:
        return None
    raw = image_bytes_from_src(s, base_url)
    if not raw:
        return None
    mime = sniff_image_mime(raw)
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def image_bytes_from_src(src: str, base_url: str | None = None) -> bytes | None:
    """Descarga HTTP(S) o decodifica data URL image/*;base64."""
    original = (src or "").strip()
    if not original:
        return None
    if original.startswith("data:"):
        m = re.match(r"data:image/[^;]+;base64,(.*)", original, re.DOTALL | re.IGNORECASE)
        if not m:
            return None
        b64 = re.sub(r"\s+", "", m.group(1))
        pad = (-len(b64)) % 4
        b64 += "=" * pad
        try:
            return base64.standard_b64decode(b64, validate=False)
        except Exception:
            try:
                return base64.urlsafe_b64decode(b64)
            except Exception:
                return None
    eff_base = base_url
    if eff_base is None:
        from app.config import get_settings  # noqa: PLC0415

        eff_base = get_settings().asset_origin.rstrip("/") + "/"
    s = normalize_media_url(original, eff_base)
    if s.lower().startswith("http://") or s.lower().startswith("https://"):
        try:
            import httpx  # noqa: PLC0415

            with httpx.Client(timeout=45.0, follow_redirects=True) as c:
                r = c.get(s)
                r.raise_for_status()
                return r.content
        except Exception:
            return None
    return None
