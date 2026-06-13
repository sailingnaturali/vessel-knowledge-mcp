import pytest

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


def test_write_review_path_and_content(tmp_path):
    out = write_review(tmp_path, "oceanvolt-hpsp25", "SP25 User manual.pdf", "content")
    assert out == tmp_path / "reviews" / "oceanvolt-hpsp25--SP25 User manual.md"
    assert out.read_text() == "content"


def test_write_review_rejects_bad_slug(tmp_path):
    with pytest.raises(ValueError):
        write_review(tmp_path, "../evil", "m.pdf", "content")
