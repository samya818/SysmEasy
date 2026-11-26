# -*- coding: utf-8 -*-
"""
Test de conformité stricte à la norme RFC 8785 (JSON Canonicalization Scheme - JCS).
Vérifie les règles ECMAScript Number.prototype.toString vs json.dumps standard Python.
"""
import jcs

def test_rfc8785_number_serialization():
    # En Python standard, json.dumps(90.0) retourne "90.0" et json.dumps(1e-7) retourne "1e-07".
    # RFC 8785 (ES6) exige "90" et "1e-7".
    assert jcs.canonicalize({"val": 90.0}) == b'{"val":90}'
    assert jcs.canonicalize({"val": 1e-7}) == b'{"val":1e-7}'
    assert jcs.canonicalize({"val": 1e21}) == b'{"val":1e+21}'
    assert jcs.canonicalize({"b": [1, 2], "a": {"z": "test", "y": True}}) == b'{"a":{"y":true,"z":"test"},"b":[1,2]}'
    print("PASS : Conformité stricte RFC 8785 (JCS) validée sur vecteurs de test numériques et lexicographiques.")

if __name__ == "__main__":
    test_rfc8785_number_serialization()
