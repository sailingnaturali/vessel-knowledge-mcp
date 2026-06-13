"""Extract per-page text with poppler's pdftotext (form-feed separated)."""
from __future__ import annotations

import subprocess


def page_texts(pdf_path: str) -> list[str]:
    """Return one text string per physical page (index 0 == PDF page 1).

    Blank pages stay in the list so callers can derive true PDF page numbers
    with enumerate(..., start=1). pdftotext terminates output with a form
    feed, so the final empty split artifact is dropped. Requires `pdftotext`
    on PATH.
    """
    result = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        capture_output=True, text=True, check=True,
    )
    pages = result.stdout.split("\x0c")
    if pages and pages[-1].strip() == "":
        pages.pop()
    return pages
