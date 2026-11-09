# Questions humaines

Deux fichiers que tu modifies :
- **`questions.csv`** : le texte des questions (verrouillé) et leurs métadonnées ;
- **`attendus.yaml`** : ta réponse attendue pour chaque question, au format de `spec/manifest_schema.yaml`.

Dans `questions.csv`, les colonnes `statut_attendu`, `entites_attendues`, `mesure`, `axes` et `periode` sont une **proposition de départ**. La référence est `attendus.yaml` : le contrôle liste les écarts entre les deux, à arbitrer.

| Fichier | Rôle | Qui le modifie |
|---|---|---|
| `questions.csv` | les questions et leur étiquetage | toi (Excel ou éditeur) |
| `questions.lock` | empreinte SHA-256 du texte de chaque question enregistrée | l'outil, jamais à la main |
| `attendus.yaml` | **la réponse attendue** de chaque question (Manifest, candidats, terme inconnu ou refus) | toi |
| `lacunes.yaml` | les lacunes de la spec révélées par les questions (codes G01…) | toi |
| `LACUNES.md` | vue lisible de `lacunes.yaml`, générée | jamais à la main |

## Ajouter une question

**Méthode recommandée**, en ligne de commande (depuis la racine du projet) :

```bash
python build/human_questions.py add "combien de plaquette vendu a namur en octobre ?"
python build/human_questions.py add "..." --split dev      # si tu comptes t'en servir pour corriger la spec
```

L'outil attribue l'identifiant suivant (H-040…), enregistre le texte tel quel et son empreinte. Il reste à remplir l'étiquetage dans `questions.csv`.

**Dans Excel** : ajoute une ligne en bas avec un identifiant nouveau, puis lance `python build/human_questions.py lock` pour l'enregistrer. Enregistre toujours au format **CSV UTF-8**.

Puis, dans tous les cas :

```bash
python build/human_questions.py check
```

## Écrire une réponse attendue

Dans `attendus.yaml`, chaque question a une entrée (vide tant qu'elle n'est pas écrite). Selon le statut :

```yaml
H-012:                          # resolved : le cœur du Manifest
  statut: resolved
  manifest:
    intent: ranking
    champs:
      - {role: mesure,  ref: M05}
      - {role: filtre,  dimension: sous_famille, valeurs: ["piece:cat:vp-1-4-10-3"]}
      - {role: axe,     dimension: marque}
      - {role: periode, debut: "2026-01-01", fin: "2026-09-30"}
    tri: {mesure: M05, ordre: desc}
    limite: 1

H-004:                          # ambiguous : les candidats, au moins deux
  statut: ambiguous
  ambiguites:
    - {terme: "bruxelles", candidats: ["geo:commune:BE-21004", "mecanova:site:agence-bruxelle"]}

H-001:                          # unknown : le terme et la raison
  statut: unknown
  inconnus:
    - {terme: "durites de frein", raison: absent_du_catalogue}

H-008:                          # out_of_scope : le sujet
  statut: out_of_scope
  hors_perimetre: {sujet: organisation}
```

Rôles des champs : `mesure`, `filtre`, `axe`, `periode`, `comparaison`, `seuil`. Intents, raisons et contraintes : `spec/manifest_schema.yaml`. Les identifiants se cherchent dans l'explorateur HTML ou dans `catalog/entities.csv`. Une clé `commentaire` est permise partout.

Le contrôle vérifie chaque réponse : identifiants présents dans le catalogue **et du bon type pour leur dimension**, mesures et axes du glossaire, dates réelles, contraintes de l'intent (un `ranking` a un axe, un tri et une limite…), identifiants en double.

## Les règles

1. **Le texte d'une question ne change jamais.** Fautes et tournures sont des données de test. Si le contrôle signale « texte modifié », c'est qu'il a changé, même d'un espace.
2. **Une question ne se supprime pas, elle se retire** : `etat = retiree`. Elle sort des évaluations mais garde son identifiant.
3. **Un identifiant n'est jamais réutilisé**, même après retrait.
4. **Écris la question avant de chercher son étiquette**, pour ne pas écrire des questions que le catalogue sait déjà résoudre.

## Les colonnes

| Colonne | Valeurs | Obligatoire |
|---|---|---|
| `id` | H-001, H-002… | oui |
| `question` | texte brut, sur une ligne | oui |
| `etat` | `active` · `retiree` | oui |
| `split` | `test` (évaluation, ne pas s'en servir pour corriger) · `dev` (sert à corriger la spec) | oui |
| `auteur` | nom de la personne qui a écrit la question | oui |
| `date_ajout` | AAAA-MM-JJ | oui |
| `persona` | `P1` directrice commerciale · `P2` chef de produit · `P3` responsable d'agence | |
| `statut_attendu` | `resolved` · `ambiguous` · `unknown` · `out_of_scope` | |
| `entites_attendues` | identifiants du catalogue séparés par `\|` (tous les candidats si `ambiguous`) | |
| `mesure` | identifiant du glossaire (M01…M26) | |
| `axes` | dimensions ou axes temporels du glossaire séparés par `\|` (`pays`, `marque`, `mois`…) | |
| `periode` | `2026-01-01..2026-09-30`, `photo 2026-09-30`, `2025`, ou deux périodes séparées par ` vs ` | |
| `intention_humaine` | ce que l'auteur voulait dire quand la spec ne permet pas de le résoudre (texte libre) | |
| `lacunes_spec` | codes de `lacunes.yaml` séparés par `\|` | |
| `piege` | ce que la question met à l'épreuve (texte libre) | |
| `validation` | vide (à valider) · `ok` · `a_revoir` | |
| `commentaire` | texte libre | |

Une question sans `statut_attendu` est acceptée (avertissement « pas encore étiquetée ») mais ne compte pas dans l'évaluation tant qu'elle n'est pas étiquetée.

## Ce que vérifie `check`

- Bloquant :
  - le texte de chaque question enregistrée est identique au caractère près ;
  - aucune question enregistrée n'a disparu du fichier ;
  - les identifiants sont uniques et bien formés ;
  - les valeurs de chaque colonne contrôlée sont valides ;
  - chaque entité existe dans le catalogue ;
  - chaque mesure et chaque axe existe dans le glossaire ;
  - chaque lacune existe dans `lacunes.yaml` ;
  - les dates des périodes sont réelles et dans l'ordre ;
  - le fichier est en UTF-8.
- Avertissement : réponses attendues à écrire, étiquetage à revoir, texte en double.
- Information : écarts entre ta réponse attendue et la proposition de départ du CSV.

Les tests de l'outil sont dans `tests/test_human_questions.py` (`python -m pytest tests`). Le contrôle global (`build/check_global.py`) lance les deux.

## Pièges d'Excel

- Excel peut changer une date `2026-11-04` en `04/11/2026` : mets les colonnes `date_ajout` et `periode` au format **Texte**. Sinon, le contrôle le signale.
- Un texte qui commence par `=`, `+` ou `-` est pris pour une formule : tape une apostrophe devant.
- Le séparateur `;` et le séparateur `,` sont tous les deux acceptés en lecture.
