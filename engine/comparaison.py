"""
Comparaison des configurations de l'étape approchée, sur la part « eval » de dev uniquement (30 % de
dev, même découpe par hash du case_id qu'avant). La partition test n'est jamais lue.

    python -m engine.comparaison        → reports/fuzzy_dev.md et reports/fuzzy_dev.json

  A  étape 1 seule : alias exact, mots triés, index négatif (aucune correspondance approchée) ;
  B  étape 2, SeuilFixe(0.88, 0.03) : la valeur initiale de R-RES-03 pour toutes les familles ;
  C  étape 2, SeuilsCalibres : un seuil par famille, spec/seuils_fuzzy.yaml (R-RES-10).
  B et C sont refaits sans index négatif (B−, C−), pour mesurer ce qu'il apporte.

Mesures, en global et par famille du cas (famille des entités attendues, ou de l'indice de type pour
un cas sans entité) : idéal, sûr, erreur silencieuse, et couverture du fuzzy (part des cas dont la
réponse vient de l'étape approchée : les cas « rattrapés »).

Exemples : cas rattrapés par C, cas perdus par C par rapport à B (avec la raison lue dans la trace),
et toutes les erreurs silencieuses avec leur trace complète.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict

import yaml

from engine.approche import MIXTE, SEUILS, IndexApproche, SeuilFixe, SeuilsCalibres, charger_familles
from engine.catalogue import Catalogue, console_utf8
from engine.evaluation import REP, SURS, charger_cas, noter
from engine.resolveur import ResolveurApproche, ResolveurExact

SEUIL_B, ECART_B = 0.88, 0.03
N_EXEMPLES = 10
SANS_ENTITE = "sans_entite"


def famille_cas(cas: dict, cat: Catalogue, fams: dict[str, str]) -> str:
    ids = [i for i in cas["expected_ids"].split("|") if i]
    if ids:
        f = {fams.get(cat.etype.get(i, ""), MIXTE) for i in ids}
        return f.pop() if len(f) == 1 else MIXTE
    if cas["hint_type"]:
        f = {fams.get(t, MIXTE) for t in cas["hint_type"].split("|")}
        return f.pop() if len(f) == 1 else MIXTE
    return SANS_ENTITE


def mesures(c: Counter) -> dict:
    n = c["n"]
    pct = (lambda x: round(100 * x / n, 2)) if n else (lambda x: 0.0)
    return {"n": n, "ideal": pct(c["correct"]), "sur": pct(sum(c[s] for s in SURS)),
            "silencieux": c["erreur_silencieuse"], "silencieux_pct": pct(c["erreur_silencieuse"]),
            "couverture_fuzzy": pct(c["rattrape"]), "rattrapes": c["rattrape"],
            "rattrapes_corrects": c["rattrape_correct"]}


def etape_approche(res) -> dict | None:
    return next((t for t in res.trace if t.get("regle") == "R-RES-03"), None)


def raison_perte(res_c, seuils: dict) -> str:
    """Pourquoi C n'a pas répondu comme B, d'après la trace de C."""
    et = etape_approche(res_c)
    if et is None:
        return "pas d'approché (garde-fou d'entrée)"
    fam = et.get("famille", "?")
    cal = (seuils.get("familles") or {}).get(fam, {})
    if fam == MIXTE:
        return "meilleurs noms de plusieurs familles (mixte) : désactivé"
    if cal.get("fuzzy") != "actif":
        r = cal.get("raison", "famille absente des seuils")
        motif = "volume" if "il en faut au moins" in r else "risque" if "aucun seuil" in r else "autre"
        return f"famille {fam} désactivée ({motif})"
    if et["score"] < cal["seuil"]:
        return f"κ sous θ {fam} = {cal['seuil']:.2f} (B accepte dès 0,88)"
    return "autre (écart ou garde-fou)"


def tourniquet(items: list[dict], cle: str, n: int) -> list[dict]:
    """n exemples répartis entre les valeurs de `cle` (familles), dans l'ordre des case_id."""
    par = defaultdict(list)
    for it in sorted(items, key=lambda x: x["case_id"]):
        par[it[cle]].append(it)
    out, i = [], 0
    while len(out) < n and any(i < len(v) for v in par.values()):
        for k in sorted(par):
            if i < len(par[k]) and len(out) < n:
                out.append(par[k][i])
        i += 1
    return out


def resume_cas(c: dict, fam: str, res, note: str) -> dict:
    return {"case_id": c["case_id"], "famille": fam, "categorie": c["category"], "texte": c["input_text"],
            "hint": c["hint_type"], "attendu": c["expected_status"], "attendus": c["expected_ids"],
            "statut": res.statut, "ids": list(res.ids), "note": note, "trace": list(res.trace)}


