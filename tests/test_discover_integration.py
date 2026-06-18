import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[1]
SIGNALK = REPO.parent / "signalk-server"
HARNESS = REPO / "tests" / "harness"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _has_n2k_identity(sources: dict) -> bool:
    """True once any source carries an n2k identity block with a model/maker.

    Real canboatjs/n2k-signalk decodes `manufacturerCode` to a string name and
    surfaces `modelId` from the Product Information PGN — accept either marker."""
    for label in sources.values():
        if not isinstance(label, dict):
            continue
        for sub in label.values():
            if not isinstance(sub, dict):
                continue
            n2k = sub.get("n2k")
            if isinstance(n2k, dict) and (
                n2k.get("manufacturerCode") is not None or n2k.get("modelId")
            ):
                return True
    return False


@pytest.mark.integration
def test_discover_against_virtual_device(tmp_path):
    if not (SIGNALK / "bin" / "signalk-server").exists():
        pytest.skip("signalk-server repo not present alongside this repo")
    if not (REPO.parent / "vessel-knowledge-vault").exists():
        pytest.skip("vessel-knowledge-vault not present alongside this repo")

    port = _free_port()
    emitter = HARNESS / "virtual_n2k_device.js"
    node_modules = SIGNALK / "node_modules"
    settings = {
        "interfaces": {},
        "pipedProviders": [{
            "id": "virtual-n2k", "enabled": True,
            # The canonical Actisense pipeline: execute emits a raw byte
            # stream, so a `liner` is required to split it into newline-
            # delimited Actisense sentences before canboatjs — without it
            # canboatjs takes its parseBuffer path and misreads the ASCII
            # timestamp as a binary frame (no device ever appears).
            "pipeElements": [
                {"type": "providers/execute",
                 "options": {"command": f"env NODE_PATH={node_modules} "
                                        f"node {emitter}"}},
                {"type": "providers/liner", "options": {}},
                {"type": "providers/canboatjs", "options": {}},
                {"type": "providers/n2k-signalk", "options": {}},
            ],
        }],
    }
    # A writable temp config dir so we never touch the real ~/.signalk.
    cfg_dir = tmp_path / "signalk-config"
    cfg_dir.mkdir()
    (cfg_dir / "settings.json").write_text(json.dumps(settings))

    env = {**os.environ,
           "SIGNALK_NODE_CONFIG_DIR": str(cfg_dir),
           "PORT": str(port),
           "NODE_PATH": str(node_modules)}

    proc = subprocess.Popen(
        ["node", str(SIGNALK / "bin" / "signalk-server"),
         "-s", "settings.json"],
        cwd=str(SIGNALK), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    # Drain stdout continuously so a chatty startup can't fill the pipe buffer
    # and block the server (which would turn a startup error into a 60s timeout
    # with no diagnostics).
    log_lines: list[str] = []
    threading.Thread(target=lambda: log_lines.extend(proc.stdout),
                     daemon=True).start()
    try:
        base = f"http://localhost:{port}"
        device_seen = False
        for _ in range(60):
            if proc.poll() is not None:
                raise AssertionError("signalk-server exited:\n" + "".join(log_lines))
            try:
                src = httpx.get(
                    f"{base}/signalk/v1/api/sources", timeout=2).json()
                if _has_n2k_identity(src):
                    device_seen = True
                    break
            except Exception:
                pass
            time.sleep(1)
        assert device_seen, ("virtual device never appeared in the sources tree\n"
                             + "".join(log_lines))

        declared = {"propulsion.port": {
            "equipment_id": "oceanvolt-hpsp25", "manufacturer": "Oceanvolt",
            "model": "HighPower ServoProp 25", "serial": None, "instance": "port",
            "category": "propulsion", "source": "declared",
            "paths": [{"path": "propulsion.port.temperature",
                       "measurement": "temperature"}]}}
        declared_path = tmp_path / "declared.json"
        declared_path.write_text(json.dumps(declared))
        served_path = tmp_path / "served.json"

        out = subprocess.run(
            ["uv", "run", "vessel-knowledge", "discover", "--signalk", base,
             "--vault", str(REPO.parent / "vessel-knowledge-vault"),
             "--declared", str(declared_path), "--out", str(served_path)],
            cwd=str(REPO), capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        served = json.loads(served_path.read_text())
        e = served["propulsion.port"]
        assert e["equipment_id"] == "oceanvolt-hpsp25"   # declared identity kept
        assert e["serial"], "expected the bus serial (modelSerialCode) to fill the null declared serial"
        assert "notifications" not in served               # fan-out still excluded
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
