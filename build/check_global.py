"""
Contrôle global du livrable v1.4 : reconstruit tout (sans retélécharger les sources), vérifie le
déterminisme, l'intégrité croisée de chaque fichier, puis écrit reports/check_global.md.
Code de sortie 0 si aucun contrôle bloquant n'échoue.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from common import CAT, CHAL, REP, ROOT, console_utf8, env_utf8, read_csv

console_utf8()

STEPS = ["build_open.py", "build_mecanova.py", "build_docs.py", "build_glossary.py", "build_merge.py", "build_challenges.py",
         "baseline.py"]
OUTPUTS = sorted(list(CAT.glob("*.csv")) + list(CHAL.glob("*.csv"))
                 + [ROOT / "spec" / "mesures.md", ROOT / "spec" / "regles.md", ROOT / "human" / "LACUNES.md"])
results: list[tuple[str, bool, str]] = []


def run_all():
    for s in STEPS:
        r = subprocess.run([sys.executable, s], cwd=ROOT / "build", capture_output=True, text=True, encoding="utf-8", env=env_utf8())
        if r.returncode:
            raise SystemExit(f"échec de {s} :\n{r.stderr[-2000:]}")


def digest():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUTPUTS}


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


run_all()
h1 = digest()
run_all()
h2 = digest()
check("Déterminisme : deux reconstructions identiques", h1 == h2, f"{len(h1)} fichiers comparés")

spec = subprocess.run([sys.executable, "spec/check_spec.py"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env_utf8())
check("Spec v2 cohérente avec le catalogue (34 questions)", spec.returncode == 0, spec.stdout.strip().splitlines()[-1])

ents = read_csv(CAT / "entities.csv")
ids = {e["entity_id"] for e in ents}
aliases = read_csv(CAT / "aliases.csv")
rels = read_csv(CAT / "relations.csv")
with_alias = {a["entity_id"] for a in aliases}
check("Chaque entité a au moins un alias", ids <= with_alias, f"{len(ids - with_alias)} sans alias")
check("Chaque entité et chaque alias porte une source et une licence",
      all(e["source"] and e["licence"] for e in ents) and all(a["source"] and a["licence"] for a in aliases))
check("Relations sans extrémité orpheline", all(r["subject_id"] in ids and r["object_id"] in ids for r in rels),
      f"{len(rels)} relations")
cases = read_csv(CHAL / "cases.csv")
bad = [c["case_id"] for c in cases for i in filter(None, c["expected_ids"].split("|")) if i not in ids]
check("Jeu de défis : entités attendues existantes", not bad, f"{len(cases)} cas")
split = {s["case_id"]: s["split"] for s in read_csv(CHAL / "split.csv")}
check("Jeu de défis : chaque cas a une partition dev/test", set(split) == {c["case_id"] for c in cases},
      f"test : {sum(v == 'test' for v in split.values())}")
core = read_csv(CHAL / "cases_core.csv")
check("Jeu « core » : toutes les catégories représentées",
      {c["category"] for c in core} == {c["category"] for c in cases}, f"{len(core)} cas")
hq = subprocess.run([sys.executable, "build/human_questions.py", "check"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env_utf8())
check("Questions humaines : texte inchangé, références valides (human/questions.csv)", hq.returncode == 0,
      hq.stdout.strip().splitlines()[-1])
tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env_utf8())
check("Tests unitaires", tests.returncode == 0, (tests.stdout.strip().splitlines() or ["pytest absent"])[-1])
sys.path.insert(0, str(ROOT / "build"))
from human_questions import read_questions  # noqa: E402
human = [h for h in read_questions() if h["etat"] == "active"]
base = json.loads((REP / "baseline.json").read_text(encoding="utf-8"))
check("Mesure de référence calculée", "B2_fuzzy_borne" in base,
      f"B2 erreurs silencieuses : {base['B2_fuzzy_borne']['TOTAL'].get('erreur_silencieuse', 0)}")
licences = {p.name for p in (ROOT / "sources").iterdir()}
check("Textes de licence des sources présents", {"geonamescache_LICENSE.txt", "openvehicle-data_NOTICE.txt",
      "shopify-product-taxonomy_LICENSE.txt", "spatie-belgian-cities_LICENSE.md"} <= licences)

# Préparation du POC : ce qui existe, ce qui manque (non bloquant)
readiness = [
    ("Knowledge catalog (référentiels, alias, relations, provenance)", True, f"{len(ents)} entités, {len(aliases)} alias"),
    ("Glossaire métier v2 compilé et contrôlé", True, "26 mesures, 54 règles"),
    ("Règles de résolution partagées (build/rules.py)", True, "vérité terrain = spec"),
    ("Index négatif", True, f"{len(read_csv(CAT / 'negatifs.csv'))} termes"),
    ("Jeu de défis généré avec partition dev/test", True, f"{len(cases)} cas"),
    ("Questions humaines", len(human) >= 100, f"{len(human)} / 100 visées, {len({h['auteur'] for h in human})} auteur(s), "
     f"{sum(not h['validation'] for h in human)} étiquetages à valider"),
    ("Questions écrites par quelqu'un qui ne connaît pas le catalogue", False, "aucune pour l'instant"),
    ("Données de faits (ventes, retours, commandes, stock) et oracle DuckDB", False,
     "non générés : nécessaires pour vérifier les chiffres, pas pour l'entity resolution"),
    ("Semantic model Power BI et templates DAX", False, "étape suivante de la roadmap"),
    ("Schéma du Manifest v0.1 (YAML) + validation, forme canonique, empreinte", True, "spec/manifest_schema.yaml, build/manifest.py"),
    ("Réponses attendues des questions humaines", False, "human/attendus.yaml : à écrire par l'auteur"),
]

lines = ["# Contrôle global · v1.4", "", "## Contrôles automatiques", "", "| Contrôle | Résultat | Détail |", "|---|---|---|"]
lines += [f"| {n} | {'OK' if ok else 'ÉCHEC'} | {d} |" for n, ok, d in results]
lines += ["", "## Préparation du POC", "", "| Élément | Prêt | Détail |", "|---|---|---|"]
lines += [f"| {n} | {'oui' if ok else 'non'} | {d} |" for n, ok, d in readiness]
(REP / "check_global.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
