from vessel_knowledge_mcp.models import Equipment
from vessel_knowledge_mcp.ingest import writer


def _eq(eid="bellmarine-ddw-10"):
    return Equipment(equipment_id=eid, manufacturer="Bellmarine", model="DDW-10",
                     category="propulsion")


def test_write_card_creates_file_with_source_pdf(tmp_path):
    path = writer.write_card(tmp_path, _eq(), source_pdf="Bellmarine.pdf", page=42)
    assert path.exists()
    text = path.read_text()
    assert "equipment_id: bellmarine-ddw-10" in text
    assert "Bellmarine.pdf#page=42" in text


def test_covered_pages_reports_existing(tmp_path):
    writer.write_card(tmp_path, _eq(), source_pdf="Bellmarine.pdf", page=42)
    writer.write_card(tmp_path, _eq("victron-cerbo"), source_pdf="Bellmarine.pdf", page=7)
    assert writer.covered_pages(tmp_path, "Bellmarine.pdf") == {7, 42}


def test_covered_pages_empty_for_new_source(tmp_path):
    assert writer.covered_pages(tmp_path, "New.pdf") == set()
