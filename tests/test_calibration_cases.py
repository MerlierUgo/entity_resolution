"""Tests des jeux de calibration de l'étape approchée (R-RES-10) : challenges/calibration_analyse.csv
et challenges/calibration_certif.csv, fabriqués par build/build_calibration.py. Lancer : python -m pytest tests

Seuls les identifiants d'entités de la partition test sont lus (jamais les questions humaines).
"""
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "build"))
from engine import Catalogue, ResolveurExact  # noqa: E402
from engine.approche import IndexApproche, signature  # noqa: E402
from engine.catalogue import read_csv  # noqa: E402
import build_calibration as bc  # noqa: E402
from common import write_csv  # noqa: E402


@pytest.fixture(scope="module")
def cat():
    return Catalogue.charger()


@pytest.fixture(scope="module", params=["analyse", "certif"])
def lignes(request):
    return read_csv(bc.SORTIES[request.param][0])


def test_deux_jeux_sans_terme_commun(cat):
    """Analyse et certification : graines différentes, aucun terme normalisé commun, même volume visé."""
    a, c = (read_csv(bc.SORTIES[k][0]) for k in ("analyse", "certif"))
    assert bc.GRAINE_ANALYSE != bc.GRAINE_CERTIF
    na, nc = ({cat.normaliser(r["terme"]) for r in x} for x in (a, c))
    assert not na & nc
    assert {r["case_id"][:5] for r in a} == {"CAL-A"} and {r["case_id"][:5] for r in c} == {"CAL-C"}
    pres = lambda x, f: sum(r["famille"] == f and r["nature"] == "present" for r in x)  # noqa: E731
    for fam in ("pieces", "vehicules", "geographie", "clients"):
        assert pres(a, fam) == pres(c, fam) == bc.PRESENTS_VISES, fam


def test_colonnes(lignes):
    assert list(lignes[0]) == bc.CHAMPS
    assert [r["case_id"] for r in lignes] == sorted(r["case_id"] for r in lignes)
    assert len({r["case_id"] for r in lignes}) == len(lignes)


def test_graine_fixe_meme_fichier(cat, tmp_path):
    """Même graine → même fichier, octet pour octet (petit volume pour rester rapide)."""
    interdits = bc.entites_test()
    sorties = []
    for i in range(2):
        rows, _ = bc.construire(cat, vise=12, interdits=interdits)
        f = tmp_path / f"c{i}.csv"
        write_csv(f, rows, bc.CHAMPS, sort_keys=["case_id"])
        sorties.append(f.read_bytes())
    assert sorties[0] == sorties[1]
    autre, _ = bc.construire(cat, vise=12, graine=bc.GRAINE + 1, interdits=interdits)
    assert [r["terme"] for r in autre] != [r["terme"] for r in rows]


def test_aucune_entite_de_la_partition_test(lignes):
    interdits = bc.entites_test()
    fautifs = [r["case_id"] for r in lignes if set(filter(None, r["attendu"].split("|"))) & interdits]
    assert not fautifs, fautifs[:5]


def test_aucun_cas_trouvable_par_l_exact(cat, lignes):
    """Chaque cas atteint l'approché : ni alias exact, ni mots triés, ni index négatif, garde-fous d'entrée passés."""
    exact, index = ResolveurExact(cat), IndexApproche(cat)
    for r in lignes:
        norm = cat.normaliser(r["terme"])
        assert not exact.candidats_exacts(norm)[0], (r["case_id"], r["terme"])
        assert norm not in cat.negatifs, (r["case_id"], r["terme"])
        assert index.proposer(norm)[0] is not None, (r["case_id"], r["terme"])


def test_presents_et_absents(lignes):
    par_fam = Counter((r["famille"], r["nature"]) for r in lignes)
    for fam in {r["famille"] for r in lignes}:
        pres, abs_ = par_fam[(fam, "present")], par_fam[(fam, "absent")]
        assert abs_ / (pres + abs_) >= 0.20, fam
    for fam in ("geographie", "pieces", "vehicules", "clients"):
        assert par_fam[(fam, "present")] >= bc.PRESENTS_MIN, fam
    for r in lignes:
        if r["nature"] == "absent":
            assert r["attendu"] == "" and r["statut_attendu"] == "unknown"
        else:
            assert r["attendu"] and r["statut_attendu"] in ("resolved", "ambiguous")


def test_perturbations_jamais_sur_un_chiffre(cat, lignes):
    """Les mots à chiffres (codes, cylindrées…) restent intacts ; au plus 2 perturbations par cas."""
    for r in lignes:
        if r["nature"] != "present":
            continue
        assert signature(cat.normaliser(r["terme"])) == signature(cat.normaliser(r["alias_source"])), r["case_id"]
        assert 1 <= len(r["perturbation"].split("+")) <= 2
        assert len(cat.normaliser(r["alias_source"]).replace(" ", "")) >= 4


def test_au_plus_trois_cas_par_nom(lignes):
    n = Counter((r["famille"], r["nature"], r["alias_source"]) for r in lignes)
    assert max(n.values()) <= bc.MAX_PAR_NOM
