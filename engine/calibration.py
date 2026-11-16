"""
Calibration des seuils de l'étape approchée, famille par famille (R-RES-10), par SGR (Selection with
Guaranteed Risk, Geifman et El-Yaniv, 2017, « Selective classification for deep neural networks », NeurIPS).

    python -m engine.calibration                          r* = 0,005, δ = 0,05, écart 0,03
    python -m engine.calibration --cible 0.01 --delta 0.1

Données : challenges/calibration_certif.csv (build/build_calibration.py), le jeu de CERTIFICATION :
fautes de frappe sur des noms du catalogue (« present ») et termes hors catalogue (« absent »), qui
atteignent tous l'étape approchée, sans aucune entité de la partition test. Il sert seulement à
calculer θ : on n'en regarde jamais les erreurs. Les règles se conçoivent sur le jeu d'ANALYSE,
challenges/calibration_analyse.csv (engine/diagnostic_fuzzy.py), tiré avec une autre graine et sans
terme commun. Le banc d'essai (cases.csv) n'est pas lu ici : sa part « eval » de dev sert à la
comparaison (engine/comparaison.py).

Le risque de la configuration B (seuil fixe 0,88, choisi à la main et non sur ces données) est mesuré
sur le même jeu : taux de pertes par famille et borne B*(k, n, δ) sans correction de grille, puisque
ce seuil n'est pas choisi parmi plusieurs (reports/calibration.json, clé « risque_b »).

Pour chaque cas qui atteint l'étape approchée, on note (sans seuil) :
  κ        le score Jaro-Winkler du meilleur nom (la « confiance ») ;
  famille  la famille des meilleurs noms (engine/approche.py · cle_famille, spec/familles_fuzzy.yaml),
           connue sans la réponse : c'est la clé que le moteur utilisera, pas la famille attendue ;
  perte    selon `--perte` :
           dangereuse (défaut)  1 si le nom accepté mène à une entité qui n'est pas la bonne :
                                resolved vers une entité fausse (erreur silencieuse), resolved là où
                                le cas est ambigu (trop confiant), ou ambiguous sans aucune bonne
                                entité. Un absent accepté est toujours une perte ;
           non_sure             1 si la réponse n'est pas sûre au sens du banc d'essai (ni correct,
                                ni partiel, ni acceptable).
Les cas refusés par un garde-fou (mots courts, nombre de mots) ne sont jamais retenus.

SGR sur une grille fixe, pour une famille : pour chacun des G = 20 seuils θ de GRILLE (0,80 à 0,99,
pas de 0,01), n = cas acceptés (κ ≥ θ), k = pertes parmi eux, et B*(k, n, δ/G) la borne binomiale
exacte (lemme 3.1 de l'article, Clopper-Pearson unilatérale). La correction de Bonferroni sur les G
seuils (adaptée du théorème 3.2) rend les G bornes vraies ensemble avec une probabilité d'au moins
1 − δ : on peut donc retenir n'importe lequel ; on prend le θ le plus BAS dont la borne est ≤ r* (la
plus grande couverture). Avec une probabilité d'au moins 1 − δ, le risque des réponses approchées de
cette famille est alors ≤ r* (sous l'hypothèse que les termes futurs ressemblent à ceux du jeu de
calibration). La grille ne dépend pas des données, contrairement à l'ancienne dichotomie sur les κ
observés. Une famille dont les cas ne suffisent pas, même sans aucune erreur, ou dont aucun seuil ne
tient la cible, est marquée `fuzzy: desactive`. La clé « mixte » (meilleurs noms de plusieurs
familles) est toujours désactivée.

Sorties : spec/seuils_fuzzy.yaml (lu par le moteur) et reports/calibration.json (balayage complet de la
grille par famille, pour le rapport).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date as Date
from pathlib import Path

import yaml

from engine.approche import MIXTE, SEUILS, IndexApproche, SeuilFixe, charger_familles
from engine.catalogue import ROOT, Catalogue, console_utf8, read_csv
from engine.evaluation import REP, SURS, noter
from engine.resolveur import AMBIGUOUS, ResolveurApproche

CIBLE, DELTA, ECART = 0.005, 0.05, 0.03
GRILLE = tuple(round(0.80 + i / 100, 2) for i in range(20))   # 0,80 … 0,99
SEUIL_B = 0.88
CAS_ANALYSE = ROOT / "challenges" / "calibration_analyse.csv"   # pour concevoir (diagnostic)
CAS_CERTIF = ROOT / "challenges" / "calibration_certif.csv"     # pour calculer θ, rien d'autre


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


def n_minimum(cible: float, delta: float, n_seuils: int = len(GRILLE)) -> int:
    """Plus petit n tel que zéro erreur sur n cas acceptés donne B*(0, n, δ / n_seuils) ≤ cible.

    δ est divisé par le nombre de seuils de la grille (Bonferroni), comme dans sgr. B*(0, n, δ') vaut
    1 − δ'^(1/n) : on part de la solution approchée ln(1/δ') / cible et on ajuste."""
    d = delta / n_seuils
    n = max(1, math.floor(math.log(1 / d) / cible) - 2)
    while n > 1 and borne_risque(0, n - 1, d) <= cible:
        n -= 1
    while borne_risque(0, n, d) > cible:
        n += 1
    return n


# ── SGR sur grille ───────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Choix:
    seuil: float
    borne: float
    risque: float
    retenus: int
    erreurs: int


def balayer(points: list[tuple[float, int]], delta: float, grille=GRILLE) -> list[dict]:
    """Pour chaque θ de la grille : n cas acceptés (κ ≥ θ), k pertes, risque k/n et borne B*(k, n, δ/G)."""
    d = delta / len(grille)
    out = []
    for theta in grille:
        sel = [p for k, p in points if k >= theta]
        n, err = len(sel), sum(sel)
        out.append({"seuil": theta, "n": n, "k": err, "risque": err / n if n else 0.0,
                    "borne": borne_risque(err, n, d)})
    return out


def sgr(points: list[tuple[float, int]], cible: float, delta: float, grille=GRILLE) -> Choix | None:
    """SGR sur grille fixe (voir l'en-tête). `points` : (κ, perte). Renvoie le θ le plus bas de la grille
    dont la borne est ≤ cible, ou None si aucun ne la garantit."""
    for b in balayer(points, delta, grille):   # grille croissante : le premier admissible est le plus bas
        if b["n"] and b["borne"] <= cible:
            return Choix(b["seuil"], b["borne"], b["risque"], b["n"], b["k"])
    return None


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


def charger_calibration(chemin: Path = CAS_CERTIF) -> list[dict]:
    """Cas de calibration au format du banc d'essai (input_text, expected_ids…), pour noter et perte."""
    if not chemin.exists():
        raise FileNotFoundError(f"{chemin} introuvable : lancer python build/build_calibration.py.")
    out = []
    for r in read_csv(chemin):
        out.append({"case_id": r["case_id"], "category": r["famille"], "input_text": r["terme"], "hint_type": "",
                    "expected_status": r["statut_attendu"], "expected_ids": r["attendu"], "accepted": "",
                    "nature": r["nature"], "perturbation": r["perturbation"], "alias_source": r["alias_source"]})
    return out


def sha256(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def collecter(cat: Catalogue, cas: list[dict], ecart: float = ECART, absents: bool = False,
              resolveur: ResolveurApproche | None = None, mode: str = "dangereuse") -> list[dict]:
    """Un point par cas qui atteint l'étape approchée : κ, famille et type des meilleurs noms, retenable
    (garde-fous), perte. Chaque cas passe dans le moteur avec un seuil quasi nul : on lit son score."""
    r = resolveur or ResolveurApproche(cat, SeuilFixe(1e-9, ecart))
    out = []
    for c in cas:
        res = r.resoudre(c["input_text"], c["hint_type"] or None, index_negatif=not absents)
        etape = next((t for t in res.trace if t.get("regle") == "R-RES-03"), None)
        if etape is None:
            continue
        retenu = etape["etape"] == "approche"
        out.append({"case_id": c["case_id"], "categorie": c["category"], "texte": c["input_text"],
                    "nature": c.get("nature", ""), "kappa": etape["score"], "type": etape["type"],
                    "famille": etape["famille"], "retenu": retenu,
                    "absent_simule": bool(cat.negatifs.get(res.norm)),
                    "perte": perte(c, res.statut, res.ids, mode) if retenu else 0})
    return out


def calibrer(points: list[dict], cible: float, delta: float, ecart: float, familles=(),
             grille=GRILLE) -> tuple[dict, dict]:
    """Seuil par famille (clé de la proposition, pas famille attendue) ou fuzzy désactivé.
    Renvoie (résumé pour le YAML, balayage complet de la grille pour le rapport)."""
    par_fam = defaultdict(list)
    for p in points:
        par_fam[p["famille"]].append(p)
    nmin = n_minimum(cible, delta, len(grille))
    resume, courbes = {}, {}
    for f in sorted(set(par_fam) | set(familles)):
        pts = [(p["kappa"], p["perte"]) for p in par_fam[f] if p["retenu"]]
        base = {"n_cas": len(par_fam[f]), "n_retenables": len(pts)}
        courbes[f] = balayer(pts, delta, grille) if pts else []
        # Famille désactivée : couverture nulle, et le meilleur point de la grille (plus petite borne) pour mémoire.
        meilleur = min(courbes[f], key=lambda b: b["borne"]) if pts else None
        off = {"couverture": 0.0, **base}
        if meilleur:
            off["meilleur_point"] = {"seuil": meilleur["seuil"], "n": meilleur["n"], "k": meilleur["k"],
                                     "borne": round(meilleur["borne"], 6)}
        if f == MIXTE:
            resume[f] = {"fuzzy": "desactive", **off,
                         "raison": "meilleurs noms de plusieurs familles : jamais d'approché (R-RES-10)"}
            continue
        if len(pts) < nmin:
            resume[f] = {"fuzzy": "desactive", **off,
                         "raison": f"{len(pts)} cas retenables, il en faut au moins {nmin} pour r* = {cible:g}"}
            continue
        ch = sgr(pts, cible, delta, grille)
        if ch is None:
            resume[f] = {"fuzzy": "desactive", **off,
                         "raison": f"aucun seuil de la grille ne garantit r* = {cible:g} au niveau δ = {delta:g} "
                                   f"(meilleure borne {meilleur['borne']:.4f} à θ = {meilleur['seuil']:.2f}, "
                                   f"k = {meilleur['k']} sur n = {meilleur['n']})"}
        else:
            resume[f] = {"fuzzy": "actif", "seuil": ch.seuil, "ecart": ecart, "n": ch.retenus, "k": ch.erreurs,
                         "borne": round(ch.borne, 6), "risque_empirique": round(ch.risque, 6),
                         "couverture": round(ch.retenus / len(pts), 4), **base}
    return resume, courbes


def sans_date(doc: dict) -> dict:
    """Le document sans sa date : c'est ce qu'on compare pour le déterminisme."""
    return {k: v for k, v in doc.items() if k != "date"}


def ecrire(familles: dict, cible: float, delta: float, ecart: float, absents: bool, empreinte: str,
           source: str, empreinte_cas: str, n_cas: int, mode: str = "dangereuse", grille=GRILLE,
           date: str | None = None, chemin=SEUILS) -> None:
    """Écrit le fichier de seuils. La date n'entre pas dans la comparaison de déterminisme : si le
    contenu (hors date) est inchangé, la date du fichier existant est gardée, et relancer la
    calibration ne modifie pas le fichier."""
    doc = {"methode": "SGR sur grille fixe (Geifman et El-Yaniv, 2017, lemme 3.1 et théorème 3.2 avec "
                      "Bonferroni sur la grille), un seuil par famille",
           "regle": "R-RES-10",
           "cible_risque": cible, "delta": delta, "ecart": ecart, "perte": mode,
           "grille": {"de": grille[0], "a": grille[-1], "pas": 0.01, "n_seuils": len(grille)},
           "n_minimum": n_minimum(cible, delta, len(grille)),
           "date": date or Date.today().isoformat(),
           "donnees": source, "sha256_donnees": empreinte_cas, "n_cas": n_cas,
           "familles_source": "spec/familles_fuzzy.yaml",
           "absents_simules": absents, "empreinte_catalogue": empreinte, "familles": familles}
    if date is None and chemin.exists():
        ancien = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
        if "date" in ancien and sans_date(ancien) == sans_date(yaml.safe_load(yaml.safe_dump(doc))):
            doc["date"] = ancien["date"]
    entete = ("# Seuils de l'étape approchée (R-RES-03, R-RES-10), un par famille de noms.\n"
              "# Fichier GÉNÉRÉ par python -m engine.calibration : ne pas modifier à la main, recalibrer.\n"
              "# Le moteur refuse ces seuils si l'empreinte du catalogue a changé.\n")
    chemin.write_text(entete + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=110),
                      encoding="utf-8")


def risque_seuil_fixe(points: list[dict], seuil: float = SEUIL_B, delta: float = DELTA) -> dict:
    """Risque d'un seuil fixé à l'avance (B) : par famille de proposition et au total, n acceptés,
    k pertes, taux k/n et borne B*(k, n, δ) (un seul seuil : pas de correction de grille)."""
    par = defaultdict(lambda: [0, 0])
    for p in points:
        if p["retenu"] and p["kappa"] >= seuil:
            for cle in (p["famille"], "TOTAL"):
                par[cle][0] += 1
                par[cle][1] += p["perte"]
    return {f: {"seuil": seuil, "n": n, "k": k, "risque": round(k / n, 6) if n else 0.0,
                "borne": round(borne_risque(k, n, delta), 6)}
            for f, (n, k) in sorted(par.items(), key=lambda x: (x[0] == "TOTAL", x[0]))}


def bilan_cas(cas: list[dict], points: list[dict]) -> dict:
    """Par famille attendue : cas présents et absents, et par famille de proposition : présents et absents."""
    out = defaultdict(Counter)
    for c in cas:
        out[c["category"]][c["nature"]] += 1
    prop = defaultdict(Counter)
    for p in points:
        prop[p["famille"]][p["nature"]] += 1
    return {"attendue": {k: dict(v) for k, v in sorted(out.items())},
            "proposition": {k: dict(v) for k, v in sorted(prop.items())}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Calibre les seuils Jaro-Winkler par famille (SGR sur grille, R-RES-10).")
    ap.add_argument("--cible", type=float, default=CIBLE,
                    help="r* : risque sélectif garanti, part maximale de pertes parmi les termes que l'approché "
                         f"accepte (défaut {CIBLE:g}, soit 0,5 %%)")
    ap.add_argument("--delta", type=float, default=DELTA,
                    help="δ : probabilité que la garantie soit fausse, c'est-à-dire que le vrai risque dépasse "
                         f"r* malgré la borne (défaut {DELTA:g} : garantie à 95 %%). Ce n'est pas le risque visé")
    ap.add_argument("--ecart", type=float, default=ECART, help="écart sous lequel deux noms sont ambigus")
    ap.add_argument("--perte", choices=PERTES, default="dangereuse", help="ce qui compte comme erreur")
    ap.add_argument("--cas", type=Path, default=CAS_CERTIF,
                    help="jeu de certification (défaut challenges/calibration_certif.csv)")
    ap.add_argument("--avec-absents", action="store_true",
                    help="robustesse : passer aussi les termes de l'index négatif à l'approché")
    args = ap.parse_args(argv)
    console_utf8()
    if not (0 < args.cible < 1 and 0 < args.delta < 1):
        raise SystemExit("--cible et --delta doivent être dans ]0, 1[.")
    cat = Catalogue.charger()
    fams = charger_familles(cat)
    cas = charger_calibration(args.cas)
    sonde = ResolveurApproche(cat, SeuilFixe(1e-9, args.ecart), index=IndexApproche(cat, fams))
    points = collecter(cat, cas, args.ecart, args.avec_absents, resolveur=sonde, mode=args.perte)
    resume, courbes = calibrer(points, args.cible, args.delta, args.ecart, sorted(set(fams.values())))
    try:
        source = args.cas.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        source = str(args.cas)
    empreinte_cas = sha256(args.cas)
    ecrire(resume, args.cible, args.delta, args.ecart, args.avec_absents, cat.empreinte, source, empreinte_cas,
           len(cas), args.perte)
    (REP / "calibration.json").write_text(json.dumps(
        {"cible": args.cible, "delta": args.delta, "perte": args.perte, "grille": list(GRILLE),
         "n_minimum": n_minimum(args.cible, args.delta), "sha256_donnees": empreinte_cas,
         "familles_types": {f: sorted(t for t, ff in fams.items() if ff == f) for f in sorted(set(fams.values()))},
         "donnees": source, "cas": bilan_cas(cas, points), "resume": resume, "courbes": courbes,
         "risque_b": risque_seuil_fixe(points, SEUIL_B, args.delta)},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(cas)} cas de calibration, {len(points)} atteignent l'approché · perte {args.perte} · "
          f"r* = {args.cible:g}, δ = {args.delta:g}, grille {GRILLE[0]:.2f}–{GRILLE[-1]:.2f} · "
          f"au moins {n_minimum(args.cible, args.delta)} cas acceptés par famille")
    for f, v in resume.items():
        if v["fuzzy"] == "actif":
            print(f"  {f:<20} actif      θ {v['seuil']:.2f}  n {v['n']}  k {v['k']}  borne {v['borne']:.4f}  "
                  f"couverture {100 * v['couverture']:.1f} %")
        else:
            print(f"  {f:<20} désactivé  {v['raison']}")
    print(f"→ {SEUILS.relative_to(ROOT)}, reports/calibration.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
