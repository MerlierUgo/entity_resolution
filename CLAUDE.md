# CLAUDE.md · Agent BI déterministe (POC Mécanova)

Ce fichier guide Claude Code dans ce dépôt. Lis-le en entier avant toute modification.

## Le projet en bref

Un chatbot BI qui répond **toujours de la même façon à la même question** et qui **ne se trompe jamais en silence**. Données simulées : Mécanova SA, distributeur fictif de pièces auto (Belgique, France du Nord-Est, Luxembourg, sud des Pays-Bas). Données au **2026-09-30** (`data_as_of`), historique depuis 2023-01-01.

Chaîne de traitement d'une question :

1. **Extraction** (LLM léger, température 0, JSON imposé) : découpe la question en termes, détecte `out_of_scope`. **Le LLM découpe, il ne décide jamais.**
2. **Entity resolution** (aucun LLM) : chaque terme → resolved / ambiguous / unknown.
3. **Assemblage du Manifest** (aucun LLM) : seulement si tous les termes sont resolved.
4. **Calcul** : template DAX ← Manifest (plus tard, Power BI).

Le statut d'une question est le pire de ses termes : out_of_scope > unknown > ambiguous > resolved. **Aucun chemin ne permet au LLM de produire un chiffre.** Dans le doute, le moteur demande (ambiguous) ou dit qu'il ne sait pas (unknown).

## Règles non négociables

1. **Zéro erreur silencieuse.** Une entité résolue qui n'est pas la bonne est le pire défaut possible. Une brique n'est gardée que si elle augmente les bonnes réponses **sans** créer d'erreur silencieuse.
2. **Ne jamais lire `human/attendus.yaml` ni les colonnes `statut_attendu`, `entites_attendues`, `mesure`, `axes`, `periode` de `human/questions.csv` pour concevoir ou régler le moteur.** C'est le corrigé de l'examen. On ne l'ouvre que pour **évaluer**, et seulement quand l'utilisateur le demande.
3. **Régler le moteur uniquement sur la partition `dev`** de `challenges/split.csv`. La partition `test` sert aux jalons, à la demande de l'utilisateur.
4. **Ne jamais modifier le texte d'une question humaine.** Fautes et tournures sont des données de test, verrouillées par `human/questions.lock`. Une question se retire (`etat = retiree`), elle ne se corrige ni ne se supprime.
5. **Ne jamais ajouter à la spec un alias, un synonyme ou une règle tiré des mots d'une question de test.** Ajouter une **structure** (mesure, dimension) est permis ; ajouter le **vocabulaire** qui y mène depuis une question de test fait passer cette question en `dev` (colonne `split`). En cas de doute, demander.
6. **Jamais de correspondance approchée sur un code** (référence article, code client, code douanier) : R-RES-03.
7. **La même normalisation partout** : `build/common.py · normalize()` (R-RES-02), pour le catalogue comme pour la saisie. Ne pas la réimplémenter.
8. **Déterminisme** : pas d'aléatoire non graine, sorties triées, CSV écrits en `utf-8-sig` (lisibles dans Excel).

## Sources de vérité : YAML pour le code, Markdown pour la lecture

| Source (on modifie celle-ci) | Contenu |
|---|---|
| `spec/mesures.yaml` | mesures M01… : formule, unité, additivité, alias |
| `spec/regles.yaml` | règles R-XXX-NN : texte, composant, statut d'implémentation, fichiers |
| `spec/glossaire.yaml` | dimensions, listes métier, synonymes, mots de contexte, prépositions, périodes, hors périmètre, index négatif |
| `spec/manifest_schema.yaml` | schéma du Manifest v0.1 (source unique des valeurs permises) |
| `spec/types.yaml`, `spec/questions.yaml` | types de questions, 34 questions de référence avec Manifest attendu (ancien format) |
| `human/questions.csv` | questions humaines (texte verrouillé) ; les colonnes d'étiquetage sont une *proposition* |
| `human/attendus.yaml` | **réponses attendues de l'auteur** (corrigé de l'examen) |
| `human/lacunes.yaml` | lacunes G01… révélées par les questions humaines |

**Ne jamais modifier à la main** `spec/mesures.md`, `spec/regles.md`, `human/LACUNES.md` : ce sont des vues générées par `build/build_docs.py`. Modifier le YAML, puis régénérer.

Textes de contexte (non lus par le code) : `spec/domaine.md`, `spec/personas.md`, les `README.md`.

## Catalogue (ce que le moteur charge)

- `catalog/entities.csv` : une ligne par entité (`entity_id`, `entity_type`, libellés, code, parent, source, licence, tier).
- `catalog/aliases.csv` : `alias`, `alias_norm` (forme normalisée), `alias_type`, `tier`. **C'est l'index de l'entity resolution.** Un nom peut désigner plusieurs entités (homonymes), une entité a plusieurs noms.
- `catalog/negatifs.csv` : index négatif (R-RES-07), termes plausibles connus comme absents (Paris, Allemagne, Michelin…).
- `catalog/relations.csv` : graphe (situe_dans, modele_de, compatible_avec, rattache_a…).
- `build/rules.py` : classe `Rules` qui applique R-GEO-02, R-CTX-05, R-ART-03, R-RES-09 et calcule le statut. Le moteur l'importe, il ne la duplique pas.
- Les fichiers `catalog/open_*`, `mecanova_*`, `glossaire_*` sont des couches avant fusion : le moteur ne les lit pas.

