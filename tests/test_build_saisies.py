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
CHIFFRE = re.compile(r"\d+")         # chiffres jamais modifiés ; une fusion peut coller deux nombres (« ix3 50 » → « ix350 »)


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
                                  "clavier", "espace", "choix_lettre", "phon", "nature", "repartition", "geo_banc"])
def test_poids_respectes(modele, bloc):
    poids = {"modes": modele.modes, "fautes_lu": modele.fautes["lu"], "fautes_entendu": modele.fautes["entendu"],
             "melange_lu": modele.melange["lu"], "melange_entendu": modele.melange["entendu"],
             "clavier": modele.clavier, "espace": modele.espace, "choix_lettre": modele.choix_lettre,
             "phon": modele.phon, "nature": modele.absents_nature,
             "repartition": modele.repartition, "geo_banc": modele.geo_banc}[bloc]
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
            assert "".join(CHIFFRE.findall(t)) == "".join(CHIFFRE.findall(nom.lower())), (nom, t, labels)


def test_jeux_jamais_sur_un_code(fichiers):
    for jeu, lignes in fichiers.items():
        for l in lignes:
            if l["sous_nature"] == "code_voisin":
                assert jeu == "banc"
                continue
            if l["nature"] == "present" and not l["mots_oublies"]:
                src = l["nom_source"].lower().replace(" – ", " ")
                assert l["terme"][:1] == src[:1], (jeu, l["case_id"])
                assert "".join(CHIFFRE.findall(l["terme"])) == "".join(CHIFFRE.findall(src)), (jeu, l["case_id"])


def test_calibration_fautive_et_approchee(fichiers, modele):
    for jeu in ("analyse", "certif"):
        lignes = fichiers[jeu]
        assert all(l["atteint_approche"] == "1" for l in lignes), jeu
        pres = [l for l in lignes if l["nature"] == "present"]
        assert all(l["perturbations"] or l["mots_oublies"] for l in pres), jeu
    # analyse : un terme au plus une fois, au plus 3 cas par nom
    lignes = fichiers["analyse"]
    assert len({l["terme_norm"] for l in lignes}) == len(lignes)
    par_nom = Counter(normalize(l["nom_source"]) for l in lignes if l["nature"] == "present")
    assert max(par_nom.values()) <= modele.max_par_nom["calibration"]


def test_certification_sans_plafond_et_volumes(fichiers, modele):
    """Certification : sans plafond par nom, doublons de termes permis (tirages indépendants, R-RES-10) ;
    30 000 saisies fautives par famille, 110 000 en géographie, quand le générateur les atteint."""
    assert modele.max_par_nom["certification"] is None
    for chemin in (JEUX["certif"], CHAL / "saisies_certif_pessimiste.csv"):
        lignes = fichiers["certif"] if chemin == JEUX["certif"] else read_csv(chemin)
        pres = Counter(l["famille"] for l in lignes if l["nature"] == "present")
        assert pres["geographie"] == bs.VOLUME_CERTIF_GEO, chemin.name
        assert all(n == bs.VOLUME_CERTIF for f, n in pres.items() if f != "geographie"), (chemin.name, pres)
        par_nom = Counter(normalize(l["nom_source"]) for l in lignes if l["nature"] == "present")
        assert max(par_nom.values()) > 3                        # le plafond est bien levé


def test_analyse_et_certif_sans_terme_commun(fichiers):
    a = {l["terme_norm"] for l in fichiers["analyse"]}
    for c in ({l["terme_norm"] for l in fichiers["certif"]},
              {l["terme_norm"] for l in read_csv(CHAL / "saisies_certif_pessimiste.csv")}):
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


# ── modèle v0.3 (valeurs lues dans des clés, plus jamais recopiées depuis le texte)

