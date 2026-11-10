"""
Calibration des seuils de l'étape approchée, type par type, par SGR (Selection with Guaranteed Risk,
Geifman et El-Yaniv, 2017, « Selective classification for deep neural networks », NeurIPS).

    python -m engine.calibration                          r* = 0,05, δ = 0,05, écart 0,03
    python -m engine.calibration --cible 0.05 --delta 0.1

Données : la part « calib » de dev (70 % des cas, découpe déterministe par hash du case_id, voir
engine/evaluation.py · sous_partition). La partition test n'est jamais lue.

Pour chaque cas qui atteint l'étape approchée, on note (sans seuil) :
  κ      le score Jaro-Winkler du meilleur nom (la « confiance ») ;
  type   le type des meilleurs noms (engine/approche.py · cle_type), connu sans la réponse ;
  perte  selon `--perte` :
         dangereuse (défaut)  1 si la réponse affirme à tort : resolved vers une entité fausse
                              (erreur silencieuse), resolved là où le cas est ambigu (trop
                              confiant), ou ambiguous sans aucune bonne entité ;
         non_sure             1 si la réponse n'est pas sûre au sens du banc d'essai (ni correct,
                              ni partiel, ni acceptable) : compte aussi un ambiguous qui contient la
                              bonne entité quand le cas n'accepte que unknown.
Les cas refusés par un garde-fou (mots courts, nombre de mots) ne sont jamais retenus.

Les cas sont ceux de la chaîne réelle : un terme de l'index négatif s'arrête avant l'approché.
`--avec-absents` passe aussi ces termes à l'approché, comme si l'index négatif ne les connaissait
pas : c'est un test de robustesse, pas la calibration de référence (un lieu réel hors périmètre
obtient souvent plus de 0,95 face à un lieu du catalogue, et aucun seuil ne l'en sépare).

SGR, pour un type : on trie les m cas par κ, on cherche par dichotomie (k = ⌈log2 m⌉ essais) le seuil
θ le plus bas dont la borne supérieure du risque sélectif, au niveau δ/k (borne binomiale exacte,
Clopper-Pearson), reste sous r*. Avec une probabilité d'au moins 1 − δ, le risque des réponses
approchées de ce type est alors inférieur à r* (sous l'hypothèse que les cas futurs ressemblent à
ceux du banc). Un type dont les cas ne suffisent pas, même sans aucune erreur, ou dont aucun seuil
ne tient la cible, est marqué `fuzzy: desactive`.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from dataclasses import dataclass

import yaml

from engine.approche import SEUILS, SeuilFixe
from engine.catalogue import Catalogue, console_utf8
from engine.evaluation import PART_CALIB, SURS, charger_cas, noter
from engine.resolveur import AMBIGUOUS, ResolveurApproche

CIBLE, DELTA, ECART = 0.05, 0.05, 0.03


# ── borne binomiale (Lemme 3.1 de l'article) ─────────────────────────────────────────────────────

def _log_cdf_binom(k: int, n: int, p: float) -> float:
    """log P(Bin(n, p) ≤ k), calculé en log pour rester stable jusqu'à quelques milliers de cas."""
    if p <= 0:
        return 0.0
    if p >= 1:
        return 0.0 if k >= n else -math.inf
    lp, lq = math.log(p), math.log1p(-p)
    termes = [math.lgamma(n + 1) - math.lgamma(j + 1) - math.lgamma(n - j + 1) + j * lp + (n - j) * lq
              for j in range(k + 1)]
    mx = max(termes)
    return mx + math.log(sum(math.exp(t - mx) for t in termes))


def borne_risque(erreurs: int, n: int, delta: float) -> float:
    """B*(r̂, δ, n) : le b tel que P(Bin(n, b) ≤ erreurs) = δ. Le vrai risque est ≤ b avec proba ≥ 1 − δ."""
    if n <= 0:
        return 1.0
    if erreurs >= n:
        return 1.0
    lo, hi, cible = erreurs / n, 1.0, math.log(delta)
    for _ in range(100):  # dichotomie : la fonction de répartition décroît avec b
        mil = (lo + hi) / 2
        if _log_cdf_binom(erreurs, n, mil) > cible:
            lo = mil
        else:
            hi = mil
    return hi


def n_minimum(cible: float, delta: float) -> int:
    """Plus petit nombre de cas pour lequel zéro erreur suffit à passer sous la cible (k compris)."""
    n = 1
    while borne_risque(0, n, delta / max(1, math.ceil(math.log2(n)))) >= cible:
        n += 1
    return n


# ── SGR ──────────────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Choix:
    seuil: float
    borne: float
    risque: float
    retenus: int


def sgr(points: list[tuple[float, int]], cible: float, delta: float) -> Choix | None:
    """Algorithme 1 de l'article. `points` : (κ, perte). Renvoie le seuil le plus bas qui garantit la
    cible parmi ceux essayés, ou None si aucun ne la garantit."""
    m = len(points)
    if m == 0:
        return None
    kap = sorted(k for k, _ in points)
    k_essais = max(1, math.ceil(math.log2(m)))
    zmin, zmax, meilleur = 0, m - 1, None
    for _ in range(k_essais):
        z = math.ceil((zmin + zmax) / 2)
        theta = kap[z]
        sel = [p for k, p in points if k >= theta]
        err = sum(sel)
        b = borne_risque(err, len(sel), delta / k_essais)
        if b < cible:
            if meilleur is None or theta < meilleur.seuil:
                meilleur = Choix(theta, b, err / len(sel), len(sel))
            zmax = z
        else:
            zmin = z
    return meilleur


# ── collecte des cas de l'étape approchée ────────────────────────────────────────────────────────

PERTES = ("dangereuse", "non_sure")


