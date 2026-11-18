"""
Générateur des jeux de saisies à partir du modèle de saisie explicite (spec/modele_saisie.yaml).

    python build/build_saisies.py                       banc, analyse, certif (valeurs centrales du modèle)
    python build/build_saisies.py --sensibilite         en plus : banc et analyse aux valeurs de sensibilité
    python build/build_saisies.py --part-entendu 0.4 --part-absents 0.1 --jeux banc analyse
                                                        une variante, sans modifier le YAML
    python build/build_saisies.py --scenario pessimiste banc et certification du scénario pessimiste
                                                        (spec/modele_saisie_pessimiste.yaml, valeurs v0.2)

Sorties (CSV en utf-8-sig) :
  challenges/saisies_banc.csv      suit la répartition par famille du modèle, garde les saisies à 0 faute ;
                                   pas de plafond de cas par nom (un nom revient souvent dans le trafic) ;
                                   géographie : part du modèle parmi les lieux les plus peuplés ;
  challenges/saisies_analyse.csv   pour concevoir : au moins VOLUME_CALIB saisies fautives par famille
                                   quand le catalogue le permet, plus les absents selon la part du modèle ;
  challenges/saisies_certif.csv    même construction, autre graine, aucun terme normalisé commun avec
                                   l'analyse ; ne sert qu'à calculer un seuil, une seule fois, plus tard ;
  challenges/sensibilite/…         variantes (part d'« entendu », part d'absents) ;
  challenges/saisies_{banc,certif}_pessimiste.csv
                                   scénario pessimiste (calibration des seuils, R-RES-10) ;
  challenges/negatifs_retires.csv  moitié des lieux de l'index négatif retirée de l'index CHARGÉ par le
                                   moteur pendant l'évaluation de ces jeux (absents inconnus) ;
  challenges/saisies_meta.json     graines, paramètres, volumes, manques, empreintes des fichiers.

Le moteur ne lit jamais spec/modele_saisie.yaml : il décrit les utilisateurs, pas le moteur.
Toutes les valeurs du modèle viennent du YAML et des listes de spec/absents/ ; le Python ne contient
en dur que la table des touches voisines AZERTY belge, les graines et les volumes (paramètres de
fabrication, notés dans les fichiers produits).

Réponse attendue (modèle § 8) : l'ensemble des entités compatibles avec ce qui a été tapé, avec le même
indice de type que celui donné au moteur ; voir Contexte.attendu.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "build"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from rapidfuzz import process  # noqa: E402
from rapidfuzz.distance import OSA, JaroWinkler  # noqa: E402

from common import CHAL, SPEC, STOP, console_utf8, load_yaml, normalize, read_csv, write_csv  # noqa: E402
from engine.catalogue import Catalogue, cle_triee  # noqa: E402
from engine.resolveur import ResolveurExact  # noqa: E402
from tirage_echantillon_reel import nom_a_dicter  # noqa: E402

MODELE = SPEC / "modele_saisie.yaml"
MODELE_PESSIMISTE = SPEC / "modele_saisie_pessimiste.yaml"   # scénario pessimiste (valeurs v0.2, calibration R-RES-10)
ABSENTS = SPEC / "absents"
RETIRES = CHAL / "negatifs_retires.csv"
META = CHAL / "saisies_meta.json"
SENSI = CHAL / "sensibilite"

# Paramètres de fabrication (pas des valeurs du modèle) : notés dans chaque fichier produit.
# Modèle v0.3 : nouvelles graines (v0.2 : banc 20261117, analyse 20261118, certif 20261119 ;
# v0.1 : banc 20261208, analyse 20261201, certif 20261215).
GRAINES = {"banc": 20261120, "analyse": 20261121, "certif": 20261127}
# certif : 20261122 (3 000 par famille), 20261125 (~10 000), 20261127 (30 000, 110 000 en géographie, sans plafond
# par nom) ; les deux premières ont été consultées en agrégé par une calibration.
# Scénario pessimiste (spec/modele_saisie_pessimiste.yaml) : banc et certification seulement, graines à part.
GRAINES_PESSIMISTE = {"banc": 20261123, "certif": 20261128}   # certif : 20261124 puis 20261126 avant
SUFFIXE_PESSIMISTE = "_pessimiste"
GRAINE_NEGATIFS = 20261222   # inchangée : même partage de l'index négatif qu'en v0.1 et v0.2 (comparaison)

ALPHABET = "abcdefghijklmnopqrstuvwxyz"   # clavier.choix_de_la_lettre.quelconque
VOLUME_CALIB = 3000      # saisies fautives visées par famille (modèle : calibration_volume, « au moins 3 000 »)
VOLUME_CERTIF = 30000    # certification : saisies fautives par famille (calibration R-RES-10), sans plafond par nom
VOLUME_CERTIF_GEO = 110000   # certification, géographie
VOLUME_BANC = 5000       # saisies du banc d'essai, toutes familles
CODES_BANC = 30          # codes voisins gardés dans le banc (MN-AMO-70514 / 70513) : jamais rapprochés
PREFIXES = {"banc": "SB", "analyse": "SA", "certif": "SC"}

COLONNES = ["case_id", "jeu", "graine", "famille", "mode", "terme", "terme_norm", "indice_type",
            "attendu_statut", "attendu_ids", "nature", "sous_nature", "perturbations", "nb_perturbations",
            "mots_oublies", "forme_courte", "distance", "voisins", "nom_source", "entity_id_source", "atteint_approche"]

# ── clavier AZERTY belge (seule table en dur) ──────────────────────────────────────────────────────
# Rangées de lettres ; la rangée du bas commence par la touche « < » (clavier ISO), d'où le décalage.
AZERTY_BE = ("azertyuiop", "qsdfghjklmù", "<wxcvbn")


def voisins_azerty() -> dict[str, tuple[str, ...]]:
    """Touches voisines (même rangée ±1, rangée du dessus et du dessous), lettres seulement."""
    haut, milieu, bas = AZERTY_BE
    v = defaultdict(set)

    def lier(a, b):
        if a.isalpha() and b.isalpha():
            v[a].add(b)
            v[b].add(a)

    for rangee in AZERTY_BE:
        for i in range(len(rangee) - 1):
            lier(rangee[i], rangee[i + 1])
    for i, c in enumerate(haut):          # touche du haut i : touches du milieu i-1 et i
        for j in (i - 1, i):
            if 0 <= j < len(milieu):
                lier(c, milieu[j])
    for i, c in enumerate(bas):           # touche du bas i : touches du milieu i-1 et i
        for j in (i - 1, i):
            if 0 <= j < len(milieu):
                lier(c, milieu[j])
    return {k: tuple(sorted(x)) for k, x in sorted(v.items())}


VOISINS = voisins_azerty()


def sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


# ── modèle de saisie ──────────────────────────────────────────────────────────────────────────────

class ModeleInvalide(ValueError):
    pass


def _poids(bloc: dict, ou: str, ignorer=()) -> dict:
    """Poids d'un bloc (clé → nombre), contrôlés : positifs, somme 1 à 1e-6 près."""
    out = {}
    for k, v in bloc.items():
        if k in ignorer:
            continue
        p = v["poids"] if isinstance(v, dict) else v
        if not isinstance(p, (int, float)) or p < 0:
            raise ModeleInvalide(f"{MODELE.name} · {ou} · {k} : poids « {p} » invalide (nombre positif attendu).")
        out[str(k)] = float(p)
    if abs(sum(out.values()) - 1) > 1e-6:
        raise ModeleInvalide(f"{MODELE.name} · {ou} : les poids font {sum(out.values()):.4f}, pas 1. "
                             "Corriger le YAML.")
    return out


@dataclass(frozen=True)
class Reecriture:
    src: str
    dst: str
    position: str      # partout | fin | debut


def parser_motif(motif: str) -> list[Reecriture]:
    """Traduit un motif phonétique du YAML en réécritures. Formes reconnues :
    « a ↔ b ↔ c » (équivalences), « a → b » (un sens), « x/y final ↔ z » (fin de mot),
    « ajout ou retrait de e, s en fin de mot », « h initial muet ». Toute autre forme est refusée."""
    m = motif.strip()
    r = re.fullmatch(r"ajout ou retrait de (.+) en fin de mot", m)
    if r:
        lettres = [x.strip() for x in r.group(1).split(",") if x.strip()]
        return [rw for l in lettres for rw in (Reecriture("", l, "fin"), Reecriture(l, "", "fin"))]
    r = re.fullmatch(r"(\w+) initial muet", m)
    if r:
        return [Reecriture(r.group(1), "", "debut"), Reecriture("", r.group(1), "debut")]
    for fleche, double in (("↔", True), ("→", False)):
        if fleche in m:
            parts = [p.strip() for p in m.split(fleche)]
            position = "fin" if any(p.endswith(" final") for p in parts) else "partout"
            membres = [[a.strip() for a in p.removesuffix(" final").split("/") if a.strip()] for p in parts]
            if any(not g or any(" " in a for a in g) for g in membres):
                break
            out = []
            if double:
                tous = [a for g in membres for a in g]
                out = [Reecriture(a, b, position) for a in tous for b in tous if a != b]
            else:
                if len(membres) != 2:
                    break
                out = [Reecriture(a, b, position) for a in membres[0] for b in membres[1] if a != b]
            return sorted(set(out), key=lambda x: (x.src, x.dst, x.position))
    raise ModeleInvalide(f"{MODELE.name} · phonetique : motif « {motif} » non reconnu ; formes permises : "
                         "« a ↔ b », « a → b », « a/b final ↔ c », « ajout ou retrait de x, y en fin de mot », "
                         "« h initial muet ».")


