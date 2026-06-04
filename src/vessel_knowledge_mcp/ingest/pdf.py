"""Extract per-page text with poppler's pdftotext (form-feed separated)."""
from __future__ import annotations

import subprocess


def page_texts(pdf_path: str) -> list[str]:
    """Return one text string per page. Requires `pdftotext` on PATH."""
    result = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        capture_output=True, text=True, check=True,
    )
    pages = result.stdout.split("\x0c")
    return [p for p in pages if p.strip()]
