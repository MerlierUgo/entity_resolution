"""
Contrôle de cohérence de la spec métier v2 contre le knowledge catalog.

Vérifie que :
  - glossaire, mesures.yaml, regles.yaml, types.yaml et questions.yaml se référencent correctement ;
  - les vues lisibles générées (mesures.md, regles.md, LACUNES.md) sont à jour ;
  - chaque renvoi du glossaire vers le catalogue existe, avec le bon type ;
  - le vocabulaire métier ne crée pas de collision non déclarée avec le catalogue ;
  - chaque terme des questions se résout vers l'entité attendue en appliquant les règles
    R-RES-02, R-RES-03, R-RES-06/07, R-CTX-03, R-CTX-05, R-GEO-02 et R-ART-03 ;
  - les Manifest attendus sont canoniques et ne citent que des entités du bon type.

Usage : python spec/check_spec.py   (depuis la racine du catalogue, après build/run_all.sh)
Code de sortie 0 si tout est cohérent.
"""
from __future__ import annotations

import csv
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import yaml
from rapidfuzz import process
from rapidfuzz.distance import JaroWinkler

ROOT = Path(__file__).resolve().parent.parent
SPEC, CAT = ROOT / "spec", ROOT / "catalog"
STOP = {"de", "d", "du", "des", "la", "le", "les", "l", "a", "au", "aux", "en", "et"}
errors, notes = [], []


def err(m): errors.append(m)


def normalize(s):
    s = str(s).replace("%", " pourcent ").replace("€", " euros ").replace("’", "'")
    s = "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))
    toks = [t for t in re.sub(r"[^a-z0-9]+", " ", s).split() if t not in STOP]
    return " ".join(t[:-1] if len(t) > 3 and t[-1] in "sx" and not t.endswith("ss") else t for t in toks)


def rd(p):
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


g = yaml.safe_load((SPEC / "glossaire.yaml").read_text(encoding="utf-8"))
q = yaml.safe_load((SPEC / "questions.yaml").read_text(encoding="utf-8"))
types_q = {t["id"] for t in yaml.safe_load((SPEC / "types.yaml").read_text(encoding="utf-8"))["types"]}
mesures_y = yaml.safe_load((SPEC / "mesures.yaml").read_text(encoding="utf-8"))
regles_y = yaml.safe_load((SPEC / "regles.yaml").read_text(encoding="utf-8"))
regle_list = [r["id"] for s in regles_y["sections"] for r in s["regles"]]
regle_ids = set(regle_list)

sys.path.insert(0, str(ROOT / "build"))
from rules import Rules  # noqa: E402

RULES = Rules(CAT)
ents = {e["entity_id"]: e for e in rd(CAT / "entities.csv")}
etype = {i: e["entity_type"] for i, e in ents.items()}
index = defaultdict(set)
for a in rd(CAT / "aliases.csv"):
    index[a["alias_norm"]].add(a["entity_id"])
sindex = defaultdict(set)
for k, v in index.items():
    sindex[" ".join(sorted(k.split()))] |= v
parent = defaultdict(set)
located = defaultdict(set)
fam_cats = defaultdict(set)
for r in rd(CAT / "relations.csv"):
    if r["predicate"] == "situe_dans":
        parent[r["subject_id"]].add(r["object_id"])
        located[r["object_id"]].add(r["subject_id"])
    if r["predicate"] == "famille_mecanova":
        fam_cats[r["object_id"]].add(r["subject_id"])
negatifs = {n["terme_norm"] for n in rd(CAT / "negatifs.csv")}

# ----------------------------------------------------------------- dimensions
dims = {d["id"]: d for d in g["dimensions"]}
cat_types = set(etype.values())
dim_types = {}
for d in g["dimensions"]:
    if "catalogue" in d:
        bad = set(d["catalogue"]) - cat_types
        if bad:
            err(f"dimension {d['id']} : types absents du catalogue {sorted(bad)}")
        dim_types[d["id"]] = set(d["catalogue"])
    elif "liste_metier" in d:
        if d["liste_metier"] not in g["listes_metier"]:
            err(f"dimension {d['id']} : liste métier inconnue")
        dim_types[d["id"]] = {d["liste_metier"]}
