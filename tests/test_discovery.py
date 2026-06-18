from vessel_knowledge_mcp.discovery.n2k_sources import parse_devices, DiscoveredDevice


def test_parse_devices_extracts_n2k_identity():
    sources = {
        "defaults": {},
        "n2k-1": {
            "22": {"n2k": {"manufacturerCode": 358, "modelId": "ServoProp 25",
                           "modelSerialCode": "OV-25-00412", "canName": "abc"}},
            "16": {"label": "no n2k block here"},
        },
        "signalk-mock-vessel": {},
    }
    devs = parse_devices(sources)
    assert len(devs) == 1
    d = devs[0]
    assert isinstance(d, DiscoveredDevice)
    assert d.source_ref == "n2k-1.22"
    assert d.manufacturer_code == 358
    assert d.model == "ServoProp 25"
    assert d.serial == "OV-25-00412"


def test_parse_devices_string_manufacturer_code():
    sources = {"bus": {"3": {"n2k": {"manufacturerCode": "Victron Energy",
                                      "modelId": "Cerbo GX"}}}}
    d = parse_devices(sources)[0]
    assert d.manufacturer == "Victron Energy"
    assert d.manufacturer_code is None
