# Étape approchée · comparaison A, B, C · dev, part eval

Généré par `python -m engine.comparaison`. 2133 cas (30 % de dev, hash du case_id), jamais vus par la calibration.

- **A** : étape 1 seule (exact)
- **B** : SeuilFixe(0.88, 0.03)
- **C** : SeuilsCalibres (SGR, r* = 0.05, δ = 0.05)

| Catégorie | Cas | A idéal | A sûr | A silencieux | B idéal | B sûr | B silencieux | C idéal | C sûr | C silencieux |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C01_libelle_canonique | 83 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C02_traduction_officielle | 120 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C03_variante_geonames | 105 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C04_terme_metier | 20 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C05_homonyme | 148 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C06_indice_de_type | 196 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C07_faute_de_frappe | 554 | 0.0 | 100.0 | 0.0 | 84.5 | 95.7 | 0.0 | 44.2 | 98.9 | 0.0 |
| C08_hors_perimetre_proche | 136 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C09_code | 237 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C10_client | 237 | 83.1 | 100.0 | 0.0 | 83.1 | 100.0 | 0.0 | 83.1 | 100.0 | 0.0 |
| C11_marque | 40 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C12_vehicule | 167 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C13_abreviation | 90 | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 100.0 | 0.0 |
| **TOTAL** | 2133 | 67.9 | 100.0 | 0.0 | 89.9 | 98.9 | 0.0 | 79.4 | 99.7 | 0.0 |

## Robustesse : termes de l'index négatif passés à l'approché

- B : 47 erreurs silencieuses sur 139 termes
- C : 34 erreurs silencieuses sur 139 termes

## Risque-couverture par type (seuil 0,88 et seuil calibré)

Perte « dangereuse », celle de la calibration. La courbe complète, avec la perte « non_sure », est dans fuzzy_dev.json.

| Type | Cas | Couverture à 0,88 | Risque à 0,88 | Seuil C | Couverture C | Risque C |
|---|---:|---:|---:|---:|---:|---:|
| ville | 342 | 74.6 % | 0.0 % | 0.8596 | 74.6 % | 0.0 % |
| localite_postale | 92 | 77.2 % | 0.0 % | désactivé | 0 % | · |
| commune | 57 | 82.5 % | 2.1 % | désactivé | 0 % | · |
| categorie_piece | 49 | 91.8 % | 0.0 % | désactivé | 0 % | · |
| mixte | 41 | 90.2 % | 0.0 % | désactivé | 0 % | · |
| modele_vehicule | 38 | 79.0 % | 0.0 % | désactivé | 0 % | · |
