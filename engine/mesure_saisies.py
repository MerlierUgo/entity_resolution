"""
Mesures sur les jeux de saisies générés depuis spec/modele_saisie.yaml, et sur l'échantillon réel.

    python -m engine.mesure_saisies            → reports/mesure_saisies.json (puis engine.rapport_saisies)

Quatre parties :
  1. vérification du générateur contre l'échantillon réel (human/echantillon_reel/saisies_combinees.csv) :
     mêmes indicateurs des deux côtés, par mode (distance OSA, mots oubliés, types de fautes, exemples) ;
     mots oubliés repérés par alignement sur le réel, notés à la génération sur le généré.
     Le côté généré est un « miroir » : les mêmes noms, dans le même mode, tapés MIROIR fois par le
     générateur ;
  2. moteur actuel (Jaro-Winkler, seuil fixe 0,88 PROVISOIRE, écart 0,03) sur saisies_banc.csv ;
  3. diagnostic des erreurs à 0,88 sur saisies_analyse.csv ;
  4. moteur sur l'échantillon réel, puis les mesures 2 et 3 aux valeurs de sensibilité.

Collision exacte (modèle § 8, v0.2) : saisie fautive qui tombe exactement sur un autre nom réel (« opel »
tapé pour la localité Hopel, résolu vers la marque). Comptée dans le total des erreurs silencieuses,
affichée à part, exclue des métriques « fuzzy seul » (risque_approche) : aucun seuil n'y peut rien.

Aucun seuil n'est calculé ici. saisies_certif.csv n'est JAMAIS ouvert : on ne l'utilisera qu'une fois,
plus tard, le moteur figé, pour calculer un seuil sans regarder ses erreurs.

Index négatif : pendant l'évaluation des jeux générés, les lieux de challenges/negatifs_retires.csv
(« absents inconnus ») sont retirés de l'index négatif CHARGÉ (charger_catalogue_jeux) ; le fichier
catalog/negatifs.csv n'est pas modifié. L'échantillon réel est évalué avec l'index complet.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

from rapidfuzz.distance import OSA

from engine.approche import SeuilFixe
from engine.catalogue import ROOT, Catalogue, console_utf8, normalize, read_csv
from engine.resolveur import ResolveurApproche

sys.path.insert(0, str(ROOT / "build"))
import build_saisies as bs  # noqa: E402

CHAL = ROOT / "challenges"
REP = ROOT / "reports"
REEL = ROOT / "human" / "echantillon_reel" / "saisies_combinees.csv"
SORTIE = REP / "mesure_saisies.json"
MODES_REELS = {"oreille": "entendu", "memoire": "lu"}
MIROIR = 10            # saisies simulées par saisie réelle (même nom, même mode)
EXEMPLES = 10
GRAINE_MESURE = 20261229


# ── chargement ────────────────────────────────────────────────────────────────────────────────────

def charger_jeu(chemin: Path) -> list[dict]:
    """Lit un jeu généré. Refuse le jeu de certification : il ne sert qu'à calculer un seuil, une fois."""
    if "certif" in chemin.name:
        raise SystemExit(f"{chemin.name} : jeu de certification, réservé au calcul d'un seuil, une seule fois, "
                         "le moteur figé. Ses erreurs ne sont jamais regardées.")
    if not chemin.exists():
        raise FileNotFoundError(f"{chemin} introuvable : lancer python build/build_saisies.py (--sensibilite).")
    return read_csv(chemin)


def charger_catalogue_jeux(cat: Catalogue, retires: frozenset[str] | None = None) -> Catalogue:
    """Copie du catalogue dont l'index négatif CHARGÉ perd les « absents inconnus » (negatifs_retires.csv).
    Les index d'alias sont partagés, rien n'est réécrit sur disque."""
    retires = bs.charger_retires() if retires is None else retires
    inconnus = retires - set(cat.negatifs)
    if inconnus:
        raise ValueError(f"negatifs_retires.csv : {len(inconnus)} terme(s) absent(s) de l'index négatif "
                         f"(ex. {sorted(inconnus)[0]}) ; régénérer : python build/build_saisies.py.")
    return dataclasses.replace(cat, negatifs={k: v for k, v in cat.negatifs.items() if k not in retires})


