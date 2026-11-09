"""
Fusionne les couches ouverte et Mécanova en un catalogue unique et contrôle son intégrité.
Produit catalog/entities.csv, aliases.csv, relations.csv et reports/catalog_stats.json.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from common import CAT, REP, read_csv, write_csv

oe, me = read_csv(CAT / "open_entities.csv"), read_csv(CAT / "mecanova_entities.csv")
ge = read_csv(CAT / "glossaire_entities.csv")
ents = oe + me + ge
ids = [e["entity_id"] for e in ents]
dup = [k for k, v in Counter(ids).items() if v > 1]
assert not dup, f"identifiants dupliqués : {dup[:5]}"
idset = set(ids)

aliases = read_csv(CAT / "open_aliases.csv") + read_csv(CAT / "mecanova_aliases.csv") + read_csv(CAT / "glossaire_aliases.csv")
seen, al = set(), []
for a in aliases:
    assert a["entity_id"] in idset, f"alias orphelin {a}"
    k = (a["entity_id"], a["alias_norm"])
    if k not in seen:
        seen.add(k)
        al.append(a)

rels = read_csv(CAT / "open_relations.csv") + read_csv(CAT / "mecanova_relations.csv") + read_csv(CAT / "glossaire_relations.csv")
broken = [r for r in rels if r["subject_id"] not in idset or r["object_id"] not in idset]
assert not broken, f"relations cassées : {broken[:5]}"
parents = [e for e in ents if e.get("parent_id") and e["parent_id"] not in idset]
assert not parents, f"parents manquants : {[(p['entity_id'], p['parent_id']) for p in parents[:5]]}"

fields_e = list(dict.fromkeys(k for e in ents for k in e.keys()))
write_csv(CAT / "entities.csv", ents, fields_e, ["entity_id"])
write_csv(CAT / "aliases.csv", al, ["entity_id", "alias", "alias_norm", "lang", "alias_type", "tier", "source", "licence"], ["entity_id", "alias_norm"])
write_csv(CAT / "relations.csv", rels, ["subject_id", "predicate", "object_id", "source"], ["subject_id", "predicate", "object_id"])

index = defaultdict(set)
for a in al:
    index[a["alias_norm"]].add(a["entity_id"])
etype = {e["entity_id"]: e["entity_type"] for e in ents}
domain = {e["entity_id"]: e["domain"] for e in ents}
amb = {k: v for k, v in index.items() if len(v) > 1}
stats = {
    "entites": len(ents), "alias": len(al), "relations": len(rels),
    "entites_par_type": dict(sorted(Counter(e["entity_type"] for e in ents).items())),
    "alias_par_tier": dict(sorted(Counter(a["tier"] for a in al).items())),
    "alias_par_type": dict(Counter(a["alias_type"] for a in al).most_common()),
    "relations_par_predicat": dict(Counter(r["predicate"] for r in rels).most_common()),
    "cles_normalisees": len(index),
    "cles_ambigues": len(amb),
    "cles_ambigues_multi_domaines": sum(1 for v in amb.values() if len({domain[i] for i in v}) > 1),
    "cles_ambigues_multi_types": sum(1 for v in amb.values() if len({etype[i] for i in v}) > 1),
}
(REP / "catalog_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1))
print(json.dumps({k: v for k, v in stats.items() if not isinstance(v, dict)}, ensure_ascii=False))
