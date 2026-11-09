<!-- Fichier généré par build/build_docs.py depuis spec/regles.yaml : ne pas modifier à la main. Modifier le YAML, puis relancer le script. -->


# Règles de gestion

> Version 2.1.0 · statut : figée · `data_as_of` = **2026-09-30** · source : `spec/regles.yaml`
>
> Ces règles s'appliquent partout : génération des données, mesures DAX, oracle, résolution des termes par l'agent. Chaque règle a un identifiant stable, à citer dans le code et dans les tests.

**État d'implémentation** : 56 règles · 6 codées · 2 prototypées · 48 à coder

## Chiffre d'affaires et montants

**R-CA-01 · Mesure par défaut.** « CA », « chiffre d'affaires », « ventes » (sans unité) et « chiffre » désignent le **CA net** (M05). « Facturé » ou « facturation » désignent le **CA net facturé** (M03).

*à coder · calcul*

**R-CA-02 · Ventes en volume.** « Ventes » accompagné d'une unité (« en unités », « en volume », « en pièces ») ou une question en « combien… vendu » désigne la **quantité vendue nette** (M09).

*à coder · calcul*

**R-CA-03 · Consignes.** Les lignes `type_ligne = 'Consigne'` (échange standard) sont exclues de **toutes** les mesures de CA, de quantité et de marge. Elles n'apparaissent que dans M06.

*à coder · calcul*

**R-CA-04 · Hors taxes.** Tous les montants sont en euros hors taxes. Une question sur la TVA ou un montant TTC est hors périmètre (R-HP-01).

*à coder · calcul*

**R-CA-05 · Rattachement.** Une vente est rattachée au **site qui facture**, au **client facturé** et au **canal de la commande**. L'entrepôt central ne facture jamais.

*à coder · calcul*

**R-CA-06 · Besoin de pièces.** « Avoir besoin de pièces », « besoin de plus de pièces » désigne la **quantité vendue nette** (M09). Avec une marque ou un modèle de véhicule, les pièces sont comptées via la compatibilité (R-VEH-01).

*à coder · resolution*

## Remises

**R-REM-01 · Taux de remise.** Le taux de remise d'une ligne est la somme de la remise contractuelle du client et d'une éventuelle remise promotionnelle, **plafonnée à 45 %**.

*à coder · calcul*

**R-REM-02 · Particuliers.** Les particuliers n'ont pas de remise contractuelle. Ils ne bénéficient que des promotions, de 0 à 10 %.

*à coder · calcul*

## Retours

**R-RET-01 · Effet d'un retour.** Seuls les retours au statut `Accepté` ont un effet. Ils réduisent le CA net, la quantité vendue nette et le coût des ventes, à la **date du retour**, et non à la date de la facture d'origine.

*à coder · calcul*

**R-RET-02 · Délai.** Un retour est accepté jusqu'à **30 jours** après la facture. Le taux de retour d'une période rapporte donc des retours en partie liés aux ventes de la période précédente. Cette approximation est assumée et documentée.

*à coder · calcul*

**R-RET-03 · Motifs.** Quatre motifs : Erreur de commande, Pièce défectueuse, Incompatibilité véhicule, Colis endommagé. Les retours pour pièce défectueuse alimentent les réclamations fournisseurs.

*à coder · calcul*

## Marge

**R-MRG-01 · Marge % et taux de marge.** « Marge % », « % de marge », « taux de marque », « rentabilité », « rentable » → **M14** (marge / CA net). L'expression exacte « taux de marge » → **M15** (marge / coût). Quand l'agent répond avec M15, il précise toujours en une phrase que c'est la marge rapportée au coût.

*à coder · calcul*

**R-MRG-02 · Coût standard.** Le coût d'un article est un coût standard fixé au 1er janvier de chaque année. Il ne change pas en cours d'année.

*à coder · calcul*

## Stock

**R-STK-01 · Semi-additivité.** Le stock ne s'additionne jamais dans le temps. Pour une période de plusieurs mois, on prend la **photo de fin du dernier mois** de la période. « Le stock en 2025 » signifie le stock au 2025-12-31.

*à coder · calcul*

**R-STK-02 · Périmètre par défaut.** Sans site précisé, le stock inclut **l'entrepôt central et toutes les agences**. Les ruptures (M26) excluent toujours l'entrepôt.

*à coder · calcul*

**R-STK-03 · Date par défaut.** Sans période précisée, le stock est celui de la dernière fin de mois disponible (2026-09-30).

