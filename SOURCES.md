# Sources et licences

Toutes les sources sont téléchargées par `build/fetch_sources.sh`, avec empreintes SHA-256 dans `sources/SHA256SUMS`. Les textes de licence fournis par les sources sont dans `sources/`.

| Couche | Source | Version | Licence | Attribution requise |
|---|---|---|---|---|
| Pays, régions, provinces, cantons | ISO 3166-1 et 3166-2 avec traductions iso-codes, via [pycountry](https://pypi.org/project/pycountry/) | 26.2.16 | LGPL-2.1 (données iso-codes) | non |
| Communes, arrondissements, provinces et régions belges (FR, NL) | Statbel, découpage communal 2020, republié par [vandenbroucke/belgian_municipalities](https://github.com/vandenbroucke/belgian_municipalities) | 2020 | Données ouvertes Statbel ; **le dépôt n'a pas de licence explicite** | Statbel |
| Localités postales belges | Liste bpost, republiée par [spatie/belgian-cities-geocoded](https://github.com/spatie/belgian-cities-geocoded) | 2015, mise à jour ultérieurement | MIT | non |
| Villes France (Hauts-de-France, Grand Est), Pays-Bas (Limbourg, Brabant-Septentrional), Luxembourg ; variantes de noms ; lieux hors périmètre | [GeoNames](https://www.geonames.org) `cities500`, via [geonamescache](https://pypi.org/project/geonamescache/) | 3.0.2 | CC BY 4.0 | **oui** : « Données géographiques : GeoNames (geonames.org), CC BY 4.0 » |
| Taxonomie des pièces, en EN, FR, NL, DE | [Shopify Standard Product Taxonomy](https://github.com/Shopify/product-taxonomy) | commit `5b79b5f` | MIT | non |
| Marques et modèles de véhicules | [openvehicle-data](https://github.com/mirkobechini/openvehicle-data), d'après EEA (surveillance CO2 2025, Italie), Wikidata et RDW | 0.3.0, empreintes vérifiées | CC BY 4.0 | **oui** : « openvehicle-data (M. Bechini), d'après l'Agence européenne pour l'environnement, CC BY 4.0 » |
| Codes douaniers (Système harmonisé, en anglais) | [datasets/harmonized-system](https://github.com/datasets/harmonized-system), d'après UN Comtrade | branche main | ODC-PDDL-1.0 | non |
| Couche Mécanova (clients, articles, sites, marques de pièces, formes juridiques, rattachements) | Générée (graine 20261102) ou curée à la main | — | CC0 (données synthétiques) | non |

## Points d'attention

- Les marques de pièces (Bosch, Brembo, Valeo…) et de véhicules sont de vraies marques, utilisées pour identifier des produits. **Les articles, clients et chiffres de Mécanova sont fictifs** et ne disent rien de ces marques.
- Les noms de clients sont générés (bibliothèque Faker) : toute ressemblance avec une entreprise existante est fortuite.
- Pour un usage au-delà du POC, remplacer la republication Statbel par le fichier officiel et vérifier la curation des groupes industriels, qui évolue avec les rachats.