axes_temps = {a["id"] for a in g["axes_temporels"]}
periodes = {p["id"]: p for p in g["periodes"]}

# ----------------------------------------------------------------- mesures
mes_list = [m["id"] for m in mesures_y["mesures"]]
mes_ids = set(mes_list)
if len(mes_list) != len(mes_ids):
    err("mesures.yaml : identifiant de mesure en double")
if len(regle_list) != len(regle_ids):
    err("regles.yaml : identifiant de règle en double")
for m in mesures_y["mesures"]:
    if m["famille"] not in {f["famille"] for f in mesures_y["familles"]}:
        err(f"mesure {m['id']} : famille inconnue")
    if m["additivite"] not in mesures_y["additivite"]:
        err(f"mesure {m['id']} : additivité « {m['additivite']} » non définie")
    for ref in set(re.findall(r"\bM\d\d\b", m.get("formule", ""))) - mes_ids:
        err(f"mesure {m['id']} : la formule cite {ref}, inexistante")
for s_ in regles_y["sections"]:
    for r in s_["regles"]:
        if r["statut"] not in regles_y["statuts_implementation"]:
            err(f"{r['id']} : statut « {r['statut']} » inconnu")
        if r["composant"] not in regles_y["composants"]:
            err(f"{r['id']} : composant « {r['composant']} » inconnu")
        for f in r.get("implementation", []):
            if not (ROOT / f.split(" ")[0]).exists():
                err(f"{r['id']} : fichier d'implémentation {f} introuvable")
sys.path.insert(0, str(ROOT / "build"))
from build_docs import stale  # noqa: E402
for f in stale():
    err(f"vue lisible non à jour : {f} (lancer python build/build_docs.py)")
for m in mes_ids:
    if f"metier:mesure:{m}" not in ents:
        err(f"mesure {m} non compilée dans le catalogue : relancer build/build_glossary.py")

# ----------------------------------------------------------------- glossaire compilé = glossaire courant
for s in g["synonymes_metier"]:
    hits = index.get(normalize(s["terme"]), set())
    if not set(s["cibles"]) <= hits:
        err(f"synonyme « {s['terme']} » absent de l'index compilé (relancer la construction)")
    for c in s["cibles"]:
        if c not in ents:
            err(f"synonyme « {s['terme']} » → entité inexistante {c}")

# ----------------------------------------------------------------- collisions vocabulaire métier × catalogue
declared = {normalize(c["terme"]): set(c["entites"]) for c in g.get("collisions_connues", [])}
multi_syn = {normalize(s["terme"]) for s in g["synonymes_metier"] if len(s["cibles"]) > 1}
for k, v in index.items():
    metier = {i for i in v if i.startswith("metier:")}
    if metier and len(v) > 1 and k not in multi_syn:
        if k not in declared or v != declared[k]:
            err(f"collision non déclarée entre vocabulaire métier et catalogue : « {k} » → {sorted(v)}")
for k, v in declared.items():
    if index.get(k, set()) != v:
        err(f"collision déclarée « {k} » ne correspond plus au catalogue : {sorted(index.get(k, set()))}")
for t in g["termes_sans_filtre"]:
    hit = index.get(normalize(t["terme"]))
    if hit:
        notes.append(f"terme sans filtre « {t['terme']} » aussi alias de {sorted(hit)} : R-RES-08 tranche")
for n in negatifs & set(index):
    err(f"terme négatif « {n} » aussi présent dans le catalogue")
for v in g["valeurs_absentes"]:
    if normalize(v["terme"]) in index:
        err(f"valeur absente « {v['terme']} » présente dans le catalogue : {sorted(index[normalize(v['terme'])])}")


