"""Tire au hasard (graine fixe) les noms à dicter pour l'échantillon réel de saisie.

Sorties dans human/echantillon_reel/ :
  - liste_dictee.csv  : ordre ; nom à dicter ; saisie (vide, à remplir)  -> la seule à ouvrir pendant la dictée
  - correspondance.csv : ordre ; nom ; famille ; type ; entity_id       -> à n'ouvrir que pour étiqueter
Les entités qui servent d'attendu dans la partition test de challenges/ sont exclues.
"""
import csv
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "human" / "echantillon_reel"
GRAINE = 20261116

# famille -> (types, nombre à tirer)
PLAN = {
    "geographie": (["commune", "ville", "localite_postale", "arrondissement", "province"], 70),
    "pieces": (["categorie_piece", "famille_mecanova", "article"], 50),
    "vehicules": (["modele_vehicule"], 40),
    "clients": (["client"], 40),
    "marques": (["marque_piece", "marque_vehicule", "groupe_industriel"], 25),
    "vocabulaire_metier": (["mesure", "site", "commercial", "canal", "type_client", "motif_retour", "segment"], 15),
}


def lire(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def nom_a_dicter(e, ents):
    if e["entity_type"] == "client" and e["trade_name"]:
        return e["trade_name"]                      # on dit « Garage Dupont », pas « Garage Dupont SRL »
    if e["entity_type"] == "modele_vehicule":
        marque = ents.get(e["parent_id"])
        if marque and not e["label"].lower().startswith(marque["label"].lower()):
            return f'{marque["label"]} {e["label"]}'  # on dit « Fiat 500 », pas « 500 »
    return e["label_fr"] or e["label"]


def main():
    ents = {e["entity_id"]: e for e in lire(ROOT / "catalog" / "entities.csv")}
    split = {r["case_id"]: r["split"] for r in lire(ROOT / "challenges" / "split.csv")}
    exclus = set()
    for c in lire(ROOT / "challenges" / "cases.csv"):
        if split.get(c["case_id"]) == "test":
            exclus.update(i for i in c["expected_ids"].split("|") if i)

    rng = random.Random(GRAINE)
    tirage, vus = [], set()
    for fam, (types, n) in PLAN.items():
        pool = sorted((e for e in ents.values() if e["entity_type"] in types and e["entity_id"] not in exclus),
                      key=lambda e: e["entity_id"])
        if fam == "geographie":
            # moitié parmi les lieux les plus peuplés (ceux qu'on cite le plus), moitié au hasard
            pop = sorted((e for e in pool if e["population"]), key=lambda e: -float(e["population"]))[:300]
            choix = rng.sample(pop, n // 2)
            reste = [e for e in pool if e not in choix]
            choix += rng.sample(reste, n - n // 2)
        else:
            choix = rng.sample(pool, min(n, len(pool)))
        for e in choix:
            nom = nom_a_dicter(e, ents)
            if nom.lower() in vus:
                continue
            vus.add(nom.lower())
            tirage.append((nom, fam, e["entity_type"], e["entity_id"]))

    rng.shuffle(tirage)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "liste_dictee.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ordre", "nom_a_dicter", "saisie"])
        for i, (nom, *_ ) in enumerate(tirage, 1):
            w.writerow([i, nom, ""])
    with open(OUT / "correspondance.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ordre", "nom_a_dicter", "famille", "entity_type", "entity_id"])
        for i, row in enumerate(tirage, 1):
            w.writerow([i, *row])
    print(f"{len(tirage)} noms tirés (graine {GRAINE}) -> {OUT}")


if __name__ == "__main__":
    main()
