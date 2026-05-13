from __future__ import annotations

import re
from html.parser import HTMLParser


def soft_wrap_long_tokens(text: str, max_token: int = 40) -> str:
    """Inserta saltos blandos (U+200B) en palabras larguísimas sin espacios para forzar ajuste en PDF/Word/HTML."""
    if not text or max_token < 8:
        return text

    def repl(m: re.Match[str]) -> str:
        chunk = m.group(0)
        if len(chunk) <= max_token:
            return chunk
        parts: list[str] = []
        for i in range(0, len(chunk), max_token):
            parts.append(chunk[i : i + max_token])
        return "\u200b".join(parts)

    return re.sub(r"\S{%d,}" % (max_token + 1), repl, text)


def plain_from_html(s: str) -> str:
    """Extrae texto legible de HTML simple (p, span, etc.)."""
    if not s:
        return ""
    if "<" not in s:
        return soft_wrap_long_tokens(s.strip())
    low = s.lower()
    if low.strip().startswith("<!") or "<html" in low:
        return soft_wrap_long_tokens(re.sub(r"<[^>]+>", " ", s).strip())

    class _TP(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []

        def handle_data(self, data: str) -> None:  # noqa: N802
            self.parts.append(data)

    p = _TP()
    try:
        p.feed(s)
    except Exception:  # noqa: BLE001
        return soft_wrap_long_tokens(re.sub(r"<[^>]+>", " ", s).strip())
    return soft_wrap_long_tokens("".join(p.parts).strip())
