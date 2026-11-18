"""
Calibration des seuils de l'étape approchée, par famille (R-RES-10) : garantie de risque sélectif SGR,
choix du seuil par test en séquence fixe.

    python -m engine.calibration                        → spec/seuils_fuzzy.yaml, reports/calibration.json
    python -m engine.calibration --r-etoile 0.005 --delta 0.05 --theta-min 0.80 --theta-max 0.99 --pas 0.01

Objectif (Geifman et El-Yaniv, 2017, « Selective Classification for Deep Neural Networks », SGR) : le fuzzy
accepte un nom si son score Jaro-Winkler κ ≥ θ ; on choisit θ par famille pour garantir, avec une confiance
1 − δ, que le taux d'erreur parmi les noms que le fuzzy résout reste ≤ r*.

Pour une famille et un jeu de certification, on ne garde que les saisies dont la résolution passe par l'étape
approchée (une proposition de noms existe ; la famille est celle des types des meilleurs noms, comme dans le
moteur). Pour chaque θ de la grille :
  n = saisies où le fuzzy répond RESOLVED (κ ≥ θ, garde-fous franchis, une seule entité) ; un ambiguous n'est
      ni un choix ni une perte : il sort de n ;
  k = pertes parmi elles. Perte « dangereuse » : resolved vers une entité hors de l'ensemble attendu, ou
      resolved alors qu'on attendait unknown. Les collisions exactes (résolues avant l'approché) n'entrent
      jamais dans ces saisies.
Borne haute du vrai risque : B*(k, n, δ) tel que P(Binomiale(n, B*) ≤ k) = δ (binomiale exacte, en log).

Choix de θ : test en séquence fixe (fixed sequence testing ; Angelopoulos, Bates, Candès, Jordan et Lei, 2021,
« Learn then Test », arXiv 2110.01052). Ordre fixé à l'avance, du plus strict au plus permissif : 0,99, 0,98, …,
0,80. Chaque θ est testé au niveau δ entier : il passe si B*(k, n, δ) ≤ r*. On s'arrête au premier θ qui échoue ;
θ retenu = le dernier qui a passé ; si 0,99 échoue, approché désactivé pour la famille. L'ordre étant fixé
avant de voir les données, la probabilité de retenir un θ dont le vrai risque dépasse r* reste ≤ δ, sans
correction pour le nombre de seuils.

Une seule exécution du moteur par saisie suffit : avec l'écart fixe, les noms retenus, les garde-fous et les
règles ne dépendent pas du seuil ; un seuil θ résout exactement les saisies résolues au plus petit seuil de
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
R_ETOILE = 0.005          # risque visé parmi les noms résolus par le fuzzy
DELTA = 0.05              # 1 − confiance ; chaque θ de la séquence est testé au niveau δ entier
THETA_MIN, THETA_MAX, PAS = 0.80, 0.99, 0.01
ECART = 0.03              # écart de R-RES-03, inchangé : seul le seuil est calibré
METHODE = "séquence fixe (Learn then Test, arXiv 2110.01052), de θ max à θ min, chaque θ au niveau δ"


def grille(theta_min: float = THETA_MIN, theta_max: float = THETA_MAX, pas: float = PAS) -> list[float]:
    """Grille croissante des θ (la séquence de test la parcourt à l'envers)."""
    n = int(round((theta_max - theta_min) / pas)) + 1
    g = [round(theta_min + i * pas, 6) for i in range(n)]
    if not g or g[-1] > theta_max + 1e-9 or any(not 0 < t <= 1 for t in g):
        raise ValueError(f"grille de θ invalide : de {theta_min} à {theta_max} par {pas}.")
    return g


# ── borne binomiale ───────────────────────────────────────────────────────────────────────────────

def log_cdf_binomiale(k: int, n: int, b: float) -> float:
    """log P(Binomiale(n, b) ≤ k), calculé en log (somme log-exp) pour la stabilité numérique."""
    if k >= n or b <= 0:
        return 0.0
    if b >= 1:
        return -math.inf
    lb, l1b = math.log(b), math.log1p(-b)
    termes = [math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lb + (n - i) * l1b
              for i in range(k + 1)]
    m = max(termes)
    return m + math.log(sum(math.exp(t - m) for t in termes))


def borne_haute(k: int, n: int, delta: float, iterations: int = 200) -> float:
    """B*(k, n, δ) : la valeur b telle que P(Binomiale(n, b) ≤ k) = δ (Clopper-Pearson à une queue).
    Dichotomie sur b. n = 0 ou k = n : aucune information, borne 1."""
    if not 0 < delta < 1:
        raise ValueError(f"δ = {delta} hors de ]0, 1[.")
    if k < 0:
        raise ValueError("k négatif.")
    if n <= 0 or k >= n:
        return 1.0
    cible = math.log(delta)
    bas, haut = k / n, 1.0
    if log_cdf_binomiale(k, n, bas) < cible:
        bas = 0.0
    for _ in range(iterations):
        milieu = (bas + haut) / 2
        if log_cdf_binomiale(k, n, milieu) > cible:
            bas = milieu
        else:
            haut = milieu
    return haut


def n_necessaire(taux: float, r_etoile: float, delta: float) -> int | None:
    """Plus petit nombre de noms résolus n tel que B*(round(taux · n), n, δ) ≤ r*, si le taux d'erreur observé
    se maintient. None si taux ≥ r* (aucun volume ne suffit)."""
    if taux >= r_etoile:
        return None
    ok = lambda n: borne_haute(round(taux * n), n, delta) <= r_etoile
    haut = max(1, int(math.log(1 / delta) / r_etoile))
    while not ok(haut):
        haut *= 2
        if haut > 10 ** 9:
            return None
    bas = 0
    while haut - bas > 1:
        m = (bas + haut) // 2
        if ok(m):
            haut = m
        else:
            bas = m
    return haut


# ── choix du seuil : séquence fixe ────────────────────────────────────────────────────────────────

def courbe(saisies: list[tuple[float, bool, bool]], thetas: list[float], delta: float) -> list[dict]:
    """saisies : (κ, résolue par le fuzzy au plus petit seuil, perte) pour les saisies d'une famille passées
    par l'approché. Pour chaque θ (ordre croissant) : n, k, borne, risque observé, couverture (part des saisies
    passées par l'approché que le fuzzy résout)."""
    total = len(saisies)
    out = []
    for t in thetas:
        acc = [p for s, r, p in saisies if r and s >= t]
        n, k = len(acc), sum(acc)
        out.append({"theta": t, "n": n, "k": k, "borne": borne_haute(k, n, delta),
                    "risque_observe": (k / n) if n else None, "couverture": (n / total) if total else 0.0})
    return out


def choisir(points: list[dict], r_etoile: float) -> dict:
    """Séquence fixe, du θ le plus haut au plus bas : on s'arrête au premier θ dont la borne dépasse r* ;
    θ retenu = le dernier qui a passé. Si le premier échoue : désactivé. `points` dans n'importe quel ordre."""
    sequence = sorted(points, key=lambda p: -p["theta"])
    passes = []
    echec = None
    for pt in sequence:
        if pt["borne"] <= r_etoile:
            passes.append(pt)
        else:
            echec = pt
            break
    if not passes:
        meilleur = min(points, key=lambda p: (p["borne"], -p["theta"])) if points else None
        return {"seuil": None, "desactive": True, "theta_testes": 1 if echec else 0, "premier_echec": echec,
                "meilleur_point": meilleur}
    retenu = passes[-1]
    return {"seuil": retenu["theta"], "desactive": False, "theta_testes": len(passes) + (1 if echec else 0),
            "premier_echec": echec, **retenu}


def plus_strict(choix: dict[str, dict]) -> float | None:
    """Seuil final : le plus haut des seuils des scénarios ; désactivé si l'un des scénarios désactive."""
    seuils = [c["seuil"] for c in choix.values()]
    if not seuils or any(s is None for s in seuils):
        return None
    return max(seuils)


def volume_necessaire(points: list[dict], saisies_approche: int, r_etoile: float, delta: float) -> dict:
    """Volume estimé pour passer, si les taux d'erreur observés se maintiennent : on multiplie toutes les
    saisies de la famille par un même facteur f. Pour atteindre θ en séquence fixe, tous les θ' ≥ θ doivent
    passer : f(θ) = max sur θ' ≥ θ de n_nécessaire(taux observé à θ') / n(θ'). Cible : le θ le plus
    permissif atteignable (taux observé < r* et au moins un nom résolu à tous les θ' ≥ θ). On donne aussi le
    volume pour passer le premier palier (θ max), qui seul débloque la séquence."""
    sequence = sorted(points, key=lambda p: -p["theta"])
    facteur, cible, premier_palier = 1.0, None, None
    for pt in sequence:
        if not pt["n"]:
            break
        besoin = n_necessaire(pt["k"] / pt["n"], r_etoile, delta)
        if besoin is None:
            break
        facteur = max(facteur, besoin / pt["n"])
        cible = {"theta": pt["theta"], "taux_observe": pt["k"] / pt["n"], "facteur": facteur,
                 "noms_resolus_necessaires": math.ceil(facteur * pt["n"]),
                 "saisies_approche_necessaires": math.ceil(facteur * saisies_approche)}
        if pt is sequence[0]:
            premier_palier = {"theta": pt["theta"], "taux_observe": pt["k"] / pt["n"], "facteur": max(1.0, facteur),
                              "noms_resolus_necessaires": besoin,
                              "saisies_approche_necessaires": math.ceil(max(1.0, facteur) * saisies_approche)}
    if cible is None:
        premier = sequence[0] if sequence else None
        raison = ("aucun nom résolu par le fuzzy à θ max" if premier is not None and not premier["n"]
                  else "taux d'erreur observé ≥ r* dès θ max")
        return {"theta": None, "raison": raison}
    return {**cible, "premier_palier": premier_palier}


# ── données : une résolution par saisie ───────────────────────────────────────────────────────────

def perte(att_statut: str, att_ids: set[str], statut: str, ids: set[str]) -> bool:
    """Perte dangereuse : resolved hors de l'ensemble attendu, ou resolved alors qu'on attendait unknown."""
    return statut == "resolved" and (att_statut == "unknown" or not ids <= att_ids)


def lire_certif(chemin: Path) -> list[dict]:
    """Lecture d'un jeu de certification POUR LA CALIBRATION SEULEMENT (comptes agrégés, aucune erreur
    affichée une par une). engine/mesure_saisies.py refuse toujours ces fichiers."""
    if not chemin.exists():
        raise FileNotFoundError(f"{chemin} introuvable : lancer python build/build_saisies.py --jeux certif "
                                f"(et --scenario pessimiste --jeux certif).")
    return read_csv(chemin)


def saisies_par_famille(res: ResolveurApproche, famille_de: dict, lignes: list[dict]) -> tuple[dict, dict]:
    """Résout chaque saisie une fois (seuil = plus petit θ de la grille) et range par famille du nom trouvé.
    Renvoie {famille: [(κ, résolue par le fuzzy, perte)]} et des comptes."""
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
        resolue = r.etape == "approche" and r.statut == "resolved"
        if r.etape == "approche" and r.statut == "ambiguous":
            comptes["ambigues_hors_n"] += 1
        att = {i for i in l["attendu_ids"].split("|") if i}
        par[next(iter(fams))].append((float(app["score"]), resolue,
                                      resolue and perte(l["attendu_statut"], att, r.statut, set(r.ids))))
        comptes["approche"] += 1
    return dict(par), dict(comptes)


def sha256(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def calibrer(cat: Catalogue, familles: dict, scenarios: dict[str, Path], r_etoile: float, delta: float,
             thetas: list[float]) -> dict:
    famille_de = {t: f for f, ts in familles.items() for t in ts}
    res = ResolveurApproche(cat, SeuilFixe(min(thetas), ECART))
    out = {"scenarios": {}, "familles": {}}
    for sc, chemin in scenarios.items():
        lignes = lire_certif(chemin)
        par, comptes = saisies_par_famille(res, famille_de, lignes)
        fautives = defaultdict(int)
        for l in lignes:
            if l["nature"] == "present":
                fautives[l["famille"]] += 1
        out["scenarios"][sc] = {"fichier": str(chemin.relative_to(ROOT)).replace("\\", "/"),
                                "sha256": sha256(chemin), "comptes": comptes, "saisies": len(lignes),
                                "presents_par_famille": dict(sorted(fautives.items())), "familles": {}}
        for f in sorted(familles):
            pts = courbe(par.get(f, []), thetas, delta)
            n_app = len(par.get(f, []))
            out["scenarios"][sc]["familles"][f] = {"saisies_approche": n_app, "choix": choisir(pts, r_etoile),
                                                   "volume_necessaire": volume_necessaire(pts, n_app, r_etoile, delta),
                                                   "courbe": pts}
    for f in sorted(familles):
        choix = {sc: out["scenarios"][sc]["familles"][f]["choix"] for sc in scenarios}
        out["familles"][f] = plus_strict(choix)
    return out


# ── sorties ───────────────────────────────────────────────────────────────────────────────────────

def _arr(x, d=6):
    return None if x is None else round(float(x), d)


def _point(p: dict | None) -> dict | None:
    if not p:
        return None
    return {"theta": p["theta"], "n": p["n"], "k": p["k"], "borne": _arr(p["borne"]), "couverture": _arr(p["couverture"], 4)}


def yaml_seuils(cal: dict, r_etoile: float, delta: float, thetas: list[float], jour: str) -> str:
    """Texte de spec/seuils_fuzzy.yaml (ordre fixe : deux exécutions donnent le même fichier, hors date)."""
    familles = {}
    for f, final in cal["familles"].items():
        bloc = {}
        for sc, d in cal["scenarios"].items():
            fd = d["familles"][f]
            c = fd["choix"]
            vol = fd["volume_necessaire"]
            vol_y = ({"theta_vise": vol["theta"], "taux_observe": _arr(vol["taux_observe"]),
                      "noms_resolus_necessaires": vol["noms_resolus_necessaires"],
                      "saisies_approche_necessaires": vol["saisies_approche_necessaires"],
                      "facteur": _arr(vol["facteur"], 2),
                      "premier_palier": {"theta": vol["premier_palier"]["theta"],
                                         "noms_resolus_necessaires": vol["premier_palier"]["noms_resolus_necessaires"],
                                         "saisies_approche_necessaires": vol["premier_palier"]["saisies_approche_necessaires"],
                                         "facteur": _arr(vol["premier_palier"]["facteur"], 2)}}
                     if vol["theta"] is not None else {"raison": vol["raison"]})
            if c["desactive"]:
                bloc[sc] = {"seuil": None, "desactive": True, "saisies_approche": fd["saisies_approche"],
                            "premier_echec": _point(c["premier_echec"]), "meilleur_point": _point(c["meilleur_point"]),
                            "volume_necessaire": vol_y}
            else:
                bloc[sc] = {"seuil": c["seuil"], "n": c["n"], "k": c["k"], "borne": _arr(c["borne"]),
                            "couverture": _arr(c["couverture"], 4), "saisies_approche": fd["saisies_approche"],
                            "theta_testes": c["theta_testes"], "premier_echec": _point(c["premier_echec"]),
                            "volume_necessaire": vol_y}
        bloc["seuil_final"] = final
        familles[f] = bloc
    doc = {"version": 2, "regle": "R-RES-10", "date": jour,
           "parametres": {"r_etoile": r_etoile, "delta": delta, "methode": METHODE,
                          "n": "noms résolus (resolved) par le fuzzy ; un ambiguous sort de n", "ecart": ECART,
                          "grille": {"min": thetas[0], "max": thetas[-1], "pas": round(thetas[1] - thetas[0], 6)
                                     if len(thetas) > 1 else None, "nombre": len(thetas), "ordre_de_test": "décroissant"}},
           "jeux": {sc: {"fichier": d["fichier"], "sha256": d["sha256"], "saisies": d["saisies"]}
                    for sc, d in cal["scenarios"].items()},
           "familles": familles}
    entete = (
        "# Seuils de l'étape approchée par famille (R-RES-10).\n"
        "# Écrit par python -m engine.calibration : ne pas modifier à la main.\n"
        "# Garantie SGR (Geifman et El-Yaniv, 2017) ; choix du seuil par test en séquence fixe (Angelopoulos et al., 2021,\n"
        "# « Learn then Test », arXiv 2110.01052) : θ testés de 0,99 à 0,80, chacun au niveau δ, avec la borne binomiale\n"
        "# exacte ; arrêt au premier échec ; θ retenu = le dernier qui a passé ; null = approché désactivé.\n"
        "# n : noms résolus (resolved) par le fuzzy ; k : pertes dangereuses parmi eux ; couverture : n / saisies passées\n"
        "# par l'approché. Seuil final = le plus strict des deux scénarios. Garantie valable si le réel est entre les\n"
        "# deux scénarios (modèle v0.3 et pessimiste). volume_necessaire : estimation si les taux observés se maintiennent.\n"
        "# Lu par le moteur : engine/approche.py · SeuilsCalibres.\n")
    return entete + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120)


def resume(f: str, final, cal: dict) -> str:
    morceaux = []
    for sc, d in cal["scenarios"].items():
        c = d["familles"][f]["choix"]
        if c["desactive"]:
            e = c["premier_echec"] or {}
            morceaux.append(f"{sc} désactivé (échec à θ {e.get('theta')} : n {e.get('n')}, k {e.get('k')}, "
                            f"borne {100 * e.get('borne', 1):.2f} %)")
        else:
            morceaux.append(f"{sc} θ {c['seuil']:.2f} (n {c['n']}, k {c['k']}, borne {100 * c['borne']:.2f} %, "
                            f"couverture {100 * c['couverture']:.1f} %)")
    return f"{f} : {'désactivé' if final is None else f'θ final {final:.2f}'} · " + " ; ".join(morceaux)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Calibration des seuils fuzzy par famille (R-RES-10, séquence fixe).")
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
    RAPPORT.write_text(json.dumps({"parametres": {"r_etoile": args.r_etoile, "delta": args.delta, "methode": METHODE,
                                                  "grille": thetas, "ecart": ECART}, **cal},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
    for f, final in cal["familles"].items():
        print(resume(f, final, cal))
    print(f"→ {args.sortie.relative_to(ROOT) if args.sortie.is_relative_to(ROOT) else args.sortie}, "
          f"{RAPPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
