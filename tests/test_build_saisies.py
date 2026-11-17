"""Tests du générateur de saisies (build/build_saisies.py) et des jeux qu'il produit.

Lancer : python -m pytest tests/test_build_saisies.py
"""
import random
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "build"):
    sys.path.insert(0, str(p))
import build_saisies as bs  # noqa: E402
from common import normalize, read_csv  # noqa: E402

CHAL = ROOT / "challenges"
JEUX = {j: CHAL / f"saisies_{j}.csv" for j in ("banc", "analyse", "certif")}
CHIFFRE = re.compile(r"\w*\d\w*")


@pytest.fixture(scope="module")
def modele():
    return bs.Modele.charger()


@pytest.fixture(scope="module")
def ctx(modele):
    return bs.Contexte(modele)


@pytest.fixture(scope="module")
def partage(ctx, modele):
    return bs.partage_negatifs(ctx.cat, modele)


@pytest.fixture(scope="module")
def fichiers():
    manquants = [str(p) for p in JEUX.values() if not p.exists()]
    if manquants:
        pytest.fail(f"jeux absents {manquants} : lancer python build/build_saisies.py")
    return {j: read_csv(p) for j, p in JEUX.items()}


def petit(ctx, modele, partage, jeu):
    gardes, retires = partage
    plan = bs.plan_jeu(jeu, modele, volume_banc=150, volume_calib=12)
    return bs.generer_jeu(ctx, modele, plan, set(retires), gardes)[0]


# ── modèle

def test_modele_charge_et_controle(modele):
    assert set(modele.modes) == {"lu", "entendu"}
    assert modele.generiques and "garage" in modele.generiques
    assert normalize("van") in modele.exclus_generiques and normalize("van") not in modele.generiques


def test_motif_inconnu_refuse():
    with pytest.raises(bs.ModeleInvalide, match="non reconnu"):
        bs.parser_motif("quelque chose de libre")
    assert bs.Reecriture("er", "é", "fin") in bs.parser_motif("er/et/ez final ↔ é")
    assert bs.parser_motif("oe → ou") == [bs.Reecriture("oe", "ou", "partout")]


def test_azerty_symetrique():
    for k, vs in bs.VOISINS.items():
        for v in vs:
            assert k in bs.VOISINS[v], (k, v)
    assert set(bs.VOISINS["a"]) == {"z", "q"} and "s" in bs.VOISINS["d"]


def test_variante_sans_modifier_le_yaml(modele):
    v = modele.avec_parts(entendu=0.4, absents=0.25)
    assert v.modes == {"lu": 0.6, "entendu": 0.4} and v.absents_part == 0.25
    assert modele.modes["entendu"] == 0.20 and modele.absents_part == 0.10
    with pytest.raises(bs.ModeleInvalide):
        modele.avec_parts(absents=1.0)


# ── poids

@pytest.mark.parametrize("bloc", ["modes", "fautes_lu", "fautes_entendu", "melange_lu", "melange_entendu",
                                  "clavier", "phon", "nature", "repartition"])
def test_poids_respectes(modele, bloc):
    poids = {"modes": modele.modes, "fautes_lu": modele.fautes["lu"], "fautes_entendu": modele.fautes["entendu"],
             "melange_lu": modele.melange["lu"], "melange_entendu": modele.melange["entendu"],
             "clavier": modele.clavier, "phon": modele.phon, "nature": modele.absents_nature,
             "repartition": modele.repartition}[bloc]
    rng = random.Random(1)
    n = 40_000
    c = Counter(bs.tirer(rng, poids) for _ in range(n))
    for k, w in poids.items():
        assert abs(c[k] / n - w) <= 0.02, (bloc, k, c[k] / n, w)


def test_banc_suit_le_modele(fichiers, modele):
    banc = fichiers["banc"]
    pres = [l for l in banc if l["nature"] == "present"]
    for f, w in modele.repartition.items():
        assert abs(sum(l["famille"] == f for l in pres) / len(pres) - w) <= 0.02, f
    for m, w in modele.modes.items():
        assert abs(sum(l["mode"] == m for l in pres) / len(pres) - w) <= 0.02, m
    absents = sum(l["nature"] == "absent" and l["sous_nature"] != "code_voisin" for l in banc)
    assert abs(absents / len(banc) - modele.absents_part) <= 0.02
    assert any(l["nb_perturbations"] == "0" and not l["mots_oublies"] for l in pres)   # garde les saisies exactes


