# Knowledge catalog Mécanova · v1.4 (glossaire métier v2, questions humaines)

Knowledge catalog construit à partir de **sources ouvertes** et complété par des données générées, pour tester un moteur d'entity resolution déterministe. Contexte : Mécanova SA, distributeur fictif de pièces automobiles en Belgique, France, Luxembourg et Pays-Bas.

La **spec métier v2** (dossier `spec/`) fait partie du livrable : glossaire, mesures, règles, personas, types et questions, alignés sur ce catalogue et contrôlés automatiquement.

## Ce que contient le catalogue

| | |
|---|---|
| Entités | **13 348**, de 28 types |
| Alias | **36 077**, dont 13 461 officiels (tier 1), 6 992 de référence ouverte (tier 2) et 15 624 générés, curés ou issus du glossaire (tier 3) |
| Relations | **31 827** (situé dans, sous-catégorie de, modèle de, fabriqué par, compatible avec, remplacé par, rattaché à, suivi par…) |
| Langues | français, néerlandais, allemand, anglais, plus les variantes GeoNames |
| Formes ambiguës | 1 731 formes normalisées partagées par plusieurs entités, dont 740 entre types différents |
| Index négatif | 22 743 termes plausibles mais absents (lieux hors périmètre, pays non servis, marques absentes) |
| Jeu de défis | **10 078 cas** avec vérité terrain, 13 catégories, partition dev / test figée |

| Domaine | Entités | Source |
|---|---|---|
| Géographie | 4 pays, 5 régions, 12 provinces, 12 cantons, 43 arrondissements, 816 communes (BE, LU), 3 804 villes (FR, NL), 2 782 localités postales belges | ISO 3166, Statbel, bpost, GeoNames |
| Pièces | 252 catégories en 4 langues, 13 familles Mécanova, 280 codes douaniers | Shopify Product Taxonomy, Système harmonisé |
| Véhicules | 84 marques, 1 179 modèles | EEA via openvehicle-data |
| Mécanova (généré) | 2 520 articles, 1 400 clients, 38 marques de pièces, 22 groupes industriels, 11 formes juridiques, 10 sites, 10 commerciaux | graine fixe et curation |
| Métier (glossaire v2) | 26 mesures, 14 valeurs métier (segments, canaux, motifs de retour), 30 synonymes d'atelier | `spec/glossaire.yaml`, compilé |

## YAML pour le code, Markdown pour la lecture

Tout ce que le code lit est en **YAML** (ou CSV pour les données) : c'est la source unique, la seule qu'on modifie. Les **Markdown** servent à la lecture ; ils sont de deux sortes :

| Markdown | Nature | Se modifie |
|---|---|---|
| `spec/mesures.md`, `spec/regles.md`, `human/LACUNES.md` | **vues générées** depuis `mesures.yaml`, `regles.yaml`, `lacunes.yaml` | jamais : modifier le YAML puis lancer `python build/build_docs.py` |
| `spec/personas.md`, `spec/domaine.md`, les `README.md` | **textes de contexte**, qu'aucun code ne lit | à la main |

`spec/check_spec.py` échoue si une vue générée n'est plus à jour.

| Source YAML | Lue par |
|---|---|
| `spec/mesures.yaml` | compilation du catalogue (alias des mesures), validation du Manifest et des questions, futurs templates DAX |
| `spec/regles.yaml` | contrôle des références de règles ; registre de l'état d'implémentation (codée, prototypée, à coder) |
| `spec/glossaire.yaml` | compilation du catalogue (dimensions, listes métier, synonymes, index négatif) |
| `spec/types.yaml`, `spec/questions.yaml` | `check_spec.py` |
| `spec/manifest_schema.yaml` | validation du Manifest (`build/manifest.py`) |
| `human/attendus.yaml`, `human/lacunes.yaml` | contrôle des questions humaines |

## Organisation

```
human/                      questions écrites à la main (questions.csv, texte verrouillé par questions.lock),
                            réponses attendues (attendus.yaml), lacunes (lacunes.yaml → LACUNES.md), mode d'emploi (README.md)
spec/                       spec métier v2 : glossaire.yaml, mesures.yaml, regles.yaml, personas.md, domaine.md,
                            types.yaml, questions.yaml (34 questions), check_spec.py,
                            manifest_schema.yaml (schéma du Manifest v0.1)
catalog/
  entities.csv              une ligne par entité : id, type, libellés FR/NL/DE/EN, code, parent, source, licence, tier
  aliases.csv               une ligne par alias : texte, forme normalisée, langue, type d'alias, tier, source
  relations.csv             graphe de connaissance : sujet, prédicat, objet, source
  negatifs.csv              index négatif (R-RES-07), compilé depuis le glossaire et GeoNames
  hors_perimetre_geonames.csv  23 418 lieux réels hors périmètre (FR, NL, DE), source de l'index négatif
  open_*.csv, mecanova_*.csv, glossaire_*.csv   les trois couches avant fusion
challenges/
  cases.csv                 10 078 cas : texte saisi, indice de type, statut et entités attendus, issues acceptées
  cases_core.csv            780 cas stratifiés (60 par catégorie) pour la CI
  split.csv                 partition dev / test (2 923 cas test, à ne regarder qu'à l'évaluation finale)
reports/
  qualite_sources.md        anomalies trouvées dans les sources ouvertes et leur traitement
  baseline.md               résultats de trois résolveurs de référence
  source_issues.csv, taxonomy_translation_issues.csv, catalog_stats.json
build/                      scripts de reconstruction (run_all.sh reconstruit tout), outil human_questions.py
tests/                      tests unitaires (python -m pytest tests)
sources/                    licences et empreintes des sources
```

