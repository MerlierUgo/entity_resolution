# Moteur · étape 2 (Jaro-Winkler borné, seuil fixe 0.88, écart 0.03) · partition dev

Généré par `python -m engine.evaluation --fuzzy fixe`. Alias chargés : tiers 1, 2, 3. En % des cas de chaque catégorie.

| Catégorie | Cas | Idéal | Sûr | Silencieux | Détail des non idéaux |
|---|---:|---:|---:|---:|---|
| C01_libelle_canonique | 299 | 100.0 | 100.0 | 0.0 | · |
| C02_traduction_officielle | 345 | 100.0 | 100.0 | 0.0 | · |
| C03_variante_geonames | 349 | 100.0 | 100.0 | 0.0 | · |
| C04_terme_metier | 63 | 100.0 | 100.0 | 0.0 | · |
| C05_homonyme | 491 | 100.0 | 100.0 | 0.0 | · |
| C06_indice_de_type | 598 | 100.0 | 100.0 | 0.0 | · |
| C07_faute_de_frappe | 1932 | 83.1 | 95.0 | 0.0 | acceptable 194, incorrect 91, partiel 37, trop_confiant 5 |
| C08_hors_perimetre_proche | 436 | 100.0 | 100.0 | 0.0 | · |
| C09_code | 791 | 100.0 | 100.0 | 0.0 | · |
| C10_client | 822 | 83.1 | 100.0 | 0.0 | acceptable 139 |
| C11_marque | 127 | 100.0 | 100.0 | 0.0 | · |
| C12_vehicule | 551 | 100.0 | 100.0 | 0.0 | · |
| C13_abreviation | 354 | 0.3 | 100.0 | 0.0 | acceptable 353 |
| **TOTAL** | 7158 | 88.6 | 98.7 | 0.0 | acceptable 686, incorrect 91, partiel 37, trop_confiant 5 |

## Erreurs silencieuses : 0


## Réponses ni idéales ni sûres (catégorie, note, étape décisive)

- C07_faute_de_frappe · incorrect · approche : 91
- C07_faute_de_frappe · trop_confiant · approche : 5
