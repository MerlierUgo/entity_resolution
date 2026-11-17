"""Tests du moteur, étape 2 : Jaro-Winkler borné à seuil fixe 0,88 (engine/approche.py, provisoire)
et découpe calib / eval de dev. Lancer : python -m pytest tests

Les cas viennent du banc d'essai (challenges/cases.csv, partition dev), jamais des questions humaines.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import Catalogue, ResolveurApproche, SeuilFixe  # noqa: E402
from engine.approche import compatible, signature  # noqa: E402
from engine.evaluation import charger_cas, evaluer, sous_partition  # noqa: E402


@pytest.fixture(scope="module")
def cat():
    return Catalogue.charger()


@pytest.fixture(scope="module")
def r(cat):
    return ResolveurApproche(cat, SeuilFixe(0.88, 0.03))


def approche(res):
    return next((t for t in res.trace if t.get("regle") == "R-RES-03"), None)


# ── politiques de seuil

def test_seuil_fixe_valide():
    assert SeuilFixe().regle("ville") == (0.88, 0.03)
    with pytest.raises(ValueError):
        SeuilFixe(1.2, 0.03)
    with pytest.raises(ValueError):
        SeuilFixe(0.88, 0.5)








# ── résolution approchée

def test_faute_de_frappe_resolue(r):
    res = r.resoudre("500 HYBRuD")  # ER-03049
    assert res.statut == "resolved" and res.ids == ("veh:modele:fiat-500-hybrid",)
    assert res.etape == "approche" and approche(res)["score"] >= 0.88


def test_exact_avant_approche(r):
    res = r.resoudre("Liège")
    assert res.etape == "exact" and approche(res) is None


def test_jamais_sur_un_code(r):
    for code in ("MN-AMO-70514", "MN-ANO-70513", "2710.21"):
        res = r.resoudre(code)
        assert res.statut == "unknown", code
        assert approche(res) is None, code
    assert signature("500 hybrud") == ("500",)


def test_jamais_sous_quatre_caracteres(r):
    res = r.resoudre("abc")
    assert res.statut == "unknown" and "4 caractères" in res.trace[-1]["raison"]


def test_index_negatif_avant_approche(r):
    res = r.resoudre("Aalen")  # proche de « aarlen » (JW 0,956)
    assert res.statut == "unknown" and res.etape == "index_negatif" and approche(res) is None
    simule = r.resoudre("Aalen", index_negatif=False)
    assert approche(simule) is not None  # sans l'index négatif, l'approché s'en mêlerait


def test_garde_fou_mots_courts(r):
    for terme in ("St.-Jan", "Ste-Cécile"):  # donnaient « t jan » et « steil »
        res = r.resoudre(terme)
        assert res.statut == "unknown" and "garde-fou" in res.trace[-1]["raison"], terme
    assert compatible("woluwe st lambert", "woluwe st lambert")
    assert not compatible("st jan", "t jan") and not compatible("ste cecile", "steil")


def test_ecart_rend_ambigu(cat):
    res = ResolveurApproche(cat, SeuilFixe(0.88, 0.03)).resoudre("Alije")  # ER-03117
    assert res.statut == "ambiguous" and len(approche(res)["noms"]) >= 2
    serre = ResolveurApproche(cat, SeuilFixe(0.88, 0.0)).resoudre("Alije")
    assert len(approche(serre)["noms"]) < len(approche(res)["noms"])


def test_seuil_refuse(cat):
    res = ResolveurApproche(cat, SeuilFixe(0.999, 0.03)).resoudre("500 HYBRuD")
    assert res.statut == "unknown" and "sous le seuil" in res.trace[-1]["raison"]


def test_determinisme(r):
    assert r.resoudre("ARyURA SPIDER") == r.resoudre("ARyURA SPIDER")


# ── découpe calib / eval

def test_sous_partition():
    dev = charger_cas("dev")
    calib, ev = charger_cas("dev", "calib"), charger_cas("dev", "eval")
    assert len(calib) + len(ev) == len(dev)
    assert not {c["case_id"] for c in calib} & {c["case_id"] for c in ev}
    assert 0.68 < len(calib) / len(dev) < 0.72
    assert sous_partition("ER-00001") == sous_partition("ER-00001")
    with pytest.raises(ValueError):
        charger_cas("test", "calib")


# ── banc d'essai : SeuilFixe(0.88, 0.03) sur tout dev

def test_banc_dev_seuil_fixe(r):
    res = evaluer(r, charger_cas("dev"))
    total = res["comptes"]["TOTAL"]
    assert total.get("erreur_silencieuse", 0) == 0, [e for e in res["echecs"] if e["note"] == "erreur_silencieuse"][:5]
    assert total["correct"] / sum(total.values()) > 0.85