# ── notation (modèle § 8) ─────────────────────────────────────────────────────────────────────────

NOTES = ("ideal", "sur", "trop_confiant", "silencieux", "incorrect")


def noter(att_statut: str, att_ids, statut: str, ids) -> str:
    """ideal : réponse attendue exacte ; sur : réponse prudente (ambiguous qui contient une entité attendue,
    ou unknown alors qu'on attendait resolved ou ambiguous) ; trop_confiant : resolved vers une des entités
    d'un attendu ambiguous ; silencieux : resolved hors de l'ensemble attendu, ou resolved sur un absent ;
    incorrect : le reste (ex. ambiguous sur un absent)."""
    exp, ids = set(att_ids), set(ids)
    if statut == att_statut and ids == exp:
        return "ideal"
    if statut == "resolved":
        if att_statut == "unknown" or not ids <= exp:
            return "silencieux"
        return "trop_confiant"
    if att_statut in ("resolved", "ambiguous"):
        if statut == "unknown" or (statut == "ambiguous" and ids & exp):
            return "sur"
    return "incorrect"


def collision_exacte(note: str, etape: str, fautive: bool) -> bool:
    """Erreur silencieuse d'une saisie fautive résolue AVANT l'approché (exact ou mots triés) : la saisie
    tombe exactement sur un autre nom réel."""
    return note == "silencieux" and etape != "approche" and fautive


def taux(c: Counter) -> dict:
    """c : notes, plus « collision » (sous-ensemble des silencieux)."""
    n = sum(c[k] for k in NOTES)
    if not n:
        return {"n": 0}
    return {"n": n, "ideal": round(100 * c["ideal"] / n, 2), "sur": round(100 * (c["ideal"] + c["sur"]) / n, 2),
            "silencieux": c["silencieux"], "silencieux_pct": round(100 * c["silencieux"] / n, 2),
            "dont_collision_exacte": c["collision"],
            "silencieux_hors_collision_pct": round(100 * (c["silencieux"] - c["collision"]) / n, 2),
            "trop_confiant": c["trop_confiant"], "incorrect": c["incorrect"]}


class Evaluateur:
    """Moteur 0,88 avec cache (même terme et même indice → même résolution)."""

    def __init__(self, cat: Catalogue):
        self.res = ResolveurApproche(cat, SeuilFixe(0.88, 0.03))
        self.cache = {}

    def __call__(self, terme: str, hint: str | None):
        cle = (terme, hint or "")
        if cle not in self.cache:
            r = self.res.resoudre(terme, hint or None)
            app = next((t for t in r.trace if t.get("regle") == "R-RES-03"), {})
            self.cache[cle] = {"statut": r.statut, "ids": list(r.ids), "etape": r.etape,
                               "score": round(app.get("score", 0), 4) if app else None,
                               "noms": app.get("noms", app.get("meilleurs", []))[:3] if app else []}
        return self.cache[cle]


def evaluer(ev: Evaluateur, lignes: list[dict]) -> list[dict]:
    out = []
    for l in lignes:
        r = ev(l["terme"], l["indice_type"])
        att = [i for i in l["attendu_ids"].split("|") if i]
        note = noter(l["attendu_statut"], att, r["statut"], r["ids"])
        fautive = bool(l["perturbations"] or l["mots_oublies"])
        out.append({**l, "r_statut": r["statut"], "r_ids": r["ids"], "r_etape": r["etape"], "r_score": r["score"],
                    "r_noms": r["noms"], "note": note, "collision": collision_exacte(note, r["etape"], fautive)})
    return out


def tableau(res: list[dict], cle) -> dict:
    groupes = defaultdict(Counter)
    for r in res:
        for k in ({cle(r), "TOTAL"}):
            groupes[k][r["note"]] += 1
            groupes[k]["collision"] += bool(r.get("collision"))
    return {k: taux(v) for k, v in sorted(groupes.items(), key=lambda kv: (kv[0] == "TOTAL", kv[0]))}


