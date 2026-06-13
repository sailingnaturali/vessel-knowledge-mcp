# Deterministic Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Claude-API page extraction in `vessel-knowledge ingest` with a deterministic candidate-mining pipeline that writes a human-review file (closes issue #7).

**Architecture:** `pdftotext` already extracts page text deterministically (`ingest/pdf.py`). The new flow mines numeric spec candidates (value + unit token) from each page with regexes, converts to SignalK canonical SI units with fixed arithmetic, and writes a markdown review file with verbatim source lines and true PDF page numbers. A human promotes verified candidates into the (pre-existing, `--equipment-id`-named) card. No model anywhere in the data path; `ingest/extract.py`, `ingest/writer.py`, and the `anthropic` dependency are deleted.

**Tech Stack:** Python 3.11+, stdlib `re`/`dataclasses`, poppler `pdftotext`, pytest. No new dependencies.

**Repo:** `~/src/sailingnaturali/vessel-knowledge-mcp` (work on `main`; commit & push per machine policy).

---

### Task 1: True PDF page numbers from `page_texts`

`page_texts` currently drops blank pages (`[p for p in pages if p.strip()]`), so `enumerate(..., start=1)` in the caller misnumbers every page after the first blank one — provenance poison. Make it return one entry per physical page (only stripping the trailing empty artifact after the final form feed).

**Files:**
- Modify: `src/vessel_knowledge_mcp/ingest/pdf.py`
- Test: `tests/ingest/test_pdf.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/ingest/test_pdf.py` (keep existing tests; adapt any that asserted blank-page dropping — if one does, change its expectation to match the new contract):

```python
def test_page_texts_preserves_blank_pages(monkeypatch):
    import subprocess
    from vessel_knowledge_mcp.ingest import pdf

    def fake_run(cmd, capture_output, text, check):
        class R:
            stdout = "page one\x0c\x0cpage three\x0c"
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    pages = pdf.page_texts("whatever.pdf")
    assert len(pages) == 3
    assert pages[0] == "page one"
    assert pages[1] == ""
    assert pages[2] == "page three"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/ingest/test_pdf.py -v`
Expected: the new test FAILS (current code returns 2 pages and never an empty string).

- [ ] **Step 3: Implement**

Replace the body of `page_texts` in `src/vessel_knowledge_mcp/ingest/pdf.py`:

```python
def page_texts(pdf_path: str) -> list[str]:
    """Return one text string per physical page (index 0 == PDF page 1).

    Blank pages stay in the list so callers can derive true PDF page numbers
    with enumerate(..., start=1). pdftotext terminates output with a form
    feed, so the final empty split artifact is dropped.
    """
    result = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        capture_output=True, text=True, check=True,
    )
    pages = result.stdout.split("\x0c")
    if pages and pages[-1].strip() == "":
        pages.pop()
    return pages
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingest/test_pdf.py -v`
Expected: PASS (all tests in file).

- [ ] **Step 5: Commit**

```bash
git add src/vessel_knowledge_mcp/ingest/pdf.py tests/ingest/test_pdf.py
git commit -m "fix: page_texts preserves blank pages so page numbers are true PDF pages"
```

---

### Task 2: SI conversion table (`ingest/mine.py`, part 1)

**Files:**
- Create: `src/vessel_knowledge_mcp/ingest/mine.py`
- Test: `tests/ingest/test_mine.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/ingest/test_mine.py`:

