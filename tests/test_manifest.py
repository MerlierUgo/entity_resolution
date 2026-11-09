"""Tests du schéma du Manifest (build/manifest.py) et des réponses attendues. Lancer : python -m pytest tests"""
import copy
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build"))
import human_questions as hq  # noqa: E402
from manifest import canonical, load_manifest_refs, manifest_hash, validate_answer, validate_manifest  # noqa: E402

R = load_manifest_refs()
H012 = {
    "intent": "ranking",
    "champs": [
        {"role": "mesure", "ref": "M05"},
        {"role": "filtre", "dimension": "sous_famille", "valeurs": ["piece:cat:vp-1-4-10-3"]},
        {"role": "axe", "dimension": "marque"},
        {"role": "periode", "debut": "2026-01-01", "fin": "2026-09-30"},
    ],
    "tri": {"mesure": "M05", "ordre": "desc"},
    "limite": 1,
}


def mod(**changes):
    m = copy.deepcopy(H012)
    m.update(changes)
    return m


def test_exemple_valide():
    assert validate_manifest(H012, R) == []


def test_dates_yaml_non_citees_acceptees():
    m = yaml.safe_load("intent: aggregate\nchamps:\n  - {role: mesure, ref: M05}\n"
                       "  - {role: periode, debut: 2026-01-01, fin: 2026-09-30}\n")
    assert validate_manifest(m, R) == []
    assert canonical(m)["champs"][1]["debut"] == "2026-01-01"


@pytest.mark.parametrize("m,attendu", [
    (mod(intent="classement"), "intent"),
    (mod(champs=H012["champs"] + [{"role": "filtre", "dimension": "pays", "valeurs": ["geo:pays:XX"]}]), "absent du catalogue"),
    (mod(champs=H012["champs"] + [{"role": "filtre", "dimension": "pays", "valeurs": ["piece:marque:bosch"]}]), "type marque_piece"),
    (mod(champs=[{"role": "mesure", "ref": "M99"}] + H012["champs"][1:]), "mesure « M99 »"),
    (mod(champs=H012["champs"][:3]), "période est requise"),
    (mod(champs=H012["champs"] + [{"role": "periode", "photo": "2026-09-30"}]), "une seule période"),
    (mod(champs=H012["champs"][:3] + [{"role": "periode", "debut": "2026-09-30", "fin": "2026-01-01"}]), "postérieur"),
    (mod(champs=H012["champs"][:3] + [{"role": "periode", "debut": "2026-02-30", "fin": "2026-03-31"}]), "dates"),
    (mod(champs=H012["champs"] + [{"role": "filtre", "dimension": "sous_famille", "valeurs": ["piece:cat:vp-1-4-1-6"]}]), "filtrée deux fois"),
    (mod(champs=H012["champs"] + [{"role": "axe", "dimension": "planete"}]), "axe « planete »"),
    (mod(champs=H012["champs"] + [{"role": "mesure"}]), "clés"),
    (mod(champs=H012["champs"] + [{"role": "devise", "ref": "EUR"}]), "rôle « devise »"),
    (mod(tri={"mesure": "M09", "ordre": "desc"}), "parmi les champs mesure"),
    (mod(tri={"mesure": "M05", "ordre": "croissant"}), "ordre"),
    (mod(limite=0), "limite"),
    (mod(limite=None), "limite requis"),
    (mod(intent="aggregate"), "tri interdit"),
    (mod(question="Quelle marque ?"), "clés inconnues"),
])
def test_erreurs_detectees(m, attendu):
    errors = validate_manifest(m, R)
    assert any(attendu in e for e in errors), errors


def test_compare_exige_comparaison_ou_plusieurs_valeurs():
    base = {"intent": "compare", "champs": [{"role": "mesure", "ref": "M10"},
            {"role": "filtre", "dimension": "marque", "valeurs": ["piece:marque:bosch"]},
            {"role": "periode", "debut": "2026-01-01", "fin": "2026-09-30"}]}
    assert any("compare" in e for e in validate_manifest(base, R))
    base["champs"][1]["valeurs"].append("piece:marque:brembo")
    assert validate_manifest(base, R) == []


def test_seuil():
    m = {"intent": "list", "champs": [{"role": "mesure", "ref": "M17"}, {"role": "axe", "dimension": "client"},
         {"role": "periode", "debut": "2026-01-01", "fin": "2026-09-30"},
         {"role": "seuil", "mesure": "M17", "operateur": ">", "valeur": 200}]}
    assert validate_manifest(m, R) == []
    m["champs"][3]["operateur"] = "plus de"
    assert any("opérateur" in e for e in validate_manifest(m, R))


def test_hash_independant_de_l_ordre_et_des_dates():
    m2 = copy.deepcopy(H012)
    m2["champs"].reverse()
    m3 = yaml.safe_load(yaml.safe_dump(H012).replace("'2026-01-01'", "2026-01-01"))
    assert manifest_hash(H012) == manifest_hash(m2) == manifest_hash(m3)
    assert manifest_hash(H012) != manifest_hash(mod(limite=3))


