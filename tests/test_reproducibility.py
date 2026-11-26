# -*- coding: utf-8 -*-
"""
Test de reproductibilité de bout en bout (Annexe B) utilisant la canonicalisation stricte RFC 8785 (jcs).
"""
import json
import hashlib
import os
import jcs

def test_reproducible_hash_chain():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f_v10 = os.path.join(base_dir, "examples", "rover_v1.0.input1.json")
    f_v11 = os.path.join(base_dir, "examples", "rover_v1.1.input1.json")
    
    with open(f_v10, "r", encoding="utf-8") as f:
        env_v10 = json.load(f)
    with open(f_v11, "r", encoding="utf-8") as f:
        env_v11 = json.load(f)
        
    h10 = hashlib.sha256(jcs.canonicalize(env_v10["content"])).hexdigest()
    h11 = hashlib.sha256(jcs.canonicalize(env_v11["content"])).hexdigest()
    
    assert h10 == env_v10["canonical_sha256"], "Reproductibilité RFC 8785 rompue sur v1.0"
    assert h11 == env_v11["canonical_sha256"], "Reproductibilité RFC 8785 rompue sur v1.1"
    assert env_v11["content"]["parent_sha256"] == h10, "Chaînage de provenance rompu entre v1.0 et v1.1"
    
    print("PASS : Reproductibilité déterministe RFC 8785 et chaînage v1.0 -> v1.1 validés avec succès.")

if __name__ == "__main__":
    test_reproducible_hash_chain()