## Les trois niveaux de confiance (tier)

| Tier | Origine | Exemples |
|---|---|---|
| 1 | Source officielle ou de référence, traduction officielle | « Luik » pour Liège (Statbel), « Remblokken » pour plaquettes de frein (Shopify NL) |
| 2 | Référence ouverte, non vérifiée | variantes GeoNames (« Lüttich »), alias EEA (« SSANGJONG ») |
| 3 | Généré ou curé pour Mécanova | clients, articles, termes d'atelier (« soupapes »), marques de pièces |

Le moteur peut choisir les tiers qu'il charge. Tester avec et sans le tier 2 est instructif : il apporte du rappel et des collisions.

## Le jeu de défis

Chaque cas est **dérivé des données**, jamais écrit à la main. La vérité terrain se calcule en deux temps :
1. les candidats de l'index du catalogue (une forme qui correspond à plusieurs entités est ambiguë, une forme absente dont l'intention est hors catalogue est inconnue) ;
2. **les règles de la spec v2**, appliquées par le module partagé `build/rules.py` : localité absorbée par sa commune homonyme (R-GEO-02), agence ajoutée quand sa ville est candidate (R-CTX-05), famille à catégorie unique (R-ART-03), indice de type (R-RES-09).

Le même module sert à la génération des cas, aux résolveurs de référence et à `spec/check_spec.py` : la vérité terrain ne peut pas diverger de la spec. 633 cas sur 10 078 ont été modifiés par ces règles (colonne `ground_truth` : « règles de la spec appliquées »). Exemple : « Liège » attend la commune, l'arrondissement, la province **et** l'agence, sans les deux localités postales.

