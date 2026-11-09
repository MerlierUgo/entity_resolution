# Contrôle global · v1.4

## Contrôles automatiques

| Contrôle | Résultat | Détail |
|---|---|---|
| Déterminisme : deux reconstructions identiques | OK | 20 fichiers comparés |
| Spec v2 cohérente avec le catalogue (34 questions) | OK | OK : spec v2 cohérente avec le catalogue |
| Chaque entité a au moins un alias | OK | 0 sans alias |
| Chaque entité et chaque alias porte une source et une licence | OK |  |
| Relations sans extrémité orpheline | OK | 31827 relations |
| Jeu de défis : entités attendues existantes | OK | 10078 cas |
| Jeu de défis : chaque cas a une partition dev/test | OK | test : 2923 |
| Jeu « core » : toutes les catégories représentées | OK | 780 cas |
| Questions humaines : texte inchangé, références valides (human/questions.csv) | OK | OK · 0 erreur(s), 1 avertissement(s) |
| Tests unitaires | OK | 71 passed in 0.81s |
| Mesure de référence calculée | OK | B2 erreurs silencieuses : 274 |
| Textes de licence des sources présents | OK |  |

## Préparation du POC

| Élément | Prêt | Détail |
|---|---|---|
| Knowledge catalog (référentiels, alias, relations, provenance) | oui | 13348 entités, 36077 alias |
| Glossaire métier v2 compilé et contrôlé | oui | 26 mesures, 54 règles |
| Règles de résolution partagées (build/rules.py) | oui | vérité terrain = spec |
| Index négatif | oui | 22743 termes |
| Jeu de défis généré avec partition dev/test | oui | 10078 cas |
| Questions humaines | non | 39 / 100 visées, 1 auteur(s), 39 étiquetages à valider |
| Questions écrites par quelqu'un qui ne connaît pas le catalogue | non | aucune pour l'instant |
| Données de faits (ventes, retours, commandes, stock) et oracle DuckDB | non | non générés : nécessaires pour vérifier les chiffres, pas pour l'entity resolution |
| Semantic model Power BI et templates DAX | non | étape suivante de la roadmap |
| Schéma du Manifest v0.1 (YAML) + validation, forme canonique, empreinte | oui | spec/manifest_schema.yaml, build/manifest.py |
| Réponses attendues des questions humaines | non | human/attendus.yaml : à écrire par l'auteur |