def risque_approche(res: list[dict]) -> dict:
    """Parmi les termes acceptés par l'approché seul (resolved à l'étape approchée), part d'erreurs silencieuses.
    Les collisions exactes n'y entrent jamais (résolues avant l'approché ; exclues aussi explicitement)."""
    par = defaultdict(Counter)
    for r in res:
        if r["r_etape"] == "approche" and r["r_statut"] == "resolved" and not r.get("collision"):
            for k in (r["famille"], "TOTAL"):
                par[k]["acceptes"] += 1
                par[k]["silencieux"] += r["note"] == "silencieux"
    return {k: {**v, "risque_pct": round(100 * v["silencieux"] / v["acceptes"], 2) if v["acceptes"] else None}
            for k, v in sorted(par.items(), key=lambda kv: (kv[0] == "TOTAL", kv[0]))}


def mesures_jeu(res: list[dict]) -> dict:
    return {"global": tableau(res, lambda r: "TOTAL")["TOTAL"],
            "par_famille": tableau(res, lambda r: r["famille"]),
            "par_nature": tableau(res, lambda r: r["nature"] + "/" + r["sous_nature"]),
            "par_mode": tableau(res, lambda r: r["mode"]),
            "par_indice": tableau(res, lambda r: "avec indice" if r["indice_type"] else "sans indice"),
            "risque_approche": risque_approche(res)}


# ── diagnostic (analyse) ──────────────────────────────────────────────────────────────────────────

def voisin_a_une_faute(ctx: bs.Contexte, norm: str, types: set[str], exclus: set[str]) -> str:
    """Un nom réel des types donnés, à une faute (OSA ≤ 1) du terme, hors des noms exclus ; '' sinon."""
    for n in sorted(ctx.voisins(norm, 1, types)):
        if n not in exclus:
            return n
    return ""


def exemple(ctx, r: dict, voisin: str = "") -> dict:
    lab = lambda ids: [ctx.cat.label.get(i, i) for i in ids][:4]
    return {"case_id": r["case_id"], "famille": r["famille"], "mode": r["mode"], "terme": r["terme"],
            "nom_source": r["nom_source"], "sous_nature": r["sous_nature"], "perturbations": r["perturbations"],
            "mots_oublies": r["mots_oublies"], "indice": r["indice_type"], "attendu": r["attendu_statut"],
            "attendu_labels": lab([i for i in r["attendu_ids"].split("|") if i]),
            "moteur": r["r_statut"], "moteur_labels": lab(r["r_ids"]), "score": r["r_score"],
            "voisin_a_une_faute": voisin}


def diagnostic(ctx: bs.Contexte, res: list[dict], rng: random.Random) -> dict:
    """Erreurs à 0,88 : présents confondus, présents trop confiants, absents acceptés (par sous-nature).
    Pour chaque erreur : un autre nom réel du même type est-il à une seule faute du terme tapé ?"""
    cats = {"collision_exacte": [r for r in res if r.get("collision")],
            "present_confondu": [r for r in res if r["nature"] == "present" and r["note"] == "silencieux"
                                 and not r.get("collision")],
            "present_trop_confiant": [r for r in res if r["nature"] == "present" and r["note"] == "trop_confiant"],
            "absent_accepte": [r for r in res if r["nature"] == "absent" and r["note"] == "silencieux"
                               and not r.get("collision")]}
    out = {}
    for nom, lignes in cats.items():
        details = []
        for r in lignes:
            norm = r["terme_norm"]
            if r["nature"] == "present":
                types = {ctx.cat.etype[r["entity_id_source"]]}
                exclus = {n for n, ids in ctx.cat.noms.items() if r["entity_id_source"] in ids}
            else:
                types = {ctx.cat.etype[i] for i in r["r_ids"]}
                exclus = set()
            details.append((r, voisin_a_une_faute(ctx, norm, types, exclus)))
        ex = rng.sample(details, min(EXEMPLES, len(details)))
        out[nom] = {"n": len(lignes),
                    "par_famille": dict(sorted(Counter(r["famille"] for r, _ in details).items())),
                    "par_sous_nature": dict(sorted(Counter(r["sous_nature"] for r, _ in details).items())),
                    "par_mode": dict(sorted(Counter(r["mode"] for r, _ in details).items())),
                    "avec_voisin_a_une_faute": sum(bool(v) for _, v in details),
                    "exemples": [exemple(ctx, r, v) for r, v in sorted(ex, key=lambda x: x[0]["case_id"])]}
    out["absent_ambigu"] = {"n": sum(r["nature"] == "absent" and r["r_statut"] == "ambiguous" for r in res)}
    out["absents_total"] = dict(sorted(Counter(r["sous_nature"] for r in res if r["nature"] == "absent").items()))
    out["presents_total"] = sum(r["nature"] == "present" for r in res)
    return out


