"""
Diagnostic des pertes de l'étape approchée, sur un jeu de calibration (outil de conception, R-RES-10).

    python -m engine.diagnostic_fuzzy                                  → challenges/calibration_analyse.csv
    python -m engine.diagnostic_fuzzy --cas challenges/calibration_cases.csv

À lancer seulement sur le jeu d'ANALYSE : le jeu de certification (calibration_certif.csv) sert
uniquement à calculer θ, on n'en regarde jamais les erreurs. Le module refuse ce fichier.

Pour chaque famille (famille de la proposition, celle qui choisit le seuil) et pour deux seuils, le
meilleur point de la grille (plus petite borne) et θ = 0,88 (configuration B), les pertes parmi les
termes acceptés (κ ≥ θ) sont réparties en deux sortes :

  present_confondu  le terme est une faute sur un nom du catalogue, et l'approché mène à une autre
                    entité (résolu faux, résolu là où l'attendu est ambigu, ou ambigu sans la bonne) ;
  absent_accepte    le terme n'est pas dans le catalogue, et l'approché l'accepte quand même.

Pour un présent confondu, on cherche un « voisin réel » : un autre nom du catalogue, d'un type des
entités attendues, à une seule faute de frappe du terme tapé (distance OSA ≤ 1 : substitution,
omission, insertion ou transposition de deux lettres voisines), comme Fressin pour « Fresin »
(faute sur Fretin). La distance se calcule sur les formes normalisées, dans l'ordre et en mots triés.

Sortie : reports/diagnostic_fuzzy.json (et un résumé à l'écran), 10 exemples par sorte et par seuil.
`--variante avant` (sans les deux corrections de structure), `mots_tries` ou `voisinage` (une seule)
écrivent reports/diagnostic_fuzzy_<variante>.json : c'est la mesure avant/après des corrections.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from rapidfuzz import process
from rapidfuzz.distance import OSA

from engine.approche import IndexApproche, SeuilFixe, charger_familles, distance  # noqa: F401
from engine.calibration import (CAS_ANALYSE, CAS_CERTIF, CIBLE, DELTA, ECART, GRILLE, SEUIL_B, balayer,
                                charger_calibration, perte)
from engine.catalogue import ROOT, Catalogue, cle_triee, console_utf8
from engine.evaluation import REP, noter
from engine.resolveur import ResolveurApproche

N_EXEMPLES = 10
VARIANTES = {"avant": (False, False), "mots_tries": (True, False), "voisinage": (False, True),
             "actuel": (True, True)}   # (ordre des mots, R-RES-11)
SORTES = ("present_confondu", "absent_accepte")


class Voisins:
    """Noms comparables du catalogue, par type d'entité, pour chercher un nom à une faute d'un terme."""

    def __init__(self, cat: Catalogue):
        self.cat = cat
        par_type = defaultdict(set)
        for nom, ents in cat.noms.items():
            for e in ents:
                par_type[cat.etype[e]].add(nom)
        self.par_type = {t: sorted(v) for t, v in par_type.items()}

    def a_une_faute(self, norm: str, types: set[str], exclus: set[str]) -> list[str]:
        """Noms des types donnés, hors `exclus`, à distance OSA ≤ 1 de `norm` (ordre ou mots triés)."""
        out = set()
        for t in sorted(types):
            pool = self.par_type.get(t, [])
            for q, choix in ((norm, pool), (cle_triee(norm), None)):
                if choix is None:     # mots triés : comparer les clés triées des noms
                    cles = [cle_triee(n) for n in pool]
                    res = process.extract(q, cles, scorer=OSA.distance, score_cutoff=1, limit=None)
                    out |= {pool[i] for _, _, i in res}
                else:
                    res = process.extract(q, choix, scorer=OSA.distance, score_cutoff=1, limit=None)
                    out |= {n for n, _, _ in res}
        return sorted(out - exclus)


def diagnostiquer(cat: Catalogue, cas: list[dict], resolveur: ResolveurApproche, seuils_par_famille: dict,
                  n_exemples: int = N_EXEMPLES) -> dict:
    """Pertes par famille et par seuil (« meilleur » et « b »), réparties par sorte, avec exemples."""
    vois = Voisins(cat)
    points = []
    for c in cas:
        res = resolveur.resoudre(c["input_text"], None)
        et = next((t for t in res.trace if t.get("regle") == "R-RES-03"), None)
        if et is None or et["etape"] != "approche":
            continue                                   # pas d'approché, ou refus d'un garde-fou
        p = perte(c, res.statut, res.ids)
        points.append({"c": c, "res": res, "et": et, "kappa": et["score"], "famille": et["famille"], "perte": p})

    out = {}
    for fam in sorted({p["famille"] for p in points} | set(seuils_par_famille)):
        pts = [p for p in points if p["famille"] == fam]
        if not pts:
            continue
        courbe = balayer([(p["kappa"], p["perte"]) for p in pts], DELTA)
        meilleur = min(courbe, key=lambda b: b["borne"])
        out[fam] = {"n_retenables": len(pts)}
        for nom, theta in (("meilleur", meilleur["seuil"]), ("b", SEUIL_B)):
            acc = [p for p in pts if p["kappa"] >= theta]
            pertes = [p for p in acc if p["perte"]]
            bloc = {"seuil": theta, "n": len(acc), "k": len(pertes),
                    "borne": next(b["borne"] for b in courbe if b["seuil"] == theta),
                    "par_sorte": {}, "exemples": {}}
            for sorte in SORTES:
                nat = "present" if sorte == "present_confondu" else "absent"
                lot = sorted((p for p in pertes if p["c"]["nature"] == nat), key=lambda p: p["c"]["case_id"])
                notes = Counter(noter(p["c"], p["res"].statut, p["res"].ids) for p in lot)
                d = {"n": len(lot), "notes": dict(notes),
                     "par_origine": dict(Counter(p["c"].get("perturbation", "").split(":")[0]
                                                 if nat == "absent" else "faute_de_frappe" for p in lot))}
                if sorte == "present_confondu":
                    avec = 0
                    for p in lot:
                        exp = [i for i in p["c"]["expected_ids"].split("|") if i]
                        types = {cat.etype[i] for i in exp if i in cat.etype}
                        sources = {n for n, ents in cat.noms.items() if ents & set(exp)}
                        p["voisins_reels"] = vois.a_une_faute(p["res"].norm, types, sources)
                        avec += bool(p["voisins_reels"])
                    d["avec_voisin_reel"] = avec
                bloc["par_sorte"][sorte] = d
                bloc["exemples"][sorte] = [exemple(p) for p in lot[:n_exemples]]
            out[fam][nom] = bloc
    return out


def exemple(p: dict) -> dict:
    c, res, et = p["c"], p["res"], p["et"]
    return {"case_id": c["case_id"], "terme": c["input_text"], "source": c.get("alias_source", ""),
            "perturbation": c.get("perturbation", ""), "attendu": c["expected_status"],
            "attendus": c["expected_ids"], "kappa": round(p["kappa"], 4), "noms": et.get("noms", []),
            "statut": res.statut, "ids": list(res.ids), "note": noter(c, res.statut, res.ids),
            **({"voisins_reels": p["voisins_reels"]} if "voisins_reels" in p else {})}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Diagnostic des pertes de l'étape approchée (jeu d'analyse).")
    ap.add_argument("--cas", type=Path, default=CAS_ANALYSE, help="jeu à diagnostiquer (jamais le jeu de certification)")
    ap.add_argument("--sortie", type=Path, default=None,
                    help="défaut : reports/diagnostic_fuzzy.json, ou reports/diagnostic_fuzzy_<variante>.json")
    ap.add_argument("--variante", choices=sorted(VARIANTES), default="actuel",
                    help="avant : sans les deux corrections ; mots_tries ou voisinage : une seule ; actuel : les deux")
    args = ap.parse_args(argv)
    console_utf8()
    if args.sortie is None:
        args.sortie = REP / ("diagnostic_fuzzy.json" if args.variante == "actuel" else f"diagnostic_fuzzy_{args.variante}.json")
    if args.cas.resolve() == CAS_CERTIF.resolve():
        raise SystemExit(f"{CAS_CERTIF.name} sert seulement à calculer θ : on n'en regarde pas les erreurs. "
                         f"Diagnostiquer {CAS_ANALYSE.name}.")
    cat = Catalogue.charger()
    fams = charger_familles(cat)
    cas = charger_calibration(args.cas)
    mt, vs = VARIANTES[args.variante]
    sonde = ResolveurApproche(cat, SeuilFixe(1e-9, ECART), index=IndexApproche(cat, fams, mots_tries=mt), voisinage=vs)
    diag = diagnostiquer(cat, cas, sonde, {f: None for f in set(fams.values())})
    try:
        source = args.cas.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        source = str(args.cas)
    args.sortie.write_text(json.dumps({"donnees": source, "variante": args.variante, "n_cas": len(cas), "cible": CIBLE, "delta": DELTA,
                                       "grille": list(GRILLE), "familles": diag}, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    for fam, d in diag.items():
        print(f"\n{fam} · {d['n_retenables']} termes retenables")
        for nom in ("meilleur", "b"):
            b = d[nom]
            pc, aa = b["par_sorte"]["present_confondu"], b["par_sorte"]["absent_accepte"]
            print(f"  θ {b['seuil']:.2f} ({'meilleur point' if nom == 'meilleur' else 'B'}) · n {b['n']} · k {b['k']} · "
                  f"borne {100 * b['borne']:.2f} % · présents confondus {pc['n']} (voisin réel à 1 faute : "
                  f"{pc['avec_voisin_reel']}) · absents acceptés {aa['n']}")
    print(f"\n→ {args.sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