@dataclass
class Modele:
    """Valeurs du modèle de saisie, contrôlées au chargement."""
    modes: dict
    fautes: dict                 # mode → {n: poids}
    melange: dict                # mode → {clavier, phonetique}
    clavier: dict                # type → poids
    espace: dict                 # fusion | coupure → poids
    choix_lettre: dict           # touche_voisine | quelconque → poids
    fusion_mots_vides: bool      # clavier.espace : une fusion peut-elle toucher un mot vide ?
    fusion_mots_a_chiffre: bool  # … un mot qui contient un chiffre ?
    coupure_morceau_min: int     # longueur minimale de chaque morceau d'une coupure
    transcription: dict          # nb_regles {n: poids}, tirage, proba_voyelle, longueur_min, voyelles [(x, y)]
    phon: dict                   # règle → poids (transcription_libre comprise)
    phon_reecritures: dict       # règle → [Reecriture] (les sept règles à motifs)
    omission_proba: dict         # catégorie de type (article, modele_vehicule, client, autres) → probabilité en « lu »
    omission_mult_entendu: float
    omission_plafond: float
    omission_par_type: dict      # catégorie de type → {catégorie de mot oublié: poids}
    generiques: frozenset        # mots génériques des clients (normalisés)
    familiaux: frozenset
    exclus_generiques: frozenset
    absents_part: float
    absents_sensibilite: list
    entendu_sensibilite: list
    absents_nature: dict
    partage_negatif: dict
    longueur_min: int
    max_par_nom: dict            # calibration (analyse) | banc | certification → plafond (None : sans plafond)
    repartition: dict
    geo_banc: dict               # plus_peuples | au_hasard → poids
    nombre_plus_peuples: int
    voisins_distance_max: int    # attendu § 8 : un voisin est ajouté s'il est à ≤ min(d, cette borne)
    part_indice: float
    familles: dict               # famille → [types]
    source: dict = field(default_factory=dict)

    @classmethod
    def charger(cls, chemin: Path = MODELE) -> "Modele":
        y = load_yaml(chemin)
        if y.get("statut") != "valide":
            raise ModeleInvalide(f"{chemin.name} : statut « {y.get('statut')} », il faut « valide » pour générer.")
        modes = _poids(y["modes"], "modes", ignorer=("sensibilite_entendu",))
        nf = y["nombre_de_fautes"]
        fautes = {m: {int(k): v for k, v in _poids(nf[m], f"nombre_de_fautes.{m}").items()} for m in modes}
        if "classe_4" in nf:
            raise ModeleInvalide(f"{chemin.name} · nombre_de_fautes.classe_4 : clé supprimée en v0.3 ; chaque classe "
                                 "est maintenant un nombre exact de perturbations.")
        melange = {m: _poids(y["melange_fautes"][m], f"melange_fautes.{m}") for m in modes}
        cl = y["clavier"]
        if cl.get("disposition") != "azerty_be":
            raise ModeleInvalide(f"{chemin.name} · clavier.disposition : seule azerty_be est connue du générateur.")
        clavier = _poids(cl["types"], "clavier.types")
        inconnus = set(clavier) - {"omission", "substitution", "inversion", "insertion", "doublement", "espace"}
        if inconnus:
            raise ModeleInvalide(f"{chemin.name} · clavier.types : type(s) inconnu(s) {sorted(inconnus)}.")
        opts_espace = ("note", "fusion_mots_vides", "fusion_mots_a_chiffre", "coupure_morceau_min")
        espace = _poids(cl["espace"], "clavier.espace", ignorer=opts_espace) if "espace" in clavier else {}
        if espace and set(espace) != {"fusion", "coupure"}:
            raise ModeleInvalide(f"{chemin.name} · clavier.espace : fusion et coupure attendues.")
        ce = cl.get("espace", {})
        fusion_vides, fusion_chiffre = ce.get("fusion_mots_vides"), ce.get("fusion_mots_a_chiffre")
        morceau = ce.get("coupure_morceau_min")
        if espace and (not isinstance(fusion_vides, bool) or not isinstance(fusion_chiffre, bool)
                       or not isinstance(morceau, int) or morceau < 1):
            raise ModeleInvalide(f"{chemin.name} · clavier.espace : fusion_mots_vides et fusion_mots_a_chiffre "
                                 "(true / false) et coupure_morceau_min (entier ≥ 1) attendus.")
        choix = _poids(cl.get("choix_de_la_lettre", {"touche_voisine": 1.0}), "clavier.choix_de_la_lettre")
        if set(choix) - {"touche_voisine", "quelconque"}:
            raise ModeleInvalide(f"{chemin.name} · clavier.choix_de_la_lettre : touche_voisine et quelconque attendues.")
        regles = y["phonetique"]["regles"]
        phon = _poids(regles, "phonetique.regles")
        reecr = {k: sorted({rw for mo in v["motifs"] for rw in parser_motif(mo)},
                           key=lambda x: (x.src, x.dst, x.position))
                 for k, v in regles.items() if "motifs" in v}
        sans_motif = set(regles) - set(reecr)
        if sans_motif - {"transcription_libre"}:
            raise ModeleInvalide(f"{chemin.name} · phonetique.regles : règle(s) sans motifs {sorted(sans_motif)}.")
        transcription = {}
        if "transcription_libre" in regles:
            tl = regles["transcription_libre"]
            ou = f"{chemin.name} · phonetique.regles.transcription_libre"
            try:
                nbr = {int(k): v for k, v in _poids(tl["nombre_de_regles"], "transcription_libre.nombre_de_regles").items()}
                transcription = {"nb_regles": nbr, "tirage": tl["tirage_des_regles"],
                                 "proba_voyelle": float(tl["proba_voyelle_proche"]),
                                 "longueur_min": int(tl["longueur_min_mot"]),
                                 "voyelles": [tuple(str(x) for x in paire) for paire in tl["voyelles_proches"]]}
            except KeyError as k:
                raise ModeleInvalide(f"{ou} : clé {k} manquante.") from None
            if transcription["tirage"] not in ("pondere", "uniforme"):
                raise ModeleInvalide(f"{ou}.tirage_des_regles : « {transcription['tirage']} » (pondere ou uniforme).")
            if min(nbr) < 1 or not 0 <= transcription["proba_voyelle"] <= 1 or \
                    any(len(pr) != 2 for pr in transcription["voyelles"]):
                raise ModeleInvalide(f"{ou} : nombre_de_regles ≥ 1, proba_voyelle_proche entre 0 et 1, "
                                     "voyelles_proches en paires attendus.")
        om = y["omissions_de_mots"]
        par_type = {t: _poids(v, f"omissions_de_mots.par_famille.{t}")
                    for t, v in om["par_famille"].items() if isinstance(v, dict)}
        proba = {str(k): float(v) for k, v in om["probabilite_par_type"].items()}
        if set(proba) != set(par_type) or any(not 0 <= p <= 1 for p in proba.values()):
            raise ModeleInvalide(f"{chemin.name} · omissions_de_mots : probabilite_par_type {sorted(proba)} et "
                                 f"par_famille {sorted(par_type)} doivent avoir les mêmes clés, probabilités entre 0 et 1.")
        plafond = float(om["plafond"])
        if not 0 <= plafond <= 1:
            raise ModeleInvalide(f"{chemin.name} · omissions_de_mots.plafond : {plafond} (entre 0 et 1).")
        vmax = y["attendu"]["voisins_distance_max"]
        if not isinstance(vmax, int) or vmax < 0:
            raise ModeleInvalide(f"{chemin.name} · attendu.voisins_distance_max : « {vmax} » (entier ≥ 0).")
        mg = om["mots_generiques_clients"]
        nz = lambda xs: frozenset(normalize(x) for x in xs if normalize(x))
        ab = y["absents"]
        fam_path = ROOT / y["familles"]
        if not fam_path.exists():
            raise ModeleInvalide(f"{chemin.name} · familles : {y['familles']} introuvable.")
        familles = load_yaml(fam_path)["familles"]
        rep = _poids({k: v for k, v in y["repartition_par_famille"].items() if isinstance(v, (int, float))},
                     "repartition_par_famille")
        hors = set(rep) - set(familles)
        if hors:
            raise ModeleInvalide(f"{chemin.name} · repartition_par_famille : famille(s) {sorted(hors)} absente(s) "
                                 f"de {y['familles']}.")
        gb = y["repartition_par_famille"].get("geographie_dans_le_banc", {"au_hasard": 1.0})
        geo_banc = _poids(gb, "repartition_par_famille.geographie_dans_le_banc", ignorer=("note", "nombre_plus_peuples"))
        if set(geo_banc) - {"plus_peuples", "au_hasard"}:
            raise ModeleInvalide(f"{chemin.name} · geographie_dans_le_banc : plus_peuples et au_hasard attendues.")
        n_peuples = gb.get("nombre_plus_peuples", 0)
        if geo_banc.get("plus_peuples") and (not isinstance(n_peuples, int) or n_peuples < 1):
            raise ModeleInvalide(f"{chemin.name} · geographie_dans_le_banc.nombre_plus_peuples : entier ≥ 1 attendu.")
        ex = y["exclusions"]
        mx = ex["max_cas_par_nom"]
        if not isinstance(mx, dict) or not {"calibration", "banc"} <= set(mx) <= {"calibration", "banc", "certification"}:
            raise ModeleInvalide(f"{chemin.name} · exclusions.max_cas_par_nom : clés calibration, banc (et certification) "
                                 "attendues.")
        max_par_nom = {}
        for k, v in mx.items():
            if v == "sans_plafond":
                max_par_nom[k] = None
            elif isinstance(v, int) and v > 0:
                max_par_nom[k] = v
            else:
                raise ModeleInvalide(f"{chemin.name} · max_cas_par_nom.{k} : « {v} » (entier ou sans_plafond attendu).")
        max_par_nom.setdefault("certification", max_par_nom["calibration"])   # absente : comme l'analyse
        return cls(modes=modes, fautes=fautes, melange=melange, clavier=clavier, espace=espace, choix_lettre=choix,
                   fusion_mots_vides=bool(fusion_vides), fusion_mots_a_chiffre=bool(fusion_chiffre),
                   coupure_morceau_min=int(morceau or 1), transcription=transcription,
                   phon=phon, phon_reecritures=reecr,
                   omission_proba=proba, omission_mult_entendu=float(om["multiplicateur_entendu"]),
                   omission_plafond=plafond, omission_par_type=par_type, geo_banc=geo_banc,
                   nombre_plus_peuples=int(n_peuples), voisins_distance_max=vmax,
                   generiques=nz(mg["generiques"]), familiaux=nz(mg["complements_familiaux"]),
                   exclus_generiques=nz(mg["exclus_volontairement"]),
                   absents_part=float(ab["part"]), absents_sensibilite=list(ab["sensibilite"]),
                   entendu_sensibilite=list(y["modes"]["sensibilite_entendu"]),
                   absents_nature=_poids(ab["nature"], "absents.nature"),
                   partage_negatif=_poids({k: v for k, v in ab["partage_index_negatif"].items() if k != "graine"},
                                          "absents.partage_index_negatif"),
                   longueur_min=int(ex["longueur_minimale"]), max_par_nom=max_par_nom,
                   repartition=rep, part_indice=float(y["attendu"]["indice_de_type"]["part_avec_indice"]),
                   familles=familles, source={"version": y.get("version"), "date": str(y.get("date"))})

    def categorie_oubli(self, typ: str) -> str:
        """Clé de omissions_de_mots pour un type d'entité : le type lui-même s'il est nommé, sinon « autres »."""
        return typ if typ in self.omission_proba and typ != "autres" else "autres"

    def proba_oubli(self, typ: str, mode: str) -> float:
        """Probabilité d'oubli d'un mot (§ 4) : par type en « lu » ; × multiplicateur en « entendu », plafonnée."""
        p = self.omission_proba[self.categorie_oubli(typ)]
        if mode == "entendu":
            p = min(p * self.omission_mult_entendu, self.omission_plafond)
        return p

    def avec_parts(self, entendu: float | None = None, absents: float | None = None) -> "Modele":
        """Variante de sensibilité : autre part d'« entendu » (le reste en « lu ») ou d'absents."""
        import copy
        m = copy.copy(self)
        if entendu is not None:
            if set(self.modes) != {"lu", "entendu"} or not 0 <= entendu <= 1:
                raise ModeleInvalide(f"part d'entendu {entendu} invalide (entre 0 et 1, modes lu et entendu).")
            m.modes = {"lu": round(1 - entendu, 6), "entendu": float(entendu)}
        if absents is not None:
            if not 0 <= absents < 1:
                raise ModeleInvalide(f"part d'absents {absents} invalide (entre 0 et 1 exclu).")
            m.absents_part = float(absents)
        return m


