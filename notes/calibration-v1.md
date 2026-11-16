# Calibration v1 : ce qui a été retiré et pourrait être réimplémenté

> **Pour Claude Code.** Ce fichier décrit du travail **retiré** du code en revenant au commit d'avant la calibration SGR.
> Le code complet est conservé dans le tag Git **`calibration-v1`** (`git show calibration-v1:<chemin>` pour lire un fichier).
> **Ne rien réimplémenter sans demande explicite.** Ces éléments ont été conçus sur des jeux générés dont les hypothèses
> n'avaient pas été discutées. Avant de les reprendre, il faut les re-justifier sur les nouveaux jeux issus de
> `spec/modele_saisie.yaml`, et sur le jeu d'**analyse** uniquement, jamais sur le jeu de certification.

État de la branche actuelle : fuzzy Jaro-Winkler à **seuil fixe 0,88** (écart 0,03). C'est un **seuil provisoire au
risque connu** (voir § 1). Ce n'est pas une valeur validée.

---

## 1. Ce qu'on a appris (à garder en tête, même sans le code)

| Constat | Chiffres (tag `calibration-v1`) |
|---|---|
| Le 0,88 fixe est sans erreur silencieuse sur dev, mais **pas sûr** sur un jeu plus difficile | B : 0 silencieux sur dev-évaluation ; **7,0 % d'erreurs** sur le jeu de certification (752 / 10 748 acceptés, borne 7,4 %), de 3,9 % (marques) à 19,7 % (douane) |
| Cause principale : des **termes absents acceptés à tort**, surtout des **noms recombinés** (un mot entier remplacé) | ≈ 83 % des absents acceptés ; « 911 TIGER 50 » → « 911 TURBO 50 », « nombre de Julie » → « nombre client ». Sur une chaîne longue, le Jaro-Winkler reste > 0,9 malgré un mot faux |
| Cause secondaire : **des noms réels voisins** | « Fresin » (faute pour Fretin) est à 0,97 de Fressin. Minoritaire : 22 cas sur 91 confusions en géographie à 0,88 |
| **Ordre des mots** : l'exact réunit les deux ordres, le fuzzy n'en cherchait qu'un | « Fiat 500 Abarth » / « Abarth 500 » → resolved au lieu d'ambiguous |
| L'**index négatif** est indispensable | B sans index négatif : 36 à 47 erreurs silencieuses (Solingen, Tignes…) |
| Calibration SGR à r\* = 0,5 %, δ = 5 % | seules les **pièces** passent (θ = 0,97 ; n = 1 815 ; k = 1 ; borne 0,45 %, de justesse). Véhicules 0,88 % au mieux, géographie 1,26 %, clients 2,30 % ; douane, marques et vocabulaire : trop peu de noms |
| A / B / C sur dev-évaluation (2 133 cas) | A 67,9 % idéal ; B 89,5 % ; C 69,4 % ; tous à 0 silencieux |
| Le risque mesuré dépend fortement de la **part d'absents** (fixée à 25 % sans justification) | c'est ce qui a motivé `spec/modele_saisie.yaml` |

---

## 2. Corrections du moteur (logique du fuzzy)

### 2.1 R-RES-11 : règle de voisinage → ambiguous
- **Quoi** : si un autre nom du catalogue est **aussi proche** du terme tapé que le meilleur nom (même distance
  d'édition, ou score à moins de l'écart 0,03), le statut est **ambiguous** avec les deux candidats, au lieu de resolved.
