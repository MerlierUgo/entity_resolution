"""
Évaluation du moteur sur le banc d'essai (challenges/cases.csv), partition dev par défaut.

    python -m engine.evaluation                  partition dev → reports/moteur_dev.md et .json
    python -m engine.evaluation --tiers 1        idem avec les seuls alias officiels (tier 1)
    python -m engine.evaluation --fuzzy fixe     étape 2, SeuilFixe(0.88, 0.03) (--seuil, --ecart)
    python -m engine.evaluation --fuzzy calibre  étape 2, seuils de spec/seuils_fuzzy.yaml
    python -m engine.evaluation --sous-partition eval   seulement les 30 % de dev réservés à l'évaluation
    python -m engine.evaluation --partition test jalon, seulement à la demande de l'utilisateur

Notation identique à build/baseline.py, pour comparer avec les références B0, B1, B2 :
  correct             réponse attendue exactement                         → idéal, sûr
  partiel             bon statut ambiguous, mais pas exactement les mêmes candidats → sûr
  acceptable          réponse prudente prévue par la colonne accepted     → sûr
  trop_confiant       resolved vers un des candidats d'un cas ambigu
  erreur_silencieuse  resolved vers une entité qui n'est pas la bonne. Objectif : 0.
  incorrect           tout le reste
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from engine.approche import SeuilFixe, SeuilsCalibres
from engine.catalogue import ROOT, TIERS, Catalogue, console_utf8, read_csv
from engine.resolveur import ResolveurApproche, ResolveurExact

CHAL = ROOT / "challenges"
REP = ROOT / "reports"
SURS = ("correct", "partiel", "acceptable")


def noter(cas: dict, statut: str, ids) -> str:
    """Note une réponse contre un cas du banc d'essai (même sémantique que build/baseline.py · score)."""
    exp = set(filter(None, cas["expected_ids"].split("|")))
    acc = set(filter(None, cas["accepted"].split("|")))
    ids = set(ids)
    if statut == "resolved" and not ids <= exp:
        return "erreur_silencieuse"
    if statut == cas["expected_status"]:
        return "correct" if statut == "unknown" or ids == exp else "partiel"
    if statut in acc:
        return "acceptable"
    if statut == "resolved" and cas["expected_status"] == "ambiguous":
        return "trop_confiant"
    return "incorrect"


PART_CALIB = 70  # % de dev pour la calibration ; le reste sert à l'évaluation


def sous_partition(case_id: str) -> str:
    """Découpe déterministe de dev : « calib » (70 %) ou « eval » (30 %), par hash SHA-256 du case_id."""
    h = int.from_bytes(hashlib.sha256(case_id.encode("utf-8")).digest()[:8], "big")
    return "calib" if h % 100 < PART_CALIB else "eval"


def charger_cas(partition: str = "dev", sous: str | None = None) -> list[dict]:
    """Cas d'une partition ; `sous` (calib ou eval) restreint dev à l'une de ses deux parts."""
    if sous and partition != "dev":
        raise ValueError("--sous-partition ne s'applique qu'à la partition dev.")
    if sous not in (None, "calib", "eval"):
        raise ValueError(f"sous-partition « {sous} » inconnue : calib ou eval.")
    split = {r["case_id"]: r["split"] for r in read_csv(CHAL / "split.csv")}
    cas = read_csv(CHAL / "cases.csv")
    manquants = [c["case_id"] for c in cas if c["case_id"] not in split]
    if manquants:
        raise ValueError(f"challenges/split.csv : {len(manquants)} cas sans partition (ex. {manquants[0]}) ; "
                         "reconstruire le banc d'essai (build/build_challenges.py).")
    return [c for c in cas if split[c["case_id"]] == partition
            and (sous is None or sous_partition(c["case_id"]) == sous)]


def evaluer(resolveur: ResolveurExact, cas: list[dict]) -> dict:
    """Passe chaque cas dans le résolveur. Renvoie les comptes par catégorie et les cas non idéaux."""
    par_cat = defaultdict(Counter)
    echecs = []
    for c in cas:
        r = resolveur.resoudre(c["input_text"], c["hint_type"] or None)
        note = noter(c, r.statut, r.ids)
        par_cat[c["category"]][note] += 1
        par_cat["TOTAL"][note] += 1
        if note != "correct":
            echecs.append({"case_id": c["case_id"], "categorie": c["category"], "texte": c["input_text"],
                           "hint": c["hint_type"], "note": note, "attendu": c["expected_status"],
                           "attendus": c["expected_ids"], "statut": r.statut, "ids": list(r.ids),
                           "etape": r.etape, "trace": list(r.trace)})
    return {"comptes": {k: dict(sorted(v.items())) for k, v in sorted(par_cat.items())}, "echecs": echecs}


