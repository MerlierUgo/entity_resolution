"""Tests du moteur, étape 2 : Jaro-Winkler borné (engine/approche.py), calibration SGR
(engine/calibration.py) et découpe calib / eval de dev. Lancer : python -m pytest tests

Les cas viennent du banc d'essai (challenges/cases.csv, partition dev), jamais des questions humaines.
"""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import Catalogue, ResolveurApproche, SeuilFixe, SeuilsCalibres  # noqa: E402
from engine.approche import compatible, signature  # noqa: E402
from engine.calibration import borne_risque, calibrer, n_minimum, perte, sgr  # noqa: E402
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


def test_seuils_calibres_par_type(cat):
    pol = SeuilsCalibres(types={"modele_vehicule": None, "ville": (0.9, 0.03)})
    res = ResolveurApproche(cat, pol).resoudre("500 HYBRuD")
    assert res.statut == "unknown" and "désactivé pour le type modele_vehicule" in res.trace[-1]["raison"]
    assert pol.regle("type_jamais_calibre") is None  # prudence : un type inconnu n'est pas approché


def test_seuils_calibres_empreinte(cat, tmp_path):
    f = tmp_path / "seuils.yaml"
    f.write_text("empreinte_catalogue: autre\ntypes:\n  ville: {fuzzy: actif, seuil: 0.9, ecart: 0.03}\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="Recalibrer"):
        SeuilsCalibres.charger(cat, f)
    f.write_text(f"empreinte_catalogue: {cat.empreinte}\ntypes:\n  ville: {{fuzzy: peut-etre}}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="actif ou desactive"):
        SeuilsCalibres.charger(cat, f)


def test_seuils_du_depot_a_jour(cat):
    """spec/seuils_fuzzy.yaml doit correspondre au catalogue : sinon, recalibrer."""
    pol = SeuilsCalibres.charger(cat)
    assert pol.empreinte == cat.empreinte and pol.types


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


# ── SGR

def test_borne_binomiale():
    assert borne_risque(0, 100, 0.05) == pytest.approx(1 - 0.05 ** (1 / 100), abs=1e-9)
    assert borne_risque(2, 100, 0.05) > borne_risque(1, 100, 0.05) > borne_risque(0, 100, 0.05)
    assert borne_risque(5, 5, 0.05) == 1.0


def test_n_minimum():
    n = n_minimum(0.05, 0.05)
    k = math.ceil(math.log2(n))
    assert borne_risque(0, n, 0.05 / k) < 0.05 <= borne_risque(0, n - 1, 0.05 / math.ceil(math.log2(n - 1)))


def test_sgr():
    sains = [(0.80 + i / 1000, 0) for i in range(200)]
    ch = sgr(sains, 0.05, 0.05)
    assert ch is not None and ch.borne < 0.05 and ch.seuil < 0.85
    bruites = [(0.80 + i / 1000, int(i < 100)) for i in range(200)]  # les pertes sont sous 0,90
    ch = sgr(bruites, 0.05, 0.05)
    assert ch is None or ch.seuil >= 0.90
    assert sgr(sains[:20], 0.05, 0.05) is None


def test_calibrer_desactive_petit_type():
    pts = [{"type": "rare", "kappa": 0.95, "perte": 0, "retenu": True}] * 10
    pts += [{"type": "ville", "kappa": 0.80 + i / 2000, "perte": 0, "retenu": True} for i in range(400)]
    types = calibrer(pts, 0.05, 0.05, 0.03, "x")
    assert types["rare"]["fuzzy"] == "desactive" and "au moins" in types["rare"]["raison"]
    assert types["ville"]["fuzzy"] == "actif" and types["ville"]["empreinte_catalogue"] == "x"


def test_perte():
    cas = {"expected_ids": "a", "accepted": "unknown", "expected_status": "resolved"}
    assert perte(cas, "resolved", ("b",)) == 1                       # erreur silencieuse
    assert perte(cas, "ambiguous", ("a", "b")) == 0                  # demande, avec la bonne entité
    assert perte(cas, "ambiguous", ("a", "b"), "non_sure") == 1      # non accepté par le banc
    assert perte(cas, "ambiguous", ("b", "c")) == 1


# ── banc d'essai : SeuilFixe(0.88, 0.03) sur tout dev

def test_banc_dev_seuil_fixe(r):
    res = evaluer(r, charger_cas("dev"))
    total = res["comptes"]["TOTAL"]
    assert total.get("erreur_silencieuse", 0) == 0, [e for e in res["echecs"] if e["note"] == "erreur_silencieuse"][:5]
    assert total["correct"] / sum(total.values()) > 0.85
