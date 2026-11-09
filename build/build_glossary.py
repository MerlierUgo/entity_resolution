"""
Compile le glossaire métier v2 (spec/glossaire.yaml) dans le catalogue :
  - mesures (spec/mesures.yaml) et listes métier deviennent des entités (types « mesure », « segment », « canal »…) ;
  - les synonymes d'atelier deviennent des alias des entités du catalogue qu'ils ciblent ;
  - les valeurs absentes connues rejoignent l'index négatif.
Produit catalog/glossaire_entities.csv, glossaire_aliases.csv, glossaire_relations.csv, negatifs.csv.
"""
from __future__ import annotations

import yaml

from common import CAT, ROOT, load_mesures, normalize, read_csv, slug, write_csv

SRC = ("Glossaire métier v2 (spec/glossaire.yaml)", "CC0")
SRC_MES = ("Mesures (spec/mesures.yaml)", "CC0")
g = yaml.safe_load((ROOT / "spec" / "glossaire.yaml").read_text(encoding="utf-8"))
known = {e["entity_id"] for e in read_csv(CAT / "open_entities.csv")} | {e["entity_id"] for e in read_csv(CAT / "mecanova_entities.csv")}
E, A, R = [], [], []


def ent(eid, etype, label, src=SRC, **kw):
    E.append({"entity_id": eid, "entity_type": etype, "domain": "metier", "label": label, "tier": 3,
              "source": src[0], "licence": src[1], **kw})
    alias(eid, label, "libelle_canonique", src)


def alias(eid, text, atype, src=SRC):
    if normalize(str(text)):
        A.append({"entity_id": eid, "alias": str(text), "alias_norm": normalize(str(text)), "lang": "fr",
                  "alias_type": atype, "tier": 3, "source": src[0], "licence": src[1]})


for m in load_mesures():
    eid = f"metier:mesure:{m['id']}"
    ent(eid, "mesure", m["libelle"], src=SRC_MES, code=m["id"])
    for a in m["alias"]:
        alias(eid, a, "synonyme_mesure", SRC_MES)

for liste, values in g["listes_metier"].items():
    for v in values:
        eid = f"metier:{liste}:{slug(v['canonique'])}"
        ent(eid, liste, v["canonique"])
        for a in v["alias"]:
            alias(eid, a, "synonyme_metier")
        if v.get("groupe"):
            R.append({"subject_id": eid, "predicate": "groupe_de_canaux", "object_id": f"metier:groupe_canal:{slug(v['groupe'])}",
                      "source": SRC[0]})

missing = []
for s in g["synonymes_metier"]:
    for c in s["cibles"]:
        if c not in known:
            missing.append((s["terme"], c))
        alias(c, s["terme"], "synonyme_atelier")
assert not missing, f"synonymes vers des entités inexistantes : {missing}"

neg = [{"terme": v["terme"], "terme_norm": normalize(v["terme"]), "ressemble_a": v["ressemble_a"], "source": SRC[0]}
       for v in g["valeurs_absentes"]]
neg += [{"terme": o["name"], "terme_norm": o["name_norm"], "ressemble_a": "lieu", "source": "GeoNames, hors périmètre"}
        for o in read_csv(CAT / "hors_perimetre_geonames.csv")]

positive = {a["alias_norm"] for f in ("open_aliases.csv", "mecanova_aliases.csv") for a in read_csv(CAT / f)} | {a["alias_norm"] for a in A}
masked = [n for n in neg if n["terme_norm"] in positive]
neg = [n for n in neg if n["terme_norm"] not in positive]
print(f"index négatif : {len(masked)} termes retirés car présents dans le catalogue (le positif l'emporte)")

write_csv(CAT / "glossaire_entities.csv", E, ["entity_id", "entity_type", "domain", "label", "code", "tier", "source", "licence"], ["entity_id"])
write_csv(CAT / "glossaire_aliases.csv", A, ["entity_id", "alias", "alias_norm", "lang", "alias_type", "tier", "source", "licence"], ["entity_id", "alias_norm"])
write_csv(CAT / "glossaire_relations.csv", R, ["subject_id", "predicate", "object_id", "source"], ["subject_id"])
write_csv(CAT / "negatifs.csv", neg, ["terme", "terme_norm", "ressemble_a", "source"], ["terme_norm", "terme"])
print(f"glossaire compilé : {len(E)} entités, {len(A)} alias, {len(R)} relations, {len(neg)} termes négatifs")
