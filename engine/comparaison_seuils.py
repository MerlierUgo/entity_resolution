"""
Comparaison des politiques de seuil de l'étape approchée (mesure « avant corrections »).

    python -m engine.comparaison_seuils          → reports/comparaison_seuils.json

  A = exact seul (AucunApproche) ; B = seuil fixe 0,88, écart 0,03 (SeuilFixe) ;
  C = seuils calibrés par famille (SeuilsCalibres, spec/seuils_fuzzy.yaml, R-RES-10).

Jeux : banc (v0.3), banc pessimiste, échantillon réel (sans indice et avec l'indice du type), variantes de
sensibilité des absents (banc et analyse, absents 5 % et 25 %). Les deux jeux de certification ne sont JAMAIS
évalués ici (ils servent à la calibration seulement, en comptes agrégés).

Indicateurs, global et par famille : idéal, sûr, erreurs silencieuses (dont collisions exactes), couverture du
fuzzy (part des saisies passées par l'étape approchée où le fuzzy accepte un nom), et risque du fuzzy seul
(erreurs silencieuses parmi les noms acceptés par le fuzzy). Notation du modèle de saisie § 8
(engine/mesure_saisies.py · noter).
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict

from engine.approche import AucunApproche, SeuilFixe, SeuilsCalibres
from engine.catalogue import ROOT, console_utf8, normalize
from engine.mesure_saisies import (CHAL, bs, charger_catalogue_jeux, charger_jeu, collision_exacte, lignes_reelles,
                                   mots_oublies, noter)
from engine.resolveur import ResolveurApproche

SORTIE = ROOT / "reports" / "comparaison_seuils.json"
JEUX = {"banc": CHAL / "saisies_banc.csv",
        "banc_pessimiste": CHAL / "saisies_banc_pessimiste.csv",
        "banc_absents_0.05": CHAL / "sensibilite" / "saisies_banc_e0.20_a0.05.csv",
        "banc_absents_0.25": CHAL / "sensibilite" / "saisies_banc_e0.20_a0.25.csv",
        "analyse_absents_0.05": CHAL / "sensibilite" / "saisies_analyse_e0.20_a0.05.csv",
        "analyse_absents_0.25": CHAL / "sensibilite" / "saisies_analyse_e0.20_a0.25.csv"}


def politiques() -> dict:
    return {"A": AucunApproche(), "B": SeuilFixe(0.88, 0.03), "C": SeuilsCalibres.charger()}


def evaluer(res: ResolveurApproche, cas: list[dict], cache: dict) -> list[dict]:
    """cas : terme, indice, attendu_statut, attendu_ids (set), famille, fautive."""
    out = []
    for c in cas:
        cle = (c["terme"], c["indice"])
        if cle not in cache:
            r = res.resoudre(c["terme"], c["indice"] or None)
            app = any(t.get("regle") == "R-RES-03" for t in r.trace)
            cache[cle] = (r.statut, set(r.ids), r.etape, app)
        statut, ids, etape, app = cache[cle]
        note = noter(c["attendu_statut"], c["attendu_ids"], statut, ids)
        out.append({"famille": c["famille"], "note": note, "statut": statut,
                    "collision": collision_exacte(note, etape, c["fautive"]),
                    "approche": app, "accepte_fuzzy": etape == "approche"})
    return out


def indicateurs(res: list[dict]) -> dict:
    n = len(res)
    if not n:
        return {"n": 0}
    c = Counter(r["note"] for r in res)
    coll = sum(r["collision"] for r in res)
    app = [r for r in res if r["approche"]]
    acc = [r for r in app if r["accepte_fuzzy"]]
    sil_fuzzy = sum(r["note"] == "silencieux" for r in acc)
    return {"n": n, "ideal": round(100 * c["ideal"] / n, 2), "sur": round(100 * (c["ideal"] + c["sur"]) / n, 2),
            "silencieux": c["silencieux"], "silencieux_pct": round(100 * c["silencieux"] / n, 2),
            "dont_collision_exacte": coll, "silencieux_hors_collision": c["silencieux"] - coll,
            "trop_confiant": c["trop_confiant"], "incorrect": c["incorrect"],
            "passe_par_approche": len(app), "acceptes_fuzzy": len(acc),
            "couverture_fuzzy": round(100 * len(acc) / len(app), 2) if app else None,
            "silencieux_fuzzy": sil_fuzzy,
            "risque_fuzzy_pct": round(100 * sil_fuzzy / len(acc), 2) if acc else None}


def mesurer(res: list[dict]) -> dict:
    par = defaultdict(list)
    for r in res:
        par[r["famille"]].append(r)
    return {"global": indicateurs(res), "par_famille": {f: indicateurs(v) for f, v in sorted(par.items())}}


def cas_generes(lignes: list[dict]) -> list[dict]:
    return [{"terme": l["terme"], "indice": l["indice_type"], "attendu_statut": l["attendu_statut"],
             "attendu_ids": {i for i in l["attendu_ids"].split("|") if i}, "famille": l["famille"],
             "fautive": bool(l["perturbations"] or l["mots_oublies"])} for l in lignes]


def cas_reels(ctx, avec_indice: bool) -> list[dict]:
    reels, _, _ = lignes_reelles()
    out = []
    for r in reels:
        src, t = normalize(r["nom_cible"]), normalize(r["saisie"])
        oublies, court = mots_oublies(src, t)
        hint = r["entity_type"] if avec_indice else ""
        att = ctx.attendu(r["saisie"], src, r["entity_id"], court if oublies else None, hint or None)
        out.append({"terme": r["saisie"], "indice": hint, "attendu_statut": att["statut"],
                    "attendu_ids": set(att["ids"]), "famille": r["famille"], "fautive": t != src})
    return out


def main(argv=None) -> int:
    console_utf8()
    modele = bs.Modele.charger()
    ctx = bs.Contexte(modele)
    cat_jeux = charger_catalogue_jeux(ctx.cat)
    pol = politiques()
    out = {"politiques": {k: p.decrire() for k, p in pol.items()}, "jeux": {}}
    resolveurs = {("jeux", k): ResolveurApproche(cat_jeux, p) for k, p in pol.items()}
    resolveurs.update({("reel", k): ResolveurApproche(ctx.cat, p) for k, p in pol.items()})
    caches = defaultdict(dict)
    jeux = {nom: ("jeux", cas_generes(charger_jeu(chemin))) for nom, chemin in JEUX.items()}
    jeux["reel_sans_indice"] = ("reel", cas_reels(ctx, False))
    jeux["reel_avec_indice"] = ("reel", cas_reels(ctx, True))
    for nom, (cat_cle, cas) in jeux.items():
        out["jeux"][nom] = {}
        for k in pol:
            m = mesurer(evaluer(resolveurs[(cat_cle, k)], cas, caches[(cat_cle, k)]))
            out["jeux"][nom][k] = m
            g = m["global"]
            print(f"{nom} · {k} : idéal {g['ideal']} %, sûr {g['sur']} %, silencieux {g['silencieux']} "
                  f"({g['silencieux_pct']} %, dont collisions {g['dont_collision_exacte']}), couverture fuzzy "
                  f"{g['couverture_fuzzy']} %, risque fuzzy {g['risque_fuzzy_pct']} %", flush=True)
    SORTIE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {SORTIE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
