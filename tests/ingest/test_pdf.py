from vessel_knowledge_mcp.ingest import pdf


def test_page_texts_splits_on_formfeed(monkeypatch):
    def fake_run(args, **kwargs):
        class R:
            stdout = "page one text\x0cpage two text\x0c"
            returncode = 0
        return R()
    monkeypatch.setattr(pdf.subprocess, "run", fake_run)
    pages = pdf.page_texts("whatever.pdf")
    assert pages == ["page one text", "page two text"]


def test_page_texts_preserves_blank_pages(monkeypatch):
    def fake_run(args, **kwargs):
        class R:
            stdout = "page one\x0c\x0cpage three\x0c"
            returncode = 0
        return R()
    monkeypatch.setattr(pdf.subprocess, "run", fake_run)
    pages = pdf.page_texts("whatever.pdf")
    assert pages == ["page one", "", "page three"]