# ── déterminisme

def test_graine_fixe_fichier_identique(ctx, modele, partage, tmp_path):
    for jeu in ("banc", "analyse"):
        a, b = petit(ctx, modele, partage, jeu), petit(ctx, modele, partage, jeu)
        bs.write_csv(tmp_path / "a.csv", a, bs.COLONNES)
        bs.write_csv(tmp_path / "b.csv", b, bs.COLONNES)
        assert (tmp_path / "a.csv").read_bytes() == (tmp_path / "b.csv").read_bytes(), jeu
    assert {l["graine"] for l in a} == {bs.GRAINES["analyse"]}


def test_graines_differentes(fichiers):
    graines = {j: {l["graine"] for l in ls} for j, ls in fichiers.items()}
    assert all(len(g) == 1 for g in graines.values())
    assert len({next(iter(g)) for g in graines.values()}) == 3


# ── exclusions

def test_aucune_entite_de_la_partition_test(ctx, fichiers):
    for jeu, lignes in fichiers.items():
        for l in lignes:
            ids = set(filter(None, l["attendu_ids"].split("|"))) | ({l["entity_id_source"]} - {""})
            assert not ids & ctx.exclus, (jeu, l["case_id"])


def test_jamais_sur_un_code_ni_la_premiere_lettre(modele, ctx):
    pert = bs.Perturbateur(modele)
    rng = random.Random(7)
    noms = sorted({ctx.nom_source(e) for e in list(ctx.ents)[::7]})
    noms += ["MERCEDES-BENZ AMG GLE 63 S 4MATIC+", "BMW 430D XDRIVE", "Hopel Astra", "Kia Ceed"]
    for nom in noms:
        for mode in ("lu", "entendu"):
            t, labels = pert.fautes(rng, nom.lower(), mode, 3)
            assert t[:1] == nom.lower()[:1], (nom, t, labels)
            assert CHIFFRE.findall(t) == CHIFFRE.findall(nom.lower()), (nom, t, labels)


def test_jeux_jamais_sur_un_code(fichiers):
    for jeu, lignes in fichiers.items():
        for l in lignes:
            if l["sous_nature"] == "code_voisin":
                assert jeu == "banc"
                continue
            if l["nature"] == "present" and not l["mots_oublies"]:
                src = l["nom_source"].lower().replace(" – ", " ")
                assert l["terme"][:1] == src[:1], (jeu, l["case_id"])
                assert CHIFFRE.findall(l["terme"]) == CHIFFRE.findall(src), (jeu, l["case_id"])


def test_calibration_fautive_et_approchee(fichiers, modele):
    for jeu in ("analyse", "certif"):
        lignes = fichiers[jeu]
        assert all(l["atteint_approche"] == "1" for l in lignes), jeu
        pres = [l for l in lignes if l["nature"] == "present"]
        assert all(l["perturbations"] or l["mots_oublies"] for l in pres), jeu
        assert len({l["terme_norm"] for l in lignes}) == len(lignes), jeu
        par_nom = Counter(normalize(l["nom_source"]) for l in pres)
        assert max(par_nom.values()) <= modele.max_par_nom


def test_analyse_et_certif_sans_terme_commun(fichiers):
    a = {l["terme_norm"] for l in fichiers["analyse"]}
    c = {l["terme_norm"] for l in fichiers["certif"]}
    assert not a & c


# ── réponse attendue (§ 8)

def test_attendu_voisin_rend_ambigu(ctx):
    att = ctx.attendu("Fresin", "fretin", "geo:ville:FR-3017100", None, None)
    assert att["statut"] == "ambiguous" and "fressin" in att["voisins"]


def test_attendu_mot_oublie_autre_entite(ctx):
    eid = next(e for e, x in ctx.ents.items() if x["entity_type"] == "modele_vehicule"
               and normalize(ctx.nom_source(e)).startswith("skoda "))
    att = ctx.attendu("skoda", normalize(ctx.nom_source(eid)), eid, "skoda", None)
    assert att["statut"] == "resolved" and att["ids"] == ["veh:marque:skoda"]


def test_negatifs_partages_en_deux(ctx, partage):
    gardes, retires = partage
    assert not set(gardes) & set(retires)
    assert abs(len(retires) - len(gardes)) <= 1
    assert set(gardes) | set(retires) == {k for k, (_, ra) in ctx.cat.negatifs.items() if ra == "lieu"}
