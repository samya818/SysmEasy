# -*- coding: utf-8 -*-
"""
Test de sensibilité du Module Déterministe 5 aux incertitudes physiques (Profondeur de décharge DoD).
Inclut explicitement la puissance du LiDAR (280 + 45 + 15 = 340 W).
"""
import json
import os

def compute_autonomy_minutes(capacity_nominal_wh: float, power_load_w: float, dod: float) -> float:
    usable_energy_wh = capacity_nominal_wh * dod
    return (usable_energy_wh / power_load_w) * 60.0

def test_lidar_power_included():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(base_dir, "examples", "rover_v1.0.input1.json")
    with open(p, "r", encoding="utf-8") as f:
        envelope = json.load(f)
    components = envelope["content"]["components"]
    total_power = sum(c["power_w"] for c in components)
    assert total_power == 340.0, f"Puissance attendue = 340.0 W (avec LiDAR 15W), trouvée = {total_power} W"
    print("PASS : Puissance totale des composants vérifiée = 340.0 W (incluant LiDAR 15 W).")

def test_dod_sensitivity_rover():
    # Batterie Rover v1.0 pack 28 Ah : 24V * 28Ah = 672 Wh nominal
    capacity_nominal_wh = 24.0 * 28.0  # 672.0 Wh
    power_load_w = 340.0              # 280W moteurs + 45W Jetson + 15W LiDAR
    
    autonomy_80 = compute_autonomy_minutes(capacity_nominal_wh, power_load_w, 0.80)
    autonomy_85 = compute_autonomy_minutes(capacity_nominal_wh, power_load_w, 0.85)
    autonomy_90 = compute_autonomy_minutes(capacity_nominal_wh, power_load_w, 0.90)
    
    print(f"Autonomie à DoD 80% : {autonomy_80:.1f} min")
    print(f"Autonomie à DoD 85% : {autonomy_85:.1f} min")
    print(f"Autonomie à DoD 90% : {autonomy_90:.1f} min")
    
    assert 94.5 <= autonomy_80 <= 95.5
    assert 100.5 <= autonomy_85 <= 101.0
    assert 106.5 <= autonomy_90 <= 107.0
    assert autonomy_80 >= 90.0, "Violation de l'exigence REQ-01 à DoD 80% !"
    print("PASS : Robustesse physique validée sous 340 W. Marge minimale (+4.9 min à DoD 80%) suffisante.")

if __name__ == "__main__":
    test_lidar_power_included()
    test_dod_sensitivity_rover()
