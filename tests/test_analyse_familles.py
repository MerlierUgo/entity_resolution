"""Tests de l'analyse descriptive des familles (engine/analyse_familles.py) et de la section 8 du rapport
(engine/rapport_familles.py). Lancer : python -m pytest tests/test_analyse_familles.py"""
import json
import sys
from pathlib import Path

import pytest
from rapidfuzz.distance import JaroWinkler

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import analyse_familles as af  # noqa: E402
from engine import rapport_familles as rf  # noqa: E402
from engine.calibration import borne_haute  # noqa: E402


def test_quantile_et_resume():
    assert af.quantile([], 0.5) is None
    assert af.quantile([1, 2, 3, 4], 0.5) == 2.5
    assert af.quantile([1, 2, 3, 4], 0.25) == pytest.approx(1.75)
    r = af.resume([4, 1, 3, 2])
    assert r["n"] == 4 and r["mediane"] == 2.5 and r["min"] == 1 and r["max"] == 4 and r["moyenne"] == 2.5
    assert af.resume([]) == {"n": 0}


@pytest.mark.parametrize("l, t", [(1, "≤ 6"), (6, "≤ 6"), (7, "7–10"), (15, "11–15"), (16, "16–25"), (25, "16–25"),
                                  (26, "> 25")])
def test_tranches(l, t):
    assert af.tranche(l) == t


def test_issue():
    assert af.issue(0.95, 0.99, "approche", "resolved", 1) == "unknown_sous_seuil"
    assert af.issue(0.995, 0.99, "approche", "resolved", 1) == "resolved"
    assert af.issue(0.90, 0.80, "approche", "ambiguous", 3) == "ambiguous_voisins"
    assert af.issue(0.90, 0.80, "approche", "ambiguous", 1) == "ambiguous_homonymes"
    assert af.issue(0.90, 0.80, "absent", "unknown", 2) == "unknown_garde_fou"
    assert af.issue(0.90, 0.80, "approche", "unknown", 1) == "unknown_regles"


@pytest.mark.parametrize("longueur", [12, 19, 20, 30, 45])
def test_une_faute_et_palier_099(longueur):
    """Calcul de la section 8 : une omission en fin de nom donne JW = 1 − 0,2 / L (≥ 0,99 ⇔ L ≥ 20) ;
    une substitution en fin de nom, 1 − 0,4 / L (≥ 0,99 ⇔ L ≥ 40)."""
    nom = "abcdefghijklmnopqrstuvwxyz" * 2
    nom = nom[:longueur]
    omis = JaroWinkler.normalized_similarity(nom[:-1], nom)
    subst = JaroWinkler.normalized_similarity(nom[:-1] + "#", nom)
    assert omis == pytest.approx(1 - 0.2 / longueur, abs=1e-9)
    assert subst == pytest.approx(1 - 0.4 / longueur, abs=1e-9)
    assert (omis >= 0.99 - 1e-12) == (longueur >= 20)
    assert (subst >= 0.99 - 1e-12) == (longueur >= 40)


def donnees_factices():
    fam = ("clients", "geographie")
    boite = {"n": 10, "moyenne": 0.95, "p05": 0.85, "q1": 0.92, "mediane": 0.95, "q3": 0.97, "p95": 0.99,
             "min": 0.8, "max": 1.0}
    issues = {k: 5 for k in af.ISSUES}
    a = {"saisies_analyse": 100, "fautives_presentes": 80, "theta_moteur": 0.8, "paliers": list(af.PALIERS),
         "longueurs": {"par_famille": {f: {**boite, "mediane": 20 if f == "clients" else 8, "part_le_8": 0.1,
                                           "part_ge_20": 0.5} for f in fam}, "ecartes": {}},
         "scores": {f: {"fautives": 40, "avec_score": 30, "sans_score": {}, "score": boite,
                        "part_ge": {f"{p:.2f}": 0.1 for p in af.PALIERS}, "long_source": boite,
                        "issues": {"0.80": issues, "0.95": issues, "0.99": issues}} for f in fam},
         "une_faute": {"par_tranche": {t: {**boite, "part_ge_099": 0.0, "part_ge_095": 0.5} for *_, t in af.TRANCHES},
                       "sans_score": 3}}
    courbe = [{"theta": 0.97, "n": 5000, "k": 2}, {"theta": 0.99, "n": 100, "k": 0}]
    cal = {"parametres": {"r_etoile": 0.005, "delta": 0.05}, "familles": {"clients": 0.95, "geographie": None},
           "scenarios": {sc: {"familles": {f: {"courbe": courbe} for f in fam}} for sc in ("central", "pessimiste")}}
    return a, cal


def test_section_pourquoi_se_construit():
    a, cal = donnees_factices()
    h = rf.section_pourquoi(a, cal, borne_haute)
    assert 'id="pourquoi"' in h and h.count("<svg") == 4 and h.count("<li>") == 5
    assert "geographie ✕" in h and "clients ✕" not in h
    assert "borne sous r*" in h          # géographie : 2 pertes sur 5 000 à 0,97 → borne sous 0,5 %


def test_rapport_reel_si_present():
    """Si l'analyse a été lancée, la section se construit sur les vraies données."""
    chemin = ROOT / "reports" / "analyse_familles.json"
    cal = ROOT / "reports" / "calibration.json"
    if not (chemin.exists() and cal.exists()):
        pytest.skip("lancer python -m engine.analyse_familles et python -m engine.calibration")
    a = json.loads(chemin.read_text(encoding="utf-8"))
    h = rf.section_pourquoi(a, json.loads(cal.read_text(encoding="utf-8")), borne_haute)
    assert h.count("<svg") == 4 and "jeux de certification ne sont pas lus" in h