- **Effet mesuré** (0,88, jeu d'analyse) : confusions totales 155 → 94 ; géographie 121 → 65. Coût sur dev : −0,3 point d'idéal.
- **Détails décidés** :
  - « même type » = un type des meilleurs noms ;
  - un voisin ajouté reste soumis aux garde-fous (même nombre de mots, mêmes mots courts) ; s'il ne les passe pas,
    **toute la réponse devient unknown**, plutôt que d'écarter le voisin en silence.
- **Où** : `engine/approche.py`, `spec/regles.yaml` (R-RES-11), `tests/test_engine_fuzzy.py`.

### 2.2 Fuzzy sur les deux ordres de mots
- **Quoi** : chercher sur l'alias **et** sur l'alias aux mots triés, puis réunir les noms trouvés, comme le fait l'exact.
- **Effet mesuré** : confusions clients 11 → 0, véhicules 10 → 3.
- **Où** : `engine/approche.py`.

### 2.3 Distance d'édition OSA
- **Quoi** : *Optimal String Alignment*, où une transposition de deux lettres voisines compte pour une seule faute.
  Calculée dans l'ordre d'origine et en mots triés. Sert à R-RES-11.
- **Où** : `engine/approche.py`.

### 2.4 Garde-fou par mot (proposé, **jamais implémenté**)
- **Idée** : chaque mot du terme doit rester à 1 ou 2 fautes du mot correspondant du nom. Vise directement les noms
  recombinés, la cause principale des 7 %.
- À concevoir sur le jeu d'analyse ; il faudra alors une **nouvelle graine** de certification.

---

## 3. Calibration SGR (Geifman et El-Yaniv 2017)

### 3.1 `engine/calibration.py`
- **Grille fixe** de 0,80 à 0,99 par pas de 0,01 (20 seuils), à la place de la dichotomie.
- **Borne binomiale exacte** B\*(k, n, δ/20) : lemme 3.1, avec une correction de Bonferroni sur les 20 seuils.
- On retient le **θ le plus bas** dont B\* ≤ r\*. Si aucun ne passe, le fuzzy est désactivé pour la famille.
- `n_minimum` : δ divisé par le **nombre de seuils de la grille** (et non par ⌈log₂ n⌉). Il faut au moins
  1 196 acceptés sans erreur pour r\* = 0,5 %.
- Valeurs par défaut : `CIBLE, DELTA, ECART = 0.005, 0.05, 0.03` ; perte « dangereuse » (nom accepté → mauvaise entité).
- Aide de `--delta` corrigée : δ = probabilité que la garantie soit fausse, ce n'est pas le risque visé.
- Pour la borne de B (0,88), le calcul se fait au niveau δ **sans** correction de grille, puisque 0,88 n'a pas été
  choisi sur ces données.

### 3.2 `spec/seuils_fuzzy.yaml`
- En-tête : r\*, δ, grille, date, SHA-256 du jeu de certification.
- Par famille : θ (ou désactivé), n, k, borne, couverture. Pour une famille désactivée : le meilleur point de la grille
  et une couverture de 0.
- La date **n'entre pas** dans la comparaison de déterminisme : si le contenu n'a pas changé, la date existante est
  gardée.

### 3.3 `spec/familles_fuzzy.yaml` (validé)
| Famille | Types |
|---|---|
| geographie | ville, localite_postale, commune, arrondissement, canton, province, region, pays |
| pieces | categorie_piece, article, famille_mecanova, gamme, qualite |
| vehicules | modele_vehicule |
| clients | client |
| marques | marque_piece, marque_vehicule, groupe_industriel |
| douane | code_douanier |
| vocabulaire_metier | mesure, site, commercial, canal, groupe_canal, segment, type_client, motif_retour, forme_juridique |
| *(mixte)* | fuzzy toujours désactivé |

### 3.4 R-RES-10 : seuil fuzzy calibré (règle de la spec)
- r\* = 0,5 % et δ = 5 % sont des **décisions métier** : au plus ≈ 4 erreurs pour 900 termes rattrapés par mois,
  garanties à 95 %.
- **À réécrire dans `spec/regles.yaml`** quand la calibration sera réactivée.

---

## 4. Jeux de calibration (à **remplacer** par ceux du modèle de saisie)

- `build/build_calibration.py` → `challenges/calibration_analyse.csv` (graine 20261113, 17 708 cas) et
  `challenges/calibration_certif.csv` (graine 20261127, 17 687 cas). Les deux jeux n'ont aucun terme normalisé en
  commun ; les noms sources peuvent être partagés.
- **Principe à conserver** : on conçoit les règles sur le jeu d'**analyse** ; on calcule θ **une seule fois** sur le
  jeu de **certification**, le moteur figé, sans jamais regarder ses erreurs une par une. Si on corrige le moteur
  après avoir vu un résultat de certification, il faut **une nouvelle graine**.
- Choix faits **sans discussion** (raison de leur remplacement) :
  - 3 000 présents par famille quand c'est possible, absents = 25 % du total, au plus 3 cas par nom source ;
  - absents = fautes de frappe sur l'index négatif, noms recombinés (certains peu naturels :
    « Phare – Achsen Standard »), vraies marques hors catalogue écrites en dur ;
  - perturbations : substitution, omission, insertion, transposition, touche voisine AZERTY, lettre doublée, accent ou
    trait d'union (seulement en combinaison, puisqu'ils seuls disparaissent à la normalisation) ;
  - réponse attendue d'un présent = celle du résolveur exact sur le nom d'origine, sans indice de type.
- Bug corrigé : un terme de l'index négatif pouvait produire jusqu'à 6 cas au lieu de 3 (« Michelin »).
- Tests : `tests/test_calibration_cases.py` (graine → fichier identique, aucune entité de la partition test, aucun cas
  trouvable par l'exact).

---

## 5. Outils de mesure et rapport

- `engine/diagnostic_fuzzy.py` : sépare **présents confondus** et **absents acceptés**, indique pour chaque confusion si
  un voisin réel est à une faute, et fournit 10 exemples de chaque. Sorties dans `reports/diagnostic_fuzzy*.json`.
  **Très utile à reprendre tel quel** pour analyser les nouveaux jeux.
- `engine/comparaison.py` : A / B / C, avec et sans index négatif, en global et par famille ; options `mots_tries` et
  `voisinage` pour mesurer chaque correction séparément.
- `engine/rapport_calibration.py` : génère dans `reports/etat_moteur_2.html` les sections diagnostic, calibration
  (tableau et courbes risque-couverture par famille, avec r\* et θ), risque de B, A/B/C. Ne remplace que son propre bloc.
- Recommandation retenue : mesurer **deux risques séparés** (présents confondus, absents acceptés), puis les combiner
  avec une part d'absents justifiée par l'échantillon réel.

---

## 6. Petites corrections, indépendantes de la calibration (à refaire en priorité, sans risque)

- `.gitignore` avec `__pycache__/` et `*.pyc` ; retirer les `.pyc` déjà suivis : `git rm -r --cached` sur les
  dossiers `__pycache__`.
- Option `--sans-details` pour `build/human_questions.py check` et `build/rebuild_spec.py` : n'affiche que le **nombre**
  d'écarts avec les réponses attendues, et masque aussi la ligne « statut proposé ». Claude Code ne doit pas voir le
  corrigé de l'examen.
- Écritures de fichiers en `encoding="utf-8"` partout (Windows).
- Mettre à jour CLAUDE.md : le 0,88 est un seuil provisoire, au risque connu.
