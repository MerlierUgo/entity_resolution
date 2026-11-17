"""Tests de la calibration SGR des seuils fuzzy (engine/calibration.py, R-RES-10) et de la politique
SeuilsCalibres. Lancer : python -m pytest tests/test_calibration.py"""
import math
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import calibration as cal  # noqa: E402
from engine.approche import SeuilsCalibres  # noqa: E402
from engine.catalogue import Catalogue, read_csv  # noqa: E402

THETAS = cal.grille()
DP = cal.DELTA / len(THETAS)


# ── borne binomiale

def test_grille_par_defaut():
    assert len(THETAS) == 20 and THETAS[0] == 0.80 and THETAS[-1] == 0.99 and 0.88 in THETAS


@pytest.mark.parametrize("n", [500, 2000, 10000])
def test_borne_k0_connue(n):
    b = cal.borne_haute(0, n, DP)
    assert b == pytest.approx(1 - DP ** (1 / n), rel=1e-6)          # solution exacte pour k = 0
    assert b == pytest.approx(math.log(1 / DP) / n, rel=0.01)       # ≈ ln(1/δ')/n


@pytest.mark.parametrize("k, n", [(1, 100), (5, 2000), (30, 4000), (99, 100)])
def test_borne_resout_l_equation(k, n):
    b = cal.borne_haute(k, n, DP)
    assert k / n < b < 1
    assert cal.log_cdf_binomiale(k, n, b) == pytest.approx(math.log(DP), abs=1e-6)


def test_borne_sans_information():
    assert cal.borne_haute(0, 0, DP) == 1.0
    assert cal.borne_haute(7, 7, DP) == 1.0


def test_borne_croit_avec_k_et_decroit_avec_n():
    assert cal.borne_haute(1, 1000, DP) < cal.borne_haute(2, 1000, DP)
    assert cal.borne_haute(2, 2000, DP) < cal.borne_haute(2, 1000, DP)


# ── choix du seuil

def point(theta, n, k):
    return {"theta": theta, "n": n, "k": k, "borne": cal.borne_haute(k, n, DP), "risque_observe": k / n if n else None,
            "couverture": 0.5}


def test_plus_petit_theta_admissible():
    pts = [point(0.80, 3000, 40), point(0.81, 2800, 8), point(0.82, 2500, 0), point(0.83, 2400, 0), point(0.84, 100, 0)]
    assert pts[1]["borne"] > 0.005 >= pts[2]["borne"]
    c = cal.choisir(pts, 0.005)
    assert not c["desactive"] and c["seuil"] == 0.82 and c["n"] == 2500 and c["k"] == 0
    # non monotone : un θ admissible plus bas qu'un θ refusé est quand même retenu
    pts = [point(0.80, 3000, 40), point(0.81, 2500, 0), point(0.82, 2400, 9)]
    assert cal.choisir(pts, 0.005)["seuil"] == 0.81


def test_famille_desactivee_faute_de_cas():
    pts = cal.courbe([], THETAS, DP)
    assert all(p["n"] == 0 and p["borne"] == 1.0 for p in pts)
    c = cal.choisir(pts, 0.005)
    assert c["desactive"] and c["seuil"] is None and "meilleur_point" in c
    # 500 noms acceptés sans aucune perte ne suffisent pas pour r* = 0,5 % (il en faut ≈ ln(400)/0,005 ≈ 1 200)
    peu = [(0.95, True, False)] * 500
    c = cal.choisir(cal.courbe(peu, THETAS, DP), 0.005)
    assert c["desactive"] and c["meilleur_point"]["n"] == 500 and c["meilleur_point"]["k"] == 0


