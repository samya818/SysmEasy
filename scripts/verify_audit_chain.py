# -*- coding: utf-8 -*-
"""
Vérificateur de la chaîne de hachage linéaire d'audit (scripts/verify_audit_chain.py).
Formule : sha256(prev_hash || step_order || agent || payload_summary)
"""
import json
import hashlib
import os

def verify_audit_chain(trace_path: str) -> bool:
    with open(trace_path, "r", encoding="utf-8") as f:
        trace = json.load(f)

    prev = "0" * 64
    for step in trace["steps"]:
        assert step["prev_hash"] == prev, f"Rupture de chaîne à l'étape {step['step_order']}"
        raw_str = f"{prev}||{step['step_order']}||{step['agent']}||{step['payload_summary']}"
        expected = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
        assert step["entry_hash"] == expected, f"Hash altéré à l'étape {step['step_order']}"
        prev = expected

    assert trace["trace_sha256"] == prev, "Le trace_sha256 final ne correspond pas à la dernière étape"
    print(f"PASS : Chaîne d'audit vérifiée ({len(trace['steps'])} étapes). trace_sha256 = {prev}")
    return True

if __name__ == "__main__":
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    verify_audit_chain(os.path.join(base, "examples", "rover_audit_trace.json"))