# ----------------------------------------------------------------- résolution simulée
CONTEXT = [("à l'agence de ", {"site"}, False), ("l'agence de ", {"site"}, False), ("agence de ", {"site"}, False),
           ("agence ", {"site"}, False), ("compatibles avec la ", {"modele_vehicule"}, True),
           ("compatible avec la ", {"modele_vehicule"}, True), ("compatibles avec ", {"modele_vehicule"}, True),
           ("au ", {"pays"}, True), ("aux ", {"pays"}, True), ("en ", {"pays"}, True), ("à ", {"ville", "site"}, True)]


def lookup(t):
    n = normalize(t)
    return set(index.get(n, set())) | set(sindex.get(" ".join(sorted(n.split())), set()))


def resolve(text, fuzzy_types=None):
    ctx, core = None, text
    for prefix, d, strip in CONTEXT:
        if text.lower().startswith(prefix):
            ctx, core = d, (text[len(prefix):] if strip else text)
            break
    hits = {h for h in lookup(core) if not h.startswith("metier:mesure:")}
    if not hits and normalize(core) in negatifs:
        return "absent", set()
    if not hits and fuzzy_types and len(normalize(core)) >= 4 and not re.search(r"\d", core):
        keys = [k for k, v in index.items() if any(etype[i] in fuzzy_types for i in v)]
        res = process.extract(normalize(core), keys, scorer=JaroWinkler.normalized_similarity, limit=3, score_cutoff=0.88)
        if res and (len(res) == 1 or res[0][1] - res[1][1] >= 0.03):
            hits = {i for i in index[res[0][0]] if etype[i] in fuzzy_types}
    # R-GEO-02, R-CTX-05, R-ART-03, R-RES-09 : mêmes règles que la vérité terrain (build/rules.py)
    allowed = None
    if ctx:
        allowed = {"pays"} if ctx == {"pays"} else set().union(*(dim_types[d] for d in ctx))
    hits = RULES.apply(hits, allowed)
    return ("resolved" if len(hits) == 1 else "ambiguous" if hits else "unknown"), hits