Identifiants : `geo:commune:BE-62063`, `piece:cat:vp-1-4-20-3`, `piece:marque:bosch`, `veh:marque:renault`, `veh:modele:renault-clio`, `mecanova:site:agence-liege`, `metier:mesure:M05`.

## Le Manifest (spec/manifest_schema.yaml)

Cœur canonique et hashé, indépendant de la formulation :

```yaml
intent: ranking            # aggregate | breakdown | ranking | timeseries | compare | share | list | detail
champs:
  - {role: mesure,  ref: M05}
  - {role: filtre,  dimension: sous_famille, valeurs: ["piece:cat:vp-1-4-10-3"]}
  - {role: axe,     dimension: marque}
  - {role: periode, debut: "2026-01-01", fin: "2026-09-30"}   # ou {photo: "2026-09-30"} pour le stock
tri: {mesure: M05, ordre: desc}
limite: 1
```

La question brute, la langue, la trace terme → champ et le rendu restent **hors** du cœur (hors hash). Validation, forme canonique et empreinte : `build/manifest.py` (`validate_manifest`, `validate_answer`, `canonical`, `manifest_hash`).

## Commandes (depuis la racine, environnement virtuel activé)

```bash
python build/rebuild_spec.py            # après toute modification de spec/ ou human/ : reconstruit et contrôle
python build/rebuild_spec.py --rapide   # contrôles seulement
python build/human_questions.py check   # questions humaines et réponses attendues
python spec/check_spec.py               # cohérence de la spec
python -m pytest -q tests               # tests unitaires
```

Ne pas lancer `build/run_all.sh` ni `build/check_global.py` sur la machine de l'utilisateur : ils retéléchargent les sources ouvertes (dossier `raw/` absent du dépôt) et demandent bash.

Environnement : Windows (PowerShell) et Python 3.13 chez l'utilisateur. Dépendances : `pyyaml`, `rapidfuzz`, `pytest`. Écrire du code multiplateforme (chemins via `pathlib`, pas de commande shell spécifique).

**Avant de considérer une tâche terminée** : `python build/rebuild_spec.py` doit afficher « OK · tout est à jour et cohérent ».

## Feuille de route du moteur (dossier `engine/`, à créer)

`build/` fabrique le catalogue, `engine/` répond aux questions. Chaque étape a ses tests dans `tests/` et se mesure sur le banc d'essai (`challenges/cases.csv`, partition dev) avec les métriques **idéal / sûr / erreur silencieuse** (voir `build/baseline.py`, à battre).

1. **Résolveur exact** : normalisation → alias exact (puis mots triés) → index négatif → `Rules.apply` → statut. Objectif ≈ 66 % idéal, **0 % erreur silencieuse** (comme la référence B0).
2. **Jaro-Winkler borné** (rapidfuzz) : seulement si rien n'est trouvé ; borné au type attendu ; seuil 0,88 ; au moins 4 caractères ; jamais sur un code ; ambigu si les deux meilleurs **noms** sont à moins de 0,03. Raisonner **par nom, pas par entité** : un nom trouvé ramène toutes ses entités (homonymes), puis les règles de contexte tranchent. Pour les noms de plusieurs mots (clients), comparer les mots distinctifs en ignorant les mots génériques (« garage », « auto », « carrosserie ») : G14.
3. **Contexte et assemblage** : prépositions et mots de contexte (R-CTX-03), profil (« mon agence », R-CTX-02), rôles, période par défaut (R-TPS-02), assemblage et validation du Manifest. Test : les 34 questions de `spec/questions.yaml`.
4. **Extraction LLM** : sortie JSON validée, température 0, cache sur la question normalisée.
5. **Examen** : les questions humaines de bout en bout, sur demande de l'utilisateur ; chaque échec est rattaché à une lacune (G…) ou à un module manquant.

Chaque résolution produit une **trace** par terme (étape, score, règle appliquée) : c'est elle qui explique un échec.

## Pièges connus (à couvrir par des tests sur le banc d'essai, pas sur l'examen)

- **Liège** : l'index renvoie commune, arrondissement, province et deux localités ; R-GEO-02 retire les localités, R-CTX-05 ajoute l'agence → ambiguous à 4 candidats.
- **Dinan / Dinant** : lieu réel hors périmètre très proche d'un lieu du catalogue ; l'index négatif doit répondre avant le fuzzy (catégorie C08).
- **Codes voisins** : MN-AMO-70514 n'est pas MN-AMO-70513 (C09).
- **Collisions entre domaines** : Champion (marque / localité), Bayon, Tivoli, Seres, « en ligne » → localité Ligne, « appel » → localité Appels.
- **Stock** : toujours une photo (`{photo}`), jamais additionné dans le temps (R-STK-01).

## Vocabulaire

- **Erreur silencieuse** : entité résolue fausse. **Sûr** : réponse attendue ou réponse prudente acceptée (colonne `accepted`). **Idéal** : exactement la réponse attendue.
- **Tier** d'alias : 1 officiel, 2 référence ouverte (GeoNames, EEA), 3 généré, curé ou glossaire.
- **dev / test** : dev pour régler et corriger, test pour mesurer ce que le moteur n'a jamais vu.

## Style

- Code et commentaires en français, comme le reste du dépôt ; noms de variables courts et explicites.
- Petites fonctions pures et testées ; pas de dépendance nouvelle sans le dire.
- Messages d'erreur destinés à l'utilisateur : en français, avec le fichier, la ligne ou l'identifiant concerné, et la correction à faire.
- Ne pas committer ni pousser sans demande explicite.
