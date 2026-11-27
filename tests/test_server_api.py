"""Integration tests for FastAPI endpoints in server.py."""

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from server import app
from sysmeasy.orchestrator.audit_logger import AuditLogger

client = TestClient(app)


def _load_rover_v10() -> dict:
    root = Path(__file__).resolve().parent.parent
    return json.loads((root / "examples" / "rover_v1.0.input1.json").read_text(encoding="utf-8"))


def test_root_serves_existing_frontend():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


def test_legacy_run_pipeline_still_works():
    resp = client.post(
        "/api/run-pipeline",
        json={"prompt": "Système de batterie 24V pour rover", "view_level": "component"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert "sysml_code" in body
    assert "audit_report" in body


def test_v2_verify_input1_endpoint_passes_and_rejects_tampering():
    payload = _load_rover_v10()
    resp = client.post(
        "/api/v2/verify-input1",
        json={"sealed_input1": payload, "battery_capacity_ah": 28.0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "PASS"
    assert body["physics"]["total_power_w"] == 340.0
    assert AuditLogger.verify_trace(body["audit_trace"]) == body["audit_trace"]["trace_sha256"]

    tampered = copy.deepcopy(payload)
    tampered["content"]["components"][0]["mass_kg"] = 99.0
    resp_bad = client.post("/api/v2/verify-input1", json={"sealed_input1": tampered})
    assert resp_bad.status_code == 422
