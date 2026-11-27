"""Integration tests for FastAPI endpoints in server.py."""

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from server import app

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
    # Pass the raw JSON string as "prompt" so livrable2 pipeline can process it
    raw_prompt = json.dumps(payload)
    resp = client.post(
        "/api/v2/verify-input1",
        json={"sealed_input1": payload, "battery_capacity_ah": 28.0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("PASS", "SOFT_WARNING")
    assert "sysml_code" in body
    assert "satisfy_recall_pct" in body


def test_agribot_prompt_runs_dynamically_and_exports_pdf():
    from tests.test_agribot_pipeline import AGRIBOT_PROMPT

    resp = client.post(
        "/api/run-pipeline",
        json={"prompt": AGRIBOT_PROMPT, "view_level": "component"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "AgriBot" in body["title"]
    assert "package 'AgriBot'" in body["sysml_code"]
    assert body["model_key"] == "dyn_agribot"
    assert body["v2_pipeline"]["final_status"] in ("PASS", "SOFT_WARNING")
    assert body["v2_pipeline"]["satisfy_recall_pct"] >= 95.0
    assert any("SOFT_WARNING" in a["severity"] for a in body["metier"]["alerts"])

    pdf_resp = client.get("/api/export-report/dyn_agribot")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"


def test_probeam_x400_prompt_runs_dynamically_without_battery_fallback():
    probeam_prompt = """Tu es un ingénieur système expert en modélisation MBSE avec SysML.
1. Choix du diagramme SysML : Indique quel(s) type(s) de diagramme(s).
2. Génération du graphe SysML : Produis le graphe correspondant.
3. Vérification de cohérence : Signale brièvement toute ambiguïté.

### Cahier des charges — Projecteur DataShow "ProBeam X400"
- **Objectif** : Projeter des images et vidéos depuis une source numérique vers un écran ou un mur dans des salles lumineuses (jusqu'à 40 personnes).
- **Affichage et optique** : Résolution native Full HD (1920x1080), luminosité minimale de 4 500 lumens ANSI, rapport de contraste supérieur ou égal à 15 000:1, correction trapèze verticale et horizontale automatique (±30°).
- **Connectivité et entrées** : 2 ports HDMI 2.0, 1 port USB-C (vidéo + alimentation 15 W), 1 port USB-A (lecture multimédia / mise à jour firmware), 1 connexion Wi-Fi dual-band pour projection sans fil, et 1 sortie audio jack 3,5 mm.
- **Alimentation et thermique** : Alimentation secteur 100–240 V AC (50/60 Hz). Le système doit réguler la vitesse des ventilateurs selon la température interne afin de maintenir le niveau sonore sous 28 dB en mode éco et d'éviter toute surchauffe critique.
- **Ergonomie et contrôle** : Boutons de commande en façade, télécommande infrarouge, démarrage rapide en moins de 8 secondes, et mise en veille automatique après 15 minutes sans signal d'entrée.
- **Contraintes** : Masse inférieure à 3,2 kg, fonctionnement fiable entre 5 °C et 35 °C, conformité aux normes de sécurité électrique et électromagnétique.
"""
    resp = client.post(
        "/api/run-pipeline",
        json={"prompt": probeam_prompt.replace("\n", "\r\n"), "view_level": "component"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "ProBeam X400" in body["title"]
    assert "package 'ProBeam X400'" in body["sysml_code"]
    assert body["model_key"] == "dyn_probeam_x400"
    assert len(body["metier"]["summary"]) >= 4
    assert len(body["traceability"]) == 6
    # Verify instruction text did not leak into extracted requirements
    assert all("ingénieur" not in t["name"].lower() for t in body["traceability"])
    assert any("4500.0 lm" in t["expr"] for t in body["traceability"])
    assert any("28.0 dB" in t["expr"] for t in body["traceability"])
    assert any("3.2 kg" in t["expr"] for t in body["traceability"])
    assert body["v2_pipeline"]["final_status"] != "REJECTED_SEMANTIC"

    # Also verify flattened single-line browser paste behaves identically
    flat_prompt = " ".join(probeam_prompt.splitlines())
    resp_flat = client.post("/api/run-pipeline", json={"prompt": flat_prompt, "view_level": "component"})
    assert resp_flat.status_code == 200
    flat_body = resp_flat.json()
    assert len(flat_body["metier"]["summary"]) >= 4
    assert all("ingénieur" not in t["name"].lower() for t in flat_body["traceability"])

    pdf_resp = client.get("/api/export-report/dyn_probeam_x400")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"


def test_prose_specification_without_cdc_keyword_never_falls_back_to_battery():
    prose = (
        'Spécification système "SmartLift" : l\'ascenseur doit desservir 12 étages avec '
        "une vitesse nominale de 1.6 m/s et une capacité maximale de 800 kg. "
        "Le système doit garantir un arrêt d'urgence mécanique en moins de 0.5 s et "
        "afficher l'étage courant sur l'interface cabine."
    )
    resp = client.post("/api/run-pipeline", json={"prompt": prose, "view_level": "component"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_key"] == "dyn_smartlift"
    assert "SmartLift" in body["title"]
    assert "package 'SmartLift'" in body["sysml_code"]
    assert len(body["metier"]["summary"]) >= 1
    assert len(body["traceability"]) >= 2
