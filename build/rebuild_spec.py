"""
Relance tout ce qui dépend de la spec et des questions humaines, sans retélécharger les sources.
À utiliser après une modification de spec/*.yaml, human/*.yaml ou human/questions.csv.

    python build/rebuild_spec.py            reconstruit puis contrôle
    python build/rebuild_spec.py --rapide   contrôle seulement (aucune reconstruction)

Fonctionne sous Windows, macOS et Linux. Le catalogue ouvert (catalog/open_*.csv, mecanova_*.csv)
n'est pas reconstruit : il ne dépend pas de la spec. Pour tout reconstruire depuis les sources
ouvertes, utiliser build/run_all.sh (bash et accès réseau requis).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = [
    ("vues lisibles (.md) depuis les YAML", ["build/build_docs.py"]),
    ("vocabulaire métier compilé dans le catalogue", ["build/build_glossary.py"]),
    ("fusion du catalogue", ["build/build_merge.py"]),
    ("banc d'essai", ["build/build_challenges.py"]),
    ("mesure de référence", ["build/baseline.py"]),
]
CHECKS = [
    ("cohérence de la spec", ["spec/check_spec.py"]),
    ("questions humaines et réponses attendues", ["build/human_questions.py", "check"]),
    ("tests unitaires", ["-m", "pytest", "-q", "tests"]),
]


def run(label: str, args: list[str]) -> bool:
    print(f"\n── {label}")
    r = subprocess.run([sys.executable, *args], cwd=ROOT)
    return r.returncode == 0


def main() -> int:
    steps = CHECKS if "--rapide" in sys.argv else BUILD + CHECKS
    failed = []
    for label, args in steps:
        if not run(label, args):
            failed.append(label)
            if (label, args) in BUILD:
                break  # inutile de continuer sur un catalogue incomplet
    print("\n" + ("OK · tout est à jour et cohérent" if not failed else "ÉCHEC · " + ", ".join(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