def tirer(rng: random.Random, poids: dict):
    """Tirage pondéré déterministe (clés triées)."""
    cles = sorted(poids, key=str)
    return rng.choices(cles, weights=[poids[k] for k in cles])[0]


# ── perturbations ─────────────────────────────────────────────────────────────────────────────────

MOT = re.compile(r"\w+")


@dataclass(frozen=True)
class Saisie:
    terme: str
    perturbations: tuple[str, ...] = ()
    mots_oublies: tuple[str, ...] = ()
    forme_courte: str = ""


class Perturbateur:
    """Applique les fautes du modèle. Jamais sur la première lettre du nom, jamais sur un mot à chiffre
    (code, nombre), un mot vide ou un mot de moins de `longueur_min` lettres."""

    def __init__(self, modele: Modele):
        self.m = modele

    def mots_eligibles(self, texte: str) -> list[tuple[int, int]]:
        out = []
        for mo in MOT.finditer(texte):
            w = mo.group()
            if any(c.isdigit() for c in w) or "_" in w:
                continue
            if len(w) < self.m.longueur_min or normalize(w) in ("", *STOP) or w.lower() in STOP:
                continue
            out.append((mo.start(), mo.end()))
        return out

    def est_vide(self, w: str) -> bool:
        return normalize(w) in ("", *STOP) or w.lower() in STOP

    # sites clavier : (début, fin, remplacement) ; sous-type pour espace (fusion | coupure) et
    # pour substitution / insertion (touche_voisine | quelconque)
    def sites_clavier(self, t: str, typ: str, sous: str = "touche_voisine") -> list[tuple[int, int, str]]:
        sites = []
        if typ == "espace" and sous == "fusion":
            # deux mots voisins séparés seulement par des espaces ou tirets ; mots vides et mots à chiffre
            # selon clavier.espace ; la longueur minimale ne s'applique pas (« e tron » → « etron »)
            def permis(w: str) -> bool:
                if self.est_vide(w) and not self.m.fusion_mots_vides:
                    return False
                return self.m.fusion_mots_a_chiffre or not any(c.isdigit() for c in w)
            mots = list(MOT.finditer(t))
            for m1, m2 in zip(mots, mots[1:]):
                sep = t[m1.end():m2.start()]
                if sep and set(sep) <= {" ", "-"} and permis(m1.group()) and permis(m2.group()):
                    sites.append((m1.end(), m2.start(), ""))
            return sites
        lettres = (lambda c: VOISINS.get(c, ())) if sous == "touche_voisine" else (lambda c: ALPHABET)
        for a, b in self.mots_eligibles(t):
            for p in range(max(a, 1), b):
                c = t[p]
                if typ == "omission":
                    sites.append((p, p + 1, ""))
                elif typ == "substitution":
                    sites += [(p, p + 1, v) for v in lettres(c) if v != c]
                elif typ == "inversion":
                    if p + 1 < b and t[p + 1] != c:
                        sites.append((p, p + 2, t[p + 1] + c))
                elif typ == "insertion":
                    sites += [(p + 1, p + 1, v) for v in lettres(c)]
                elif typ == "doublement":
                    if p + 1 < b and t[p + 1] == c:
                        sites.append((p + 1, p + 2, ""))          # dédoublement
                    elif not (p > a and t[p - 1] == c):
                        sites.append((p + 1, p + 1, c))           # doublement
                elif typ == "espace" and sous == "coupure":
                    k = self.m.coupure_morceau_min
                    if p - a >= k and b - p >= k:                 # jamais un morceau trop court
                        sites.append((p, p, " "))
        return sites

    def sites_phonetiques(self, t: str, regle: str, spans=None) -> list[tuple[int, int, str, str]]:
        sites = []
        voyelles = "aeiouyàâäéèêëîïôöûüù"
        for a, b in (spans if spans is not None else self.mots_eligibles(t)):
            mot = t[a:b]
            for rw in self.m.phon_reecritures[regle]:
                if rw.position == "fin":
                    if rw.src and mot.endswith(rw.src) and b - len(rw.src) >= max(a, 1):
                        sites.append((b - len(rw.src), b, rw.dst, f"{rw.src or '∅'}→{rw.dst or '∅'}"))
                    elif not rw.src and not mot.endswith(rw.dst):
                        sites.append((b, b, rw.dst, f"∅→{rw.dst}"))
                elif rw.position == "debut":
                    if a == 0:
                        continue                                   # jamais la première lettre du nom
                    if rw.src and mot.startswith(rw.src) and len(mot) > len(rw.src):
                        sites.append((a, a + len(rw.src), rw.dst, f"{rw.src}→∅"))
                    elif not rw.src and mot[0] in voyelles:
                        sites.append((a, a, rw.dst, f"∅→{rw.dst}"))
                else:
                    i = mot.find(rw.src)
                    while i >= 0:
                        if a + i >= 1:
                            sites.append((a + i, a + i + len(rw.src), rw.dst, f"{rw.src}→{rw.dst}"))
                        i = mot.find(rw.src, i + 1)
        return sites

    def sites_voyelles(self, t: str, a: int, b: int) -> list[tuple[int, int, str, str]]:
        """Voyelle remplacée par une voyelle de son proche (a ↔ e, e ↔ i, o ↔ ou, u ↔ ou, i ↔ y)."""
        sites = []
        for x, y in self.m.transcription["voyelles"]:
            for src, dst in ((x, y), (y, x)):
                i = t.find(src, a, b)
                while 0 <= i and i + len(src) <= b:
                    j = i + len(src)
                    deja_ou = (src == "o" and t[j:j + 1] == "u") or (src == "u" and i > 0 and t[i - 1] == "o")
                    if i >= 1 and not deja_ou:
                        sites.append((i, j, dst, f"{src}→{dst}"))
                    i = t.find(src, i + 1, b)
        return sorted(set(sites))

    def transcription(self, rng: random.Random, t: str) -> tuple[str, str] | None:
        """transcription_libre (§ 3) : sur UN mot d'au moins longueur_min_mot lettres, un nombre de règles
        phonétiques tiré selon nombre_de_regles, chaque règle tirée selon tirage_des_regles parmi les règles
        à motifs (avec remise ; une règle sans site sur le mot est retirée du tirage), puis, avec la probabilité
        proba_voyelle_proche, une voyelle de son proche. Si aucun mot n'admet le plus petit nombre de règles : None."""
        tr = self.m.transcription
        spans = [(a, b) for a, b in self.mots_eligibles(t) if b - a >= tr["longueur_min"]]
        rng.shuffle(spans)
        poids7 = {k: (v if tr["tirage"] == "pondere" else 1.0)
                  for k, v in self.m.phon.items() if k in self.m.phon_reecritures}
        for a, b in spans:
            k = int(tirer(rng, tr["nb_regles"]))
            cur, fin, faites, pool = t, b, [], dict(poids7)
            etats = {normalize(t)}
            while len(faites) < k and pool:
                regle = tirer(rng, pool)
                sites = [s_ for s_ in self.sites_phonetiques(cur, regle, [(a, fin)])
                         if normalize(cur[:s_[0]] + s_[2] + cur[s_[1]:]) not in etats]
                if not sites:
                    del pool[regle]
                    continue
                x, y, r, motif = sites[rng.randrange(len(sites))]
                cur = cur[:x] + r + cur[y:]
                fin += len(r) - (y - x)
                etats.add(normalize(cur))
                faites.append(f"{regle}({motif})")
            if len(faites) < min(tr["nb_regles"]):
                continue
            if rng.random() < tr["proba_voyelle"]:
                sv = [s_ for s_ in self.sites_voyelles(cur, a, fin)
                      if normalize(cur[:s_[0]] + s_[2] + cur[s_[1]:]) not in etats]
                if sv:
                    x, y, r, motif = sv[rng.randrange(len(sv))]
                    cur = cur[:x] + r + cur[y:]
                    faites.append(f"voyelle({motif})")
            return cur, "phonetique:transcription_libre[" + " + ".join(faites) + "]"
        return None

    def une_faute(self, rng: random.Random, t: str, mode: str, essais: int = 12,
                  vus: frozenset = frozenset()) -> tuple[str, str] | None:
        """Une perturbation visible après normalisation, ou None si le texte n'en admet aucune.
        `vus` : formes normalisées déjà atteintes ; une perturbation qui y ramène (e → ai puis ai → e)
        ne compte pas et est retirée."""
        vus = vus | {normalize(t)}
        ok = lambda x: normalize(x) not in vus and x[:1] == t[:1] and normalize(x)
        for _ in range(essais):
            sorte = tirer(rng, self.m.melange[mode])
            if sorte == "clavier":
                typ = tirer(rng, self.m.clavier)
                sous = (tirer(rng, self.m.espace) if typ == "espace" else
                        tirer(rng, self.m.choix_lettre) if typ in ("substitution", "insertion") else "")
                sites = self.sites_clavier(t, typ, sous or "touche_voisine")
                if not sites:
                    continue
                a, b, r = sites[rng.randrange(len(sites))]
                label = f"clavier:{typ}" + (f"({sous})" if sous else "")
            else:
                regle = tirer(rng, self.m.phon)
                if regle not in self.m.phon_reecritures:
                    res = self.transcription(rng, t)
                    if res is None:
                        continue
                    nouveau, label = res
                    if ok(nouveau):
                        return nouveau, label
                    continue
                sites = self.sites_phonetiques(t, regle)
                if not sites:
                    continue
                a, b, r, motif = sites[rng.randrange(len(sites))]
                label = f"phonetique:{regle}({motif})"
            nouveau = t[:a] + r + t[b:]
            if ok(nouveau):
                return nouveau, label
        return None

    def nb_fautes(self, rng: random.Random, mode: str) -> int:
        """Nombre de perturbations (§ 2)."""
        return int(tirer(rng, self.m.fautes[mode]))

    def fautes(self, rng: random.Random, t: str, mode: str, n: int) -> tuple[str, list[str]]:
        labels, vus = [], set()
        for _ in range(n):
            r = self.une_faute(rng, t, mode, vus=frozenset(vus))
            if r is None:
                break
            vus.add(normalize(t))
            t, lab = r
            labels.append(lab)
        return t, labels


