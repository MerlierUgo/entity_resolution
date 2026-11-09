"""
Jeu de défis pour l'entity resolution déterministe.

Chaque cas est dérivé des données (jamais écrit à la main), avec sa vérité terrain :
  expected_status    resolved | ambiguous | unknown
  expected_ids       entités attendues (une si resolved, l'ensemble des candidats si ambiguous)
  accepted           issues acceptables en plus de l'attendue (ex. une faute de frappe proche d'une
                     autre entité peut être ambiguous, jamais résolue vers la mauvaise entité)
  hint_type          type d'entité fourni comme contexte (comme le ferait l'étape intention), ou vide

La règle de vérité est celle du catalogue : un texte dont la forme normalisée correspond aux alias de
plusieurs entités est ambigu ; un texte qui ne correspond à aucun alias et dont l'intention réelle est
hors du catalogue est inconnu.
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict

from rapidfuzz import process
from rapidfuzz.distance import JaroWinkler

from common import CAT, CHAL, SEED, code_key, normalize, read_csv, write_csv
from rules import Rules

rng = random.Random(SEED + 7)
ents = {e["entity_id"]: e for e in read_csv(CAT / "entities.csv")}
aliases = read_csv(CAT / "aliases.csv")
index = defaultdict(set)
for a in aliases:
    index[a["alias_norm"]].add(a["entity_id"])
sorted_index = defaultdict(set)
for k, v in index.items():
    sorted_index[" ".join(sorted(k.split()))] |= v
by_entity = defaultdict(list)
for a in aliases:
    by_entity[a["entity_id"]].append(a)
etype = {i: e["entity_type"] for i, e in ents.items()}
CODE_TYPES = {"article", "client", "code_douanier"}

CASES: list[dict] = []
RULES = Rules(CAT)


def truth(raw, hint=None):
    """Vérité terrain = candidats de l'index, puis règles de la spec v2 (build/rules.py)."""
    return RULES.apply(set(raw), hint)


def lookup(text: str) -> set[str]:
    n = normalize(text)
    return set(index.get(n, set())) | set(sorted_index.get(" ".join(sorted(n.split())), set()))


def add(cat, text, status, ids, why, difficulty=1, hint="", accepted=(), note="", raw=None):
    if raw is None:
        r = lookup(text)
        raw = r if r and truth(r) == set(ids) else set(ids)
    if set(raw) != set(ids):
        why += " ; règles de la spec appliquées"
    CASES.append({"category": cat, "input_text": text, "hint_type": hint, "expected_status": status,
                  "expected_ids": "|".join(sorted(ids)), "accepted": "|".join(accepted), "difficulty": difficulty,
                  "ground_truth": why, "note": note})


def expect_from_index(text):
    hits = truth(lookup(text))
    return Rules.status(hits), hits


def sample(seq, k):
    seq = sorted(seq)
    return rng.sample(seq, min(k, len(seq)))


# C01 · libellés canoniques (contrôle de base, tous types)
by_type = defaultdict(list)
for i, e in ents.items():
    by_type[e["entity_type"]].append(i)
for t, ids in sorted(by_type.items()):
    for i in sample(ids, 25 if len(ids) > 25 else len(ids)):
        st, hits = expect_from_index(ents[i]["label"])
        add("C01_libelle_canonique", ents[i]["label"], st, hits, "index du catalogue", 1)

# C02 · traductions officielles (FR ↔ NL ↔ DE ↔ EN)
tr = [a for a in aliases if a["alias_type"] in ("traduction_officielle", "traduction_iso")
      and a["alias_norm"] != normalize(ents[a["entity_id"]]["label"])]
for a in sample([(x["entity_id"], x["alias"]) for x in tr], 500):
    st, hits = expect_from_index(a[1])
    add("C02_traduction_officielle", a[1], st, hits, "traduction officielle de la source", 1)

# C03 · variantes et exonymes GeoNames
gv = [(a["entity_id"], a["alias"]) for a in aliases if a["alias_type"] == "variante_geonames"
      and a["alias_norm"] != normalize(ents[a["entity_id"]]["label"])]
for eid, text in sample(gv, 500):
    st, hits = expect_from_index(text)
    add("C03_variante_geonames", text, st, hits, "nom alternatif GeoNames", 2)

