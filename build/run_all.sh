#!/usr/bin/env bash
# Reconstruit tout le catalogue et le jeu de défis depuis les sources ouvertes.
set -euo pipefail
cd "$(dirname "$0")"
pip install -q pycountry==26.2.16 geonamescache==3.0.2 rapidfuzz faker==40.44.0 pyyaml pytest 2>/dev/null \
  || pip install -q --break-system-packages pycountry==26.2.16 geonamescache==3.0.2 rapidfuzz faker==40.44.0 pyyaml pytest
bash fetch_sources.sh
python3 build_open.py        # couche 1 : référentiels ouverts
python3 build_mecanova.py    # couche 2 : compléments Mécanova (graine fixe)
python3 build_docs.py        # vues lisibles générées depuis les YAML
python3 build_glossary.py    # couche 3 : glossaire métier v2 compilé dans le catalogue
python3 build_merge.py       # fusion et contrôles d'intégrité
python3 build_challenges.py  # jeu de défis
python3 baseline.py          # mesure de référence
python3 human_questions.py check  # questions humaines : texte inchangé, références valides
python3 ../spec/check_spec.py  # cohérence spec v2 × catalogue
