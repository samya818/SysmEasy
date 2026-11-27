"""Tests for Motte-methodology LLM diagram selector and minimalist PDF renderer."""

import json
from pathlib import Path

from sysmeasy.contracts.llm_provider import LLMResponse
from sysmeasy.livrable2_pipeline import run_livrable2_pipeline
from sysmeasy.methodology import render_selected_diagrams, select_diagrams


class _MockDiagramLLM:
    def complete(self, system_prompt: str, user_prompt: str, *, temperature: float = 0.0) -> LLMResponse:
        assert "MagicGrid" in system_prompt
        assert "HarmonySE" in system_prompt
        return LLMResponse(
            content=json.dumps({
                "methodology": "HarmonySE",
                "diagrams": [
                    {"type": "context_bdd", "title": "Contexte", "comment": "Vue globale du système."},
                    {"type": "ibd", "title": "Architecture", "comment": "Flux entre composants."},
                    {"type": "stm", "title": "Modes", "comment": "États et transitions."},
                ],
            }),
            model="mock-llm",
        )


def test_llm_provider_decides_diagrams_using_motte_rules(tmp_path: Path):
    prompt = (
        '### Cahier des charges — "SmartValve"\n'
        "- Objectif : Réguler un débit hydraulique.\n"
        "- REQ-01 : pression max <= 10 bar.\n"
        "- Capteur pression : 0.5 kg, 5 W.\n"
        "- Actionneur vanne : 2.0 kg, 25 W.\n"
    )
    res = run_livrable2_pipeline(prompt)
    plan = select_diagrams(res, prompt, provider=_MockDiagramLLM())
    assert plan.methodology == "HarmonySE"
    assert [d.type for d in plan.diagrams] == ["context_bdd", "ibd", "stm"]

    rendered = render_selected_diagrams(res, plan, str(tmp_path), raw_prompt=prompt)
    assert len(rendered) == 3
    assert all(Path(d["img_path"]).is_file() for d in rendered)


def test_offline_fallback_chooses_relevant_views_without_modes_or_with_budgets(tmp_path: Path):
    from tests.test_agribot_pipeline import AGRIBOT_PROMPT

    res = run_livrable2_pipeline(AGRIBOT_PROMPT)
    plan = select_diagrams(res, AGRIBOT_PROMPT, provider=None)
    types = [d.type for d in plan.diagrams]
    assert 2 <= len(types) <= 4
    assert "context_bdd" in types
    assert "ibd" in types
    assert "par" in types  # AgriBot has mass + power + autonomy budgets


def test_agrowing_s2_excludes_editorial_sections_and_extracts_connections():
    agrowing = (
        '### Cahier des charges — Drone Agricole "AgroWing S2"\n'
        "- **Objectif** : Cartographier des parcelles agricoles par imagerie multispectrale.\n"
        "- **Propulsion et énergie** : Puissance maximale des moteurs en montée : 650 W, batterie LiPo 22,2 V / 10 000 mAh (222 Wh).\n"
        "- **Charge utile et capteurs** : Caméra multispectrale + LiDAR léger.\n"
        "- **Navigation et communication** : Contrôleur de vol + GNSS + télémétrie radio.\n"
        "- **Contraintes et environnement** : MTOW <= 2.8 kg, autonomie minimale de 35 minutes.\n"
    )
    res = run_livrable2_pipeline(agrowing)
    labels = [c["label"].lower() for c in res.components]
    assert not any("objectif" in l for l in labels)
    assert not any("contraintes" in l for l in labels)
    assert len(res.components) == 3
    assert len(res.connections) >= 2
    assert res.total_mass_kg == 2.8
    assert any("crête" in w for w in res.soft_warnings)
    assert any(r["unit"] == "kg" and r["numerical_val"] == 2.8 for r in res.requirements)


def test_plantuml_source_and_png_rendering(tmp_path):
    from sysmeasy.methodology.diagram_renderer import build_plantuml_source, render_plantuml_to_png

    prompt = (
        '### Cahier des charges — "SmartValve"\n'
        "- Objectif : Réguler un débit hydraulique.\n"
        "- REQ-01 : pression max <= 10 bar.\n"
        "- Capteur pression : 0.5 kg, 5 W.\n"
        "- Actionneur vanne : 2.0 kg, 25 W.\n"
    )
    res = run_livrable2_pipeline(prompt)
    for dtype in ("context_bdd", "ibd", "stm", "act", "par"):
        puml = build_plantuml_source(res, dtype, raw_prompt=prompt)
        assert puml.startswith("@startuml")
        assert puml.endswith("@enduml")

    out_png = tmp_path / "smartvalve_ibd.png"
    ibd_puml = build_plantuml_source(res, "ibd", raw_prompt=prompt)
    render_plantuml_to_png(ibd_puml, str(out_png))
    assert out_png.is_file()
    assert out_png.read_bytes().startswith(b"\x89PNG")



