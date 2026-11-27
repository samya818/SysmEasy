"""Tests de non-régression formelle pour le cas IN-05 et le module physique strict."""

import pytest
from fastapi.testclient import TestClient

from server import app
from sysmeasy.elicitation.nl_parser import CDCUnreadableError, validate_cdc_payload
from sysmeasy.livrable2_pipeline import run_livrable2_pipeline


def test_in05_binary_pdf_stream_is_blocked():
    """Vérifie qu'un flux binaire brut est immédiatement bloqué sans inférence."""
    raw_binary = "%PDF-1.4 \x00\x01\x02\x03\x04 corrupt data stream"
    with pytest.raises(CDCUnreadableError) as exc_info:
        validate_cdc_payload(raw_binary)
    assert "IN-05 BLOQUÉ" in str(exc_info.value)


def test_in05_compressed_or_unreadable_file_placeholder_is_blocked():
    """Vérifie qu'un message d'échec d'extraction bloque le pipeline."""
    placeholder = "Erreur : document binaire ou compressé non extractible."
    with pytest.raises(CDCUnreadableError) as exc_info:
        validate_cdc_payload(placeholder)
    assert "IN-05 BLOQUÉ" in str(exc_info.value)


def test_in05_insufficient_content_is_blocked():
    """Vérifie qu'un texte de moins de 20 caractères alphabétiques est bloqué."""
    too_short = "Projet 123."
    with pytest.raises(CDCUnreadableError) as exc_info:
        validate_cdc_payload(too_short)
    assert "IN-05 BLOQUÉ" in str(exc_info.value)


def test_no_phantom_battery_calculated_for_pure_software():
    """Vérifie qu'aucun calcul d'autonomie fictif n'est inventé sans spécification explicite de batterie."""
    pure_software_spec = (
        '### Spécification Système "SysmEasyPlatform"\n'
        "- **Objectif** : Plateforme logicielle web d'ingénierie système SysML v2.\n"
        "- **Composants** : Serveur d'orchestration web + Moteur de validation ANTLR4.\n"
        "- **Exigences** : Temps de réponse <= 2.0 s, disponibilité >= 99.9 %.\n"
    )
    result = run_livrable2_pipeline(pure_software_spec)
    # L'autonomie doit être strictement None car aucune batterie n'a été déclarée
    assert result.autonomy_min is None, f"Autonomie fantôme détectée : {result.autonomy_min}"


def test_server_returns_422_on_in05_blocked_payload():
    """Vérifie que l'endpoint HTTP renvoie le code 422 (Unprocessable) au lieu de synthétiser un faux rapport."""
    client = TestClient(app)
    resp = client.post("/api/run-pipeline", json={
        "prompt": "%PDF-1.7 binaire brut sans texte extractible...",
        "attached_file_name": "corrupt.pdf",
        "attached_file_content": ""
    })
    assert resp.status_code == 422
    assert "IN-05 BLOQUÉ" in resp.json()["detail"]
