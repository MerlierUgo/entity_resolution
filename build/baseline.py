"""
Mesure de référence : trois résolveurs simples passés sur le jeu de défis, pour montrer ce que le jeu
attrape. Ce ne sont pas des propositions de moteur, seulement des étalons.

  B0  exact      : forme normalisée (et mots triés) dans l'index des alias, rien d'autre
  B1  fuzzy naïf : B0, puis Jaro-Winkler ≥ 0,88 sur tout l'index, meilleur candidat retenu
  B2  fuzzy borné: B0, puis Jaro-Winkler ≥ 0,88 borné au type indiqué, jamais sur un code,
                   jamais sous 4 caractères, ambigu si les deux meilleurs sont à moins de 0,03

Métrique principale : l'erreur silencieuse, c'est-à-dire une réponse « resolved » vers une entité
qui n'est pas la bonne. Une réponse ambiguous ou unknown peut être imparfaite ; une erreur
silencieuse ne l'est jamais.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

from rapidfuzz import process
from rapidfuzz.distance import JaroWinkler

from common import CAT, CHAL, REP, normalize, read_csv
from rules import Rules

ents = {e["entity_id"]: e for e in read_csv(CAT / "entities.csv")}
aliases = read_csv(CAT / "aliases.csv")
index, sorted_index = defaultdict(set), defaultdict(set)
for a in aliases:
    index[a["alias_norm"]].add(a["entity_id"])
for k, v in index.items():
    sorted_index[" ".join(sorted(k.split()))] |= v
etype = {i: e["entity_type"] for i, e in ents.items()}
CODE_TYPES = {"article", "client", "code_douanier"}
keys_all = sorted(index)
keys_by_type = defaultdict(list)
for k, v in index.items():
    for t in {etype[i] for i in v}:
        keys_by_type[t].append(k)
CODE_RE = re.compile(r"\d")


def exact(text, hint):
    n = normalize(text)
    return index.get(n, set()) | sorted_index.get(" ".join(sorted(n.split())), set())


RULES = Rules(CAT)
_HINT = {"value": None}


def verdict(hits):
    """Chaque résolveur applique les règles de la spec v2 à ses candidats (même sémantique que la vérité terrain)."""
    h = _HINT["value"]
    hits = RULES.apply(set(hits), {h} if h else None)
    return Rules.status(hits), hits


def b0(text, hint):
    return verdict(exact(text, hint))


def b1(text, hint):
    hits = exact(text, hint)
    if hits:
        return verdict(hits)
    best = process.extractOne(normalize(text), keys_all, scorer=JaroWinkler.normalized_similarity, score_cutoff=0.88)
    return verdict(set(sorted(index[best[0]])[:1]) if best else set())


def b2(text, hint):
    hits = exact(text, hint)
    if hits:
        return verdict(hits)
    q = normalize(text)
    if len(q.replace(" ", "")) < 4 or CODE_RE.search(q):
        return verdict(set())
    pool = keys_by_type[hint] if hint else keys_all
    res = process.extract(q, pool, scorer=JaroWinkler.normalized_similarity, limit=5, score_cutoff=0.88)
    if not res:
        return verdict(set())
    top = res[0][1]
    close = [k for k, s, _ in res if top - s < 0.03]
    found = set().union(*(index[k] for k in close))
    if hint:
        found = {f for f in found if etype[f] == hint}
    return verdict(found)


def score(case, status, hits):
    exp = set(filter(None, case["expected_ids"].split("|")))
    acc = set(filter(None, case["accepted"].split("|")))
    if status == "resolved" and hits and next(iter(hits)) not in exp:
        return "erreur_silencieuse"
    if status == case["expected_status"]:
        if status == "unknown" or hits == exp:
            return "correct"
        return "partiel"
    if status in acc:
        return "acceptable"
    if status == "resolved" and case["expected_status"] == "ambiguous":
        return "erreur_silencieuse" if next(iter(hits)) not in exp else "trop_confiant"
    return "incorrect"


cases = read_csv(CHAL / "cases.csv")
out = {}
for name, fn in (("B0_exact", b0), ("B1_fuzzy_naif", b1), ("B2_fuzzy_borne", b2)):
    per = defaultdict(Counter)
    for c in cases:
        _HINT["value"] = c["hint_type"] or None
        st, hits = fn(c["input_text"], c["hint_type"])
        per[c["category"]][score(c, st, hits)] += 1
        per["TOTAL"][score(c, st, hits)] += 1
    out[name] = {k: dict(v) for k, v in sorted(per.items())}
(REP / "baseline.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))

lines = ["# Mesure de référence sur le jeu de défis", "",
         "Trois résolveurs volontairement simples (voir `build/baseline.py`). En % des cas de chaque catégorie :",
         "- **idéal** : la réponse attendue exactement ;",
         "- **sûr** : idéal, ou une réponse prudente acceptée (unknown face à une faute, ambiguous incluant la bonne entité) ;",
         "- **silencieux** : une entité résolue qui n'est pas la bonne. C'est l'erreur à ramener à zéro.", "",
         "| Catégorie | Cas | " + " | ".join(f"{n} idéal | sûr | silencieux" for n in out) + " |",
         "|---|---:|" + "---:|---:|---:|" * len(out)]
for cat in sorted(out["B0_exact"]):
    tot = sum(out["B0_exact"][cat].values())
    cells = []
    for n in out:
        c = out[n][cat]
        ideal = c.get("correct", 0)
        safe = ideal + c.get("acceptable", 0) + c.get("partiel", 0)
        cells += [f"{100 * ideal / tot:.1f}", f"{100 * safe / tot:.1f}", f"{100 * c.get('erreur_silencieuse', 0) / tot:.1f}"]
    lines.append(f"| {cat} | {tot} | " + " | ".join(cells) + " |")
(REP / "baseline.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