```python
import pytest

from vessel_knowledge_mcp.ingest.mine import to_si


@pytest.mark.parametrize("value,unit,si_value,si_units", [
    (120, "degC", 393.15, "K"),
    (0.8, "bar", 80000.0, "Pa"),
    (11, "bar", 1100000.0, "Pa"),
    (25, "kW", 25000.0, "W"),
    (400, "W", 400.0, "W"),
    (48, "V", 48.0, "V"),
    (500, "A", 500.0, "A"),
    (3000, "rpm", 50.0, "Hz"),
    (100, "L/h", pytest.approx(2.7778e-5, rel=1e-3), "m3/s"),
    (30, "psi", pytest.approx(206842.7, rel=1e-4), "Pa"),
])
def test_to_si(value, unit, si_value, si_units):
    got_value, got_units = to_si(value, unit)
    assert got_value == si_value
    assert got_units == si_units


def test_to_si_unknown_unit_passes_through():
    assert to_si(5, "furlongs") == (None, None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingest/test_mine.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError` (mine.py doesn't exist).

- [ ] **Step 3: Implement**

Create `src/vessel_knowledge_mcp/ingest/mine.py`:

```python
"""Deterministic candidate mining: numeric spec values near unit tokens.

No model in the data path (issue #7). Mining finds *candidates*; a human
promotes verified values into the equipment card. SI conversions are fixed
arithmetic into SignalK canonical units (K, Pa, W, Hz, m3/s).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# unit key -> (kind, si_units, converter)
_CONVERSIONS: dict[str, tuple[str, str, "callable"]] = {
    "degC": ("temperature", "K", lambda v: round(v + 273.15, 4)),
    "bar":  ("pressure", "Pa", lambda v: v * 100_000.0),
    "kPa":  ("pressure", "Pa", lambda v: v * 1_000.0),
    "psi":  ("pressure", "Pa", lambda v: v * 6_894.757),
    "Pa":   ("pressure", "Pa", lambda v: v),
    "kW":   ("power", "W", lambda v: v * 1_000.0),
    "W":    ("power", "W", lambda v: v),
    "V":    ("voltage", "V", lambda v: v),
    "A":    ("current", "A", lambda v: v),
    "rpm":  ("rotation", "Hz", lambda v: v / 60.0),
    "L/h":  ("flow", "m3/s", lambda v: v * 0.001 / 3600.0),
}


def to_si(value: float, unit: str) -> tuple[float | None, str | None]:
    """Convert a value in a mined unit to SignalK canonical SI, or (None, None)."""
    entry = _CONVERSIONS.get(unit)
    if entry is None:
        return (None, None)
    _, si_units, conv = entry
    return (conv(value), si_units)


def kind_of(unit: str) -> str:
    entry = _CONVERSIONS.get(unit)
    return entry[0] if entry else "other"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingest/test_mine.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vessel_knowledge_mcp/ingest/mine.py tests/ingest/test_mine.py
git commit -m "feat: deterministic SI conversion table for ingest mining"
```

---

### Task 3: Candidate mining (`ingest/mine.py`, part 2)

Line-based regex mining. Real manual quirks this must handle (all seen in the SP25/Zen 100 manuals on 2026-06-12): European decimal commas ("0,8 bar"), ranges ("7-8 bar"), unit spellings ("120 celsius", "48 Vdc", "25 kW", "500 A", "400 Watt").

**Files:**
- Modify: `src/vessel_knowledge_mcp/ingest/mine.py`
- Test: `tests/ingest/test_mine.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ingest/test_mine.py`:

```python
from vessel_knowledge_mcp.ingest.mine import Candidate, mine_page, mine_pages


def _by_unit(cands, unit):
    return [c for c in cands if c.unit == unit]


def test_mine_page_temperature_spellings():
    text = (
        "warning if the motor temperature is higher than 120 celsius\n"
        "controller limit 110 °C in continuous use\n"
        "store above 5°C\n"
    )
    cands = mine_page(text, page_no=58)
    temps = _by_unit(cands, "degC")
    assert [c.value for c in temps] == [120.0, 110.0, 5.0]
    assert temps[0].si_value == 393.15
    assert temps[0].si_units == "K"
    assert temps[0].page == 58
    assert temps[0].line_no == 1
    assert "120 celsius" in temps[0].line


def test_mine_page_decimal_comma_and_range():
    text = (
        "stops if the pump pressure exceeds 11 bar or doesn't reach 0,8 bar\n"
        "check the working pressure of the unit is correct (7-8 bar)\n"
    )
    cands = mine_page(text, page_no=31)
    bars = _by_unit(cands, "bar")
    # line 1: two singles; line 2: one range candidate (not two singles)
    assert [(c.value, c.value_high) for c in bars] == [
        (11.0, None), (0.8, None), (7.0, 8.0)]
    rng = bars[2]
    assert rng.si_value == 700000.0
    assert rng.si_value_high == 800000.0


def test_mine_page_power_current_voltage():
    text = (
        "SP25 nominal power 25 kW and peak 30 kW\n"
        "current nominal 500 A peak 600 A on the 48 Vdc bus\n"
        "average electric consumption: 400 Watt\n"
    )
    cands = mine_page(text, page_no=12)
    assert [c.value for c in _by_unit(cands, "kW")] == [25.0, 30.0]
    assert [c.value for c in _by_unit(cands, "A")] == [500.0, 600.0]
    assert [c.value for c in _by_unit(cands, "V")] == [48.0]
    assert [c.value for c in _by_unit(cands, "W")] == [400.0]


def test_mine_page_ignores_unitless_and_page_numbers():
    text = "Table 5 error codes\n65\ncode 12 motor feedback error\n"
    assert mine_page(text, page_no=65) == []


def test_mine_pages_numbers_from_one():
    pages = ["", "limit 90 °C", ""]
    cands = mine_pages(pages)
    assert len(cands) == 1
    assert cands[0].page == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingest/test_mine.py -v`
Expected: new tests FAIL with ImportError (`Candidate`, `mine_page`, `mine_pages` undefined).

- [ ] **Step 3: Implement**

Append to `src/vessel_knowledge_mcp/ingest/mine.py`:

```python
@dataclass
class Candidate:
    page: int                 # true PDF page number (1-based)
    line_no: int              # 1-based within the page
    line: str                 # verbatim source line (stripped)
    value: float
    unit: str                 # normalized unit key from _CONVERSIONS
    kind: str
    value_high: float | None = None       # set for ranges like "7-8 bar"
    si_value: float | None = None
    si_value_high: float | None = None
    si_units: str | None = None


_NUM = r"\d+(?:[.,]\d+)?"

# Unit token regexes -> normalized unit key. Order matters: longer/more
# specific tokens first so "kW" isn't matched as "W" and "Vdc" not as "V".
_UNIT_TOKENS: list[tuple[str, str]] = [
    (r"(?:°\s*C|℃|deg\s*C|celsius)", "degC"),
    (r"kPa\b", "kPa"),
    (r"Pa\b", "Pa"),
    (r"bar\b", "bar"),
    (r"psi\b", "psi"),
    (r"kW\b", "kW"),
    (r"[Ww]att(?:s)?\b", "W"),
    (r"W\b", "W"),
    (r"V(?:dc|DC|ac|AC)?\b", "V"),
    (r"A\b", "A"),
    (r"rpm\b", "rpm"),
    (r"(?:L|[Ll]it\.?)\s*/\s*h(?:our)?\b", "L/h"),
]


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _patterns() -> list[tuple[re.Pattern, str, bool]]:
    """(compiled pattern, unit key, is_range) — ranges first per unit."""
    pats: list[tuple[re.Pattern, str, bool]] = []
    for token_re, unit in _UNIT_TOKENS:
        pats.append((re.compile(
            rf"(?<![\w.,])({_NUM})\s*[-–—]\s*({_NUM})\s*{token_re}"), unit, True))
        pats.append((re.compile(
            rf"(?<![\w.,])({_NUM})\s*{token_re}"), unit, False))
    return pats


_PATTERNS = _patterns()


def mine_page(text: str, page_no: int) -> list[Candidate]:
    out: list[Candidate] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        consumed: list[tuple[int, int]] = []
        found: list[tuple[int, Candidate]] = []
        for pattern, unit, is_range in _PATTERNS:
            for m in pattern.finditer(line):
                span = m.span()
                if any(span[0] < e and span[1] > s for s, e in consumed):
                    continue  # inside an already-matched (range) span
                consumed.append(span)
                value = _num(m.group(1))
                value_high = _num(m.group(2)) if is_range else None
                si_value, si_units = to_si(value, unit)
                si_high = to_si(value_high, unit)[0] if value_high is not None else None
                found.append((span[0], Candidate(
                    page=page_no, line_no=line_no, line=line,
                    value=value, value_high=value_high, unit=unit,
                    kind=kind_of(unit), si_value=si_value,
                    si_value_high=si_high, si_units=si_units)))
        out.extend(c for _, c in sorted(found, key=lambda t: t[0]))
    return out


def mine_pages(pages: list[str]) -> list[Candidate]:
    """Mine every page; page numbers are 1-based true PDF pages."""
    out: list[Candidate] = []
    for page_no, text in enumerate(pages, start=1):
        if text.strip():
            out.extend(mine_page(text, page_no))
    return out
```

- [ ] **Step 4: Run tests, iterate until green**

Run: `uv run pytest tests/ingest/test_mine.py -v`
Expected: PASS. Likely first-run failures to watch for: the bare-`A`/`V`/`W` tokens overmatching words (the `\b` boundary plus the leading `(?<![\w.,])` number guard prevents most; if a test fails on ordering, remember per-line candidates sort by match start offset).

- [ ] **Step 5: Run mining against the real manuals as a smoke test**

```bash
cd ~/src/sailingnaturali/vessel-knowledge-mcp
uv run python - <<'EOF'
from vessel_knowledge_mcp.ingest.pdf import page_texts
from vessel_knowledge_mcp.ingest.mine import mine_pages
pages = page_texts("/Users/clarkbw/src/sailingnaturali/vessel-knowledge-vault/manuals/SP25 User manual ENG Release v2r0a0_2025_06_26.pdf")
cands = mine_pages(pages)
print(len(cands), "candidates")
hits = [c for c in cands if c.page == 58 and c.unit == "degC"]
for c in hits: print(c.page, c.value, c.line[:70])
EOF
```

Expected: a few hundred candidates; page 58 includes 120 and 110 °C lines (the thresholds we verified by hand). If page 58 shows nothing, the page-number fidelity from Task 1 is broken — stop and fix.

- [ ] **Step 6: Commit**

```bash
git add src/vessel_knowledge_mcp/ingest/mine.py tests/ingest/test_mine.py
git commit -m "feat: deterministic candidate mining with verbatim line provenance"
```

---

### Task 4: Review file (`ingest/review.py`)

**Files:**
- Create: `src/vessel_knowledge_mcp/ingest/review.py`
- Test: `tests/ingest/test_review.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/ingest/test_review.py`:

```python
from pathlib import Path

from vessel_knowledge_mcp.ingest.mine import Candidate
from vessel_knowledge_mcp.ingest.review import render_review, write_review


def _cand(**kw):
    base = dict(page=58, line_no=3, line="warning at 120 celsius", value=120.0,
                unit="degC", kind="temperature", si_value=393.15, si_units="K")
    base.update(kw)
    return Candidate(**base)


def test_render_review_groups_by_page_with_provenance():
    cands = [
        _cand(),
        _cand(page=31, line_no=7, line="working pressure (7-8 bar)", value=7.0,
              value_high=8.0, unit="bar", kind="pressure",
              si_value=700000.0, si_value_high=800000.0, si_units="Pa"),
    ]
    md = render_review("oceanvolt-hpsp25", "SP25 User manual.pdf", cands)
    assert md.startswith("# Ingest review: oceanvolt-hpsp25")
    assert "SP25 User manual.pdf" in md
    # grouped by page, ascending
    assert md.index("## Page 31") < md.index("## Page 58")
    # verbatim line + conversion + checkbox
    assert "- [ ] **7–8 bar** (= 700000–800000 Pa, pressure)" in md
    assert "`working pressure (7-8 bar)` (line 7)" in md
    assert "- [ ] **120 degC** (= 393.15 K, temperature)" in md


def test_write_review_path_and_slug_guard(tmp_path):
    out = write_review(tmp_path, "oceanvolt-hpsp25", "SP25 User manual.pdf", "content")
    assert out == tmp_path / "reviews" / "oceanvolt-hpsp25--SP25 User manual.md"
    assert out.read_text() == "content"


def test_write_review_rejects_bad_slug(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        write_review(tmp_path, "../evil", "m.pdf", "content")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingest/test_review.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement**

Create `src/vessel_knowledge_mcp/ingest/review.py`:

```python
"""Render mined candidates into a human-review markdown file.

The review file is the hand-off point: a human verifies each candidate
against the manual page and promotes real limits into the equipment card's
zones (with source_page provenance), then deletes the review file.
"""
from __future__ import annotations

import re
from pathlib import Path

from vessel_knowledge_mcp.ingest.mine import Candidate

_SLUG_RE = re.compile(r"^[a-z0-9-]+$")


def _fmt_num(v: float) -> str:
    return f"{v:g}"


def _entry(c: Candidate) -> str:
    val = _fmt_num(c.value)
    if c.value_high is not None:
        val = f"{val}–{_fmt_num(c.value_high)}"
    si = ""
    if c.si_value is not None:
        si_val = _fmt_num(c.si_value)
        if c.si_value_high is not None:
            si_val = f"{si_val}–{_fmt_num(c.si_value_high)}"
        si = f" (= {si_val} {c.si_units}, {c.kind})"
    return f"- [ ] **{val} {c.unit}**{si} — `{c.line}` (line {c.line_no})"


def render_review(equipment_id: str, source_pdf: str,
                  candidates: list[Candidate]) -> str:
    lines = [
        f"# Ingest review: {equipment_id}",
        "",
        f"Source: `{source_pdf}` — {len(candidates)} candidates on "
        f"{len({c.page for c in candidates})} pages.",
        "",
        f"Verify each value against the manual page, promote the real limits into",
        f"`equipment/{equipment_id}.md` (zones in SI units, `source_page:` pointing at",
        "the PDF page), then delete this file. Values below are MINED CANDIDATES,",
        "not verified limits.",
    ]
    by_page: dict[int, list[Candidate]] = {}
    for c in candidates:
        by_page.setdefault(c.page, []).append(c)
    for page in sorted(by_page):
        lines += ["", f"## Page {page}", ""]
        lines += [_entry(c) for c in by_page[page]]
    return "\n".join(lines) + "\n"


def write_review(vault_root: Path, equipment_id: str, source_pdf: str,
                 content: str) -> Path:
    if not _SLUG_RE.match(equipment_id):
        raise ValueError(
            f"equipment_id {equipment_id!r} is not a valid slug (^[a-z0-9-]+$)")
    out_dir = Path(vault_root) / "reviews"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{equipment_id}--{Path(source_pdf).stem}.md"
    out.write_text(content, encoding="utf-8")
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingest/test_review.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vessel_knowledge_mcp/ingest/review.py tests/ingest/test_review.py
git commit -m "feat: review-file renderer for mined ingest candidates"
```

---

### Task 5: CLI rewrite — require `--equipment-id`, no model

**Files:**
- Modify: `src/vessel_knowledge_mcp/ingest/cli.py`
- Test: `tests/ingest/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ingest/test_cli.py`:

```python
import pytest


def test_ingest_requires_equipment_id(tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main(["ingest", "manual.pdf", "--vault", str(tmp_path)])
    assert exc.value.code == 2  # argparse usage error


def test_ingest_refuses_unknown_equipment_id(tmp_path, capsys):
    _seed_vault(tmp_path)
    rc = cli.main(["ingest", "manual.pdf", "--vault", str(tmp_path),
                   "--equipment-id", "does-not-exist"])
    assert rc == 1
    assert "create the equipment card first" in capsys.readouterr().err


def test_ingest_writes_review_file(tmp_path, capsys, monkeypatch):
    from vessel_knowledge_mcp.ingest import pdf
    _seed_vault(tmp_path)
    monkeypatch.setattr(pdf, "page_texts",
                        lambda p: ["", "motor limit 90 °C and 25 kW"])
    rc = cli.main(["ingest", "manual.pdf", "--vault", str(tmp_path),
                   "--equipment-id", "bellmarine-ddw-10"])
    assert rc == 0
    review = tmp_path / "reviews" / "bellmarine-ddw-10--manual.md"
    content = review.read_text()
    assert "## Page 2" in content
    assert "90 degC" in content and "363.15 K" in content
    assert "2 candidates" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingest/test_cli.py -v`
Expected: the three new tests FAIL (old CLI has no `--equipment-id` and calls anthropic).

- [ ] **Step 3: Implement**

In `src/vessel_knowledge_mcp/ingest/cli.py`, replace `_cmd_ingest` entirely:

```python
def _cmd_ingest(args) -> int:
    # Deterministic pipeline (issue #7): pdftotext -> regex mining -> review
    # file. No model in the data path; never mints new equipment IDs.
    from vessel_knowledge_mcp.ingest import pdf
    from vessel_knowledge_mcp.ingest.mine import mine_pages
    from vessel_knowledge_mcp.ingest.review import render_review, write_review

    vault_root = Path(args.vault)
    card = vault_root / "equipment" / f"{args.equipment_id}.md"
    if not card.is_file():
        print(f"no card at {card} — create the equipment card first; "
              "ingest mines review candidates for an existing card",
              file=sys.stderr)
        return 1
    pages = pdf.page_texts(args.pdf)
    candidates = mine_pages(pages)
    source_pdf = Path(args.pdf).name
    out = write_review(vault_root, args.equipment_id, source_pdf,
                       render_review(args.equipment_id, source_pdf, candidates))
    print(f"{len(candidates)} candidates on {len({c.page for c in candidates})} "
          f"pages -> {out}")
    return 0
```

And replace the `p_ingest` parser block in `main`:

```python
    p_ingest = sub.add_parser(
        "ingest",
        help="mine spec candidates from a manual PDF into a review file")
    p_ingest.add_argument("pdf")
    p_ingest.add_argument("--vault", required=True)
    p_ingest.add_argument("--equipment-id", required=True,
                          help="existing card the candidates are for "
                               "(ingest never creates new equipment IDs)")
    p_ingest.set_defaults(func=_cmd_ingest)
```

(`--source` and `--force` were LLM-era flags; they go away. `import json` and the rest of the file are untouched.)

Note for the monkeypatch in the test to work, `_cmd_ingest` must call `pdf.page_texts(...)` through the module (as written above), not `from ...pdf import page_texts`.

- [ ] **Step 4: Run the file's tests**

Run: `uv run pytest tests/ingest/test_cli.py -v`
Expected: PASS (including the pre-existing zones test).

- [ ] **Step 5: Commit**

```bash
git add src/vessel_knowledge_mcp/ingest/cli.py tests/ingest/test_cli.py
git commit -m "feat: ingest CLI requires --equipment-id, writes review file, no model"
```

---

### Task 6: Delete the LLM path; docs; version

**Files:**
- Delete: `src/vessel_knowledge_mcp/ingest/extract.py`, `tests/ingest/test_extract.py`,
  `src/vessel_knowledge_mcp/ingest/writer.py`, `tests/ingest/test_writer.py`
  (writer.py served only the LLM flow: card-minting + page-resume; grep first to confirm nothing else imports them)
- Modify: `pyproject.toml` (drop `[project.optional-dependencies] ingest`; bump version 0.3.0 → 0.4.0)
- Modify: `README.md` (CLI bullet + install + usage lines)

- [ ] **Step 1: Confirm nothing else imports the deleted modules**

Run: `grep -rn "ingest.writer\|ingest.extract\|from vessel_knowledge_mcp.ingest import" --include="*.py" src tests`
Expected: hits only in the files being deleted (and cli.py's new imports of pdf/mine/review).

- [ ] **Step 2: Delete and update**

```bash
git rm src/vessel_knowledge_mcp/ingest/extract.py tests/ingest/test_extract.py \
       src/vessel_knowledge_mcp/ingest/writer.py tests/ingest/test_writer.py
```

In `pyproject.toml`: delete the two lines

```toml
[project.optional-dependencies]
ingest = ["anthropic>=0.40.0"]
```

and change `version = "0.3.0"` → `version = "0.4.0"`.

In `README.md`:
- Line ~10 bullet: change to `- **Build-time CLI** (\`vessel-knowledge\`) — deterministically mines manual PDFs (pdftotext + regex, no LLM) into per-card review files, builds`
- Remove the `uv sync --extra ingest` line (~33).
- Replace the usage lines (~60–61) with:

```
    # Mine a manual PDF into a review file for an existing card (requires pdftotext)
    uv run vessel-knowledge ingest manual.pdf --vault /path/to/vault --equipment-id oceanvolt-hpsp25
```

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest -q`
Expected: all tests pass, none collected from deleted files.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat!: remove LLM extraction path from ingest (closes #7)

ingest is now deterministic end-to-end: pdftotext -> regex candidate
mining -> human review file. anthropic dependency dropped."
```

---

### Task 7: End-to-end run, push, close the issue

- [ ] **Step 1: Real-manual end-to-end**

```bash
cd ~/src/sailingnaturali/vessel-knowledge-mcp
uv run vessel-knowledge ingest \
  "/Users/clarkbw/src/sailingnaturali/vessel-knowledge-vault/manuals/MANUAL-ZEN100-12_24V-TRASD-ENG.pdf" \
  --vault ~/src/sailingnaturali/vessel-knowledge-vault \
  --equipment-id schenker-zen-100
```

Expected: `N candidates on M pages -> .../reviews/schenker-zen-100--MANUAL-ZEN100-12_24V-TRASD-ENG.md`. Spot-check the review file: page 14 should contain the 11 bar / 0,8 bar transducer lines; page 31 the 7–8 bar working range. These match the hand-verified card, proving the pipeline finds what a human found.

- [ ] **Step 2: Decide what to do with the generated review file**

The zen-100 card is already verified by hand, so delete the generated review file rather than committing it to the vault (it would imply unreviewed work):

```bash
rm ~/src/sailingnaturali/vessel-knowledge-vault/reviews/schenker-zen-100--*.md
rmdir ~/src/sailingnaturali/vessel-knowledge-vault/reviews 2>/dev/null || true
```

- [ ] **Step 3: Update the vault README usage line**

In `~/src/sailingnaturali/vessel-knowledge-vault/README.md`, replace the "Ingest a new manual" block with:

```
Mine a manual into a review file (deterministic — no LLM; see vessel-knowledge-mcp#7):

    VESSEL_KNOWLEDGE_VAULT_PATH=/path/to/this/repo \
      uv run vessel-knowledge ingest manual.pdf --vault /path/to/this/repo --equipment-id <id>

Then verify candidates in `reviews/<id>--<manual>.md` against the PDF, promote real
limits into the card's zones, and delete the review file.
```

Commit & push the vault repo.

- [ ] **Step 4: Push and close**

```bash
cd ~/src/sailingnaturali/vessel-knowledge-mcp && git push
gh issue close 7 --repo sailingnaturali/vessel-knowledge-mcp --comment \
  "Fixed in 0.4.0: ingest is deterministic end-to-end (pdftotext -> regex candidate mining -> human review file with verbatim line + true-page provenance). --equipment-id is required and must name an existing card; the anthropic dependency and LLM extraction path are removed. Verified against the SP25 + Zen 100 manuals: the miner surfaces the same thresholds we hand-verified (120/110 °C p.58; 0.8/11 bar p.14, 7-8 bar p.31)."
```

---

## Self-review notes

- **Spec coverage:** issue req 1 (deterministic extraction) → Tasks 1–3; req 2 (require `--equipment-id`, never mint IDs) → Task 5; req 3 (candidate mining + review file, human confirmation) → Tasks 3–4; req 4 (provenance: true page + verbatim line) → Tasks 1, 3, 4. Bonus: page-number bug fix (Task 1) is itself a provenance requirement.
- **Types:** `Candidate` fields used in review.py/test_review match Task 3's dataclass; `to_si`/`kind_of` defined in Task 2 are used in Task 3.
- **No placeholders:** every code step is complete; commands carry expected output.
