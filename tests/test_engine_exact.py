"""Tests du moteur, étape 1 : résolveur exact (engine/). Lancer : python -m pytest tests

Les cas viennent du banc d'essai (challenges/cases.csv, partition dev), jamais des questions humaines.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import Catalogue, ResolveurExact  # noqa: E402
from engine.catalogue import cle_triee, normalize  # noqa: E402
from engine.evaluation import charger_cas, evaluer, noter, taux  # noqa: E402

LIEGE = {"geo:arrondissement:be-liege", "geo:commune:BE-62063", "geo:province:BE-WLG",
         "mecanova:site:agence-liege"}


@pytest.fixture(scope="module")
def cat():
    return Catalogue.charger()


@pytest.fixture(scope="module")
def r(cat):
    return ResolveurExact(cat)


def regles(res):
    return [(t["regle"], t["action"], t["id"]) for t in res.trace if t["etape"] == "regle"]


# ── normalisation : la même que le catalogue (R-RES-02)

def test_normalisation_partagee(cat):
    assert cat.normaliser("Liège") == normalize("Liège") == "liege"


def test_cle_triee():
    assert cle_triee("garage dupont") == cle_triee("dupont garage") == "dupont garage"


def test_terme_vide(r):
    res = r.resoudre("la")
    assert (res.statut, res.ids, res.etape) == ("unknown", (), "vide")


# ── pièges connus

def test_liege_quatre_candidats(r):
    res = r.resoudre("Liège")
    assert res.statut == "ambiguous" and set(res.ids) == LIEGE
    assert ("R-CTX-05", "ajoute", "mecanova:site:agence-liege") in regles(res)
    assert ("R-GEO-02", "retire", "geo:localite:BE-4000-liege") in regles(res)
    assert ("R-GEO-02", "retire", "geo:localite:BE-4020-liege") in regles(res)


@pytest.mark.parametrize("hint,attendu", [
    ("commune", ("geo:commune:BE-62063",)),
    ("province", ("geo:province:BE-WLG",)),
    ("localite_postale", ("geo:localite:BE-4000-liege", "geo:localite:BE-4020-liege")),
])
def test_liege_indice_de_type(r, hint, attendu):
    res = r.resoudre("Liège", hint)
    assert res.ids == attendu
    assert any(t[0] == "R-RES-09" for t in regles(res))


@pytest.mark.parametrize("texte,hint,statut,ids", [
    ("Champion", None, "ambiguous", ("geo:localite:BE-5020-champion", "piece:marque:champion")),
    ("Champion", "marque_piece", "resolved", ("piece:marque:champion",)),
    ("Champion", "localite_postale", "resolved", ("geo:localite:BE-5020-champion",)),
    ("en ligne", None, "ambiguous", ("geo:localite:BE-7812-ligne", "metier:groupe_canal:digital")),
    ("appel", None, "ambiguous", ("geo:localite:BE-9200-appel", "metier:groupe_canal:telephone")),
    ("SERES", None, "ambiguous", ("geo:commune:BE-62096", "veh:marque:seres")),
    ("Tivoli", None, "ambiguous", ("geo:ville:NL-2746282", "veh:modele:kg-mobility-tivoli",
                                   "veh:modele:ssangyong-tivoli")),
])
def test_collisions_entre_domaines(r, texte, hint, statut, ids):
    res = r.resoudre(texte, hint)
    assert (res.statut, res.ids) == (statut, ids)


def test_indice_sans_candidat_du_type_ignore(r):
    res = r.resoudre("Champion", "province")
    assert res.statut == "ambiguous"
    assert any(t["etape"] == "indice_type" for t in res.trace)


def test_code_voisin_jamais_approche(r):
    assert r.resoudre("mn-amo-70513").ids == ("mecanova:article:MN-AMO-70513",)
    res = r.resoudre("MN-AMO-70514")
    assert (res.statut, res.ids, res.etape) == ("unknown", (), "absent")


# ── index négatif (R-RES-07)

@pytest.mark.parametrize("texte,ressemble", [("Aalen", "lieu"), ("Allemagne", "pays"), ("Michelin", "marque")])
def test_index_negatif(r, texte, ressemble):
    res = r.resoudre(texte)
    assert (res.statut, res.etape) == ("unknown", "index_negatif")
    neg = next(t for t in res.trace if t["etape"] == "index_negatif")
    assert neg["regle"] == "R-RES-07" and neg["ressemble_a"] == ressemble


def test_catalogue_avant_index_negatif(r):
    """Une valeur du catalogue l'emporte toujours sur l'index négatif (gamme Éco)."""
    res = r.resoudre("Éco")
    assert res.ids == ("mecanova:gamme:eco",) and res.etape == "exact"


def test_index_negatif_disjoint_du_catalogue(cat):
    """Si un terme négatif était aussi un alias, l'exact le masquerait : la parade serait inopérante."""
    assert not set(cat.negatifs) & set(cat.index)


