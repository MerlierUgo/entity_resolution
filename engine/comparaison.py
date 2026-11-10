"""
Comparaison des configurations de l'étape approchée, sur la part « eval » de dev uniquement (30 %,
jamais vue par la calibration). La partition test n'est jamais lue.

    python -m engine.comparaison        → reports/fuzzy_dev.md et reports/fuzzy_dev.json

  A  étape 1 seule : alias exact, mots triés, index négatif (aucune correspondance approchée) ;
  B  étape 2, SeuilFixe(0.88, 0.03) : la valeur initiale de R-RES-03 pour tous les types ;
  C  étape 2, SeuilsCalibres : spec/seuils_fuzzy.yaml, écrit par python -m engine.calibration.

Trois mesures :
  1. idéal / sûr / erreur silencieuse par catégorie, pour A, B et C ;
  2. robustesse : les termes de l'index négatif passés à l'approché, comme s'il ne les connaissait
     pas (un lieu réel hors périmètre absent de GeoNames, par exemple) ;
  3. courbe risque-couverture par type : pour chaque seuil θ, la part des cas du type qui reçoivent
     une réponse approchée (couverture) et la part de pertes parmi elles (risque sélectif).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

import yaml

from engine.approche import SEUILS, SeuilFixe, SeuilsCalibres
from engine.calibration import PERTES, collecter
from engine.catalogue import Catalogue, console_utf8
from engine.evaluation import REP, charger_cas, evaluer, taux
from engine.resolveur import ResolveurApproche, ResolveurExact

SEUIL_B, ECART_B = 0.88, 0.03
MIN_COURBE = 20      # cas retenables minimum pour tracer la courbe d'un type


def courbe(points: list[dict], n_type: int) -> list[dict]:
    """Points (seuil, couverture, risque) pour chaque κ distinct, du plus strict au plus large."""
    pts = sorted((p for p in points if p["retenu"]), key=lambda p: -p["kappa"])
    out, err = [], 0
    for i, p in enumerate(pts, 1):
        err += p["perte"]
        if i == len(pts) or pts[i]["kappa"] < p["kappa"]:
            out.append({"seuil": round(p["kappa"], 4), "couverture": round(i / n_type, 4),
                        "risque": round(err / i, 4), "retenus": i, "pertes": err})
    return out


def point_a(points: list[dict], n_type: int, seuil: float) -> dict:
    sel = [p for p in points if p["retenu"] and p["kappa"] >= seuil]
    return {"seuil": seuil, "couverture": round(len(sel) / n_type, 4) if n_type else 0.0,
            "risque": round(sum(p["perte"] for p in sel) / len(sel), 4) if sel else 0.0,
            "retenus": len(sel), "pertes": sum(p["perte"] for p in sel)}


def comptes_taux(comptes: dict) -> dict:
    return {cat: {"n": taux(c)[0], "ideal": round(taux(c)[1], 2), "sur": round(taux(c)[2], 2),
                  "silencieux": round(taux(c)[3], 2), "detail": c} for cat, c in comptes.items()}


def main() -> int:
    console_utf8()
    cat = Catalogue.charger()
    seuils = yaml.safe_load(SEUILS.read_text(encoding="utf-8"))
    politique_c = SeuilsCalibres.charger(cat)
    cas = charger_cas("dev", "eval")
    configs = {"A": ResolveurExact(cat), "B": ResolveurApproche(cat, SeuilFixe(SEUIL_B, ECART_B))}
    configs["C"] = ResolveurApproche(cat, politique_c, index=configs["B"].index)
    noms = {"A": "étape 1 seule (exact)", "B": f"SeuilFixe({SEUIL_B}, {ECART_B})",
            "C": f"SeuilsCalibres (SGR, r* = {seuils['cible_risque']:g}, δ = {seuils['delta']:g})"}

    resultats = {k: comptes_taux(evaluer(r, cas)["comptes"]) for k, r in configs.items()}

    # robustesse : termes de l'index négatif passés à l'approché
    negs = [c for c in cas if cat.negatifs.get(cat.normaliser(c["input_text"]))
            and not configs["A"].candidats_exacts(cat.normaliser(c["input_text"]))[0]]
    robustesse = {}
    for k in ("B", "C"):
        sil = []
        for c in negs:
            r = configs[k].resoudre(c["input_text"], c["hint_type"] or None, index_negatif=False)
            if r.statut == "resolved" and r.ids[0] not in c["expected_ids"].split("|"):
                sil.append({"texte": c["input_text"], "ids": list(r.ids)})
        robustesse[k] = {"n": len(negs), "silencieux": len(sil), "exemples": sil[:8]}

    # courbes risque-couverture par type, pour les deux définitions de la perte
    sonde = ResolveurApproche(cat, SeuilFixe(1e-9, ECART_B), index=configs["B"].index)
    par_mode = {m: collecter(cat, cas, ECART_B, mode=m, resolveur=sonde) for m in PERTES}
    courbes = {}
    for t in sorted({p["type"] for p in par_mode["dangereuse"]},
                    key=lambda t: -sum(p["type"] == t for p in par_mode["dangereuse"])):
        cal = seuils["types"].get(t, {})
        c = {"n_cas": 0, "calibration": cal}
        for m, pts in par_mode.items():
            pts = [p for p in pts if p["type"] == t]
            c["n_cas"] = len(pts)
            c[m] = {"points": courbe(pts, len(pts)), "b": point_a(pts, len(pts), SEUIL_B),
                    "c": point_a(pts, len(pts), cal["seuil"]) if cal.get("fuzzy") == "actif" else None}
        if sum(p["type"] == t and p["retenu"] for p in par_mode["dangereuse"]) >= MIN_COURBE:
            courbes[t] = c

    sortie = {"n_cas_eval": len(cas), "configurations": noms, "seuils": seuils, "resultats": resultats,
              "robustesse": robustesse, "courbes": courbes}
    (REP / "fuzzy_dev.json").write_text(json.dumps(sortie, ensure_ascii=False, indent=1), encoding="utf-8")

    lignes = ["# Étape approchée · comparaison A, B, C · dev, part eval", "",
              f"Généré par `python -m engine.comparaison`. {len(cas)} cas (30 % de dev, hash du case_id), "
              "jamais vus par la calibration.", ""]
    lignes += [f"- **{k}** : {v}" for k, v in noms.items()]
    lignes += ["", "| Catégorie | Cas | " + " | ".join(f"{k} idéal | {k} sûr | {k} silencieux" for k in noms) + " |",
               "|---|---:|" + "---:|---:|---:|" * len(noms)]
    for cat_ in resultats["A"]:
        cel = []
        for k in noms:
            v = resultats[k][cat_]
            cel += [f"{v['ideal']:.1f}", f"{v['sur']:.1f}", f"{v['silencieux']:.1f}"]
        nom = f"**{cat_}**" if cat_ == "TOTAL" else cat_
        lignes.append(f"| {nom} | {resultats['A'][cat_]['n']} | " + " | ".join(cel) + " |")
    lignes += ["", "## Robustesse : termes de l'index négatif passés à l'approché", ""]
    lignes += [f"- {k} : {v['silencieux']} erreurs silencieuses sur {v['n']} termes" for k, v in robustesse.items()]
    mode = seuils.get("perte", "dangereuse")
    lignes += ["", "## Risque-couverture par type (seuil 0,88 et seuil calibré)", "",
               f"Perte « {mode} », celle de la calibration. La courbe complète, avec la perte « non_sure », "
               "est dans fuzzy_dev.json.", "",
               "| Type | Cas | Couverture à 0,88 | Risque à 0,88 | Seuil C | Couverture C | Risque C |",
               "|---|---:|---:|---:|---:|---:|---:|"]
    for t, c in courbes.items():
        b, cc = c[mode]["b"], c[mode]["c"]
        lignes.append(f"| {t} | {c['n_cas']} | {100 * b['couverture']:.1f} % | {100 * b['risque']:.1f} % | "
                      + (f"{cc['seuil']:.4f} | {100 * cc['couverture']:.1f} % | {100 * cc['risque']:.1f} % |" if cc
                         else "désactivé | 0 % | · |"))
    (REP / "fuzzy_dev.md").write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print("\n".join(lignes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
