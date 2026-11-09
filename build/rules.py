"""
Règles de résolution de la spec v2, en un seul endroit.

Utilisé par la génération du jeu de défis (vérité terrain), la mesure de référence et spec/check_spec.py,
pour que les trois appliquent exactement la même sémantique :

  R-GEO-02  une localité postale homonyme de sa commune est absorbée par la commune
  R-CTX-05  une commune ou une ville candidate ajoute le site Mécanova qui s'y trouve
  R-ART-03  une famille qui ne contient qu'une catégorie l'emporte sur cette catégorie
  R-RES-09  un indice de type (ensemble de types) filtre les candidats, y compris à l'exact

Ordre : candidats bruts de l'index → règles → filtre par l'indice de type.
Un indice de type désigne ce que l'utilisateur a explicitement demandé : les candidats bruts de ce type
restent admis même si une règle les a absorbés (« la localité de Torhout » reste une localité).
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import csv


class Rules:
    def __init__(self, catalog_dir: Path):
        def rd(name):
            with open(catalog_dir / name, encoding="utf-8-sig") as f:
                return list(csv.DictReader(f))

        ents = {e["entity_id"]: e for e in rd("entities.csv")}
        self.etype = {i: e["entity_type"] for i, e in ents.items()}
        self.label = {i: e["label"] for i, e in ents.items()}
        self.parent = defaultdict(set)
        self.located = defaultdict(set)
        self.fam_cats = defaultdict(set)
        for r in rd("relations.csv"):
            if r["predicate"] == "situe_dans":
                self.parent[r["subject_id"]].add(r["object_id"])
                self.located[r["object_id"]].add(r["subject_id"])
            elif r["predicate"] == "famille_mecanova":
                self.fam_cats[r["object_id"]].add(r["subject_id"])
        from common import normalize  # même normalisation que le catalogue
        self.norm = {i: normalize(l) for i, l in self.label.items()}

    def apply(self, raw: set[str], hint: set[str] | None = None) -> set[str]:
        hits = set(raw)
        # R-GEO-02
        absorbed = set()
        for h in list(hits):
            if self.etype[h] != "localite_postale":
                continue
            for p in self.parent[h]:
                if self.etype.get(p) == "commune" and self.norm[p] == self.norm[h]:
                    absorbed.add(h)
                    hits.add(p)
            if self.parent[h] & hits:
                absorbed.add(h)
        hits -= absorbed
        # R-CTX-05
        hits |= {s for h in list(hits) if self.etype[h] in ("commune", "ville")
                 for s in self.located[h] if self.etype.get(s) == "site"}
        # R-ART-03
        for f in [h for h in hits if self.etype[h] == "famille_mecanova"]:
            if len(self.fam_cats[f]) == 1:
                hits -= self.fam_cats[f]
        # R-RES-09
        if hint:
            typed = {h for h in hits | set(raw) if self.etype[h] in hint}
            if typed:
                hits = typed
        return hits

    @staticmethod
    def status(hits: set[str]) -> str:
        return "resolved" if len(hits) == 1 else "ambiguous" if hits else "unknown"
