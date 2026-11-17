"""Tests des mesures sur les jeux de saisies (engine/mesure_saisies.py). Lancer : python -m pytest tests"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.catalogue import Catalogue  # noqa: E402
from engine.mesure_saisies import (CHAL, Decomposeur, charger_catalogue_jeux, charger_jeu, mots_oublies,  # noqa: E402
                                   noter, operations)
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