# ── contexte : catalogue, noms, réponse attendue ──────────────────────────────────────────────────

def distance(a: str, b: str) -> int:
    """Distance OSA entre deux formes normalisées, en ordre d'origine et en mots triés (le minimum)."""
    return min(OSA.distance(a, b), OSA.distance(cle_triee(a), cle_triee(b)))


def entites_exclues_test() -> frozenset[str]:
    """Entités attendues dans la partition test de challenges/ : jamais utilisées (lecture mécanique,
    comme build/tirage_echantillon_reel.py ; aucun texte de cas n'est lu)."""
    split = {r["case_id"]: r["split"] for r in read_csv(CHAL / "split.csv")}
    out = set()
    for c in read_csv(CHAL / "cases.csv"):
        if split.get(c["case_id"]) == "test":
            out.update(i for i in c["expected_ids"].split("|") if i)
    return frozenset(out)


class Contexte:
    """Catalogue chargé une fois : noms sources, pools de noms par type, réponse attendue (§ 8)."""

    def __init__(self, modele: Modele, cat: Catalogue | None = None):
        self.m = modele
        self.cat = cat or Catalogue.charger()
        self.exact = ResolveurExact(self.cat)
        self.exclus = entites_exclues_test()
        self.ents = {e["entity_id"]: e for e in read_csv(ROOT / "catalog" / "entities.csv")}
        self.famille_de = {t: f for f, ts in modele.familles.items() for t in ts}
        noms_type = defaultdict(set)
        mots_type = defaultdict(lambda: defaultdict(set))
        for nom, ids in self.cat.noms.items():
            for e in ids:
                t = self.cat.etype[e]
                noms_type[t].add(nom)
                for w in set(nom.split()):
                    mots_type[t][w].add(e)
        self.noms_type = {t: sorted(v) for t, v in noms_type.items()}
        self.tries_type = {t: [cle_triee(n) for n in v] for t, v in self.noms_type.items()}
        self.mots_type = mots_type
        self.tous_noms = sorted(self.cat.noms)
        gam = [normalize(e["label"]) for e in self.ents.values() if e["entity_type"] == "gamme"]
        self.gammes = frozenset(g for g in gam if g)

    # noms
    def nom_source(self, eid: str) -> str:
        return nom_a_dicter(self.ents[eid], self.ents)

    def familles_de_nom(self, nom_norm: str) -> set[str]:
        return {self.famille_de.get(self.cat.etype[e], "hors_famille") for e in self.cat.noms.get(nom_norm, ())}

    def trouve_exact(self, norm: str) -> set[str]:
        return self.exact.candidats_exacts(norm)[0] if norm else set()

    def plus_proche(self, norm: str) -> tuple[str, float]:
        r = process.extractOne(norm, self.tous_noms, scorer=JaroWinkler.normalized_similarity)
        return (r[0], r[1]) if r else ("", 0.0)

    # réponse attendue
    def voisins(self, t: str, d: int, types: set[str]) -> set[str]:
        """Noms des types donnés à une distance OSA ≤ d du terme (ordre d'origine ou mots triés)."""
        out = set()
        for ty in sorted(types):
            noms = self.noms_type.get(ty, [])
            out.update(n for n, _, _ in process.extract(t, noms, scorer=OSA.distance, score_cutoff=d, limit=None))
            tries = self.tries_type.get(ty, [])
            out.update(noms[i] for _, _, i in process.extract(cle_triee(t), tries, scorer=OSA.distance,
                                                              score_cutoff=d, limit=None))
        return out

    def compatibles(self, court: str, types: set[str]) -> set[str]:
        """Entités des types donnés dont un nom contient tous les mots de la forme courte."""
        mots = court.split()
        out = set()
        for ty in types:
            idx = self.mots_type.get(ty, {})
            if not mots or any(w not in idx for w in mots):
                continue
            out |= set.intersection(*(idx[w] for w in mots))
        return out

    def appliquer(self, bruts: set[str], hint: str | None) -> set[str]:
        return self.cat.regles.apply(set(bruts), {hint} if hint else None)

    def attendu(self, terme: str, source_norm: str, eid: str | None, court_norm: str | None,
                hint: str | None) -> dict:
        """Réponse attendue d'une saisie présente (modèle § 8).

        source_norm : nom source normalisé ; court_norm : forme après mots oubliés (None si aucun).
        - nom source homonyme : ce que donne l'exact sur le nom source ;
        - mot oublié : l'entité désignée par la forme courte (exact), sinon toutes les entités du même type
          dont un nom contient tous ses mots ;
        - faute : on ajoute tout nom du même type à une distance OSA ≤ min(d, voisins_distance_max), d étant la
          distance du nom visé (un nom plus proche que la source reste compatible).
        Les règles de contexte et l'indice de type s'appliquent ensuite, comme dans le moteur."""
        t = normalize(terme)
        vise = court_norm if court_norm is not None else source_norm
        types_src = {self.cat.etype[eid]} if eid else set()
        if court_norm is not None and court_norm != source_norm:
            base = self.trouve_exact(court_norm) or self.compatibles(court_norm, types_src)
        else:
            base = self.trouve_exact(source_norm)
        d = distance(t, vise) if t != vise else 0
        ajoutes = set()
        noms_voisins = []
        if d > 0:
            types = {self.cat.etype[e] for e in base} or types_src
            for n in sorted(self.voisins(t, min(d, self.m.voisins_distance_max), types)):
                ids = {e for e in self.cat.noms[n] if self.cat.etype[e] in types} - base
                if ids:
                    noms_voisins.append(n)
                    ajoutes |= ids
        hits = self.appliquer(base | ajoutes, hint)
        return {"statut": self.cat.regles.status(hits), "ids": sorted(hits), "distance": d,
                "voisins": noms_voisins, "vise": vise}


