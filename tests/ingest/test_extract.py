from vessel_knowledge_mcp.ingest.extract import EQUIPMENT_TOOL, extract_equipment


class _Block:
    type = "tool_use"
    name = "record_equipment"
    def __init__(self, data): self.input = data


class _Resp:
    def __init__(self, data): self.content = [_Block(data)]


class _Client:
    def __init__(self, data): self._data = data; self.messages = self
    def create(self, **kwargs): self.kwargs = kwargs; return _Resp(self._data)


def test_extract_builds_equipment_with_si_zones():
    data = {"is_equipment": True, "equipment_id": "bellmarine-ddw-10",
            "manufacturer": "Bellmarine", "model": "DDW-10", "category": "propulsion",
            "measurements": {"temperature": {"signalk_key": "temperature", "units": "K",
                "display_units": "degC",
                "zones": [{"state": "normal", "lower": 273.15, "upper": 353.15}]}},
            "prose": "motor"}
    client = _Client(data)
    eq = extract_equipment("page text", source="Bellmarine 2024", client=client)
    assert eq.equipment_id == "bellmarine-ddw-10"
    assert eq.measurements["temperature"].units == "K"
    # forced tool use
    assert client.kwargs["tool_choice"] == {"type": "tool", "name": "record_equipment"}


def test_extract_returns_none_when_not_equipment():
    eq = extract_equipment("toc page", source="x", client=_Client({"is_equipment": False}))
    assert eq is None


def test_tool_schema_requires_is_equipment():
    assert EQUIPMENT_TOOL["input_schema"]["required"] == ["is_equipment"]
