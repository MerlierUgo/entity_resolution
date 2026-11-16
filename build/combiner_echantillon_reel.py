"""Combine les saisies de la dictée (mode oreille) et du mode mémoire, et retire les artefacts du tiret lu à voix haute.

Le tiret « – » des libellés d'articles (« Filtre à huile – Knecht Standard ») est lu par la synthèse vocale :
la saisie contient alors un « e » ou « eu » en trop, collé à la marque (« euknec ») ou isolé (« e mecanova »).
On ne corrige que ce cas, uniquement en mode oreille, et seulement si la correction rapproche le mot de la marque.
La saisie d'origine est gardée dans saisie_brute.
"""
import csv
import sys
from pathlib import Path

from rapidfuzz.distance import OSA

D = Path(__file__).resolve().parent.parent / "human" / "echantillon_reel"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import normalize  # noqa: E402


def lire(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def corriger_tiret(saisie, cible):
    if "–" not in cible:
        return saisie, ""
    marque = normalize(cible.split("–", 1)[1]).split()
    if not marque:
        return saisie, ""
    marque = marque[0]
    mots = saisie.split()
    for i, m in enumerate(mots):
        if m.lower() in ("e", "eu") and i + 1 < len(mots):
            return " ".join(mots[:i] + mots[i + 1:]), f"« {m} » isolé retiré"
        low = m.lower()
        # « eu » collé : le tiret lu « euh » (aucun mot du domaine ne commence par « eu » ici)
        if low.startswith("eu") and len(m) > 3 and not low.startswith(("euro", "europ")):
            reste = m[2:]
            return " ".join(mots[:i] + [reste] + mots[i + 1:]), f"« eu » collé retiré ({m} → {reste})"
        # « e » collé : seulement si le reste est vraiment proche de la marque (évite étrier, établissement, éco…)
        if low.startswith("e") and len(m) > 2:
            reste = m[1:]
            d = OSA.distance(normalize(reste), marque)
            if d < OSA.distance(normalize(m), marque) and d <= max(1, len(marque) // 2):
                return " ".join(mots[:i] + [reste] + mots[i + 1:]), f"« e » collé retiré ({m} → {reste})"
    return saisie, ""


def main():
    lignes = []
    for mode, f_sais, f_corr, col_nom in (("oreille", "saisies_ugo.csv", "correspondance.csv", "nom_a_dicter"),
                                          ("memoire", "saisies_memoire_ugo.csv", "correspondance_memoire.csv", "nom_affiche")):
        corr = {r["ordre"]: r for r in lire(D / f_corr)}
        for s in lire(D / f_sais):
            brute = s["saisie"].strip()
            c = corr.get(s["ordre"])
            if c is None:  # terme libre, hors catalogue présumé
                lignes.append(dict(ordre=s["ordre"], mode=f"libre_{mode}", nom_cible="", famille="", entity_type="",
                                   entity_id="", saisie_brute=brute, saisie=brute, correction="", duree_ms=""))
                continue
            saisie, note = corriger_tiret(brute, c[col_nom]) if mode == "oreille" else (brute, "")
            lignes.append(dict(ordre=s["ordre"], mode=mode, nom_cible=c[col_nom], famille=c["famille"],
                               entity_type=c["entity_type"], entity_id=c["entity_id"], saisie_brute=brute,
                               saisie=saisie, correction=note, duree_ms=s["duree_ms"]))
    champs = ["ordre", "mode", "nom_cible", "famille", "entity_type", "entity_id", "saisie_brute", "saisie",
              "correction", "duree_ms"]
    with open(D / "saisies_combinees.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=champs, delimiter=";")
        w.writeheader()
        w.writerows(lignes)
    for l in lignes:
        if l["correction"]:
            print(f'{l["ordre"]:>4}  {l["saisie_brute"]:<45} → {l["saisie"]:<40} ({l["nom_cible"]})')
    print(f"{len(lignes)} lignes, {sum(bool(l['correction']) for l in lignes)} corrections -> {D / 'saisies_combinees.csv'}")


if __name__ == "__main__":
    main()
