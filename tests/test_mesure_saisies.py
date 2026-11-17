"""Tests des mesures sur les jeux de saisies (engine/mesure_saisies.py). Lancer : python -m pytest tests"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.catalogue import Catalogue  # noqa: E402
from collections import Counter  # noqa: E402

from engine.mesure_saisies import (CHAL, Decomposeur, charger_catalogue_jeux, charger_jeu, collision_exacte,  # noqa: E402
                                   mots_oublies, noter, operations, risque_approche, taux)
import build_saisies as bs  # noqa: E402  (chemin ajouté par engine.mesure_saisies)


def test_certification_jamais_ouverte():
    with pytest.raises(SystemExit, match="certification"):
        charger_jeu(CHAL / "saisies_certif.csv")


def test_notation_modele_section_8():
    assert noter("resolved", ["a"], "resolved", ["a"]) == "ideal"
    assert noter("resolved", ["a"], "resolved", ["b"]) == "silencieux"
    assert noter("unknown", [], "resolved", ["b"]) == "silencieux"
    assert noter("ambiguous", ["a", "b"], "resolved", ["a"]) == "trop_confiant"
    assert noter("resolved", ["a"], "ambiguous", ["a", "c"]) == "sur"
    assert noter("resolved", ["a"], "unknown", []) == "sur"
    assert noter("unknown", [], "ambiguous", ["a", "b"]) == "incorrect"
    assert noter("unknown", [], "unknown", []) == "ideal"


def test_collision_exacte():
    # « opel » tapé pour Hopel : résolu par l'exact vers la marque → silencieux, collision exacte
    assert collision_exacte("silencieux", "", True)
    assert not collision_exacte("silencieux", "approche", True)        # erreur du fuzzy : pas une collision
    assert not collision_exacte("silencieux", "", False)               # saisie sans faute
    assert not collision_exacte("trop_confiant", "", True)
    c = Counter({"ideal": 7, "silencieux": 3, "collision": 1})
    t = taux(c)
    assert t["n"] == 10 and t["silencieux"] == 3 and t["dont_collision_exacte"] == 1
    assert t["silencieux_hors_collision_pct"] == 20.0


def test_risque_approche_sans_collision():
    res = [{"famille": "geographie", "r_etape": "approche", "r_statut": "resolved", "note": "silencieux",
            "collision": False},
           {"famille": "geographie", "r_etape": "approche", "r_statut": "resolved", "note": "ideal",
            "collision": False},
           {"famille": "marques", "r_etape": "", "r_statut": "resolved", "note": "silencieux", "collision": True}]
    r = risque_approche(res)
    assert r["TOTAL"]["acceptes"] == 2 and r["TOTAL"]["silencieux"] == 1 and "marques" not in r


def test_index_negatif_charge_sans_les_absents_inconnus():
    cat = Catalogue.charger()
    retires = bs.charger_retires()
    reduit = charger_catalogue_jeux(cat, retires)
    assert not set(reduit.negatifs) & retires
    assert len(reduit.negatifs) == len(cat.negatifs) - len(retires)
    assert reduit.index is cat.index                       # rien d'autre ne change
    assert retires <= set(Catalogue.charger().negatifs)      # catalog/negatifs.csv intact


def test_mots_oublies():
    assert mots_oublies("filtre huile knecht standard", "filtre huile standard") == (["knecht"], "filtre huile standard")
    assert mots_oublies("audi r 3 limousine", "audi r3 limousine")[0] == []      # mots collés : pas un oubli
    assert mots_oublies("garage dewulf", "garaje dewulf")[0] == []


def test_operations_clavier():
    assert operations("standard", "standatd") == ["substitution voisine"]
    assert operations("premium", "prmeium") == ["inversion"]
    assert operations("carrosserie", "carroserie") == ["dédoublement"]
    assert operations("knecht", "knech") == ["omission"]


def test_decomposeur_phonetique():
    dec = Decomposeur(bs.Modele.charger())
    assert dec("carrosserie", "carosserie") in (["clavier : dédoublement"], ["phonétique : consonne_double"])
    assert dec("tervuren", "tervurant")[0] == "phonétique : nasales"