| Catégorie | Ce qu'elle teste | Cas |
|---|---|---:|
| C01 libellé canonique | couverture et normalisation de base | 416 |
| C02 traduction officielle | FR ↔ NL ↔ DE ↔ EN (« Bergen » → Mons) | 485 |
| C03 variante GeoNames | exonymes et noms historiques | 499 |
| C04 terme métier | vocabulaire d'atelier face aux traductions automatiques | 98 |
| C05 homonyme | même forme, plusieurs entités : le moteur doit rendre **tous** les candidats | 700 |
| C06 indice de type | la même ambiguïté avec un indice de type (comme celui de l'étape intention) | 844 |
| C07 faute de frappe | une opération d'édition sur libellés et alias ; marquée ambiguë si une autre entité est au moins aussi proche | 2 731 |
| C08 hors périmètre proche | lieux réels absents mais très proches d'un lieu du catalogue (type « Dinan / Dinant ») | 594 |
| C09 code | références tolérantes au format, références voisines inexistantes, voisines existantes | 1 097 |
| C10 client | raisons sociales : forme juridique, casse, ancienne forme, abréviation, ordre des mots | 1 149 |
| C11 marque | alias de marques et groupes | 176 |
| C12 véhicule | alias EEA, marque + modèle, modèle seul | 789 |
| C13 abréviation | « St-Ghislain », « Ste-Ode », « Jemeppe-s/-Sambre » | 500 |

**Colonnes clés de `cases.csv` :**
- `expected_status` : resolved, ambiguous ou unknown ;
- `expected_ids` : l'entité attendue, ou l'ensemble exact des candidats ;
- `accepted` : une réponse prudente acceptable en plus (par exemple unknown face à une faute de frappe) ;
- `hint_type` : le type d'entité fourni comme contexte, vide sinon.

**Notation recommandée**, dans cet ordre de priorité :
1. **Erreur silencieuse** : une entité résolue qui n'est pas la bonne. Objectif : 0.
2. **Sûr** : la réponse attendue ou une réponse prudente acceptée.
3. **Idéal** : exactement la réponse attendue.

## Mesure de référence

Trois résolveurs volontairement simples, qui appliquent tous les règles de la spec à leurs candidats (détail dans `reports/baseline.md`) :

| Résolveur | Idéal | Sûr | Erreurs silencieuses |
|---|---:|---:|---:|
| B0 · correspondance exacte seule | 66,1 % | 100 % | 0 % |
| B1 · exact + Jaro-Winkler ≥ 0,88 sur tout l'index | 85,7 % | 86,9 % | **10,7 %** |
| B2 · exact + Jaro-Winkler borné au type, jamais sur un code, ambigu si écart < 0,03 | 89,2 % | 91,9 % | **2,7 %** |

Ce que ça montre :
- La correspondance exacte ne se trompe jamais, mais ne rattrape aucune faute ni abréviation.
- Le fuzzy naïf résout 41 % des codes voisins vers une **autre** référence et 100 % des lieux hors périmètre vers un lieu du catalogue.
- Le fuzzy borné (l'approche de la spec) supprime les erreurs sur les codes, mais garde 44 % d'erreurs silencieuses sur les lieux hors périmètre proches. La parade est l'**index négatif** consulté après l'exact et avant la correspondance approchée (`negatifs.csv`, règle R-RES-07). Attention : les cas C08 sont tirés de ce fichier, donc l'utiliser rend C08 trivial ; c'est un test de présence de la parade, pas de sa qualité.
- Les catégories C01 à C06, C11 et C12 sont triviales pour un moteur qui charge tout le catalogue. Ce sont des tests de non-régression et de couverture ; elles deviennent difficiles si le moteur ne charge que le tier 1, ou s'il normalise autrement que la spec.

## Questions humaines

`human/questions.csv` est le **seul fichier source** des questions humaines : texte et étiquetage sur la même ligne, modifiable dans Excel. Le texte est conservé **sans aucune correction** (fautes et tournures comprises) et son empreinte SHA-256 est enregistrée dans `human/questions.lock` : une question modifiée, même d'un espace, est refusée au contrôle. Une question ne se supprime pas, elle se retire (`etat = retiree`), et son identifiant n'est jamais réutilisé.

```bash
python build/human_questions.py add "texte de la question"   # ajoute, numérote et enregistre
python build/human_questions.py check                        # contrôle complet
```

Le contrôle vérifie aussi chaque référence : entités contre le catalogue, mesures et axes contre le glossaire, lacunes contre `lacunes.yaml`, format des périodes. Mode d'emploi complet et pièges d'Excel : `human/README.md`.

Les 39 premières questions portent un étiquetage **proposé** dans le CSV. La réponse de référence s'écrit dans `human/attendus.yaml`, au format du **schéma du Manifest v0.1** (`spec/manifest_schema.yaml`) :
- un Manifest pour une question résolue ;
- les candidats pour une question ambiguë ;
- le terme et sa raison pour une question inconnue ;
- le sujet pour une question hors périmètre.

`build/manifest.py` valide chaque réponse contre le schéma, le catalogue et le glossaire, et calcule la forme canonique et l'empreinte du Manifest.

| Persona proposé | Questions | | Statut attendu | Questions |
|---|---:|---|---|---:|
| P1 · directrice commerciale | 21 | | resolved | 16 |
| P2 · chef de produit | 14 | | ambiguous | 12 |
| P3 · responsable d'agence | 4 | | unknown | 7 |
| | | | out_of_scope | 4 |

Ces questions ont révélé 14 lacunes de la spec que les cas générés n'avaient pas fait apparaître (`human/lacunes.yaml`, vue lisible `human/LACUNES.md`). Elles sont toutes en partition **test** : les corriger dans la spec sans les déplacer en dev reviendrait à apprendre les réponses.

## Contrôle global

```bash
python build/check_global.py
```

Reconstruit tout deux fois (sans retélécharger les sources), vérifie le déterminisme et l'intégrité de chaque fichier, contrôle les questions humaines, lance les tests unitaires et écrit `reports/check_global.md` avec l'état de préparation du POC.

## Reconstruire

```bash
bash build/run_all.sh
```

Les sources passent uniquement par GitHub et PyPI. Toute la chaîne est déterministe : deux exécutions produisent des fichiers identiques au bit près (vérifié).

## Spec métier v2 et glossaire

Le partage des rôles est strict :
- le **catalogue** détient les référentiels (géographie, pièces, véhicules, clients, articles, sites, commerciaux) ;
- le **glossaire** (`spec/glossaire.yaml`) détient le vocabulaire métier : mesures, périodes, mots de contexte, expressions de profil, listes métier, synonymes d'atelier, termes sans filtre, valeurs absentes. Il ne recopie aucune valeur du catalogue : il y renvoie par identifiant.

`build/build_glossary.py` compile le glossaire dans le catalogue, pour que le moteur n'interroge qu'un index. `spec/check_spec.py` vérifie que les 34 questions se résolvent exactement comme attendu en appliquant les règles, et que le vocabulaire métier ne crée aucune collision non déclarée.

Nouveautés de la v2 par rapport à la v1 : règles R-GEO-01 à 03 (localités, hiérarchie), R-VEH-01 et 02 (compatibilité véhicules), R-CTX-05 (une ville propose aussi l'agence qui s'y trouve), R-ART-04 (catégorie hors assortiment), R-RES-07 à 09 (index négatif, termes sans filtre, indice de type dès l'exact). La v1 est remplacée.

## Licences

Voir `SOURCES.md`. Deux sources demandent une attribution : GeoNames (CC BY 4.0) et openvehicle-data (CC BY 4.0, d'après l'Agence européenne pour l'environnement).
