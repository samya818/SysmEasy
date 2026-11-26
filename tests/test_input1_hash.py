# -*- coding: utf-8 -*-
"""
Test unitaire de vérification des hashes RFC 8785 (JCS) sur contenu uniquement (hash_scope = content_only).
"""
import json
import hashlib
import os
import jcs

def canonical_sha256(content: dict) -> str:
    return hashlib.sha256(jcs.canonicalize(content)).hexdigest()

def test_rover_v10_hash():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(base_dir, "examples", "rover_v1.0.input1.json")
    with open(p, "r", encoding="utf-8") as f:
        envelope = json.load(f)
    assert envelope["hash_scope"] == "content_only"
    actual_hash = canonical_sha256(envelope["content"])
    assert actual_hash == envelope["canonical_sha256"]
    assert actual_hash == "1c8d8832059300e063a676c9b8b9475fca923d1ccee7527ec368f051afc43871"
    print("PASS : Rover v1.0 JCS SHA-256 vérifié :", actual_hash)

def test_rover_v11_hash():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(base_dir, "examples", "rover_v1.1.input1.json")
    with open(p, "r", encoding="utf-8") as f:
        envelope = json.load(f)
    assert envelope["hash_scope"] == "content_only"
    actual_hash = canonical_sha256(envelope["content"])
    assert actual_hash == envelope["canonical_sha256"]
    assert actual_hash == "9157a8d34a07a958fd822f97b25254beeb1aaa69ac529792bbcf68cf557cb22c"
    assert envelope["content"]["parent_sha256"] == "1c8d8832059300e063a676c9b8b9475fca923d1ccee7527ec368f051afc43871"
    print("PASS : Rover v1.1 JCS SHA-256 et chaînage parent vérifiés :", actual_hash)

if __name__ == "__main__":
    test_rover_v10_hash()
    test_rover_v11_hash()