# C04 · vocabulaire métier face aux traductions automatiques de la taxonomie
for a in aliases:
    if a["alias_type"] in ("terme_metier", "terme_catalogue_mecanova", "synonyme_metier"):
        st, hits = expect_from_index(a["alias"])
        add("C04_terme_metier", a["alias"], st, hits, "terme métier curé", 2)

# C05 · homonymes : une même forme normalisée, plusieurs entités
amb_keys = {k: v for k, v in index.items() if len(v) > 1}
multi_type = [k for k, v in amb_keys.items() if len({etype[i] for i in v}) > 1]
same_type = [k for k, v in amb_keys.items() if len({etype[i] for i in v}) == 1]
for k in sample(multi_type, 400) + sample(same_type, 300):
    ids = amb_keys[k]
    text = next(a["alias"] for i in sorted(ids) for a in by_entity[i] if a["alias_norm"] == k)
    st, hits = expect_from_index(text)
    types = sorted({etype[i] for i in ids})
    add("C05_homonyme", text, st, hits, "plusieurs entités partagent la forme normalisée", 3,
        note="types : " + ", ".join(types), raw=lookup(text))

# C06 · la même ambiguïté, levée (ou non) par un indice de type
for k in sample(multi_type, 400):
    ids = amb_keys[k]
    text = next(a["alias"] for i in sorted(ids) for a in by_entity[i] if a["alias_norm"] == k)
    for t in sorted({etype[i] for i in ids}):
        sub = truth(lookup(text), {t})
        add("C06_indice_de_type", text, Rules.status(sub), sub, "candidats du type indiqué", 2, hint=t,
            raw={i for i in lookup(text) if etype[i] == t})

# C07 · fautes de frappe synthétiques (une opération d'édition, graine fixe)
KEYB = {c: n for c, n in zip("azertyuiopqsdfghjklmwxcvbn", "zaeryt uiopqsdfghjklm wxcvbn")}


def typo(s: str) -> str:
    letters = [i for i, c in enumerate(s) if c.isalpha()]
    i = rng.choice(letters[1:-1] or letters)
    op = rng.choice(["del", "swap", "sub", "dup"])
    if op == "del":
        return s[:i] + s[i + 1:]
    if op == "swap" and i + 1 < len(s):
        return s[:i] + s[i + 1] + s[i] + s[i + 2:]
    if op == "dup":
        return s[:i] + s[i] + s[i:]
    c = s[i].lower()
    rep = KEYB.get(c, "e").strip() or "e"
    return s[:i] + rep + s[i + 1:]


typo_pool = [i for i, e in ents.items() if e["entity_type"] not in CODE_TYPES and len(normalize(e["label"])) >= 6]
type_keys = defaultdict(list)
for k, v in index.items():
    for i in v:
        type_keys[etype[i]].append(k)
n = 0
for eid in sample(typo_pool, 1500):
    lab = ents[eid]["label"]
    t = typo(lab)
    if normalize(t) == normalize(lab) or lookup(t):
        continue  # la faute tombe sur un libellé existant : ce n'est plus une faute
    q = normalize(t)
    own = max(JaroWinkler.normalized_similarity(q, a["alias_norm"]) for a in by_entity[eid])
    rivals = process.extract(q, type_keys[etype[eid]], scorer=JaroWinkler.normalized_similarity, limit=5,
                             score_cutoff=own - 0.0001)
    rival_ids = {i for k, _, _ in rivals for i in index[k] if i != eid}
    exp = truth({eid} | rival_ids)
    if len(exp) > 1:
        add("C07_faute_de_frappe", t, "ambiguous", exp, "faute générée ; une autre entité est au moins aussi proche",
            3, accepted=("unknown",), note=f"origine : {lab}", raw={eid} | rival_ids)
    else:
        add("C07_faute_de_frappe", t, "resolved", exp, "faute générée sur le libellé", 2, accepted=("unknown",),
            note=f"origine : {lab}", raw={eid} | rival_ids)
    n += 1

# C07b · fautes de frappe sur les alias (traductions, exonymes, marques, modèles, clients)
alias_pool = [(a["entity_id"], a["alias"]) for a in aliases
              if etype[a["entity_id"]] not in CODE_TYPES and a["alias_type"] != "libelle_canonique"
              and len(a["alias_norm"]) >= 6 and not any(ch.isdigit() for ch in a["alias"])]