def test_v0_3_valeurs_lues(modele):
    assert modele.source["version"] == "0.3"
    assert modele.clavier == {"omission": 0.40, "substitution": 0.20, "inversion": 0.15, "insertion": 0.10,
                              "doublement": 0.05, "espace": 0.10}
    assert modele.espace == {"fusion": 0.70, "coupure": 0.30}
    assert modele.fusion_mots_vides is False and modele.fusion_mots_a_chiffre is True
    assert modele.coupure_morceau_min == 2
    assert modele.choix_lettre == {"touche_voisine": 0.50, "quelconque": 0.50}
    assert modele.fautes["entendu"] == {0: 0.33, 1: 0.27, 2: 0.20, 3: 0.20}
    assert modele.phon["transcription_libre"] == 0.15 and "transcription_libre" not in modele.phon_reecritures
    tr = modele.transcription
    assert tr["nb_regles"] == {2: 0.5, 3: 0.5} and tr["tirage"] == "pondere"
    assert tr["proba_voyelle"] == 0.5 and tr["longueur_min"] == 5 and ("o", "ou") in tr["voyelles"]
    assert modele.omission_plafond == 0.6 and modele.nombre_plus_peuples == 300
    assert modele.voisins_distance_max == 2
    assert modele.max_par_nom == {"calibration": 3, "banc": None, "certification": None}


def test_nombre_de_fautes_sans_classe_4(modele):
    pert = bs.Perturbateur(modele)
    rng = random.Random(4)
    n = 40_000
    for mode in ("lu", "entendu"):
        c = Counter(pert.nb_fautes(rng, mode) for _ in range(n))
        assert set(c) == set(modele.fautes[mode]) == {0, 1, 2, 3}
        for k, w in modele.fautes[mode].items():
            assert abs(c[k] / n - w) <= 0.02, (mode, k)


def test_probabilite_oubli_par_type(modele):
    assert modele.proba_oubli("article", "lu") == 0.25
    assert modele.proba_oubli("commune", "lu") == 0.02            # autres
    assert modele.proba_oubli("article", "entendu") == pytest.approx(0.30)
    assert modele.proba_oubli("client", "entendu") == pytest.approx(0.18)
    fort = bs.Modele(**{**modele.__dict__, "omission_mult_entendu": 3.0})
    assert fort.proba_oubli("article", "entendu") == modele.omission_plafond


def test_oubli_dernier_mot(ctx):
    e = {"entity_type": "commune"}
    r = bs._omettre_categorie(ctx, random.Random(1), e, "Sint-Lambrechts-Woluwe", "dernier_mot")
    assert r == ("Sint-Lambrechts", ["Woluwe"])
    assert bs._omettre_categorie(ctx, random.Random(1), e, "Liège", "dernier_mot") is None


def test_espace_fusion_et_coupure(modele):
    pert = bs.Perturbateur(modele)
    assert (6, 7, "") in pert.sites_clavier("audi e tron", "espace", "fusion")     # « e tron » → « etron »
    assert not pert.sites_clavier("bougie d allumage", "espace", "fusion")         # jamais avec un mot vide
    assert (2, 3, "") in pert.sites_clavier("ds 4", "espace", "fusion")            # mot à chiffre permis
    sans_chiffre = bs.Perturbateur(bs.Modele(**{**modele.__dict__, "fusion_mots_a_chiffre": False}))
    assert not sans_chiffre.sites_clavier("ds 4", "espace", "fusion")
    mot = "carrosseriebedrijf"
    coupures = pert.sites_clavier(mot, "espace", "coupure")
    assert coupures and all(2 <= a <= len(mot) - 2 for a, _, _ in coupures)       # morceaux d'au moins 2 lettres
    assert not pert.sites_clavier("de la", "espace", "coupure")


def test_choix_de_la_lettre(modele):
    pert = bs.Perturbateur(modele)
    mot = "standard"
    voisine = pert.sites_clavier(mot, "substitution", "touche_voisine")
    quelconque = pert.sites_clavier(mot, "substitution", "quelconque")
    assert all(r in bs.VOISINS[mot[a]] for a, _, r in voisine)
    assert any(r not in bs.VOISINS[mot[a]] for a, _, r in quelconque)
    assert all(r != mot[a] for a, _, r in quelconque)


