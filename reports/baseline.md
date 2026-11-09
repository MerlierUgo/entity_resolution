# Mesure de référence sur le jeu de défis

Trois résolveurs volontairement simples (voir `build/baseline.py`). En % des cas de chaque catégorie :
- **idéal** : la réponse attendue exactement ;
- **sûr** : idéal, ou une réponse prudente acceptée (unknown face à une faute, ambiguous incluant la bonne entité) ;
- **silencieux** : une entité résolue qui n'est pas la bonne. C'est l'erreur à ramener à zéro.

| Catégorie | Cas | B0_exact idéal | sûr | silencieux | B1_fuzzy_naif idéal | sûr | silencieux | B2_fuzzy_borne idéal | sûr | silencieux |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C01_libelle_canonique | 416 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C02_traduction_officielle | 485 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C03_variante_geonames | 499 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C04_terme_metier | 98 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C05_homonyme | 700 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C06_indice_de_type | 844 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C07_faute_de_frappe | 2738 | 0.0 | 100.0 | 0.0 | 91.1 | 91.6 | 0.8 | 88.7 | 94.5 | 0.0 |
| C08_hors_perimetre_proche | 594 | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 99.5 | 0.8 | 0.8 | 43.8 |
| C09_code | 1097 | 100.0 | 100.0 | 0.0 | 59.1 | 59.1 | 40.9 | 100.0 | 100.0 | 0.0 |
| C10_client | 1149 | 83.6 | 100.0 | 0.0 | 97.5 | 97.5 | 0.1 | 98.2 | 98.4 | 0.0 |
| C11_marque | 176 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C12_vehicule | 789 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 | 100.0 | 0.0 |
| C13_abreviation | 500 | 0.2 | 100.0 | 0.0 | 74.2 | 94.4 | 3.6 | 71.2 | 91.8 | 2.0 |
| TOTAL | 10085 | 66.0 | 100.0 | 0.0 | 85.7 | 86.8 | 10.7 | 89.4 | 92.1 | 2.7 |