def main() -> int:
    console_utf8()
    cat = Catalogue.charger()
    fams = charger_familles(cat)
    seuils = yaml.safe_load(SEUILS.read_text(encoding="utf-8"))
    idx = IndexApproche(cat, fams)
    pol_b, pol_c = SeuilFixe(SEUIL_B, ECART_B), SeuilsCalibres.charger(cat)
    configs = {  # nom → (résolveur, index négatif)
        "A": (ResolveurExact(cat), True),
        "B": (ResolveurApproche(cat, pol_b, index=idx), True),
        "C": (ResolveurApproche(cat, pol_c, index=idx), True),
        "B−": (ResolveurApproche(cat, pol_b, index=idx), False),
        "C−": (ResolveurApproche(cat, pol_c, index=idx), False),
    }
    noms = {"A": "étape 1 seule (exact)", "B": f"SeuilFixe({SEUIL_B}, {ECART_B})",
            "C": f"SeuilsCalibres par famille (SGR, r* = {seuils['cible_risque']:g}, δ = {seuils['delta']:g})",
            "B−": "B sans index négatif", "C−": "C sans index négatif"}
    cas = charger_cas("dev", "eval")

    comptes = {k: defaultdict(Counter) for k in configs}
    par_cas = defaultdict(dict)
    silencieuses = []
    for c in cas:
        fam = famille_cas(c, cat, fams)
        for k, (r, neg) in configs.items():
            res = r.resoudre(c["input_text"], c["hint_type"] or None, index_negatif=neg)
            note = noter(c, res.statut, res.ids)
            rattrape = res.etape == "approche"
            for cle in (fam, "TOTAL"):
                cpt = comptes[k][cle]
                cpt["n"] += 1
                cpt[note] += 1
                cpt["rattrape"] += rattrape
                cpt["rattrape_correct"] += rattrape and note == "correct"
            par_cas[c["case_id"]][k] = (res, note)
            if note == "erreur_silencieuse":
                silencieuses.append({"config": k, **resume_cas(c, fam, res, note)})
        par_cas[c["case_id"]]["_fam"] = fam

    resultats = {k: {f: mesures(v) for f, v in sorted(cpt.items(), key=lambda x: (x[0] == "TOTAL", x[0]))}
                 for k, cpt in comptes.items()}

    cas_id = {c["case_id"]: c for c in cas}
    rattrapes_c, perdus_c, raisons = [], [], Counter()
    for cid, d in par_cas.items():
        fam = d["_fam"]
        (ra, na), (rb, nb), (rc, nc) = d["A"], d["B"], d["C"]
        if nc == "correct" and rc.etape == "approche" and na != "correct":
            rattrapes_c.append(resume_cas(cas_id[cid], fam, rc, nc))
        if nb == "correct" and nc != "correct":
            raison = raison_perte(rc, seuils)
            raisons[(fam, raison)] += 1
            et_b = etape_approche(rb)
            perdus_c.append({**resume_cas(cas_id[cid], fam, rc, nc), "raison": raison,
                             "b_ids": list(rb.ids), "b_statut": rb.statut,
                             "kappa": round(et_b["score"], 4) if et_b else None})

    sortie = {"n_cas_eval": len(cas), "configurations": noms, "seuils": seuils, "resultats": resultats,
              "perdus_par_c": {"total": len(perdus_c),
                               "raisons": [{"famille": f, "raison": r, "n": n} for (f, r), n in raisons.most_common()]},
              "exemples": {"rattrapes_c": tourniquet(rattrapes_c, "famille", N_EXEMPLES),
                           "n_rattrapes_c": len(rattrapes_c),
                           "perdus_c": tourniquet(perdus_c, "famille", N_EXEMPLES),
                           "silencieuses": sorted(silencieuses, key=lambda x: (x["config"], x["case_id"]))}}
    (REP / "fuzzy_dev.json").write_text(json.dumps(sortie, ensure_ascii=False, indent=1), encoding="utf-8")

    lignes = ["# Étape approchée · comparaison A, B, C · dev, part eval", "",
              f"Généré par `python -m engine.comparaison`. {len(cas)} cas (30 % de dev, hash du case_id). "
              "La partition test n'est pas lue.", ""]
    lignes += [f"- **{k}** : {v}" for k, v in noms.items()]
    lignes += ["", "Idéal et sûr en %, silencieux en nombre de cas, fuzzy = part des cas rattrapés par l'approché (%).",
               "", "| Famille | Cas | " + " | ".join(f"{k} idéal | {k} sûr | {k} sil. | {k} fuzzy" for k in configs) + " |",
               "|---|---:|" + "---:|---:|---:|---:|" * len(configs)]
    for f in resultats["A"]:
        cel = []
        for k in configs:
            v = resultats[k][f]
            cel += [f"{v['ideal']:.1f}", f"{v['sur']:.1f}", str(v["silencieux"]), f"{v['couverture_fuzzy']:.1f}"]
        lignes.append(f"| {'**TOTAL**' if f == 'TOTAL' else f} | {resultats['A'][f]['n']} | " + " | ".join(cel) + " |")
    lignes += ["", f"## Cas perdus par C par rapport à B : {len(perdus_c)}", ""]
    lignes += [f"- {f} · {r} : {n}" for (f, r), n in raisons.most_common()]
    lignes += ["", f"## Erreurs silencieuses : {len(silencieuses)}", ""]
    lignes += [f"- {s['config']} · {s['case_id']} « {s['texte']} » → {s['ids']} (attendu {s['attendus'] or s['attendu']})"
               for s in sortie["exemples"]["silencieuses"]]
    (REP / "fuzzy_dev.md").write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print("\n".join(lignes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
