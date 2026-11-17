"""
Calibration SGR des seuils de l'étape approchée, par famille (R-RES-10).

    python -m engine.calibration                        → spec/seuils_fuzzy.yaml, reports/calibration.json
    python -m engine.calibration --r-etoile 0.005 --delta 0.05 --theta-min 0.80 --theta-max 0.99 --pas 0.01

Méthode : Geifman et El-Yaniv (2017), « Selective Classification for Deep Neural Networks », algorithme SGR
(selection with guaranteed risk). Le fuzzy accepte un nom si son score Jaro-Winkler κ ≥ θ ; on choisit θ par
famille pour garantir, avec une confiance 1 − δ, que le taux d'erreur parmi les noms acceptés par le fuzzy
reste ≤ r*.

Pour une famille et un jeu de certification, on ne garde que les saisies dont la résolution passe par l'étape
approchée (une proposition de noms existe ; la famille est celle des types des meilleurs noms, comme dans le
moteur). Pour chaque θ de la grille :
  n = saisies où le fuzzy accepte un nom (κ ≥ θ et garde-fous franchis) ;
  k = pertes parmi elles. Perte « dangereuse » : resolved vers une entité hors de l'ensemble attendu, ou
      resolved alors qu'on attendait unknown. Un ambiguous ou un unknown n'est jamais une perte. Les
      collisions exactes (résolues avant l'approché) n'entrent jamais dans ces saisies.
Borne haute du vrai risque : B*(k, n, δ') tel que P(Binomiale(n, B*) ≤ k) = δ', avec δ' = δ / |grille|
(Bonferroni). θ retenu = le plus petit θ de la grille tel que B* ≤ r* ; aucun → approché désactivé.

Une seule exécution du moteur par saisie suffit : avec l'écart fixe, les noms retenus, les garde-fous et les
règles ne dépendent pas du seuil ; un seuil θ accepte exactement les saisies acceptées au plus petit seuil de
la grille dont le score κ ≥ θ.

Deux jeux de certification, une fois chacun : challenges/saisies_certif.csv (modèle v0.3) et
challenges/saisies_certif_pessimiste.csv (valeurs v0.2). Seuil final par famille = le plus strict des deux
(désactivé si l'un des deux désactive). Seuls des comptes agrégés sont calculés et écrits : aucune erreur
n'est jamais affichée une par une.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

from engine.approche import SEUILS_FUZZY, SeuilFixe
from engine.catalogue import ROOT, Catalogue, console_utf8, read_csv
from engine.resolveur import ResolveurApproche

CHAL = ROOT / "challenges"
RAPPORT = ROOT / "reports" / "calibration.json"
SCENARIOS = {"central": CHAL / "saisies_certif.csv", "pessimiste": CHAL / "saisies_certif_pessimiste.csv"}

# Paramètres par défaut (R-RES-10), modifiables en ligne de commande.
R_ETOILE = 0.005          # risque visé parmi les noms acceptés par le fuzzy
DELTA = 0.05              # 1 − confiance
THETA_MIN, THETA_MAX, PAS = 0.80, 0.99, 0.01
ECART = 0.03              # écart de R-RES-03, inchangé : seul le seuil est calibré


def grille(theta_min: float = THETA_MIN, theta_max: float = THETA_MAX, pas: float = PAS) -> list[float]:
    n = int(round((theta_max - theta_min) / pas)) + 1
    g = [round(theta_min + i * pas, 6) for i in range(n)]
    if not g or g[-1] > theta_max + 1e-9 or any(not 0 < t <= 1 for t in g):
        raise ValueError(f"grille de θ invalide : de {theta_min} à {theta_max} par {pas}.")
    return g


# ── borne binomiale ───────────────────────────────────────────────────────────────────────────────

def log_cdf_binomiale(k: int, n: int, b: float) -> float:
    """log P(Binomiale(n, b) ≤ k), calculé en log (somme log-exp) pour la stabilité numérique."""
    if k >= n:
        return 0.0
    if b <= 0:
        return 0.0
    if b >= 1:
        return -math.inf
    lb, l1b = math.log(b), math.log1p(-b)
    termes = [math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lb + (n - i) * l1b
              for i in range(k + 1)]
    m = max(termes)
    return m + math.log(sum(math.exp(t - m) for t in termes))


def borne_haute(k: int, n: int, delta_p: float, iterations: int = 200) -> float:
    """B*(k, n, δ') : la valeur b telle que P(Binomiale(n, b) ≤ k) = δ' (borne de Clopper-Pearson à une
    queue, utilisée par SGR). Dichotomie sur b. n = 0 ou k = n : aucune information, borne 1."""
    if not 0 < delta_p < 1:
        raise ValueError(f"δ' = {delta_p} hors de ]0, 1[.")
    if n <= 0 or k >= n:
        return 1.0
    if k < 0:
        raise ValueError("k négatif.")
    cible = math.log(delta_p)
    bas, haut = k / n, 1.0                        # cdf(bas) ≥ 1/2 > δ' (en pratique) ; cdf(1) = 0 < δ'
    if log_cdf_binomiale(k, n, bas) < cible:      # cas extrême : la borne est sous k/n
        bas = 0.0
    for _ in range(iterations):
        milieu = (bas + haut) / 2
        if log_cdf_binomiale(k, n, milieu) > cible:
            bas = milieu
        else:
            haut = milieu
    return haut


# ── choix du seuil (SGR) ──────────────────────────────────────────────────────────────────────────

def courbe(saisies: list[tuple[float, bool, bool]], thetas: list[float], delta_p: float) -> list[dict]:
    """saisies : (κ, acceptée au plus petit seuil, perte) pour les saisies d'une famille passées par
    l'approché. Pour chaque θ : n, k, borne, couverture (part des saisies fuzzy acceptées)."""
    total = len(saisies)
    out = []
    for t in thetas:
        acc = [(s, p) for s, a, p in saisies if a and s >= t]
        n, k = len(acc), sum(p for _, p in acc)
        out.append({"theta": t, "n": n, "k": k, "borne": borne_haute(k, n, delta_p),
                    "risque_observe": (k / n) if n else None, "couverture": (n / total) if total else 0.0})
    return out


def choisir(points: list[dict], r_etoile: float) -> dict:
    """Plus petit θ de la grille dont la borne est ≤ r* ; sinon désactivé, avec le meilleur point (borne la
    plus basse, puis le plus petit θ) pour information."""
    for pt in points:
        if pt["borne"] <= r_etoile:
            return {"seuil": pt["theta"], "desactive": False, **pt}
    meilleur = min(points, key=lambda p: (p["borne"], p["theta"])) if points else \
        {"theta": None, "n": 0, "k": 0, "borne": 1.0, "risque_observe": None, "couverture": 0.0}
    return {"seuil": None, "desactive": True, "meilleur_point": meilleur}


def plus_strict(choix: dict[str, dict]) -> float | None:
    """Seuil final : le plus haut des seuils des scénarios ; désactivé si l'un des scénarios désactive."""
    seuils = [c["seuil"] for c in choix.values()]
    if not seuils or any(s is None for s in seuils):
        return None
    return max(seuils)


# ── données : une résolution par saisie ───────────────────────────────────────────────────────────

def perte(att_statut: str, att_ids: set[str], statut: str, ids: set[str]) -> bool:
    """Perte dangereuse : resolved hors de l'ensemble attendu, ou resolved alors qu'on attendait unknown."""
    return statut == "resolved" and (att_statut == "unknown" or not ids <= att_ids)


def lire_certif(chemin: Path) -> list[dict]:
    """Lecture d'un jeu de certification POUR LA CALIBRATION SEULEMENT (comptes agrégés, aucune erreur
    affichée une par une). engine/mesure_saisies.py refuse toujours ces fichiers."""
    if not chemin.exists():
        raise FileNotFoundError(f"{chemin} introuvable : lancer python build/build_saisies.py "
                                f"(et --scenario pessimiste).")
    return read_csv(chemin)


def saisies_par_famille(res: ResolveurApproche, famille_de: dict, lignes: list[dict]) -> tuple[dict, dict]:
    """Résout chaque saisie une fois (seuil = plus petit θ de la grille) et range par famille du nom trouvé.
    Renvoie {famille: [(κ, acceptée, perte)]} et des comptes (hors approché, familles mélangées)."""
    par = defaultdict(list)
    comptes = defaultdict(int)
    cache = {}
    for l in lignes:
        cle = (l["terme"], l["indice_type"])
        if cle not in cache:
            r = res.resoudre(l["terme"], l["indice_type"] or None)
            app = next((t for t in r.trace if t.get("regle") == "R-RES-03"), None)
            cache[cle] = (r, app)
        r, app = cache[cle]
        if app is None:
            comptes["hors_approche"] += 1
            continue
        fams = {famille_de.get(t) for t in app.get("types", [])}
        if len(fams) != 1 or None in fams:
            comptes["familles_melangees"] += 1     # jamais d'approché pour ces noms (R-RES-10)
            continue
        acceptee = r.etape == "approche"
        att = {i for i in l["attendu_ids"].split("|") if i}
        par[next(iter(fams))].append((float(app["score"]), acceptee,
                                      acceptee and perte(l["attendu_statut"], att, r.statut, set(r.ids))))
        comptes["approche"] += 1
    return dict(par), dict(comptes)


def sha256(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def calibrer(cat: Catalogue, familles: dict, scenarios: dict[str, Path], r_etoile: float, delta: float,
             thetas: list[float]) -> dict:
    famille_de = {t: f for f, ts in familles.items() for t in ts}
    res = ResolveurApproche(cat, SeuilFixe(min(thetas), ECART))
    delta_p = delta / len(thetas)
    out = {"scenarios": {}, "familles": {}}
    for sc, chemin in scenarios.items():
        par, comptes = saisies_par_famille(res, famille_de, lire_certif(chemin))
        out["scenarios"][sc] = {"fichier": str(chemin.relative_to(ROOT)).replace("\\", "/"),
                                "sha256": sha256(chemin), "comptes": comptes, "familles": {}}
        for f in sorted(familles):
            pts = courbe(par.get(f, []), thetas, delta_p)
            out["scenarios"][sc]["familles"][f] = {"saisies_approche": len(par.get(f, [])),
                                                   "choix": choisir(pts, r_etoile), "courbe": pts}
    for f in sorted(familles):
        choix = {sc: out["scenarios"][sc]["familles"][f]["choix"] for sc in scenarios}
        out["familles"][f] = plus_strict(choix)
    out["delta_prime"] = delta_p
    return out


# ── sorties ───────────────────────────────────────────────────────────────────────────────────────

def _arr(x, d=6):
    return None if x is None else round(float(x), d)


def yaml_seuils(cal: dict, r_etoile: float, delta: float, thetas: list[float], jour: str) -> str:
    """Texte de spec/seuils_fuzzy.yaml (ordre fixe : deux exécutions donnent le même fichier, hors date)."""
    familles = {}
    for f, final in cal["familles"].items():
        bloc = {}
        for sc, d in cal["scenarios"].items():
            c = d["familles"][f]["choix"]
            if c["desactive"]:
                mp = c["meilleur_point"]
                bloc[sc] = {"seuil": None, "desactive": True, "saisies_approche": d["familles"][f]["saisies_approche"],
                            "meilleur_point": {"theta": mp["theta"], "n": mp["n"], "k": mp["k"],
                                               "borne": _arr(mp["borne"]), "couverture": _arr(mp["couverture"], 4)}}
            else:
                bloc[sc] = {"seuil": c["seuil"], "n": c["n"], "k": c["k"], "borne": _arr(c["borne"]),
                            "couverture": _arr(c["couverture"], 4),
                            "saisies_approche": d["familles"][f]["saisies_approche"]}
        bloc["seuil_final"] = final
        familles[f] = bloc
    doc = {"version": 1, "regle": "R-RES-10", "date": jour,
           "parametres": {"r_etoile": r_etoile, "delta": delta, "delta_prime": _arr(cal["delta_prime"], 8),
                          "correction": f"Bonferroni sur {len(thetas)} seuils", "ecart": ECART,
                          "grille": {"min": thetas[0], "max": thetas[-1], "pas": round(thetas[1] - thetas[0], 6)
                                     if len(thetas) > 1 else None, "nombre": len(thetas)}},
           "jeux": {sc: {"fichier": d["fichier"], "sha256": d["sha256"]} for sc, d in cal["scenarios"].items()},
           "familles": familles}
    entete = (
        "# Seuils de l'étape approchée par famille : calibration SGR (R-RES-10).\n"
        "# Écrit par python -m engine.calibration : ne pas modifier à la main.\n"
        "# Méthode : Geifman et El-Yaniv (2017), SGR. Pour chaque famille et chaque scénario de certification, θ est le\n"
        "# plus petit seuil de la grille dont la borne haute du risque (binomiale exacte, δ' = δ / taille de la grille)\n"
        "# est ≤ r*. Seuil final = le plus strict des deux scénarios ; null = approché désactivé pour la famille.\n"
        "# n : noms acceptés par le fuzzy ; k : pertes dangereuses parmi eux ; couverture : n / saisies passées par\n"
        "# l'approché. Garantie valable si le réel est entre les deux scénarios (modèle v0.3 et pessimiste).\n"
        "# Lu par le moteur : engine/approche.py · SeuilsCalibres.\n")
    return entete + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Calibration SGR des seuils fuzzy par famille (R-RES-10).")
    ap.add_argument("--r-etoile", type=float, default=R_ETOILE)
    ap.add_argument("--delta", type=float, default=DELTA)
    ap.add_argument("--theta-min", type=float, default=THETA_MIN)
    ap.add_argument("--theta-max", type=float, default=THETA_MAX)
    ap.add_argument("--pas", type=float, default=PAS)
    ap.add_argument("--sortie", type=Path, default=SEUILS_FUZZY)
    args = ap.parse_args(argv)
    console_utf8()
    if not 0 < args.r_etoile < 1 or not 0 < args.delta < 1:
        raise SystemExit("r* et δ doivent être dans ]0, 1[.")
    thetas = grille(args.theta_min, args.theta_max, args.pas)

    sys.path.insert(0, str(ROOT / "build"))
    import build_saisies as bs
    from engine.mesure_saisies import charger_catalogue_jeux
    familles = yaml.safe_load((ROOT / "spec" / "familles_fuzzy.yaml").read_text(encoding="utf-8"))["familles"]
    cat = charger_catalogue_jeux(Catalogue.charger(), bs.charger_retires())
    cal = calibrer(cat, familles, SCENARIOS, args.r_etoile, args.delta, thetas)
    args.sortie.write_text(yaml_seuils(cal, args.r_etoile, args.delta, thetas, date.today().isoformat()),
                           encoding="utf-8")
    RAPPORT.write_text(json.dumps({"parametres": {"r_etoile": args.r_etoile, "delta": args.delta,
                                                  "delta_prime": cal["delta_prime"], "grille": thetas, "ecart": ECART},
                                   **cal}, ensure_ascii=False, indent=1), encoding="utf-8")
    for f, final in cal["familles"].items():
        det = " ; ".join(
            f"{sc} " + (f"θ {c['seuil']:.2f} (n {c['n']}, k {c['k']}, borne {100 * c['borne']:.2f} %)" if not c["desactive"]
                        else f"désactivé (meilleur θ {c['meilleur_point']['theta']}, n {c['meilleur_point']['n']}, "
                             f"k {c['meilleur_point']['k']}, borne {100 * c['meilleur_point']['borne']:.2f} %)")
            for sc, c in ((sc, d["familles"][f]["choix"]) for sc, d in cal["scenarios"].items()))
        print(f"{f} : {'désactivé' if final is None else f'θ final {final:.2f}'} · {det}")
    print(f"→ {args.sortie.relative_to(ROOT) if args.sortie.is_relative_to(ROOT) else args.sortie}, "
          f"{RAPPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