def taux(comptes: dict) -> tuple[int, float, float, float]:
    n = sum(comptes.values())
    if not n:
        return 0, 0.0, 0.0, 0.0
    return (n, 100 * comptes.get("correct", 0) / n, 100 * sum(comptes.get(s, 0) for s in SURS) / n,
            100 * comptes.get("erreur_silencieuse", 0) / n)


def rapport_md(res: dict, partition: str, tiers, titre: str = "étape 1 (résolveur exact)", commande: str = "") -> str:
    lignes = [f"# Moteur · {titre} · partition {partition}", "",
              f"Généré par `python -m engine.evaluation {commande}`. "
              f"Alias chargés : tiers {', '.join(sorted(tiers))}. En % des cas de chaque catégorie.",
              "", "| Catégorie | Cas | Idéal | Sûr | Silencieux | Détail des non idéaux |",
              "|---|---:|---:|---:|---:|---|"]
    for cat, cpt in res["comptes"].items():
        n, ideal, sur, sil = taux(cpt)
        detail = ", ".join(f"{k} {v}" for k, v in cpt.items() if k != "correct") or "·"
        nom = f"**{cat}**" if cat == "TOTAL" else cat
        lignes.append(f"| {nom} | {n} | {ideal:.1f} | {sur:.1f} | {sil:.1f} | {detail} |")
    sil = [e for e in res["echecs"] if e["note"] == "erreur_silencieuse"]
    lignes += ["", f"## Erreurs silencieuses : {len(sil)}", ""]
    lignes += [f"- {e['case_id']} « {e['texte']} » → {e['ids']} (attendu {e['attendus'] or e['attendu']})"
               for e in sil[:50]]
    pas_surs = Counter((e["categorie"], e["note"], e["etape"]) for e in res["echecs"] if e["note"] not in SURS)
    if pas_surs:
        lignes += ["", "## Réponses ni idéales ni sûres (catégorie, note, étape décisive)", ""]
        lignes += [f"- {c} · {n} · {et or '·'} : {k}" for (c, n, et), k in sorted(pas_surs.items())]
    return "\n".join(lignes) + "\n"


def construire(cat: Catalogue, fuzzy: str = "aucun", seuil: float = 0.88, ecart: float = 0.03):
    """Résolveur d'une configuration : aucun (étape 1), fixe (SeuilFixe) ou calibre (SeuilsCalibres)."""
    if fuzzy == "aucun":
        return ResolveurExact(cat)
    if fuzzy == "fixe":
        return ResolveurApproche(cat, SeuilFixe(seuil, ecart))
    if fuzzy == "calibre":
        return ResolveurApproche(cat, SeuilsCalibres.charger(cat))
    raise ValueError(f"--fuzzy « {fuzzy} » inconnu : aucun, fixe ou calibre.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Évalue le moteur sur le banc d'essai.")
    ap.add_argument("--partition", choices=("dev", "test"), default="dev")
    ap.add_argument("--sous-partition", choices=("calib", "eval"), default=None)
    ap.add_argument("--tiers", nargs="+", default=sorted(TIERS), help="tiers d'alias chargés (1 2 3)")
    ap.add_argument("--fuzzy", choices=("aucun", "fixe", "calibre"), default="aucun")
    ap.add_argument("--seuil", type=float, default=0.88)
    ap.add_argument("--ecart", type=float, default=0.03)
    args = ap.parse_args(argv)
    console_utf8()
    if args.partition == "test":
        print("Attention : partition test, à n'utiliser que pour un jalon demandé par l'utilisateur.", file=sys.stderr)

    cat = Catalogue.charger(tiers=args.tiers)
    resolveur = construire(cat, args.fuzzy, args.seuil, args.ecart)
    res = evaluer(resolveur, charger_cas(args.partition, args.sous_partition))
    suffixe = ("" if set(args.tiers) == TIERS else "_tier" + "".join(sorted(args.tiers)))
    suffixe += "" if args.fuzzy == "aucun" else f"_fuzzy_{args.fuzzy}"
    suffixe += f"_{args.sous_partition}" if args.sous_partition else ""
    base = REP / f"moteur_{args.partition}{suffixe}"
    titre = ("étape 1 (résolveur exact)" if args.fuzzy == "aucun"
             else f"étape 2 (Jaro-Winkler borné, {resolveur.politique.decrire()})")
    commande = " ".join(argv if argv is not None else sys.argv[1:]) or "(sans option)"
    md = rapport_md(res, args.partition + (f" · {args.sous_partition}" if args.sous_partition else ""),
                    args.tiers, titre, commande)
    Path(f"{base}.md").write_text(md, encoding="utf-8")
    Path(f"{base}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(md)
    n, ideal, sur, sil = taux(res["comptes"]["TOTAL"])
    print(f"{n} cas · idéal {ideal:.1f} % · sûr {sur:.1f} % · silencieux {sil:.1f} %  →  {base}.md")
    return 1 if res["comptes"]["TOTAL"].get("erreur_silencieuse") else 0


if __name__ == "__main__":
    sys.exit(main())