# ── omissions de mots ─────────────────────────────────────────────────────────────────────────────

def _sans(mots: list[str], i: int) -> list[str]:
    out = mots[:i] + mots[i + 1:]
    while out and normalize(out[-1]) == "" and not any(c.isalnum() for c in out[-1]):
        out = out[:-1]     # « Dupont & » → « Dupont »
    return out


def omettre(ctx: Contexte, rng: random.Random, eid: str, nom: str) -> tuple[str, list[str]] | None:
    """Oublie un mot selon le type de l'entité (modèle § 4). None si aucune catégorie n'est applicable."""
    e = ctx.ents[eid]
    poids = dict(ctx.m.omission_par_type.get(ctx.m.categorie_oubli(e["entity_type"]), {}))
    while poids:
        cat_ = tirer(rng, poids)
        r = _omettre_categorie(ctx, rng, e, nom, cat_)
        if r:
            return r[0], [f"{cat_}:{w}" for w in r[1]]
        del poids[cat_]
        if poids and sum(poids.values()) <= 0:
            break
    return None


def _omettre_categorie(ctx: Contexte, rng, e: dict, nom: str, categorie: str):
    typ = e["entity_type"]
    if typ == "article":
        if " – " not in nom:
            return None
        tete, reste = nom.split(" – ", 1)
        mots = reste.split()
        gamme = [w for w in mots if normalize(w) in ctx.gammes]
        marque = [w for w in mots if normalize(w) not in ctx.gammes]
        if categorie == "marque" and marque and gamme:
            return f"{tete} {' '.join(gamme)}", [" ".join(marque)]
        if categorie == "gamme" and gamme and marque:
            return f"{tete} {' '.join(marque)}", [" ".join(gamme)]
        if categorie == "tete":
            mt = tete.split()
            if len(mt) >= 2:
                reste_tete = re.sub(r"^[dl]['’]", "", " ".join(mt[1:]))
                return f"{reste_tete} {reste}", [mt[0]]
        return None
    if typ == "client":
        mots = nom.split()
        gen = ctx.m.generiques | ctx.m.familiaux
        est_gen = [normalize(w) in gen for w in mots]
        distinctifs = [i for i, w in enumerate(mots) if not est_gen[i] and normalize(w)]
        if categorie == "mot_generique":
            cand = [i for i, g in enumerate(est_gen) if g]
            if cand and distinctifs:
                i = cand[rng.randrange(len(cand))]
                return " ".join(_sans(mots, i)), [mots[i]]
        if categorie == "complement" and distinctifs and len(mots) >= 2:
            i = distinctifs[-1]
            reste = _sans(mots, i)
            if any(normalize(w) for w in reste):
                return " ".join(reste), [mots[i]]
        return None
    if typ == "modele_vehicule":
        marque = ctx.ents.get(e["parent_id"], {}).get("label", "")
        mots = nom.split()
        nb_marque = len(marque.split()) if marque and nom.lower().startswith(marque.lower() + " ") else 0
        modele = mots[nb_marque:]
        if categorie == "version_finale" and len(modele) >= 2:
            return " ".join(mots[:-1]), [mots[-1]]
        if categorie == "marque" and nb_marque and modele:
            return " ".join(modele), [" ".join(mots[:nb_marque])]
        return None
    if categorie == "dernier_mot":
        # autres types : le dernier mot (« Sint-Lambrechts-Woluwe » → « Sint-Lambrechts ») ; tirets et
        # espaces séparent les mots ; il faut au moins deux mots
        mots = list(MOT.finditer(nom))
        if len(mots) < 2:
            return None
        reste = nom[:mots[-1].start()].rstrip(" -–'’&,")
        if not normalize(reste):
            return None
        return reste, [mots[-1].group()]
    return None


# ── génération d'un jeu ───────────────────────────────────────────────────────────────────────────

@dataclass
class Plan:
    jeu: str                       # banc | analyse | certif
    graine: int
    calibration: bool              # True : seules les saisies qui atteignent l'approché
    volume_famille: dict           # famille → saisies présentes visées
    part_absents: float
    codes_voisins: int = 0
    suffixe: str = ""


def lire_absents(nom: str) -> list[dict]:
    """Liste de spec/absents/ (séparateur « ; »). Colonnes contrôlées : terme, et valide quand elle existe."""
    import csv
    chemin = ABSENTS / nom
    with chemin.open(encoding="utf-8-sig", newline="") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    for i, r in enumerate(lignes, 2):
        if not (r.get("terme") or "").strip():
            raise ValueError(f"{chemin.relative_to(ROOT)} · ligne {i} : colonne terme vide.")
        if "valide" in r and r["valide"] not in ("ok", "non"):
            raise ValueError(f"{chemin.relative_to(ROOT)} · ligne {i} : valide = « {r['valide']} », ok ou non attendu.")
    return lignes


def partage_negatifs(cat: Catalogue, modele: Modele, graine: int = GRAINE_NEGATIFS) -> tuple[list[str], list[str]]:
    """Lieux de l'index négatif partagés en deux : (gardés, retirés). Les retirés sont les « absents
    inconnus » : retirés de l'index CHARGÉ pendant l'évaluation des jeux, jamais de catalog/negatifs.csv."""
    lieux = sorted(k for k, (_, ra) in cat.negatifs.items() if ra == "lieu")
    rng = random.Random(graine)
    rng.shuffle(lieux)
    n_ret = round(len(lieux) * modele.partage_negatif["absents_inconnus"])
    return sorted(lieux[n_ret:]), sorted(lieux[:n_ret])