*à coder · calcul*

## Clients

**R-CLI-01 · Rattachement.** Un client professionnel est rattaché à une seule agence et à un seul commercial. Ses achats peuvent néanmoins être facturés par une autre agence (dépannage).

*à coder · calcul*

**R-CLI-02 · Particuliers anonymes.** Les particuliers sont regroupés en un client technique par agence (`Particuliers – Agence X`). Ils sont exclus des comptages de clients (M18, M19) et des classements de clients (« top clients »). Toute question visant un particulier précisément est refusée (R-HP-03).

*à coder · calcul*

**R-CLI-03 · « Mes clients ».** Pour un responsable d'agence, « mes clients » désigne les clients **rattachés** à son agence (et non ceux qu'elle a facturés).

*à coder · calcul*

## Articles

**R-ART-01 · Format des références.** Une référence Mécanova suit le format `MN-XXX-00000`. La saisie est tolérante à la casse, aux espaces et aux tirets (`mn plq 10234` = `MN-PLQ-10234`), mais **jamais** à un caractère différent : aucune correspondance approchée sur un code.

*à coder · resolution*

**R-ART-02 · Références remplacées.** Quand une référence est remplacée par une nouvelle (`ref_remplacement`), une question sur l'ancienne référence porte sur **l'ancienne uniquement**, et la réponse signale la référence de remplacement. Les deux ne sont jamais additionnées implicitement.

*à coder · resolution*

