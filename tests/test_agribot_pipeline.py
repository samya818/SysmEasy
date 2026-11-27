"""End-to-end test for the AgriBot specification prompt using the Livrable 2 pipeline."""

from sysmeasy.elicitation.nl_parser import is_structured_cdc
from sysmeasy.livrable2_pipeline import run_livrable2_pipeline

AGRIBOT_PROMPT = """
# SITUATION — Cahier des Charges : Robot Agricole Autonome "AgriBot"
Exigences contractuelles :
- REQ-01 : autonomie minimale continue de 4 heures.
- REQ-02 : masse totale en ordre de marche <= 80 kg (portage manuel à 2 opérateurs).
- REQ-03 : bus d'alimentation principal 48 V DC.
- REQ-04 : vitesse de travail 0,5 m/s.

Composants nominaux :
- Châssis + réservoir vide : 35,0 kg, 0 W.
- 4 moteurs de propulsion : 4 x 1,2 kg = 4,8 kg, 4 x 75 W = 300 W cumulés.
- Pompe de pulvérisation : 2,5 kg, 80 W.
- Calculateur Jetson Orin : 1,0 kg, 50 W.
- LiDAR + caméra : 0,8 kg, 20 W.
- Batterie LiFePO4 48 V / 30 Ah, profondeur de décharge max 85 % : 15,0 kg.
- Câblage + fixations : 4,0 kg.
"""


def test_agribot_cdc_parsing_and_physics_verdict():
    assert is_structured_cdc(AGRIBOT_PROMPT) is True
    result = run_livrable2_pipeline(AGRIBOT_PROMPT)

    assert result.project_name == "AgriBot"
    assert len(result.requirements) == 4
    assert len(result.components) == 7

    # Physics checks (consultative — never blocks)
    assert result.total_mass_kg == 63.1
    assert result.total_power_w == 450.0
    assert round(result.autonomy_min, 1) == 163.2  # 2.72 h < 4.0 h (240 min)
    assert len(result.soft_warnings) > 0  # autonomy warning emitted

    # SysML code correctness
    assert "package 'AgriBot'" in result.sysml_code

    # Satisfy recall >= 95%
    assert result.satisfy_recall_pct >= 95.0

    # eBOM generated
    assert len(result.ebom) == 7
    assert all("repere" in item for item in result.ebom)
