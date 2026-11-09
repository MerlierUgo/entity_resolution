#!/usr/bin/env bash
# Télécharge les sources ouvertes dans raw/ et enregistre leurs empreintes SHA-256.
# Toutes les sources passent par GitHub ou PyPI : aucune autre dépendance réseau.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p raw/shopify raw/ovd_rel raw/gnc
GH=https://raw.githubusercontent.com

# 1. Géographie
pip download geonamescache==3.0.2 --no-deps -d raw/pip -q
unzip -o -q raw/pip/geonamescache-3.0.2-py3-none-any.whl 'geonamescache/data/cities500.json' \
  'geonamescache-3.0.2.dist-info/licenses/LICENSE' -d raw/gnc
curl -sSfL -o raw/be_municipalities_2020.json "$GH/vandenbroucke/belgian_municipalities/master/data/2020/root.json"
curl -sSfL -o raw/be_postcodes.csv "$GH/spatie/belgian-cities-geocoded/master/belgian-cities-geocoded.csv"
curl -sSfL -o raw/be_postcodes_LICENSE.md "$GH/spatie/belgian-cities-geocoded/master/LICENSE.md"
pip install -q pycountry==26.2.16 geonamescache==3.0.2 2>/dev/null || pip install -q --break-system-packages pycountry==26.2.16

# 2. Taxonomie des pièces (4 langues)
SHOPIFY_SHA=$(git ls-remote https://github.com/Shopify/product-taxonomy.git HEAD | cut -f1)
echo "$SHOPIFY_SHA" > raw/shopify/COMMIT
for loc in en fr nl de; do
  curl -sSfL -o "raw/shopify/${loc}_categories.txt" "$GH/Shopify/product-taxonomy/$SHOPIFY_SHA/dist/$loc/categories.txt"
done
curl -sSfL -o raw/shopify/LICENSE "$GH/Shopify/product-taxonomy/$SHOPIFY_SHA/LICENSE"

# 3. Véhicules (EEA via openvehicle-data, CC BY 4.0), empreintes vérifiées contre le manifeste
REL=https://github.com/mirkobechini/openvehicle-data/releases/download/data-v0.3.0
for f in manifest.json brands.csv models.csv NOTICE LICENSE-DATA; do curl -sSfL -o "raw/ovd_rel/$f" "$REL/$f"; done
python3 - <<'PY'
import hashlib, json
m = json.load(open("raw/ovd_rel/manifest.json"))["files"]
for f in ["brands.csv", "models.csv", "NOTICE", "LICENSE-DATA"]:
    assert hashlib.sha256(open(f"raw/ovd_rel/{f}", "rb").read()).hexdigest() == m[f], f
print("openvehicle-data : empreintes conformes au manifeste")
PY

# 4. Nomenclature douanière (Système harmonisé, ODC-PDDL)
curl -sSfL -o raw/hs.csv "$GH/datasets/harmonized-system/main/data/harmonized-system.csv"

find raw -type f ! -name SHA256SUMS ! -path 'raw/pip/*' | sort | xargs sha256sum > raw/SHA256SUMS
echo "Sources téléchargées : $(wc -l < raw/SHA256SUMS) fichiers"
