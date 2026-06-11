from vessel_knowledge_mcp.models import Equipment, Measurement, Zone
from vessel_knowledge_mcp.vault import Vault
from vessel_knowledge_mcp import tools


def _vault():
    eq = Equipment(
        equipment_id="bellmarine-ddw-10", manufacturer="Bellmarine", model="DDW-10",
        category="propulsion",
        measurements={"temperature": Measurement(
            signalk_key="temperature", units="K", display_units="degC",
            zones=[Zone(state="normal", lower=273.15, upper=353.15),
                   Zone(state="alarm", lower=368.15, message="over-temp")])},
        prose="Check raw-water flow and impeller if hot.",
    )
    return Vault(root=None, equipment=[eq])


_BINDINGS = {"propulsion.0.temperature":
             {"equipment_id": "bellmarine-ddw-10", "measurement": "temperature"}}


def test_explain_resolves_path_via_bindings():
    out = tools.explain_notification(_vault(), _BINDINGS, "propulsion.0.temperature",
                                     state="alarm", value=370.0)
    assert out["found"] is True
    assert out["equipment_id"] == "bellmarine-ddw-10"
    assert out["state"] == "alarm"
    assert out["message"] == "over-temp"
    assert "impeller" in out["prose"]


def test_explain_message_fallback_without_value():
    out = tools.explain_notification(_vault(), _BINDINGS, "propulsion.0.temperature",
                                     state="alarm")
    assert out["state"] == "alarm"
    assert out["message"] == "over-temp"


def test_explain_unbound_path():
    out = tools.explain_notification(_vault(), {}, "tanks.fuel.0.currentLevel", state="warn")
    assert out["found"] is False


def test_explain_strips_real_notifications_prefix():
    # SignalK fires notifications.<data-path>; bindings are keyed by the bare
    # data path. The real-world path must resolve, not silently miss.
    out = tools.explain_notification(_vault(), _BINDINGS,
                                     "notifications.propulsion.0.temperature",
                                     state="alarm", value=370.0)
    assert out["found"] is True
    assert out["equipment_id"] == "bellmarine-ddw-10"
    assert out["path"] == "notifications.propulsion.0.temperature"  # echo as given


def test_explain_surfaces_state_mismatch():
    # Fired state says normal but the value computes alarm — surface the
    # disagreement instead of silently trusting the recomputed state.
    out = tools.explain_notification(_vault(), _BINDINGS, "propulsion.0.temperature",
                                     state="normal", value=370.0)
    assert out["state"] == "alarm"
    assert out["state_mismatch"] is True

    agree = tools.explain_notification(_vault(), _BINDINGS, "propulsion.0.temperature",
                                       state="alarm", value=370.0)
    assert agree["state_mismatch"] is False