# ── mots triés (R-RES-02, point 6)

def test_mots_tries(r, cat):
    cle, ids = next((k, v) for k, v in sorted(cat.index.items()) if len(k.split()) == 2 and len(v) == 1
                    and " ".join(reversed(k.split())) not in cat.index)
    res = r.resoudre(" ".join(reversed(cle.split())))
    assert res.etape == "mots_tries" and res.statut != "unknown"
    assert any(t["etape"] == "mots_tries" for t in res.trace)


# ── déterminisme, trace, tiers

def test_deterministe(r):
    a, b = r.resoudre("Liège"), r.resoudre("Liège")
    assert a == b and list(a.ids) == sorted(a.ids)


def test_trace_complete(r):
    res = r.resoudre("Liège")
    etapes = [t["etape"] for t in res.trace]
    assert etapes[0] == "normalisation" and etapes[-1] == "statut"
    assert sum(1 for t in res.trace if t.get("decisive")) == 1


def test_tier_inconnu_refuse():
    with pytest.raises(ValueError, match="Tier inconnu"):
        Catalogue.charger(tiers={"4"})


# ── notation (même sémantique que build/baseline.py)

def _cas(statut, ids="", acc=""):
    return {"expected_status": statut, "expected_ids": ids, "accepted": acc}


@pytest.mark.parametrize("cas,statut,ids,note", [
    (_cas("resolved", "a"), "resolved", ["a"], "correct"),
    (_cas("resolved", "a"), "resolved", ["b"], "erreur_silencieuse"),
    (_cas("unknown"), "resolved", ["b"], "erreur_silencieuse"),
    (_cas("ambiguous", "a|b"), "resolved", ["a"], "trop_confiant"),
    (_cas("ambiguous", "a|b"), "resolved", ["c"], "erreur_silencieuse"),
    (_cas("ambiguous", "a|b"), "ambiguous", ["a", "c"], "partiel"),
    (_cas("resolved", "a", "unknown"), "unknown", [], "acceptable"),
    (_cas("resolved", "a"), "unknown", [], "incorrect"),
])
def test_noter(cas, statut, ids, note):
    assert noter(cas, statut, ids) == note


# ── banc d'essai, partition dev : objectif de l'étape 1

def test_banc_dev_zero_erreur_silencieuse(r):
    res = evaluer(r, charger_cas("dev"))
    n, ideal, sur, sil = taux(res["comptes"]["TOTAL"])
    assert n > 7000
    assert sil == 0, [e["case_id"] for e in res["echecs"] if e["note"] == "erreur_silencieuse"][:10]
    assert sur == 100.0
    assert ideal >= 66.0  # référence B0 : 66,0 % sur l'ensemble du banc
    assert res["comptes"]["C08_hors_perimetre_proche"] == {"correct": res["comptes"]["C08_hors_perimetre_proche"]["correct"]}