class Generateur:
    def __init__(self, ctx: Contexte, modele: Modele, plan: Plan, retires: set[str], interdits: set[str] = frozenset()):
        self.ctx, self.m, self.plan = ctx, modele, plan
        self.rng = random.Random(plan.graine)
        self.pert = Perturbateur(modele)
        self.retires = retires
        self.interdits = set(interdits)      # termes normalisés d'un autre jeu (analyse ↔ certif)
        self.vus: set[str] = set()
        self.par_nom: Counter = Counter()
        self.rejets: Counter = Counter()
        self.peuples_banc = 0              # saisies géographiques du banc tirées parmi les plus peuplés
        # Plafond de cas par nom (exclusions.max_cas_par_nom, par jeu) : calibration 3, banc sans plafond.
        cle = "banc" if not plan.calibration else "certification" if plan.jeu == "certif" else "calibration"
        cap = modele.max_par_nom[cle]
        self.cap = cap if cap is not None else 10 ** 9
        # Certification sans plafond : tirages indépendants, un même terme fautif peut revenir s'il est tiré deux
        # fois (décision de l'auteur, 17/11/2026). L'analyse garde un terme au plus une fois.
        self.doublons = plan.jeu == "certif" and cap is None

    # filtre commun
    def atteint_approche(self, norm: str) -> bool:
        """Le terme passerait l'exact et l'index négatif (tel que chargé pour l'évaluation des jeux)."""
        if not norm or self.ctx.trouve_exact(norm):
            return False
        neg = self.ctx.cat.negatifs.get(norm)
        return not (neg and norm not in self.retires)

    def accepter(self, norm: str) -> bool:
        if norm in self.interdits:
            self.rejets["terme d'un autre jeu"] += 1
            return False
        if self.plan.calibration and not self.doublons and norm in self.vus:
            self.rejets["terme déjà présent dans le jeu"] += 1
            return False
        return True

    def tirer_mode(self) -> str:
        return tirer(self.rng, self.m.modes)

    def indice(self, typ: str) -> str:
        return typ if self.rng.random() < self.m.part_indice else ""

    # présents
    def taper(self, eid: str, mode: str) -> tuple[str, list[str], list[str], str | None]:
        """Ce qu'un utilisateur tape pour l'entité, dans un mode donné (modèle § 2 à 4) :
        (terme, perturbations, mots oubliés, forme courte normalisée ou None)."""
        nom = self.ctx.nom_source(eid)
        texte = nom.replace(" – ", " ")
        court_norm, oublies = None, []
        if self.rng.random() < self.m.proba_oubli(self.ctx.cat.etype[eid], mode):
            r = omettre(self.ctx, self.rng, eid, nom)
            if r:
                texte, oublies = r[0].replace(" – ", " "), r[1]
                court_norm = normalize(texte)
        n = self.pert.nb_fautes(self.rng, mode)
        terme, labels = self.pert.fautes(self.rng, texte.lower(), mode, n)
        return terme, labels, oublies, court_norm

    def present(self, eid: str) -> dict | None:
        ctx = self.ctx
        nom = ctx.nom_source(eid)
        src_norm = normalize(nom)
        mode = self.tirer_mode()
        terme, labels, oublies, court_norm = self.taper(eid, mode)
        norm = normalize(terme)
        if self.plan.calibration and not labels and not oublies:
            self.rejets["0 faute et aucun mot oublié (calibration)"] += 1
            return None
        atteint = self.atteint_approche(norm)
        if self.plan.calibration and not atteint:
            self.rejets["trouvé par l'exact ou l'index négatif (calibration)"] += 1
            return None
        if not self.accepter(norm):
            return None
        typ = ctx.cat.etype[eid]
        hint = self.indice(typ)
        att = ctx.attendu(terme, src_norm, eid, court_norm, hint or None)
        if not att["ids"] and att["statut"] != "unknown":
            raise AssertionError(f"réponse attendue incohérente pour {eid}")
        if set(att["ids"]) & ctx.exclus:
            self.rejets["réponse attendue avec une entité de la partition test"] += 1
            return None
        self.vus.add(norm)
        return self.ligne(famille=ctx.famille_de[typ], mode=mode, terme=terme, norm=norm, hint=hint, att=att,
                          nature="present", sous=("mot_oublie" if oublies else "faute" if labels else "exact"),
                          labels=labels, oublies=oublies, nom=nom, eid=eid, atteint=atteint,
                          court=court_norm or "")

    def ligne(self, *, famille, mode, terme, norm, hint, att, nature, sous, labels, oublies, nom, eid, atteint, court=""):
        return {"jeu": self.plan.jeu + self.plan.suffixe, "graine": self.plan.graine, "famille": famille,
                "mode": mode, "terme": terme, "terme_norm": norm, "indice_type": hint,
                "attendu_statut": att["statut"], "attendu_ids": "|".join(att["ids"]),
                "nature": nature, "sous_nature": sous, "perturbations": " ; ".join(labels),
                "nb_perturbations": len(labels), "mots_oublies": " ; ".join(oublies),
                "forme_courte": court,  # forme après mots oubliés, notée à la génération (vide sans oubli)
                "distance": att.get("distance", ""), "voisins": "|".join(att.get("voisins", [])[:10]),
                "nom_source": nom, "entity_id_source": eid, "atteint_approche": int(atteint)}

    def eligibles(self, famille: str) -> list[str]:
        """Entités de la famille dont le nom source mène à l'entité par l'exact, hors partition test."""
        cache = self.ctx.__dict__.setdefault("_eligibles", {})
        if famille not in cache:
            cache[famille] = self._eligibles(famille)
        return list(cache[famille])

    def _eligibles(self, famille: str) -> list[str]:
        ctx = self.ctx
        out = []
        for eid, e in sorted(ctx.ents.items()):
            if e["entity_type"] not in self.m.familles[famille] or eid in ctx.exclus:
                continue
            nom = ctx.nom_source(eid)
            norm = normalize(nom)
            if not norm or eid not in ctx.trouve_exact(norm):
                continue          # le nom source ne mène pas à l'entité : inutilisable
            out.append(eid)
        return out

    def plus_peuples(self) -> list[str]:
        """Les nombre_plus_peuples lieux éligibles les plus peuplés (même règle que tirage_echantillon_reel)."""
        cache = self.ctx.__dict__.setdefault("_plus_peuples", {})
        if "geo" not in cache:
            pop = [e for e in self.eligibles("geographie") if (self.ctx.ents[e]["population"] or "").strip()]
            pop.sort(key=lambda e: (-float(self.ctx.ents[e]["population"]), e))
            cache["geo"] = pop[:self.m.nombre_plus_peuples]
        return list(cache["geo"])

    def presents_geo_banc(self, cible: int) -> list[dict]:
        """Géographie du banc (§ 7, v0.2) : chaque saisie vient, selon geographie_dans_le_banc, des lieux les
        plus peuplés ou de tous les lieux éligibles (tirage avec remise ; le banc n'a pas de plafond)."""
        pools = {"plus_peuples": self.plus_peuples(), "au_hasard": self.eligibles("geographie")}
        lignes, essais = [], 0
        while len(lignes) < cible and essais < cible * 20:
            essais += 1
            pool = pools[tirer(self.rng, self.m.geo_banc)]
            eid = pool[self.rng.randrange(len(pool))]
            cle = normalize(self.ctx.nom_source(eid))
            if self.par_nom[cle] >= self.cap:
                continue
            l = self.present(eid)
            if l is None:
                continue
            self.peuples_banc += eid in pools["plus_peuples"]
            self.par_nom[cle] += 1
            lignes.append(l)
        return lignes

    def presents(self, famille: str, cible: int) -> list[dict]:
        if famille == "geographie" and not self.plan.calibration and "plus_peuples" in self.m.geo_banc:
            return self.presents_geo_banc(cible)
        pool = self.eligibles(famille)
        self.rng.shuffle(pool)
        lignes = []
        cap = self.cap
        i, sans_progres = 0, 0
        while len(lignes) < cible and pool and sans_progres < len(pool) * 4:
            eid = pool[i % len(pool)]
            i += 1
            cle = normalize(self.ctx.nom_source(eid))
            if self.par_nom[cle] >= cap:
                sans_progres += 1
                continue
            l = self.present(eid)
            if l is None:
                sans_progres += 1
                continue
            sans_progres = 0
            self.par_nom[cle] += 1
            lignes.append(l)
        return lignes

    # absents
    def stocks_absents(self, gardes: list[str]) -> dict[str, list[tuple[str, str]]]:
        """Termes absents disponibles par nature : (terme, sous-nature). Un terme trouvé par l'exact est écarté."""
        st = {
            "notions_metier": [(r["terme"], "notion_metier") for r in lire_absents("notions_metier.csv")
                               if r["valide"] == "ok"],
            "marques_hors_catalogue": [(r["terme"], "marque_hors_catalogue")
                                       for r in lire_absents("marques_hors_catalogue.csv") if r["valide"] == "ok"],
            "synonyme_manquant": [(r["terme"], "synonyme_manquant") for r in lire_absents("synonymes_manquants.csv")],
        }
        trouves = {k: [t for t, _ in v if self.ctx.trouve_exact(normalize(t))] for k, v in st.items()}
        st = {k: [(t, s) for t, s in v if not self.ctx.trouve_exact(normalize(t)) and normalize(t)]
              for k, v in st.items()}
        terme_neg = {k: v[0] for k, v in self.ctx.cat.negatifs.items()}
        st["lieux_hors_perimetre"] = ([(terme_neg[k], "lieu_index_negatif") for k in gardes] +
                                      [(terme_neg[k], "lieu_inconnu") for k in sorted(self.retires)])
        self.absents_trouves = {k: v for k, v in trouves.items() if v}
        return st

    def repartir_absents(self, total: int, stocks: dict) -> dict[str, int]:
        """Répartition par nature selon les poids ; ce qui manque (plafond de cas par terme) est reporté
        sur les lieux hors périmètre, puis sur les noms recombinés (décision de l'auteur, 16/11/2026)."""
        cap = {k: len(v) * self.cap for k, v in stocks.items()}
        cap["noms_recombines"] = 10 ** 9
        brut = {k: total * w for k, w in self.m.absents_nature.items()}
        alloc = {k: int(v) for k, v in brut.items()}
        reste = total - sum(alloc.values())
        for k in sorted(brut, key=lambda k: (-(brut[k] - int(brut[k])), k))[:reste]:
            alloc[k] += 1
        manque = 0
        for k in alloc:
            if alloc[k] > cap.get(k, 0):
                manque += alloc[k] - cap[k]
                alloc[k] = cap[k]
        self.report_absents = manque
        for k in ("lieux_hors_perimetre", "noms_recombines"):
            add = min(manque, cap[k] - alloc[k])
            alloc[k] += add
            manque -= add
        return alloc

    def absent(self, terme: str, nature: str, sous: str, nom_source: str = "") -> dict | None:
        mode = self.tirer_mode()
        n = self.pert.nb_fautes(self.rng, mode)
        tape, labels = self.pert.fautes(self.rng, terme.lower(), mode, n)
        norm = normalize(tape)
        if not norm or self.ctx.trouve_exact(norm):
            self.rejets["absent devenu un nom du catalogue"] += 1
            return None
        atteint = self.atteint_approche(norm)
        if self.plan.calibration and not atteint:
            self.rejets["absent arrêté par l'index négatif (calibration)"] += 1
            return None
        if not self.accepter(norm):
            return None
        proche, _ = self.ctx.plus_proche(norm)
        fams = self.ctx.familles_de_nom(proche) - {"hors_famille"}
        famille = next(iter(fams)) if len(fams) == 1 else "mixte"
        types = sorted({self.ctx.cat.etype[e] for e in self.ctx.cat.noms.get(proche, ())})
        hint = self.indice(types[0]) if types else ""
        self.vus.add(norm)
        att = {"statut": "unknown", "ids": [], "distance": "", "voisins": [proche]}
        return self.ligne(famille=famille, mode=mode, terme=tape, norm=norm, hint=hint, att=att, nature="absent",
                          sous=sous, labels=labels, oublies=[], nom=nom_source or terme, eid="", atteint=atteint)

    def recombine(self) -> tuple[str, str] | None:
        """Nom recombiné : un mot long d'un nom du catalogue remplacé par un mot long d'un autre nom du même type."""
        ctx = self.ctx
        fam = tirer(self.rng, self.m.repartition) if not self.plan.calibration else \
            sorted(self.plan.volume_famille)[self.rng.randrange(len(self.plan.volume_famille))]
        pool = self.eligibles(fam)
        if not pool:
            return None
        eid = pool[self.rng.randrange(len(pool))]
        nom = ctx.nom_source(eid).replace(" – ", " ")
        spans = self.pert.mots_eligibles(nom)
        if len(nom.split()) < 2 or not spans:
            return None
        a, b = spans[self.rng.randrange(len(spans))]
        autre = pool[self.rng.randrange(len(pool))]
        mots = [m for m in self.pert.mots_eligibles(ctx.nom_source(autre))]
        if not mots:
            return None
        x, y = mots[self.rng.randrange(len(mots))]
        mot = ctx.nom_source(autre)[x:y]
        if normalize(mot) == normalize(nom[a:b]):
            return None
        nouveau = nom[:a] + mot.lower() + nom[b:]
        norm = normalize(nouveau)
        if ctx.trouve_exact(norm) or norm in ctx.cat.negatifs:
            return None
        return nouveau, nom

    def absents(self, total: int, gardes: list[str]) -> list[dict]:
        stocks = self.stocks_absents(gardes)
        alloc = self.repartir_absents(total, stocks)
        self.alloc_absents = dict(alloc)
        lignes = []
        for nature in sorted(alloc):
            cible = alloc[nature]
            if nature == "noms_recombines":
                essais = 0
                while sum(l["sous_nature"] == "nom_recombine" for l in lignes) < cible and essais < cible * 50:
                    essais += 1
                    r = self.recombine()
                    if r and self.par_nom[("abs", normalize(r[0]))] < self.cap:
                        l = self.absent(r[0], nature, "nom_recombine", r[1])
                        if l:
                            self.par_nom[("abs", normalize(r[0]))] += 1
                            lignes.append(l)
                continue
            if nature == "lieux_hors_perimetre":
                parts = {"lieu_index_negatif": round(cible * self.m.partage_negatif["reste_dans_index"])}
                parts["lieu_inconnu"] = cible - parts["lieu_index_negatif"]
            else:
                parts = {stocks[nature][0][1]: cible} if stocks[nature] else {}
            for sous, n in sorted(parts.items()):
                termes = [t for t, s in stocks[nature] if s == sous]
                self.rng.shuffle(termes)
                i, faits, sans_progres = 0, 0, 0
                while faits < n and termes and sans_progres < len(termes) * 4:
                    t = termes[i % len(termes)]
                    i += 1
                    cle = ("abs", normalize(t))
                    if self.par_nom[cle] >= self.cap:
                        sans_progres += 1
                        continue
                    l = self.absent(t, nature, sous)
                    if l is None:
                        sans_progres += 1
                        continue
                    sans_progres = 0
                    self.par_nom[cle] += 1
                    faits += 1
                    lignes.append(l)
        return lignes

    def codes_voisins(self, n: int) -> list[dict]:
        """Codes voisins (banc seulement) : une référence Mécanova dont le dernier chiffre change et qui
        n'existe pas. Attendu : unknown. Vérifie que le moteur ne rapproche jamais deux codes."""
        ctx = self.ctx
        refs = sorted({a["alias"] for a in read_csv(ROOT / "catalog" / "aliases.csv")
                       if a["alias_type"] == "reference_mecanova" and a["entity_id"] not in ctx.exclus})
        self.rng.shuffle(refs)
        out = []
        for ref in refs:
            if len(out) >= n:
                break
            if not ref[-1].isdigit():
                continue
            autre = ref[:-1] + str((int(ref[-1]) + 1 + self.rng.randrange(9)) % 10)
            if ctx.trouve_exact(normalize(autre)):
                continue
            att = {"statut": "unknown", "ids": [], "distance": 1, "voisins": [normalize(ref)]}
            out.append(self.ligne(famille="pieces", mode="lu", terme=autre, norm=normalize(autre), hint="",
                                  att=att, nature="absent", sous="code_voisin", labels=["code:chiffre_voisin"],
                                  oublies=[], nom=ref, eid="", atteint=self.atteint_approche(normalize(autre))))
        return out

    def generer(self, gardes: list[str]) -> list[dict]:
        lignes = []
        for fam in sorted(self.plan.volume_famille):
            lignes += self.presents(fam, self.plan.volume_famille[fam])
        n_pres = len(lignes)
        total_abs = round(self.plan.part_absents / (1 - self.plan.part_absents) * n_pres)
        lignes += self.absents(total_abs, gardes)
        if self.plan.codes_voisins:
            lignes += self.codes_voisins(self.plan.codes_voisins)
        ordre = list(range(len(lignes)))
        self.rng.shuffle(ordre)
        pref = PREFIXES[self.plan.jeu] + (self.plan.suffixe.replace(".", "") if self.plan.suffixe else "")
        out = []
        for k, i in enumerate(ordre, 1):
            l = dict(lignes[i])
            l["case_id"] = f"{pref}-{k:05d}"
            out.append(l)
        return sorted(out, key=lambda l: l["case_id"])