def test_transcription_libre(modele):
    pert = bs.Perturbateur(modele)
    rng = random.Random(11)
    src = "montataire brunssum"
    vus = 0
    for _ in range(300):
        r = pert.transcription(rng, src)
        if r is None:
            continue
        vus += 1
        t, lab = r
        regles = lab.split("[", 1)[1].rstrip("]").split(" + ")
        assert sum(not x.startswith("voyelle(") for x in regles) in modele.transcription["nb_regles"], lab
        assert t[:1] == "m" and t.count(" ") == 1
        assert sum(a != b for a, b in zip(t.split(), src.split())) == 1, (t, lab)   # un seul mot réécrit
    assert vus > 250
    assert pert.transcription(rng, "ford ka") is None             # aucun mot de 5 lettres ou plus


def test_jamais_retour_a_la_forme_de_depart(modele):
    pert = bs.Perturbateur(modele)
    rng = random.Random(5)
    for nom in ("carrosseriebedrijf de smet", "montataire", "tervuren", "sint lambrechts woluwe"):
        for _ in range(200):
            t, labels = pert.fautes(rng, nom, "entendu", 3)
            if labels:
                assert normalize(t) != normalize(nom), (nom, labels)


def test_premiere_lettre_toutes_fautes(modele, ctx):
    pert = bs.Perturbateur(modele)
    rng = random.Random(9)
    noms = sorted({ctx.nom_source(e).replace(" – ", " ").lower() for e in list(ctx.ents)[::40]})
    for nom in noms:
        for mode in ("lu", "entendu"):
            t, labels = pert.fautes(rng, nom, mode, 5)
            assert t[:1] == nom[:1], (nom, t, labels)


def test_attendu_voisins_bornes_a_2(ctx):
    eid = next(e for e, x in ctx.ents.items() if x["entity_type"] == "localite_postale" and normalize(x["label"]) == "rongy")
    att = ctx.attendu("rangie", "rongy", eid, None, None)
    assert att["distance"] == 3
    assert all(bs.distance("rangie", n) <= 2 for n in att["voisins"])


def test_banc_geographie_plus_peuplee(fichiers, ctx, modele, partage):
    import json
    meta = json.loads(bs.META.read_text(encoding="utf-8"))["jeux"]["banc"]
    geo = sum(1 for l in fichiers["banc"] if l["nature"] == "present" and l["famille"] == "geographie")
    # le compteur inclut les tirages « au hasard » tombés parmi les plus peuplés
    g = bs.Generateur(ctx, modele, bs.plan_jeu("banc", modele), set(partage[1]))
    w = modele.geo_banc
    attendu = w["plus_peuples"] + w["au_hasard"] * len(g.plus_peuples()) / len(g.eligibles("geographie"))
    assert abs(meta["geographie_plus_peuples"] / geo - attendu) <= 0.05


@pytest.mark.parametrize("avant, apres, message", [
    ("tirage_des_regles: pondere", "tirage_des_regles: au_jugé", "tirage_des_regles"),
    ("voisins_distance_max: 2", "voisins_distance_max: deux", "voisins_distance_max"),
    ("fusion_mots_vides: false", "fusion_mots_vides: parfois", "fusion_mots_vides"),
    ("  plafond: 0.6", "  plafond: 1.6", "plafond"),
])
def test_yaml_invalide_refuse(tmp_path, avant, apres, message):
    y = bs.MODELE.read_text(encoding="utf-8")
    assert y.count(avant) == 1, avant
    (tmp_path / "m.yaml").write_text(y.replace(avant, apres), encoding="utf-8")
    with pytest.raises(bs.ModeleInvalide, match=message):
        bs.Modele.charger(tmp_path / "m.yaml")


def test_mots_oublies_notes_a_la_generation(fichiers):
    for jeu in ("banc", "analyse"):
        for l in fichiers[jeu]:
            if l["mots_oublies"]:
                assert l["forme_courte"] and l["sous_nature"] == "mot_oublie", (jeu, l["case_id"])
            else:
                assert not l["forme_courte"], (jeu, l["case_id"])