# ----------------------------------------------------------------- questions
used_types = Counter()
for qq in q["questions"]:
    qid = qq["id"]
    used_types[qq["type"]] += 1
    if qq["type"] not in types_q:
        err(f"{qid} : type inconnu")
    for ref in re.findall(r"R-[A-Z]+-\d\d", " ".join(qq.get("pieges", []))):
        if ref not in regle_ids:
            err(f"{qid} : règle {ref} inexistante")
    clar = {normalize(k): set(v) for k, v in (qq.get("clarification_attendue") or {}).items()}
    for t in qq["termes"]:
        text, exp = str(t["texte"]), t["attendu"]
        kind, _, val = exp.partition(":")
        if kind == "mesure":
            if normalize(text) in ("combien vendu",):
                continue
            if f"metier:mesure:{val}" not in lookup(text):
                err(f"{qid} : « {text} » ne mène pas à la mesure {val}")
        elif kind == "entite":
            if val not in ents:
                err(f"{qid} : entité attendue inexistante {val}")
                continue
            st, hits = resolve(text, fuzzy_types={etype[val]})
            if hits != {val}:
                err(f"{qid} : « {text} » → {st} {sorted(hits)}, attendu {val}")
        elif exp == "ambigu":
            st, hits = resolve(text)
            key = next((k for k in clar if normalize(text).endswith(k)), None)
            if key is None:
                err(f"{qid} : pas de clarification_attendue pour « {text} »")
            elif st != "ambiguous" or hits != clar[key]:
                err(f"{qid} : « {text} » → {st} {sorted(hits)}, attendu ambigu {sorted(clar[key])}")
        elif kind == "absent":
            st, _ = resolve(text)
            if st != "absent":
                err(f"{qid} : « {text} » n'est pas dans l'index négatif")
        elif kind == "axe":
            if val not in dims and val not in axes_temps:
                err(f"{qid} : axe inconnu {val}")
        elif kind == "periode":
            if val not in periodes:
                err(f"{qid} : période inconnue {val}")
        elif kind == "hors_perimetre":
            if val not in {h["sujet"] for h in g["hors_perimetre"]}:
                err(f"{qid} : sujet hors périmètre inconnu {val}")
        elif exp == "sans_filtre":
            if normalize(text) not in {normalize(x["terme"]) for x in g["termes_sans_filtre"]}:
                err(f"{qid} : « {text} » n'est pas un terme sans filtre")
        elif kind not in ("comparaison", "profil", "seuil"):
            err(f"{qid} : référence attendue inconnue {exp}")
    st = qq["statut_attendu"]
    if st == "resolved":
        m = qq["manifest_attendu"]
        for mid in m["mesures"]:
            if mid not in mes_ids:
                err(f"{qid} : mesure {mid} inconnue")
        fd = [f["dimension"] for f in m["filtres"]]
        if fd != sorted(fd):
            err(f"{qid} : filtres non triés")
        for f in m["filtres"]:
            d = f["dimension"]
            if d not in dims:
                err(f"{qid} : dimension {d} inconnue")
                continue
            if f["valeurs"] != sorted(f["valeurs"]):
                err(f"{qid} : valeurs non triées pour {d}")
            for v in f["valeurs"]:
                if v not in ents:
                    err(f"{qid} : valeur {v} inexistante")
                elif etype[v] not in dim_types[d]:
                    err(f"{qid} : {v} est un {etype[v]}, pas une valeur de {d}")
        for a in m["axes"]:
            if a not in dims and a not in axes_temps:
                err(f"{qid} : axe {a} inconnu")
        if "tri" in m and m["tri"]["mesure"] not in m["mesures"]:
            err(f"{qid} : tri sur une mesure absente")
        for t in qq["termes"]:
            pid = t["attendu"].partition(":")[2] if t["attendu"].startswith("periode:") else None
            p = periodes.get(pid or "", {})
            if p.get("debut") and m["periode"].get("debut") and (str(p["debut"]), str(p["fin"])) != (str(m["periode"]["debut"]), str(m["periode"]["fin"])):
                err(f"{qid} : période du Manifest incohérente avec {pid}")
    elif st == "ambiguous" and not qq.get("clarification_attendue"):
        err(f"{qid} : ambiguous sans clarification_attendue")
    elif st in ("unknown", "out_of_scope") and "manifest_attendu" in qq:
        err(f"{qid} : {st} ne doit pas avoir de Manifest")

for f in ("glossaire.yaml", "mesures.yaml", "types.yaml", "domaine.md", "personas.md", "manifest_schema.yaml"):
    for ref in set(re.findall(r"R-[A-Z]+-\d\d", (SPEC / f).read_text(encoding="utf-8"))):
        if ref not in regle_ids:
            err(f"{f} : règle {ref} inexistante")

print(f"Catalogue : {len(ents)} entités, {sum(len(v) for v in index.values())} liens alias→entité")
print(f"Glossaire : {len(mes_ids)} mesures, {len(dims)} dimensions, {sum(len(v) for v in g['listes_metier'].values())} valeurs métier, "
      f"{len(g['synonymes_metier'])} synonymes d'atelier, {len(negatifs)} termes négatifs")
print(f"Règles : {len(regle_ids)} · questions : {len(q['questions'])} · statuts : {dict(Counter(x['statut_attendu'] for x in q['questions']))}")
missing = sorted(types_q - set(used_types))
if missing:
    print("AVERTISSEMENT types sans question :", missing)
for n in notes:
    print("NOTE", n)
for e in errors:
    print("ERREUR", e)
print("OK : spec v2 cohérente avec le catalogue" if not errors else f"{len(errors)} erreur(s)")
sys.exit(1 if errors else 0)