def test_hash_valeurs_triees():
    a = {"intent": "compare", "champs": [{"role": "filtre", "dimension": "marque",
         "valeurs": ["piece:marque:brembo", "piece:marque:bosch"]}]}
    b = {"intent": "compare", "champs": [{"role": "filtre", "dimension": "marque",
         "valeurs": ["piece:marque:bosch", "piece:marque:brembo"]}]}
    assert manifest_hash(a) == manifest_hash(b)


@pytest.mark.parametrize("a,attendu", [
    ({"statut": "resolved", "manifest": H012}, None),
    ({"statut": "ambiguous", "ambiguites": [{"terme": "bruxelles",
      "candidats": ["geo:commune:BE-21004", "mecanova:site:agence-bruxelle"]}]}, None),
    ({"statut": "ambiguous", "ambiguites": [{"terme": "productif", "candidats": ["M05", "M14", "axe:pays"]}]}, None),
    ({"statut": "unknown", "inconnus": [{"terme": "durites", "raison": "absent_du_catalogue"}]}, None),
    ({"statut": "out_of_scope", "hors_perimetre": {"sujet": "conseil"}}, None),
    ({"statut": "peut-etre"}, "statut"),
    ({"statut": "resolved"}, "requise"),
    ({"statut": "unknown", "inconnus": [{"terme": "x", "raison": "bizarre"}]}, "raison"),
    ({"statut": "ambiguous", "ambiguites": [{"terme": "x", "candidats": ["geo:pays:BE"]}]}, "deux candidats"),
    ({"statut": "ambiguous", "ambiguites": [{"terme": "x", "candidats": ["geo:pays:BE", "geo:pays:XX"]}]}, "inconnu"),
    ({"statut": "unknown", "manifest": H012, "inconnus": [{"terme": "x", "raison": "index_negatif"}]}, "en trop"),
])
def test_reponses_attendues(a, attendu):
    errors = validate_answer(a, R)
    if attendu is None:
        assert errors == []
    else:
        assert any(attendu in e for e in errors), errors


def _convert(m):
    ch = [{"role": "mesure", "ref": x} for x in m.get("mesures", [])]
    ch += [{"role": "filtre", **f} for f in m.get("filtres", [])]
    ch += [{"role": "axe", "dimension": a} for a in m.get("axes", [])]
    for k in ("periode", "comparaison", "seuil"):
        if m.get(k):
            ch.append({"role": k, **m[k]})
    return {"intent": m["intent"], "champs": ch, **{k: m[k] for k in ("tri", "limite") if k in m}}


def test_manifests_de_la_spec_valides():
    """Les Manifest de spec/questions.yaml, convertis au format v0.1, passent le schéma (hors « cible », à trancher)."""
    qs = yaml.safe_load((ROOT / "spec" / "questions.yaml").read_text(encoding="utf-8"))["questions"]
    n = 0
    for q in qs:
        m = q.get("manifest_attendu")
        if not m or m.get("intent") == "out_of_scope" or "cible" in m:
            continue
        assert validate_manifest(_convert(m), R) == [], q["id"]
        n += 1
    assert n >= 25


def test_attendus_doublon_refuse(tmp_path):
    f = tmp_path / "a.yaml"
    f.write_text("H-001:\nH-001:\n", encoding="utf-8")
    with pytest.raises(hq.FormatError, match="double"):
        hq.read_attendus(f)


def test_attendus_ecarts_avec_proposition():
    rows = [{"id": "H-001", "etat": "active", "statut_attendu": "unknown", "entites_attendues": "", "mesure": ""}]
    att = {"H-001": {"statut": "out_of_scope", "hors_perimetre": {"sujet": "conseil"}}}
    errors, _, ecarts, written = hq.check_attendus(rows, att, R)
    assert errors == [] and written == 1 and any("statut out_of_scope" in x for x in ecarts)


def test_attendus_identifiant_inconnu():
    rows = [{"id": "H-001", "etat": "active", "statut_attendu": "", "entites_attendues": "", "mesure": ""}]
    errors, *_ = hq.check_attendus(rows, {"H-999": None}, R)
    assert any("H-999" in e for e in errors)


def test_vues_lisibles_a_jour():
    """Les .md générés correspondent à leurs sources YAML."""
    from build_docs import stale
    assert stale() == []


# def test_mesures_yaml_source_unique():
#     mes = yaml.safe_load((ROOT / "spec" / "mesures.yaml").read_text(encoding="utf-8"))["mesures"]
#     g = yaml.safe_load((ROOT / "spec" / "glossaire.yaml").read_text(encoding="utf-8"))
#     assert "mesures" not in g
#     assert len(mes) == 26 and {m["id"] for m in mes} == R.mesures
#     assert all(m["alias"] and m["unite"] and m["additivite"] for m in mes)
