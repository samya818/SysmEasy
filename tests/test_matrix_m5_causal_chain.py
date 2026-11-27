# -*- coding: utf-8 -*-
"""
Test unitaire de vérification de la chaîne causale pour la matrice M5 anti-fraude.
Valide le rejet du mutant MUT-17 (satisfy REQ-01 by Chassis avec attribut mass factice).
"""
import pytest

def verify_causal_chain(requirement_id: str, target: str, part: dict) -> bool:
    """
    Vérifie qu'un composant reliant une exigence expose toute la chaîne causale requise,
    et non un attribut scalaire isolé ou trompeur.
    """
    if target == "autonomy_minutes":
        # Chaîne causale requise pour l'autonomie énergétique :
        # Nécessite à la fois une capacité d'énergie (Wh) et une gestion de flux de puissance (W)
        attrs = {a["name"]: a.get("unit") for a in part.get("attributes", [])}
        ports = [p.get("domain") for p in part.get("ports", [])]
        has_energy = any("h" in str(u).lower() or "j" in str(u).lower() for u in attrs.values())
        has_power_port = "electrical" in ports
        return has_energy and has_power_port
    
    elif target == "mass_total_kg":
        # Une exigence de masse globale doit s'appliquer au système assemblé, pas à un bloc simple
        return part.get("is_assembly", False) or len(part.get("sub_parts", [])) > 0
    
    return True

def test_mutant_17_rejected():
    # MUT-17 : Le Châssis tente de satisfaire REQ-01 (autonomie) en exposant uniquement un attribut mass
    fraudulent_chassis = {
        "name": "ChassisStructure",
        "attributes": [
            {"name": "mass", "value": 8.50, "unit": "kg"}
        ],
        "ports": [],
        "is_assembly": False
    }
    
    is_valid = verify_causal_chain("REQ-01", "autonomy_minutes", fraudulent_chassis)
    assert not is_valid, "ÉCHEC : La matrice M5 aurait dû rejeter MUT-17 (châssis sans chaîne causale d'autonomie) !"
    print("PASS : Mutant MUT-17 formellement rejeté par vérification de la chaîne causale M5.")

def test_legitimate_power_subsystem_accepted():
    # Composant légitime couvrant toute la chaîne causale d'autonomie
    valid_power_subsystem = {
        "name": "PowerSubsystem",
        "attributes": [
            {"name": "capacity", "value": 571.2, "unit": "W*h"},
            {"name": "voltage", "value": 24.0, "unit": "V"}
        ],
        "ports": [
            {"name": "power_out", "direction": "out", "domain": "electrical", "unit": "V"}
        ],
        "is_assembly": False
    }
    
    is_valid = verify_causal_chain("REQ-01", "autonomy_minutes", valid_power_subsystem)
    assert is_valid, "ÉCHEC : Le sous-système de puissance légitime aurait dû être accepté !"
    print("PASS : Sous-système légitime validé par la chaîne causale M5.")

if __name__ == "__main__":
    test_mutant_17_rejected()
    test_legitimate_power_subsystem_accepted()