for eid, lab in sample(alias_pool, 1500):
    t = typo(lab)
    if normalize(t) == normalize(lab) or lookup(t):
        continue
    q = normalize(t)
    intended = lookup(lab)
    own = JaroWinkler.normalized_similarity(q, normalize(lab))
    rivals = process.extract(q, type_keys[etype[eid]], scorer=JaroWinkler.normalized_similarity, limit=5,
                             score_cutoff=own - 0.0001)
    rival_ids = {i for k, _, _ in rivals for i in index[k]} - intended
    exp = truth(intended | rival_ids)
    add("C07_faute_de_frappe", t, Rules.status(exp), exp, "faute générée sur un alias", 3,
        accepted=("unknown",), note=f"origine : {lab}", raw=intended | rival_ids)

# C13 · abréviations usuelles des toponymes (St, Ste, Mt, s/)
ABBR = [(r"\bSaint-", "St-"), (r"\bSainte-", "Ste-"), (r"\bSaint ", "St "), (r"\bMont-", "Mt-"), (r"-sur-", "-s/-"),
        (r"\bSint-", "St.-")]
import re as _re
geo_labels = [(i, e["label"]) for i, e in ents.items() if e["domain"] == "geographie"]
for eid, lab in sample(geo_labels, len(geo_labels)):
    for pat, rep in ABBR:
        if _re.search(pat, lab):
            v = _re.sub(pat, rep, lab, count=1)
            if lookup(v):
                add("C13_abreviation", v, *expect_from_index(v), "abréviation présente dans l'index", 1)
            else:
                intended = truth(lookup(lab))
                add("C13_abreviation", v, Rules.status(intended), intended,
                    "abréviation usuelle non indexée : l'intention est le toponyme d'origine", 3,
                    accepted=("unknown",), note=f"origine : {lab}")
            break

# C08 · lieux réels hors périmètre, très proches d'un lieu du catalogue (pièges « Dinan / Dinant »)
out = read_csv(CAT / "hors_perimetre_geonames.csv")
geo_keys = sorted({a["alias_norm"] for a in aliases if ents[a["entity_id"]]["domain"] == "geographie"})
cands = [o for o in out if len(o["name_norm"]) >= 5 and not lookup(o["name"])]
rng.shuffle(cands)
kept = 0
for o in cands:
    best = process.extractOne(o["name_norm"], geo_keys, scorer=JaroWinkler.normalized_similarity, score_cutoff=0.92)
    if not best:
        continue
    near = sorted(index[best[0]])
    add("C08_hors_perimetre_proche", o["name"], "unknown", set(), "lieu GeoNames réel hors périmètre", 3,
        note=f"{o['country']} ; proche de « {best[0]} » (JW {best[1]:.3f}) → {near[0]}")
    kept += 1
    if kept >= 600:
        break

# C09 · codes : formats tolérés, codes voisins inexistants, voisins existants
arts = [e for e in ents.values() if e["entity_type"] == "article"]
codes_existing = {code_key(e["code"]) for e in arts}
for e in sample([x["entity_id"] for x in arts], 300):
    ref = ents[e]["code"]
    variant = rng.choice([ref.lower(), ref.replace("-", " "), ref.replace("-", ""), ref.replace("-", ".")])
    add("C09_code", variant, "resolved", {e}, "référence Mécanova, format toléré (R-ART-01)", 1)
    num = int(ref[-5:])
    for d in (1, 2, 3, 4, 5, 6, 7, 8, 9):
        cand = f"{ref[:7]}{(num + d) % 100000:05d}"
        if code_key(cand) not in codes_existing:
            add("C09_code", cand, "unknown", set(), "référence voisine inexistante : jamais de correspondance approchée",
                3, note=f"voisine de {ref}")
            break
neighbours = defaultdict(list)
for e in arts:
    neighbours[e["code"][:7]].append(e)
for pfx, lst in sorted(neighbours.items()):
    nums = sorted(lst, key=lambda x: x["code"])
    for a, b in zip(nums, nums[1:]):
        if sum(x != y for x, y in zip(a["code"], b["code"])) == 1:
            add("C09_code", b["code"], "resolved", {b["entity_id"]}, "référence valide à un caractère d'une autre", 3,
                note=f"voisine existante : {a['code']}")
for e in sample([i for i, x in ents.items() if x["entity_type"] == "code_douanier" and len(x["code"]) == 6], 80):
    c = ents[e]["code"]
    add("C09_code", f"{c[:4]}.{c[4:]}", "resolved", {e}, "code SH au format pointé", 1)
    add("C09_code", f"{c[:4]} {c[4:]}", "resolved", {e}, "code SH avec espace", 1)
