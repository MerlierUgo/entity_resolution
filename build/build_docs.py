"""
Génère les vues lisibles (Markdown) à partir des sources YAML lues par le code.

  spec/mesures.yaml   → spec/mesures.md
  spec/regles.yaml    → spec/regles.md
  human/lacunes.yaml  → human/LACUNES.md

Les .md générés ne se modifient jamais à la main : on modifie le YAML, puis on relance ce script.
  python build/build_docs.py           régénère les vues
  python build/build_docs.py --check   code de sortie 1 si une vue n'est pas à jour
"""
from __future__ import annotations

import sys
from collections import Counter

from common import ROOT, SPEC, console_utf8, load_yaml

BANNER = ("<!-- Fichier généré par build/build_docs.py depuis {src} : ne pas modifier à la main. "
          "Modifier le YAML, puis relancer le script. -->\n\n")


def render_mesures(d: dict) -> str:
    out = [BANNER.format(src="spec/mesures.yaml"), "# Mesures", "",
           f"> Version {d['version']} · statut : {d['statut']} · source : `spec/mesures.yaml`", ">",
           "> Chaque mesure est définie sans ambiguïté, à partir des colonnes des tables de faits. Ces définitions font "
           "foi pour les mesures DAX du semantic model, les requêtes de l'oracle et les tests.", "",
           "## Conventions", ""]
    out += [f"- {c}" for c in d["conventions"]]
    out += ["", "## Colonnes utilisées", "", "| Table | Colonnes |", "|---|---|"]
    out += [f"| `{t['table']}` | {', '.join(f'`{c}`' for c in t['colonnes'])} |" for t in d["tables"]]
    out += ["", f"Identité garantie par le générateur : {d['identite_generateur']}", "", "## Additivité", ""]
    out += [f"- **{k}** : {v}" for k, v in d["additivite"].items()]
    for fam in d["familles"]:
        out += ["", f"## {fam['titre']}", ""]
        if fam.get("note"):
            out += [fam["note"], ""]
        for m in [m for m in d["mesures"] if m["famille"] == fam["famille"]]:
            out += [f"### {m['id']} · {m['libelle']}", ""]
            if m.get("formule"):
                out.append(f"`{m['formule']}`")
                out.append("")
            if m.get("description"):
                out += [m["description"], ""]
            meta = [f"**Unité** : {m['unite']}", f"**Additivité** : {m['additivite']}"]
            if m.get("defaut_pour"):
                meta.append("**Par défaut pour** : " + ", ".join(f"« {x} »" for x in m["defaut_pour"]))
            out += [" · ".join(meta), "", "**Alias** : " + ", ".join(m["alias"]), ""]
    out += ["", "## Récapitulatif", "", "| ID | Mesure | Unité | Additivité | Par défaut pour |", "|---|---|---|---|---|"]
    out += [f"| {m['id']} | {m['libelle']} | {m['unite']} | {m['additivite']} | "
            f"{', '.join(f'« {x} »' for x in m.get('defaut_pour', []))} |" for m in d["mesures"]]
    return "\n".join(out).rstrip() + "\n"


STATUT_LABEL = {"codee": "codée", "prototypee": "prototypée", "a_coder": "à coder"}
STATUT_PLURIEL = {"codee": "codées", "prototypee": "prototypées", "a_coder": "à coder"}


def render_regles(d: dict) -> str:
    regles = [r for s in d["sections"] for r in s["regles"]]
    cnt = Counter(r["statut"] for r in regles)
    out = [BANNER.format(src="spec/regles.yaml"), "# Règles de gestion", "",
           f"> Version {d['version']} · statut : {d['statut']} · `data_as_of` = **{d['data_as_of']}** · "
           "source : `spec/regles.yaml`", ">", f"> {d['intro']}", "",
           f"**État d'implémentation** : {len(regles)} règles · "
           + " · ".join(f"{cnt.get(k, 0)} {STATUT_PLURIEL[k]}" for k in STATUT_LABEL), ""]
    for s in d["sections"]:
        out += [f"## {s['section']}", ""]
        if s.get("intro"):
            out += [s["intro"], ""]
        for r in s["regles"]:
            texte = r["texte"]
            block = texte.startswith(("|", "-", "1."))
            out.append(f"**{r['id']} · {r['titre']}.**" + ("" if block else f" {texte}"))
            if block:
                out += ["", texte]
            impl = f"*{STATUT_LABEL[r['statut']]} · {r['composant']}*"
            if r.get("implementation"):
                impl += " · " + ", ".join(f"`{x}`" for x in r["implementation"])
            out += ["", impl, ""]
    return "\n".join(out).rstrip() + "\n"


def render_lacunes(d: dict) -> str:
    out = [BANNER.format(src="human/lacunes.yaml"), "# Lacunes de la spec révélées par les questions humaines", "",
           d["intro"], "", "| Code | Lacune | Questions | Piste de correction |", "|---|---|---|---|"]
    out += [f"| {x['id']} | {x['lacune']} | {', '.join(x['questions'])} | {x['piste']} |" for x in d["lacunes"]]
    out += ["", "## Attention avant de corriger", "", d["attention"]]
    return "\n".join(out).rstrip() + "\n"


VIEWS = [
    (SPEC / "mesures.yaml", SPEC / "mesures.md", render_mesures),
    (SPEC / "regles.yaml", SPEC / "regles.md", render_regles),
    (ROOT / "human" / "lacunes.yaml", ROOT / "human" / "LACUNES.md", render_lacunes),
]


def stale() -> list[str]:
    return [dst.relative_to(ROOT).as_posix() for src, dst, fn in VIEWS
            if not dst.exists() or dst.read_text(encoding="utf-8") != fn(load_yaml(src))]


def main(argv) -> int:
    console_utf8()
    if "--check" in argv:
        s = stale()
        for f in s:
            print(f"vue non à jour : {f} (lancer python build/build_docs.py)")
        return 1 if s else 0
    for src, dst, fn in VIEWS:
        dst.write_text(fn(load_yaml(src)), encoding="utf-8")
        print(f"{dst.relative_to(ROOT).as_posix()} ← {src.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