# ── indicateurs de saisie (mêmes fonctions pour le réel et le généré) ─────────────────────────────

def mots_oublies(src: str, tape: str) -> tuple[list[str], str]:
    """Mots du nom source absents de la saisie (alignement de mots ; un mot à moitié faux est apparié).
    Renvoie (mots oubliés, forme courte normalisée)."""
    a, b = src.split(), tape.split()
    INF = 10 ** 6
    n, m = len(a), len(b)
    D = [[INF] * (m + 1) for _ in range(n + 1)]
    P = [[None] * (m + 1) for _ in range(n + 1)]
    D[0][0] = 0
    for i in range(n + 1):
        for j in range(m + 1):
            if i < n and D[i][j] + len(a[i]) + 0.5 < D[i + 1][j]:
                D[i + 1][j], P[i + 1][j] = D[i][j] + len(a[i]) + 0.5, ("del", i)
            if j < m and D[i][j] + len(b[j]) < D[i][j + 1]:
                D[i][j + 1], P[i][j + 1] = D[i][j] + len(b[j]), ("ins", j)
            if i < n and j < m:
                d = OSA.distance(a[i], b[j])
                if d <= max(1, len(a[i]) // 2) and D[i][j] + d < D[i + 1][j + 1]:
                    D[i + 1][j + 1], P[i + 1][j + 1] = D[i][j] + d, ("sub", i)
    i, j, oublies = n, m, []
    while i or j:
        op = P[i][j]
        if op[0] == "del":
            oublies.append(a[i - 1])
            i -= 1
        elif op[0] == "ins":
            j -= 1
        else:
            i, j = i - 1, j - 1
    colle = tape.replace(" ", "")
    oublies = [w for w in reversed(oublies) if w not in colle]
    reste = list(a)
    for w in oublies:
        reste.remove(w)
    return oublies, " ".join(reste)


def operations(s: str, t: str) -> list[str]:
    """Opérations d'édition OSA de s vers t, classées comme des fautes de clavier."""
    n, m = len(s), len(t)
    D = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        D[i][0] = i
    for j in range(m + 1):
        D[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i][j] = min(D[i - 1][j] + 1, D[i][j - 1] + 1, D[i - 1][j - 1] + (s[i - 1] != t[j - 1]))
            if i > 1 and j > 1 and s[i - 1] == t[j - 2] and s[i - 2] == t[j - 1] and s[i - 1] != s[i - 2]:
                D[i][j] = min(D[i][j], D[i - 2][j - 2] + 1)
    ops, i, j = [], n, m
    while i or j:
        if i and j and s[i - 1] == t[j - 1] and D[i][j] == D[i - 1][j - 1]:
            i, j = i - 1, j - 1
        elif i > 1 and j > 1 and s[i - 1] == t[j - 2] and s[i - 2] == t[j - 1] and D[i][j] == D[i - 2][j - 2] + 1:
            ops.append("inversion")
            i, j = i - 2, j - 2
        elif i and j and D[i][j] == D[i - 1][j - 1] + 1:
            a, b = s[i - 1], t[j - 1]
            ops.append("espace" if " " in (a, b) else
                       "substitution voisine" if b in bs.VOISINS.get(a, ()) else "substitution autre")
            i, j = i - 1, j - 1
        elif i and D[i][j] == D[i - 1][j] + 1:
            c = s[i - 1]
            ops.append("espace" if c == " " else
                       "dédoublement" if (i > 1 and s[i - 2] == c) or (i < n and s[i] == c) else "omission")
            i -= 1
        else:
            c = t[j - 1]
            voisins = [t[k] for k in (j - 2, j) if 0 <= k < m]
            ops.append("espace" if c == " " else "doublement" if c in voisins else
                       "insertion voisine" if any(c in bs.VOISINS.get(v, ()) for v in voisins) else "insertion autre")
            j -= 1
    return ops


class Decomposeur:
    """Explique une saisie par des règles phonétiques du modèle (gloutonnement), puis le reste par des
    opérations de clavier. Appliqué à l'identique au réel et au généré : les parts sont comparables."""

    def __init__(self, modele: bs.Modele):
        self.regles = {}
        for r, rws in modele.phon_reecritures.items():
            vus = set()
            for rw in rws:
                src, dst = bs.sans_accents(rw.src), bs.sans_accents(rw.dst)
                if src != dst:
                    vus.add((src, dst, rw.position))
            self.regles[r] = sorted(vus)

    def sites(self, s: str, src: str, dst: str, pos: str):
        for mo in bs.MOT.finditer(s):
            a, b = mo.span()
            w = mo.group()
            if pos == "fin":
                if src and w.endswith(src):
                    yield s[:b - len(src)] + dst + s[b:]
                elif not src:
                    yield s[:b] + dst + s[b:]
            elif pos == "debut":
                if src and w.startswith(src):
                    yield s[:a] + dst + s[a + len(src):]
                elif not src:
                    yield s[:a] + dst + s[a:]
            else:
                k = w.find(src)
                while k >= 0:
                    yield s[:a + k] + dst + s[a + k + len(src):]
                    k = w.find(src, k + 1)

    def __call__(self, s: str, t: str) -> list[str]:
        out, cur = [], s
        for _ in range(4):
            d0 = OSA.distance(cur, t)
            if d0 == 0:
                break
            meilleur = None
            for regle, rws in self.regles.items():
                for src, dst, pos in rws:
                    for c in self.sites(cur, src, dst, pos):
                        d = OSA.distance(c, t)
                        # une règle n'explique la saisie que si elle fait gagner au moins 2 opérations,
                        # ou 1 en réécrivant plus d'une lettre (sinon une faute de clavier suffit)
                        gain = d0 - d
                        if gain >= 2 or (gain >= 1 and max(len(src), len(dst)) >= 2):
                            if meilleur is None or d < meilleur[0]:
                                meilleur = (d, regle, c)
            if not meilleur:
                break
            out.append(f"phonétique : {meilleur[1]}")
            cur = meilleur[2]
        return out + [f"clavier : {o}" for o in operations(cur, t)]


def indicateurs(paires: list[tuple], dec: Decomposeur) -> dict:
    """paires (nom source, saisie) ou (nom source, saisie, mots oubliés, forme courte normalisée).
    Distance OSA après retrait des mots oubliés, part de mots oubliés, types de fautes.
    Sans les deux derniers éléments (échantillon réel), les mots oubliés sont repérés par alignement ;
    avec (saisies générées, modèle v0.3), ceux notés à la génération sont utilisés tels quels."""
    dist, n_oubli, types, nb_types = Counter(), 0, Counter(), 0
    for paire in paires:
        src, tape = paire[0], paire[1]
        s, t = normalize(src), normalize(tape)
        if len(paire) == 4:
            oublies, court = list(paire[2]), (paire[3] if paire[2] else s)
        else:
            oublies, court = mots_oublies(s, t)
        n_oubli += bool(oublies)
        d = bs.distance(t, court) if t != court else 0
        dist["3+" if d >= 3 else str(d)] += 1
        for op in dec(court, t):
            types[op] += 1
            nb_types += 1
    n = len(paires)
    return {"n": n,
            "distance": {k: round(100 * dist[k] / n, 1) for k in ("0", "1", "2", "3+")} if n else {},
            "mots_oublies_pct": round(100 * n_oubli / n, 1) if n else None,
            "types": [(k, round(100 * v / nb_types, 1)) for k, v in types.most_common()] if nb_types else [],
            "fautes_par_saisie": round(nb_types / n, 2) if n else None}


# ── échantillon réel ──────────────────────────────────────────────────────────────────────────────

def lignes_reelles() -> tuple[list[dict], list[dict], Counter]:
    """(saisies d'entités avec un texte, termes libres, saisies vides ou « ? » par mode)."""
    ent, libres, vides = [], [], Counter()
    for r in read_csv_sc(REEL):
        if r["mode"].startswith("libre"):
            libres.append(r)
        elif not r["saisie"].strip() or r["saisie"].strip() == "?":
            vides[MODES_REELS[r["mode"]]] += 1
        else:
            ent.append({**r, "mode_modele": MODES_REELS[r["mode"]]})
    return ent, libres, vides


def read_csv_sc(chemin: Path) -> list[dict]:
    import csv
    with chemin.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def verification(ctx: bs.Contexte, modele: bs.Modele, reels: list[dict], dec: Decomposeur) -> dict:
    """Mêmes indicateurs pour le réel et pour le générateur (miroir : mêmes noms, même mode).
    Mots oubliés : repérés par alignement sur le réel, notés à la génération sur le généré (v0.3)."""
    gen = bs.Generateur(ctx, modele, bs.Plan("miroir", GRAINE_MESURE, False, {}, 0.0), set())
    out, exemples = {}, []
    rng = random.Random(GRAINE_MESURE)
    accord = Counter()
    for mode in sorted(modele.modes):
        rr = [r for r in reels if r["mode_modele"] == mode]
        paires_r = [(r["nom_cible"], r["saisie"]) for r in rr]
        paires_g, vrais = [], []
        for r in rr:
            for _ in range(MIROIR):
                terme, labels, oublies, court = gen.taper(r["entity_id"], mode)
                paires_g.append((r["nom_cible"], terme, oublies, court))
                vrais.append((r["nom_cible"], terme, bool(oublies), labels))
        for src, terme, vrai, _ in vrais:
            detecte = bool(mots_oublies(normalize(src), normalize(terme))[0])
            accord[(vrai, detecte)] += 1
        out[mode] = {"reel": indicateurs(paires_r, dec), "genere": indicateurs(paires_g, dec)}
        for r in rng.sample(rr, min(15 if mode == "entendu" else 8, len(rr))):
            terme, labels, oublies, _ = gen.taper(r["entity_id"], mode)
            exemples.append({"mode": mode, "nom": r["nom_cible"], "reel": r["saisie"], "genere": terme,
                             "perturbations": " ; ".join(labels + oublies)})
    out["exemples"] = exemples
    out["detection_oublis_sur_genere"] = {"vrai_detecte": accord[(True, True)], "vrai_manque": accord[(True, False)],
                                          "faux_detecte": accord[(False, True)], "faux_ok": accord[(False, False)]}
    return out


def moteur_reel(ctx: bs.Contexte, ev: Evaluateur, reels: list[dict], libres: list[dict]) -> dict:
    """Moteur 0,88 sur l'échantillon réel, sans indice puis avec l'indice du type ; attendu § 8."""
    out = {}
    lignes_err = []
    for avec in (False, True):
        res = []
        for r in reels:
            src = normalize(r["nom_cible"])
            t = normalize(r["saisie"])
            oublies, court = mots_oublies(src, t)
            hint = r["entity_type"] if avec else None
            att = ctx.attendu(r["saisie"], src, r["entity_id"], court if oublies else None, hint)
            rep = ev(r["saisie"], hint)
            note = noter(att["statut"], att["ids"], rep["statut"], rep["ids"])
            coll = collision_exacte(note, rep["etape"], t != src)
            res.append({"mode": r["mode_modele"], "famille": r["famille"], "note": note, "r_etape": rep["etape"],
                        "r_statut": rep["statut"], "collision": coll})
            if note in ("silencieux", "trop_confiant") and not avec:
                lignes_err.append({"mode": r["mode_modele"], "nom": r["nom_cible"], "saisie": r["saisie"],
                                   "note": "collision_exacte" if coll else note, "attendu": att["statut"],
                                   "attendu_labels": [ctx.cat.label[i] for i in att["ids"]][:4],
                                   "moteur_labels": [ctx.cat.label[i] for i in rep["ids"]][:4],
                                   "score": rep["score"]})
        cle = "avec_indice" if avec else "sans_indice"
        out[cle] = {"par_mode": tableau(res, lambda x: x["mode"]), "par_famille": tableau(res, lambda x: x["famille"]),
                    "approche_seule": {m: {"acceptes": sum(1 for x in res if x["mode"] == m and x["r_etape"] == "approche"
                                                           and x["r_statut"] == "resolved"),
                                           "silencieux": sum(1 for x in res if x["mode"] == m and x["r_etape"] == "approche"
                                                             and x["r_statut"] == "resolved" and x["note"] == "silencieux"),
                                           "collisions_exactes": sum(1 for x in res if x["mode"] == m and x["collision"])}
                                       for m in ("lu", "entendu")}}
    out["erreurs_sans_indice"] = lignes_err
    out["libres"] = []
    for r in libres:
        rep = ev(r["saisie"], None)
        out["libres"].append({"mode": MODES_REELS[r["mode"].removeprefix("libre_")], "saisie": r["saisie"],
                              "statut": rep["statut"], "etape": rep["etape"],
                              "labels": [ctx.cat.label[i] for i in rep["ids"]][:3], "score": rep["score"]})
    return out


# ── principal ─────────────────────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mesures sur les jeux de saisies (jamais sur la certification).")
    ap.add_argument("--sans-sensibilite", action="store_true", help="ne mesure pas les variantes de sensibilité")
    args = ap.parse_args(argv)
    console_utf8()
    modele = bs.Modele.charger()
    ctx = bs.Contexte(modele)
    cat_jeux = charger_catalogue_jeux(ctx.cat)
    ev_jeux, ev_reel = Evaluateur(cat_jeux), Evaluateur(ctx.cat)
    rng = random.Random(GRAINE_MESURE)
    dec = Decomposeur(modele)
    meta = json.loads(bs.META.read_text(encoding="utf-8"))

    reels, libres, vides = lignes_reelles()
    print(f"échantillon réel : {len(reels)} saisies d'entités, {len(libres)} termes libres, "
          f"{sum(vides.values())} vides ou « ? »", flush=True)
    out = {"moteur": "Jaro-Winkler, SeuilFixe(0.88, 0.03), provisoire",
           "negatifs_retires": len(bs.charger_retires()),
           "meta_jeux": meta.get("jeux", {}), "mots_clients_frequents_hors_listes": meta.get("mots_clients_frequents_hors_listes", []),
           "reel": {"n": len(reels), "par_mode": dict(Counter(r["mode_modele"] for r in reels)),
                    "vides": dict(vides), "libres": len(libres)}}
    out["verification"] = verification(ctx, modele, reels, dec)
    print("vérification du générateur : faite", flush=True)

    banc = evaluer(ev_jeux, charger_jeu(CHAL / "saisies_banc.csv"))
    out["banc"] = {**mesures_jeu(banc), "diagnostic": diagnostic(ctx, banc, rng)}
    print(f"banc : {out['banc']['global']}", flush=True)
    analyse = evaluer(ev_jeux, charger_jeu(CHAL / "saisies_analyse.csv"))
    out["analyse"] = {**mesures_jeu(analyse), "diagnostic": diagnostic(ctx, analyse, rng)}
    print(f"analyse : {out['analyse']['global']} · risque approché {out['analyse']['risque_approche'].get('TOTAL')}",
          flush=True)
    out["reel_moteur"] = moteur_reel(ctx, ev_reel, reels, libres)
    print("échantillon réel : fait", flush=True)

    out["sensibilite"] = {}
    if not args.sans_sensibilite:
        for cle, info in sorted(meta.get("jeux", {}).items()):
            if "_e" not in cle or cle.startswith("certif"):
                continue
            jeu = cle.split("_e")[0]
            res = evaluer(ev_jeux, charger_jeu(ROOT / info["fichier"]))
            m = mesures_jeu(res)
            d = {"part_entendu": info["part_entendu"], "part_absents": info["part_absents"], "jeu": jeu,
                 "global": m["global"], "par_famille": m["par_famille"], "risque_approche": m["risque_approche"]}
            if jeu == "analyse":
                d["diagnostic_n"] = {k: v["n"] for k, v in diagnostic(ctx, res, rng).items() if isinstance(v, dict) and "n" in v}
            out["sensibilite"][cle] = d
            print(f"sensibilité {cle} : {m['global']}", flush=True)
    SORTIE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {SORTIE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