def perte(cas: dict, statut: str, ids, mode: str = "dangereuse") -> int:
    """1 si la réponse approchée est une perte (voir l'en-tête du module), 0 sinon."""
    exp = set(filter(None, cas["expected_ids"].split("|")))
    sans_bonne = statut == AMBIGUOUS and not exp & set(ids)
    if mode == "non_sure":
        return int(noter(cas, statut, ids) not in SURS or (sans_bonne and bool(exp)))
    if mode != "dangereuse":
        raise ValueError(f"perte « {mode} » inconnue : {', '.join(PERTES)}.")
    return int(noter(cas, statut, ids) in ("erreur_silencieuse", "trop_confiant") or sans_bonne)


def collecter(cat: Catalogue, cas: list[dict], ecart: float = ECART, absents: bool = False,
              resolveur: ResolveurApproche | None = None, mode: str = "dangereuse") -> list[dict]:
    """Un point par cas qui atteint l'étape approchée : κ, type, retenable (garde-fous), perte."""
    r = resolveur or ResolveurApproche(cat, SeuilFixe(1e-9, ecart))
    out = []
    for c in cas:
        res = r.resoudre(c["input_text"], c["hint_type"] or None, index_negatif=not absents)
        etape = next((t for t in res.trace if t.get("regle") == "R-RES-03"), None)
        if etape is None:
            continue
        retenu = etape["etape"] == "approche"
        out.append({"case_id": c["case_id"], "categorie": c["category"], "texte": c["input_text"],
                    "kappa": etape["score"], "type": etape["type"], "retenu": retenu,
                    "absent_simule": bool(cat.negatifs.get(res.norm)),
                    "perte": perte(c, res.statut, res.ids, mode) if retenu else 0})
    return out


def calibrer(points: list[dict], cible: float, delta: float, ecart: float, empreinte: str) -> dict:
    par_type = defaultdict(list)
    for p in points:
        par_type[p["type"]].append(p)
    nmin = n_minimum(cible, delta)
    types = {}
    for t in sorted(par_type):
        pts = [(p["kappa"], p["perte"]) for p in par_type[t] if p["retenu"]]
        base = {"n_cas": len(par_type[t]), "n_retenables": len(pts), "empreinte_catalogue": empreinte}
        if len(pts) < nmin:
            types[t] = {"fuzzy": "desactive", **base,
                        "raison": f"{len(pts)} cas retenables, il en faut au moins {nmin} pour r* = {cible:g}"}
            continue
        ch = sgr(pts, cible, delta)
        if ch is None:
            types[t] = {"fuzzy": "desactive", **base,
                        "raison": f"aucun seuil ne garantit r* = {cible:g} au niveau δ = {delta:g}"}
        else:
            types[t] = {"fuzzy": "actif", "seuil": round(ch.seuil, 6), "ecart": ecart, "borne": round(ch.borne, 6),
                        **base, "n_retenus": ch.retenus, "risque_empirique": round(ch.risque, 6)}
    return types


def ecrire(types: dict, cible: float, delta: float, ecart: float, absents: bool, empreinte: str, n_cas: int,
           mode: str = "dangereuse", chemin=SEUILS) -> None:
    doc = {"methode": "SGR (Geifman et El-Yaniv, 2017), un seuil par type",
           "cible_risque": cible, "delta": delta, "ecart": ecart, "perte": mode,
           "donnees": f"challenges/cases.csv, partition dev, part calib ({PART_CALIB} %, hash SHA-256 du case_id), "
                      f"{n_cas} cas",
           "absents_simules": absents, "empreinte_catalogue": empreinte, "types": types}
    entete = ("# Seuils de l'étape approchée (R-RES-03), un par type de nom.\n"
              "# Fichier GÉNÉRÉ par python -m engine.calibration : ne pas modifier à la main, recalibrer.\n"
              "# Le moteur refuse ces seuils si l'empreinte du catalogue a changé.\n")
    chemin.write_text(entete + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=110),
                      encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Calibre les seuils Jaro-Winkler par type (SGR).")
    ap.add_argument("--cible", type=float, default=CIBLE, help="risque sélectif visé r*")
    ap.add_argument("--delta", type=float, default=DELTA, help="niveau de confiance 1 − δ")
    ap.add_argument("--ecart", type=float, default=ECART, help="écart sous lequel deux noms sont ambigus")
    ap.add_argument("--perte", choices=PERTES, default="dangereuse", help="ce qui compte comme erreur")
    ap.add_argument("--avec-absents", action="store_true",
                    help="robustesse : passer aussi les termes de l'index négatif à l'approché")
    args = ap.parse_args(argv)
    console_utf8()
    if not (0 < args.cible < 1 and 0 < args.delta < 1):
        raise SystemExit("--cible et --delta doivent être dans ]0, 1[.")
    cat = Catalogue.charger()
    cas = charger_cas("dev", "calib")
    points = collecter(cat, cas, args.ecart, args.avec_absents, mode=args.perte)
    types = calibrer(points, args.cible, args.delta, args.ecart, cat.empreinte)
    ecrire(types, args.cible, args.delta, args.ecart, args.avec_absents, cat.empreinte, len(cas), args.perte)
    print(f"{len(cas)} cas calib, {len(points)} atteignent l'approché · perte {args.perte} · "
          f"r* = {args.cible:g}, δ = {args.delta:g}, "
          f"au moins {n_minimum(args.cible, args.delta)} cas par type")
    for t, v in types.items():
        if v["fuzzy"] == "actif":
            print(f"  {t:<20} actif      seuil {v['seuil']:.4f}  borne {v['borne']:.4f}  "
                  f"{v['n_retenus']}/{v['n_cas']} cas")
        else:
            print(f"  {t:<20} désactivé  {v['raison']}")
    print(f"→ {SEUILS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