**R-ART-03 · Même libellé à deux niveaux.** Quand une valeur existe à deux niveaux d'une même hiérarchie avec **exactement le même périmètre**, on retient le **niveau le plus haut**, sans clarification. En v2, c'est le cas d'une famille Mécanova qui ne contient qu'une catégorie (famille « Batteries » et catégorie vp-1-4-14-2, dont l'alias est « batteries »).

*codée · resolution* · `build/rules.py`

**R-ART-04 · Catégorie hors assortiment.** Une catégorie de la taxonomie qui n'est reliée à aucune famille Mécanova (pneus, jantes, sièges…) se résout normalement, mais la réponse indique qu'elle est **hors assortiment** au lieu d'afficher 0 €.

*à coder · resolution*

**R-ART-05 · Composant.** « Composant », « type de pièce » désignent une **catégorie de pièce** (dimension Sous-famille), jamais un article. « Le composant le plus vendu » classe les sous-familles.

*à coder · resolution*

## Géographie

**R-GEO-01 · Localités postales.** Une localité postale saisie (« Jupille », « 4020 Liège ») est ramenée à la **commune** à laquelle le catalogue la rattache (relation `situe_dans`). Si le catalogue ne la rattache qu'à une province (797 cas), le filtre porte sur la province et la réponse le signale.

*à coder · resolution*

**R-GEO-02 · Localité homonyme de sa commune.** Une localité postale qui porte le nom de la commune qui la contient (« Liège » 4000 et 4020 dans la commune de Liège) est **absorbée** par la commune : elle ne crée pas d'ambiguïté supplémentaire.

*codée · resolution* · `build/rules.py`

**R-GEO-03 · Hiérarchie.** Pays > région belge > province (BE, NL), région (FR) ou canton (LU) > arrondissement (BE) > commune (BE, LU) ou ville (FR, NL) > localité postale (BE). Une commune et l'arrondissement ou la province du même nom ont des périmètres différents : ils restent ambigus.

*à coder · resolution*

## Véhicules

**R-VEH-01 · Compatibilité.** Un article est compatible avec plusieurs modèles. Filtrer par marque ou modèle de véhicule revient à garder les articles compatibles, via la table de pont `bridge_compatibilite`. Une ligne de vente n'est **jamais comptée deux fois**, même si l'article est compatible avec plusieurs modèles filtrés.

*à coder · manifest*

**R-VEH-02 · Modèle exact.** « Clio » désigne le modèle `RENAULT CLIO` du catalogue, pas ses variantes (`CLIO E-TECH HYBRID`, `CLIO AUTOSCUOLA`). Inclure les variantes demande de les citer. Limite connue, documentée dans la réponse.

*à coder · manifest*

## Temps

Tous les calculs de dates partent de `data_as_of` = **2026-09-30**. L'horloge du serveur n'est jamais utilisée.

**R-TPS-01 · Expressions relatives.**

| Expression | Période |
|---|---|
| cette année, depuis le début de l'année, YTD, cumulé | 2026-01-01 → 2026-09-30 |
| l'an dernier, l'année dernière, l'année passée | 2025-01-01 → 2025-12-31 |
| ce mois-ci, ce mois | 2026-09-01 → 2026-09-30 |
| le mois dernier, le mois passé | 2026-08-01 → 2026-08-31 |
| ce trimestre | 2026-07-01 → 2026-09-30 |
| le trimestre dernier | 2026-04-01 → 2026-06-30 |
| les 12 derniers mois, sur un an glissant | 2025-10-01 → 2026-09-30 |
| les N derniers jours | de `data_as_of` − (N − 1) jours à `data_as_of` |
| un mois sans année (« en septembre ») | la dernière occurrence de ce mois ≤ `data_as_of` (septembre 2026) |
| « à fin août », « fin août » | photo de stock au 2026-08-31 |
| « depuis janvier 2024 » | 2024-01-01 → 2026-09-30 |

*à coder · manifest*

**R-TPS-02 · Période par défaut.** Sans période dans la question : **année en cours à date** pour les flux, **dernière fin de mois** pour le stock. La réponse affiche toujours la période retenue.

*à coder · manifest*

**R-TPS-03 · Comparaison à l'année précédente.** « Par rapport à l'an dernier », « vs N-1 », « évolution » comparent la période demandée à **la même période un an plus tôt**. Pour l'année en cours à date : 2026-01-01 → 2026-09-30 face à 2025-01-01 → 2025-09-30, et non à l'année 2025 complète.

*à coder · manifest*

**R-TPS-04 · Évolution en pourcentage.** `(valeur N − valeur N-1) / valeur N-1`. Si la valeur N-1 est nulle ou absente (agence Maastricht en 2023), l'évolution est **vide** et la réponse l'explique.

*à coder · manifest*

**R-TPS-05 · Semaines.** Les semaines sont des semaines ISO, du lundi au dimanche.

*à coder · manifest*

## Contexte utilisateur

**R-CTX-01 · Profil.** L'agent connaît le profil de l'utilisateur : son périmètre et son agence de rattachement (voir `personas.md`).

*à coder · resolution*

**R-CTX-02 · « Mon agence », « l'agence ».** « Mon agence », « notre agence » ou « l'agence » sans nom → l'agence de rattachement du profil. Si le profil n'en a pas, l'agent demande laquelle (statut ambiguous).

*à coder · resolution*

**R-CTX-03 · Mots de contexte.** Un mot placé juste avant une valeur oriente vers une dimension : « agence » → Site ; « province », « région », « canton » → Région ; « pays » → Pays ; « ville de » → Ville ; « marque » → Marque (ou Marque de véhicule si suivi de « véhicule » ou « voiture »). Les prépositions comptent aussi : « en », « au », « aux » devant un nom de pays → Pays (« au Luxembourg », « aux Pays-Bas ») ; « à » devant un nom → Ville ou Site, mais jamais Pays ni Région. Sans mot de contexte ni préposition décisive, une valeur présente dans plusieurs dimensions est **ambiguë**. Les mots de contexte sont lus sur la question brute, **avant** la normalisation qui supprime les mots vides.

*à coder · resolution*

**R-CTX-05 · Agence d'une ville citée.** Quand un terme désigne une commune ou une ville qui accueille un site Mécanova (relation `situe_dans`), ce site s'ajoute aux candidats. Sans mot de contexte, « Liège » propose donc la commune, l'arrondissement, la province **et** l'agence de Liège.

*codée · resolution* · `build/rules.py`

**R-CTX-04 · Périmètre du profil.** Pour un profil limité à une agence, le filtre `Site = agence du profil` s'applique par défaut à toutes les mesures de ventes, de commandes et de stock, sauf si la question cite explicitement un autre site. Pour les listes et comptages de clients, c'est l'agence de **rattachement** du client qui est filtrée (R-CLI-03). La réponse affiche toujours ce filtre implicite.

*à coder · resolution*

## Résolution des termes

**R-RES-01 · Ordre.** Synonymes validés du catalogue, puis correspondance exacte après normalisation, puis correspondance approchée (Jaro-Winkler) **bornée à une dimension**, puis attribution d'un rôle (filtre, axe, mesure).

*prototypée · resolution* · `build/baseline.py`

**R-RES-02 · Normalisation.** Appliquée à l'identique au terme saisi et aux libellés du référentiel, dans cet ordre :
1. `%` devient le mot « pourcent » et `€` le mot « euros », **avant** toute suppression de ponctuation (sinon « marge % » deviendrait « marge ») ;
2. minuscules et suppression des accents ;
3. ponctuation, apostrophes et tirets remplacés par des espaces ;
4. suppression des mots vides : *de, d, du, des, la, le, les, l, a, au, aux, en, et* ;
5. pluriel simple ramené au singulier (-s, -x final sur les mots de plus de 3 lettres) ;
6. comparaison aussi sur les mots triés par ordre alphabétique.

*codée · resolution* · `build/common.py · normalize()`

**R-RES-03 · Correspondance approchée.** Seuil initial 0,88, à calibrer sur le golden set. Jamais sur un code. Jamais pour un terme de moins de 4 caractères. Si les deux meilleurs candidats sont à moins de 0,03 d'écart : ambiguous.

*prototypée · resolution* · `build/baseline.py (B2)`

**R-RES-04 · Valeur absente.** Un terme qui ressemble à une valeur plausible mais absente des données (« Allemagne », « Suède ») renvoie **unknown**. L'agent n'approche jamais un pays ou une ville inexistants vers un autre.

*à coder · resolution*

**R-RES-05 · Pas de supposition.** Un terme ambigu n'est jamais résolu par le « candidat le plus probable ». L'agent demande toujours à l'utilisateur, sauf si R-ART-03 ou R-CTX-02/03 tranchent.

*à coder · resolution*

**R-RES-06 · Terme le plus long.** Quand plusieurs termes du glossaire se chevauchent dans la question, le plus long l'emporte : « filtres à huile » est résolu comme sous-famille avant que « filtres » (famille Filtration) ne soit considéré.

*à coder · resolution*

**R-RES-07 · Index négatif.** `catalog/negatifs.csv` rassemble les valeurs plausibles mais absentes : celles du glossaire (« Allemagne », « pneus », « Michelin ») et 23 418 lieux réels hors périmètre issus de GeoNames (dont « Dinan », proche de « Dinant »). Il est consulté juste après la correspondance exacte et **avant** toute correspondance approchée : une valeur du catalogue l'emporte toujours sur l'index négatif (un lieu hors périmètre nommé « Éco » ne doit pas masquer la gamme Éco).

*codée · resolution* · `engine/resolveur.py · ResolveurExact.resoudre()`

**R-RES-08 · Termes sans filtre.** Un terme du glossaire « sans filtre » (« Mécanova », « total », « groupe ») l'emporte sur un alias de marque : « CA total » ne filtre pas sur TotalEnergies. Il faut écrire « marque Total ».

*à coder · resolution*

**R-RES-09 · Indice de type dès l'exact.** Quand l'étape intention fournit le type attendu, il filtre aussi les correspondances **exactes**, pas seulement l'étape approchée. Raison : la normalisation crée des collisions entre domaines (« Seres » marque / « Sere » variante de Seraing ; « en ligne » / localité « Ligne »).

*codée · resolution* · `build/rules.py`

## Affichage

**R-AFF-01 · Arrondis.** Montants à l'euro, pourcentages à une décimale, couverture de stock au jour entier. L'arrondi intervient uniquement à l'affichage.

*à coder · affichage*

**R-AFF-02 · Classements déterministes.** Un classement (top, flop) trie par la mesure, puis par le libellé en ordre alphabétique pour départager les égalités. Sans N précisé, top et flop renvoient **10** lignes.

*à coder · affichage*

**R-AFF-03 · Division par zéro.** Un ratio sans dénominateur s'affiche vide, avec une explication. Jamais 0.

*à coder · affichage*

**R-AFF-04 · Provenance.** Chaque réponse indique la mesure, la période et les filtres effectivement appliqués, y compris les filtres implicites (période par défaut, périmètre du profil).

*à coder · affichage*

**R-AFF-05 · Mesure implicite.** Un classement ou une répartition sans mesure explicite (« top 10 des clients », « répartition par canal ») utilise le **CA net** (M05).

*à coder · affichage*

## Hors périmètre

**R-HP-01 · Sujets exclus.** Prévisions, objectifs et budgets, achats fournisseurs, TVA et montants TTC, logistique détaillée, ressources humaines.

*à coder · resolution*

**R-HP-02 · Réponse.** Une question hors périmètre reçoit une réponse explicite (« ce sujet n'est pas couvert par les données ») et **aucun chiffre**.

*à coder · resolution*

**R-HP-03 · Données personnelles.** Aucune information sur un particulier identifiable.

*à coder · resolution*
