"""
Analyse descriptive : pourquoi certaines familles n'obtiennent pas de seuil calibré (R-RES-10).

    python -m engine.analyse_familles        → reports/analyse_familles.json

Rien n'est modifié (moteur, seuils, catalogue). Sources : le catalogue et challenges/saisies_analyse.csv
uniquement ; les jeux de certification ne sont jamais lus (charger_jeu les refuse).

Hypothèse examinée : les noms courts perdent plus de score Jaro-Winkler par faute, donc tombent sous les paliers
stricts (0,99…) testés en premier par la séquence fixe, donc trop peu de noms résolus pour passer le premier palier.

  1. longueur des noms comparables du catalogue (formes normalisées, hors codes : Catalogue.noms), par famille ;
  2. meilleur score Jaro-Winkler κ des saisies fautives présentes de l'analyse qui atteignent l'étape approchée,
     par famille, et part au-dessus des paliers 0,99 / 0,98 / 0,97 / 0,95 / 0,90 ;
  3. issue de ces saisies (resolved, ambiguous par noms voisins ou par homonymes, unknown sous le seuil ou par
     garde-fou) à θ 0,80 et à θ 0,99 ;
  4. κ des saisies à exactement une faute (sans mot oublié ni forme courte), par tranche de longueur du nom source.

Le moteur tourne une fois par saisie à θ = 0,80 (SeuilFixe(0.80, 0.03)), comme la calibration : l'issue à un θ
plus strict s'en déduit (κ < θ → unknown, sinon même issue). Famille d'une saisie : celle du nom source tiré par le
générateur (colonne famille), pas celle des meilleurs noms trouvés.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict

import yaml

from engine.approche import FAMILLES_FUZZY, SeuilFixe
from engine.catalogue import ROOT, Catalogue, console_utf8
from engine.mesure_saisies import CHAL, charger_catalogue_jeux, charger_jeu
from engine.resolveur import ResolveurApproche

SORTIE = ROOT / "reports" / "analyse_familles.json"
JEU = CHAL / "saisies_analyse.csv"
THETA_BAS = 0.80
PALIERS = (0.99, 0.98, 0.97, 0.95, 0.90)
TRANCHES = ((0, 6, "≤ 6"), (7, 10, "7–10"), (11, 15, "11–15"), (16, 25, "16–25"), (26, 10 ** 6, "> 25"))
ISSUES = ("resolved", "ambiguous_voisins", "ambiguous_homonymes", "unknown_regles", "unknown_garde_fou",
          "unknown_sous_seuil")


# ── fonctions pures ──────────────────────────────────────────────────────────────────────────────

def quantile(xs: list[float], q: float) -> float | None:
    """Quantile à interpolation linéaire (type 7) d'une liste triée."""
    if not xs:
        return None
    h = (len(xs) - 1) * q
    i = int(h)
    return xs[i] if i + 1 >= len(xs) else xs[i] + (h - i) * (xs[i + 1] - xs[i])


def resume(xs) -> dict:
    """Boîte à moustaches (moustaches aux centiles 5 et 95) et moyenne."""
    xs = sorted(xs)
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "moyenne": round(sum(xs) / len(xs), 4),
            **{k: round(quantile(xs, q), 4) for k, q in
               (("p05", .05), ("q1", .25), ("mediane", .5), ("q3", .75), ("p95", .95))},
            "min": round(xs[0], 4), "max": round(xs[-1], 4)}


def tranche(longueur: int) -> str:
    return next(nom for bas, haut, nom in TRANCHES if bas <= longueur <= haut)


def issue(score: float, theta: float, etape: str, statut: str, nb_noms: int) -> str:
    """Issue d'une saisie passée par l'approché, au seuil θ (moteur lancé à θ ≤ score pour les saisies retenues)."""
    if score < theta:
        return "unknown_sous_seuil"
    if etape != "approche":
        return "unknown_garde_fou"          # score suffisant mais garde-fou (mots courts, nombre de mots)
    if statut == "resolved":
        return "resolved"
    if statut == "ambiguous":
        return "ambiguous_voisins" if nb_noms > 1 else "ambiguous_homonymes"
    return "unknown_regles"                 # règles de contexte ou indice : plus aucun candidat


def familles() -> dict[str, str]:
    fam = yaml.safe_load(FAMILLES_FUZZY.read_text(encoding="utf-8"))["familles"]
    return {t: f for f, ts in fam.items() for t in ts}


# ── mesures ──────────────────────────────────────────────────────────────────────────────────────