# ── jeux ──────────────────────────────────────────────────────────────────────────────────────────

def plan_jeu(jeu: str, modele: Modele, suffixe: str = "", volume_banc: int = VOLUME_BANC,
             volume_calib: int = VOLUME_CALIB, graines: dict | None = None, volume_geo: int | None = None) -> Plan:
    graines = graines or GRAINES
    if jeu == "banc":
        n_pres = round(volume_banc * (1 - modele.absents_part))
        vol = {f: round(n_pres * w) for f, w in modele.repartition.items()}
        return Plan("banc", graines["banc"], False, vol, modele.absents_part, CODES_BANC, suffixe)
    vol = {f: (volume_geo if f == "geographie" and volume_geo else volume_calib) for f in sorted(modele.familles)}
    return Plan(jeu, graines[jeu], True, vol, modele.absents_part, 0, suffixe)


def generer_pessimiste(args, ctx_central: Contexte, ret: set[str], gardes: list[str], meta: dict) -> None:
    """Scénario pessimiste : banc et certification depuis spec/modele_saisie_pessimiste.yaml.
    La certification pessimiste n'a aucun terme normalisé commun avec l'analyse (v0.3), comme la certification
    centrale. Même catalogue, même partage de l'index négatif que les jeux centraux."""
    modele = Modele.charger(MODELE_PESSIMISTE)
    ctx = Contexte(modele, ctx_central.cat)
    chemin_a = CHAL / "saisies_analyse.csv"
    if not chemin_a.exists():
        raise FileNotFoundError(f"{chemin_a} introuvable : générer l'analyse avant la certification pessimiste.")
    interdits_certif = {r["terme_norm"] for r in read_csv(chemin_a)}
    meta["scenario_pessimiste"] = {"modele": modele.source, "fichier_modele": str(MODELE_PESSIMISTE.relative_to(ROOT)).replace("\\", "/"),
                                   "graines": GRAINES_PESSIMISTE}
    for jeu in [j for j in ("banc", "certif") if j in args.jeux]:
        plan = plan_jeu(jeu, modele, SUFFIXE_PESSIMISTE, args.volume_banc,
                        args.volume_certif if jeu == "certif" else args.volume_calib, GRAINES_PESSIMISTE,
                        args.volume_certif_geo if jeu == "certif" else None)
        lignes, info = generer_jeu(ctx, modele, plan, ret, gardes, interdits_certif if jeu == "certif" else set())
        chemin = CHAL / f"saisies_{jeu}{SUFFIXE_PESSIMISTE}.csv"
        write_csv(chemin, lignes, COLONNES)
        info["fichier"] = str(chemin.relative_to(ROOT)).replace("\\", "/")
        info["sha256"] = empreinte(chemin)
        info["scenario"] = "pessimiste"
        meta["jeux"][f"{jeu}{SUFFIXE_PESSIMISTE}"] = info
        print(f"{info['fichier']} : {info['cas']} cas (graine {plan.graine}), présents "
              + ", ".join(f"{f} {n}" for f, n in info["presents_par_famille"].items())
              + f" ; absents {sum(info['absents_par_sous_nature'].values())}")