for e in sample([i for i, x in ents.items() if x["entity_type"] == "client"], 150):
    c = ents[e]["code"]
    add("C09_code", c, "resolved", {e}, "code client exact", 1)
    alt = f"CL-{(int(c[3:]) + 1) % 1000000:06d}"
    if not lookup(alt):
        add("C09_code", alt, "unknown", set(), "code client voisin inexistant", 3, note=f"voisin de {c}")

# C10 · clients : variantes de raison sociale (stockées ou non)
clients = [e for e in ents.values() if e["entity_type"] == "client"]
FORM_SWAP = {"SRL": ["S.R.L", "srl", "Srl"], "SA": ["S.A", "s.a."], "SPRL": ["S.P.R.L"], "SARL": ["S.A.R.L", "Sarl"],
             "SAS": ["S.A.S"], "B.V.": ["BV", "B.V"], "S.à r.l.": ["Sàrl", "SARL"]}
for e in sample([c["entity_id"] for c in clients], 500):
    c = ents[e]
    trade, form = c["trade_name"], c["legal_form"]
    variants = [trade, trade.upper(), f"{trade} {rng.choice(FORM_SWAP.get(form, [form]))}",
                " ".join(reversed(trade.split())) if len(trade.split()) == 2 else trade]
    base = truth(lookup(trade))
    for v in dict.fromkeys(variants):
        st, hits = expect_from_index(v)
        if hits:
            if e not in hits:
                continue
            add("C10_client", v, st, hits, "variante de raison sociale indexée", 2, note=f"client : {c['label']}")
        else:
            add("C10_client", v, Rules.status(base), base,
                "variante non indexée : l'intention est le client d'origine (ou ses homonymes)", 3,
                accepted=("unknown",), note=f"client : {c['label']}")

# C11 · marques et groupes
for e in [i for i, x in ents.items() if x["entity_type"] in ("marque_piece", "groupe_industriel", "marque_vehicule")]:
    for a in by_entity[e]:
        st, hits = expect_from_index(a["alias"])
        add("C11_marque", a["alias"], st, hits, f"alias de {etype[e]}", 1 if st == "resolved" else 3)

# C12 · véhicules : alias EEA, marque + modèle, modèle seul
models = [i for i, x in ents.items() if x["entity_type"] == "modele_vehicule"]
for e in sample(models, 400):
    for a in by_entity[e]:
        st, hits = expect_from_index(a["alias"])
        add("C12_vehicule", a["alias"].title() if rng.random() < 0.5 else a["alias"].lower(), st, hits,
            f"alias de modèle ({a['alias_type']})", 2 if st == "resolved" else 3)

# ------------------------------------------------------------------ export
uniq, seen = [], set()
for c in CASES:
    k = (c["category"], normalize(c["input_text"]), c["hint_type"])
    if k in seen:
        continue
    seen.add(k)
    uniq.append(c)
for i, c in enumerate(sorted(uniq, key=lambda c: (c["category"], c["input_text"], c["hint_type"]))):
    c["case_id"] = f"ER-{i + 1:05d}"
fields = ["case_id", "category", "input_text", "hint_type", "expected_status", "expected_ids", "accepted",
          "difficulty", "ground_truth", "note"]
write_csv(CHAL / "cases.csv", uniq, fields, ["case_id"])

# Jeu « core » : échantillon stratifié pour la CI, et partition dev / test figée
core = []
for cat in sorted({c["category"] for c in uniq}):
    pool = sorted([c for c in uniq if c["category"] == cat], key=lambda c: c["case_id"])
    core += random.Random(SEED + 11).sample(pool, min(60, len(pool)))
write_csv(CHAL / "cases_core.csv", core, fields, ["case_id"])
split = random.Random(SEED + 13)
dev_test = [{"case_id": c["case_id"], "split": "test" if split.random() < 0.3 else "dev"} for c in sorted(uniq, key=lambda c: c["case_id"])]
write_csv(CHAL / "split.csv", dev_test, ["case_id", "split"], ["case_id"])
stats = {"total": len(uniq), "core": len(core),
         "par_categorie": dict(sorted(Counter(c["category"] for c in uniq).items())),
         "par_statut": dict(Counter(c["expected_status"] for c in uniq)),
         "test": sum(1 for x in dev_test if x["split"] == "test")}
(CHAL / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(stats, ensure_ascii=False, indent=1))