def test_courbe_compte_n_k_et_couverture():
    saisies = [(0.95, True, False)] * 10 + [(0.85, True, True)] * 2 + [(0.90, False, False)] * 3 + [(0.70, False, False)]
    pts = {p["theta"]: p for p in cal.courbe(saisies, THETAS, DP)}
    assert pts[0.80]["n"] == 12 and pts[0.80]["k"] == 2 and pts[0.80]["couverture"] == 12 / 16
    assert pts[0.86]["n"] == 10 and pts[0.86]["k"] == 0
    assert pts[0.96]["n"] == 0


def test_seuil_final_le_plus_strict():
    assert cal.plus_strict({"central": {"seuil": 0.85}, "pessimiste": {"seuil": 0.90}}) == 0.90
    assert cal.plus_strict({"central": {"seuil": 0.93}, "pessimiste": {"seuil": 0.90}}) == 0.93
    assert cal.plus_strict({"central": {"seuil": 0.85}, "pessimiste": {"seuil": None}}) is None


def test_perte_dangereuse():
    assert cal.perte("resolved", {"a"}, "resolved", {"b"})
    assert cal.perte("unknown", set(), "resolved", {"b"})
    assert not cal.perte("ambiguous", {"a", "b"}, "resolved", {"a"})       # trop confiant : pas une perte
    assert not cal.perte("resolved", {"a"}, "ambiguous", {"a", "b"})
    assert not cal.perte("unknown", set(), "unknown", set())


# ── déterminisme et politique du moteur

@pytest.fixture(scope="module")
def petite_calibration(tmp_path_factory):
    """Calibration sur les 400 premières saisies de chaque jeu de certification (comptes seulement)."""
    sys.path.insert(0, str(ROOT / "build"))
    import build_saisies as bs
    from engine.mesure_saisies import charger_catalogue_jeux
    d = tmp_path_factory.mktemp("calib")
    scen = {}
    for sc, chemin in cal.SCENARIOS.items():
        lignes = read_csv(chemin)[:400]
        p = d / chemin.name
        bs.write_csv(p, lignes, list(lignes[0]))
        scen[sc] = p
    familles = yaml.safe_load((ROOT / "spec" / "familles_fuzzy.yaml").read_text(encoding="utf-8"))["familles"]
    cat = charger_catalogue_jeux(Catalogue.charger(), bs.charger_retires())
    return cat, familles, scen, d


def test_deux_executions_meme_yaml(petite_calibration, monkeypatch):
    cat, familles, scen, d = petite_calibration
    monkeypatch.setattr(cal, "ROOT", d)
    textes = [cal.yaml_seuils(cal.calibrer(cat, familles, scen, 0.005, 0.05, THETAS), 0.005, 0.05, THETAS, "2026-01-01")
              for _ in range(2)]
    assert textes[0] == textes[1]
    y = yaml.safe_load(textes[0])
    assert set(y["familles"]) == set(familles) and y["parametres"]["grille"]["nombre"] == 20
    assert all(len(j["sha256"]) == 64 for j in y["jeux"].values())


def test_politique_par_famille(tmp_path):
    y = {"parametres": {"ecart": 0.03},
         "familles": {"geographie": {"seuil_final": 0.93}, "pieces": {"seuil_final": None}, "marques": {"seuil_final": 0.9},
                      "vehicules": {"seuil_final": None}, "clients": {"seuil_final": None},
                      "vocabulaire_metier": {"seuil_final": None}, "douane": {"seuil_final": None}}}
    p = tmp_path / "seuils.yaml"
    p.write_text(yaml.safe_dump(y), encoding="utf-8")
    pol = SeuilsCalibres.charger(p)
    assert pol.regle("commune", frozenset({"commune"})) == (0.93, 0.03)
    assert pol.regle("mixte", frozenset({"commune", "localite_postale"})) == (0.93, 0.03)   # même famille
    assert pol.regle("mixte", frozenset({"commune", "marque_vehicule"})) is None            # deux familles
    assert pol.regle("article", frozenset({"article"})) is None                               # désactivée
    assert pol.regle("inconnu", frozenset({"inconnu"})) is None                               # hors famille