def generer_jeu(ctx: Contexte, modele: Modele, plan: Plan, retires: set[str], gardes: list[str],
                interdits: set[str] = frozenset()) -> tuple[list[dict], dict]:
    g = Generateur(ctx, modele, plan, retires, interdits)
    lignes = g.generer(gardes)
    pres = [l for l in lignes if l["nature"] == "present"]
    info = {
        "graine": plan.graine, "part_entendu": modele.modes.get("entendu"), "part_absents": plan.part_absents,
        "cas": len(lignes),
        "presents_par_famille": dict(sorted(Counter(l["famille"] for l in pres).items())),
        "presents_vises": plan.volume_famille,
        "absents_par_sous_nature": dict(sorted(Counter(l["sous_nature"] for l in lignes if l["nature"] == "absent").items())),
        "absents_par_famille": dict(sorted(Counter(l["famille"] for l in lignes if l["nature"] == "absent").items())),
        "absents_alloues": getattr(g, "alloc_absents", {}),
        "absents_reportes_faute_de_stock": getattr(g, "report_absents", 0),
        "absents_ecartes_trouves_par_exact": getattr(g, "absents_trouves", {}),
        "modes": dict(sorted(Counter(l["mode"] for l in lignes).items())),
        "geographie_plus_peuples": g.peuples_banc,
        "rejets": dict(sorted(g.rejets.items())),
    }
    return lignes, info


def empreinte(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def frequences_generiques(ctx: Contexte, seuil: float = 0.01) -> list[tuple[str, float]]:
    """Mots des noms de clients à plus de `seuil` de fréquence absents des trois listes du modèle."""
    clients = [e for e in ctx.ents.values() if e["entity_type"] == "client"]
    c = Counter()
    for e in clients:
        c.update(set(normalize(ctx.nom_source(e["entity_id"])).split()))
    connus = ctx.m.generiques | ctx.m.familiaux | ctx.m.exclus_generiques
    return [(w, round(n / len(clients), 4)) for w, n in c.most_common()
            if n / len(clients) > seuil and w not in connus]


def ecrire_retires(gardes: list[str], retires: list[str], cat: Catalogue) -> None:
    lignes = [{"terme": cat.negatifs[k][0], "terme_norm": k, "graine": GRAINE_NEGATIFS} for k in retires]
    write_csv(RETIRES, lignes, ["terme", "terme_norm", "graine"], sort_keys=["terme_norm"])


def charger_retires(chemin: Path = RETIRES) -> frozenset[str]:
    if not chemin.exists():
        raise FileNotFoundError(f"{chemin} introuvable : lancer python build/build_saisies.py.")
    return frozenset(r["terme_norm"] for r in read_csv(chemin))


def suffixe_variante(entendu: float, absents: float) -> str:
    return f"_e{entendu:.2f}_a{absents:.2f}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Génère les jeux de saisies depuis spec/modele_saisie.yaml.")
    ap.add_argument("--jeux", nargs="+", choices=("banc", "analyse", "certif"), default=["banc", "analyse", "certif"])
    ap.add_argument("--part-entendu", type=float, default=None, help="variante : part du mode « entendu »")
    ap.add_argument("--part-absents", type=float, default=None, help="variante : part des absents")
    ap.add_argument("--sensibilite", action="store_true",
                    help="génère aussi banc et analyse aux valeurs de sensibilité du modèle (une à la fois)")
    ap.add_argument("--volume-banc", type=int, default=VOLUME_BANC)
    ap.add_argument("--volume-calib", type=int, default=VOLUME_CALIB, help="analyse : saisies fautives par famille")
    ap.add_argument("--volume-certif", type=int, default=VOLUME_CERTIF, help="certification : saisies fautives par famille")
    ap.add_argument("--volume-certif-geo", type=int, default=VOLUME_CERTIF_GEO, help="certification : géographie")
    ap.add_argument("--scenario", choices=("central", "pessimiste"), default="central",
                    help="pessimiste : seulement banc et certification depuis spec/modele_saisie_pessimiste.yaml")
    args = ap.parse_args(argv)
    console_utf8()

    modele = Modele.charger()
    ctx = Contexte(modele)
    gardes, retires = partage_negatifs(ctx.cat, modele)
    ecrire_retires(gardes, retires, ctx.cat)
    ret = set(retires)
    meta = json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}
    meta.setdefault("jeux", {})
    if args.scenario == "pessimiste":
        generer_pessimiste(args, ctx, ret, gardes, meta)
        META.write_text(json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        print(f"→ {META.name}")
        return 0
    meta.update({"modele": modele.source, "graines": GRAINES, "graine_negatifs": GRAINE_NEGATIFS,
                 "negatifs": {"lieux_gardes": len(gardes), "lieux_retires": len(retires), "fichier": RETIRES.name},
                 "mots_clients_frequents_hors_listes": frequences_generiques(ctx)})
    meta.setdefault("jeux", {})

    variantes = []
    central = args.part_entendu is None and args.part_absents is None
    if central:
        variantes.append((modele, "", CHAL, args.jeux))
    else:
        mv = modele.avec_parts(args.part_entendu, args.part_absents)
        variantes.append((mv, suffixe_variante(mv.modes["entendu"], mv.absents_part), SENSI,
                          [j for j in args.jeux if j != "certif"]))
    if args.sensibilite:
        for e in modele.entendu_sensibilite:
            if abs(e - modele.modes["entendu"]) > 1e-9:
                mv = modele.avec_parts(entendu=e)
                variantes.append((mv, suffixe_variante(e, mv.absents_part), SENSI, ["banc", "analyse"]))
        for a in modele.absents_sensibilite:
            if abs(a - modele.absents_part) > 1e-9:
                mv = modele.avec_parts(absents=a)
                variantes.append((mv, suffixe_variante(mv.modes["entendu"], a), SENSI, ["banc", "analyse"]))

    for mv, suffixe, dossier, jeux in variantes:
        termes_analyse: set[str] = set()
        for jeu in [j for j in ("banc", "analyse", "certif") if j in jeux]:
            plan = plan_jeu(jeu, mv, suffixe, args.volume_banc,
                            args.volume_certif if jeu == "certif" else args.volume_calib,
                            volume_geo=args.volume_certif_geo if jeu == "certif" else None)
            interdits = set()
            if jeu == "certif":
                chemin_a = dossier / f"saisies_analyse{suffixe}.csv"
                if not termes_analyse:
                    if not chemin_a.exists():
                        raise FileNotFoundError(f"{chemin_a} introuvable : générer l'analyse avant la certification.")
                    termes_analyse = {r["terme_norm"] for r in read_csv(chemin_a)}
                interdits = termes_analyse
            lignes, info = generer_jeu(ctx, mv, plan, ret, gardes, interdits)
            if jeu == "analyse":
                termes_analyse = {l["terme_norm"] for l in lignes}
            chemin = dossier / f"saisies_{jeu}{suffixe}.csv"
            write_csv(chemin, lignes, COLONNES)
            info["fichier"] = str(chemin.relative_to(ROOT)).replace("\\", "/")
            info["sha256"] = empreinte(chemin)
            meta["jeux"][f"{jeu}{suffixe}"] = info
            pres = info["presents_par_famille"]
            print(f"{info['fichier']} : {info['cas']} cas (graine {plan.graine}), présents "
                  + ", ".join(f"{f} {n}" for f, n in pres.items())
                  + f" ; absents {sum(info['absents_par_sous_nature'].values())}")
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"→ {RETIRES.name} ({len(retires)} lieux retirés de l'index chargé), {META.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
