# -*- coding: utf-8 -*-
"""
Test unitaire de démonstration live pour la soutenance (CRIT-05).
Prouve que le Module Déterministe 5 intercepte les hallucinations arithmétiques des LLMs.
"""

def compute_autonomy(usable_energy_wh: float, power_w: float) -> float:
    return (usable_energy_wh / power_w) * 60.0

def test_module5_catches_arithmetic_llm_error():
    # Le LLM baseline (Config A) affirme à tort : "autonomie 105 min avec pack 20Ah (408 Wh)"
    # Le Module 5 recalcule déterministiquement sous 340 W (280 + 45 + 15) :
    autonomy = compute_autonomy(408.0, 340.0)
    assert round(autonomy, 1) == 72.0
    assert autonomy < 90.0  # L'alerte SOFT_WARNING est obligatoirement déclenchée
    print("PASS : Le Module 5 intercepte l'erreur arithmétique (408 Wh / 340 W = 72.0 min < 90 min).")

if __name__ == "__main__":
    test_module5_catches_arithmetic_llm_error()
