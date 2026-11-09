<!-- Fichier généré par build/build_docs.py depuis human/lacunes.yaml : ne pas modifier à la main. Modifier le YAML, puis relancer le script. -->


# Lacunes de la spec révélées par les questions humaines

Les 39 questions écrites à la main révèlent des manques que les 10 078 cas générés n'avaient pas fait apparaître. C'est exactement le rôle de ce jeu.

| Code | Lacune | Questions | Piste de correction |
|---|---|---|---|
| G01 | Synonyme d'atelier manquant : « durites » pour les flexibles de frein | H-001, H-029 | ajouter le synonyme au glossaire |
| G02 | Attribut non modélisé : technologie d'ampoule (LED, halogène, xénon) | H-016 | attribut d'article, ou unknown assumé |
| G03 | Périodes manquantes : « les N derniers mois », « le dernier mois » | H-007, H-021 | ajouter au glossaire (R-TPS-01) |
| G04 | « le plus vendu » : volume ou CA ? La règle R-AFF-05 choisit le CA, l'intention est souvent le volume | H-011 | règle explicite : « vendu » → M09 |
| G05 | Axe flou : « composant », « pièce », « les plus grosses remises » (par article, sous-famille, client, ligne ?) | H-017, H-026, H-030 | définir l'axe par défaut ou demander |
| G06 | Mesures non définies : « productif », « mieux », « en positif », « a besoin de pièces », « problème » | H-005, H-013, H-014, H-019, H-021 | demander la mesure (comportement attendu) ou définir des mesures composites |
| G07 | Mesures absentes : montant d'une commande (le plus gros panier), prix unitaire (la pièce la moins chère) | H-024, H-032 | ajouter M27 montant de commande, M28 prix tarif |
| G08 | Nombre de clients au référentiel, distinct du nombre de clients actifs (M18) | H-035, H-036 | ajouter une mesure de comptage du référentiel |
| G09 | Seuil écrit « 200e » (e pour euros) | H-023 | normaliser « e » après un nombre en « euros » |
| G10 | Expressions « tout pays confondu », « tous les pays » non déclarées (pas de filtre, ou axe pays ?) | H-009, H-030 | les ajouter aux termes sans filtre, ou comme axe |
| G11 | Hors périmètre non déclaré : organisation (« qui s'occupe »), causalité et actualité (« le covid », « actualité »), conseil (« comment améliorer ») | H-008, H-020, H-038, H-039 | élargir la liste hors périmètre du glossaire |
| G12 | Mesure de stock avec un nom de ville : seule l'agence a un sens, mais la règle R-CTX-05 propose aussi la ville | H-004 | règle : une mesure de stock restreint les candidats aux sites |
| G13 | « Le Luxembourg » sans préposition, comparé à la France : la spec impose de demander, un humain comprendrait le pays | H-036 | règle : comparaison avec un pays → pays |
| G14 | Fuzzy sur les noms de clients : le préfixe commun « garage » gonfle le score (« garage roulageauto » ≈ « garage gare », 0,90) | H-027 | fuzzy sur les mots distinctifs, sans « garage », « auto », « carrosserie » |
| G15 | Questions d'impact d'un événement (covid…) : aucun calendrier d'événements | H-020 | section evenements dans glossaire.yaml (covid : 2020-03-01 → 2021-06-30, dates à valider) + règle R-EVT-01 + compilation dans le catalogue |

## Attention avant de corriger

Ces 39 questions forment un jeu de **test**. Si tu corriges la spec pour qu'elles passent, elles ne mesurent plus rien : tu auras appris la réponse.

Deux façons propres de procéder :

1. **Corriger, puis déplacer.** Tu corriges les lacunes (spec v3), tu passes ces 39 questions en `dev`, puis tu écris (ou fais écrire) un nouveau lot de test que personne n'a regardé.
2. **Ne rien corriger maintenant.** Tu gardes ces questions en test, et tu mesures le POC tel quel. Les lacunes deviennent des résultats du POC (« voici ce que le moteur ne sait pas encore faire »).

La première option est la plus utile si tu prévois d'autres questions humaines. La seconde est la plus honnête si ces 39 sont les seules.