def longueurs_catalogue(cat: Catalogue, famille_de: dict) -> dict:
    par = defaultdict(list)
    hors = Counter()
    for nom, ents in cat.noms.items():
        fams = {famille_de.get(cat.etype[e]) for e in ents}
        if len(fams) != 1 or None in fams:
            hors["mixte" if len(fams - {None}) > 1 else "hors_famille"] += 1
            continue
        par[next(iter(fams))].append(len(nom))
    out = {}
    for f, ls in sorted(par.items()):
        out[f] = {**resume(ls), "part_le_8": round(sum(l <= 8 for l in ls) / len(ls), 4),
                  "part_ge_20": round(sum(l >= 20 for l in ls) / len(ls), 4)}
    return {"par_famille": out, "ecartes": dict(sorted(hors.items()))}


def passer(res: ResolveurApproche, lignes: list[dict]) -> list[dict]:
    """Une ligne par saisie fautive présente : score κ (None si l'approché n'a pas été atteint) et issue."""
    out = []
    for l in lignes:
        if l["nature"] != "present" or not (l["perturbations"] or l["mots_oublies"]):
            continue
        r = res.resoudre(l["terme"], l["indice_type"] or None)
        app = next((t for t in r.trace if t.get("regle") == "R-RES-03" and "score" in t), None)
        out.append({"famille": l["famille"], "score": app["score"] if app else None, "etape": r.etape,
                    "statut": r.statut, "nb_noms": len(app.get("noms", [])) if app else 0,
                    "fautes": int(l["nb_perturbations"] or 0), "oubli": bool(l["mots_oublies"]),
                    "courte": bool(l["forme_courte"]), "long_source": len(res.cat.normaliser(l["nom_source"]))})
    return out


def scores_par_famille(saisies: list[dict]) -> dict:
    par = defaultdict(list)
    for s in saisies:
        par[s["famille"]].append(s)
    out = {}
    for f, ss in sorted(par.items()):
        sc = [s["score"] for s in ss if s["score"] is not None]
        avant = Counter(s["etape"] for s in ss if s["score"] is None)
        out[f] = {"fautives": len(ss), "avec_score": len(sc), "sans_score": dict(sorted(avant.items())),
                  "score": resume(sc),
                  "part_ge": {f"{p:.2f}": round(sum(x >= p for x in sc) / len(sc), 4) if sc else None for p in PALIERS},
                  "long_source": resume([s["long_source"] for s in ss])}
        issues = {}
        for theta in (THETA_BAS, 0.95, 0.99):
            c = Counter(issue(s["score"], theta, s["etape"], s["statut"], s["nb_noms"]) for s in ss if s["score"] is not None)
            issues[f"{theta:.2f}"] = {k: c.get(k, 0) for k in ISSUES}
        out[f]["issues"] = issues
    return out


def une_faute_par_longueur(saisies: list[dict]) -> dict:
    par = defaultdict(list)
    exclues = 0
    for s in saisies:
        if s["fautes"] != 1 or s["oubli"] or s["courte"]:
            continue
        if s["score"] is None:
            exclues += 1
            continue
        par[tranche(s["long_source"])].append(s["score"])
    out = {}
    for _, _, nom in TRANCHES:
        sc = par.get(nom, [])
        out[nom] = {**resume(sc), "part_ge_099": round(sum(x >= 0.99 for x in sc) / len(sc), 4) if sc else None,
                    "part_ge_095": round(sum(x >= 0.95 for x in sc) / len(sc), 4) if sc else None}
    return {"par_tranche": out, "sans_score": exclues}


def main() -> int:
    console_utf8()
    import build_saisies as bs  # noqa: F401  (chemin build/ ajouté par engine.mesure_saisies)
    cat = Catalogue.charger()
    famille_de = familles()
    lignes = charger_jeu(JEU)
    res = ResolveurApproche(charger_catalogue_jeux(cat), SeuilFixe(THETA_BAS, 0.03))
    saisies = passer(res, lignes)
    out = {"jeu": JEU.name, "theta_moteur": THETA_BAS, "paliers": list(PALIERS),
           "saisies_analyse": len(lignes), "fautives_presentes": len(saisies),
           "longueurs": longueurs_catalogue(cat, famille_de),
           "scores": scores_par_famille(saisies),
           "une_faute": une_faute_par_longueur(saisies)}
    SORTIE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for f, v in out["scores"].items():
        lo = out["longueurs"]["par_famille"].get(f, {})
        print(f"{f:20s} long. méd. {lo.get('mediane')} · κ méd. {v['score'].get('mediane')} · "
              f"≥0,99 {v['part_ge']['0.99']} · issues 0,99 {v['issues']['0.99']}")
    for t, v in out["une_faute"]["par_tranche"].items():
        print(f"1 faute, {t:6s} : n {v['n']}, κ moyen {v.get('moyenne')}, ≥0,99 {v.get('part_ge_099')}")
    print(f"→ {SORTIE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
