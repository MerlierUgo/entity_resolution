<!-- Fichier généré par build/build_docs.py depuis spec/mesures.yaml : ne pas modifier à la main. Modifier le YAML, puis relancer le script. -->


# Mesures

> Version 2.1.0 · statut : figée · source : `spec/mesures.yaml`
>
> Chaque mesure est définie sans ambiguïté, à partir des colonnes des tables de faits. Ces définitions font foi pour les mesures DAX du semantic model, les requêtes de l'oracle et les tests.

## Conventions

- Montants **en euros, hors taxes**. Aucune TVA n'est jamais incluse.
- `Σ` porte sur les lignes de la période et des filtres demandés.
- Sauf mention contraire, `fact_ventes` est filtrée sur `type_ligne = 'Vente'` : les lignes de type `Consigne` sont exclues (règle R-CA-03).
- `fact_retours` est filtrée sur `statut = 'Accepté'` : les retours refusés n'ont aucun effet.
- Un ratio dont le dénominateur vaut 0 renvoie **vide**, jamais 0 (règle R-AFF-03).
- Les montants sont calculés à pleine précision et arrondis **uniquement à l'affichage** (règle R-AFF-01).

## Colonnes utilisées

| Table | Colonnes |
|---|---|
| `fact_ventes` | `date_facture`, `num_facture`, `num_commande`, `code_client`, `ref_article`, `site`, `canal`, `type_ligne`, `quantite`, `prix_tarif_unitaire`, `taux_remise`, `montant_net`, `cout_unitaire_standard` |
| `fact_retours` | `date_retour`, `num_facture_origine`, `code_client`, `ref_article`, `site`, `quantite_retournee`, `montant_rembourse`, `motif`, `statut` |
| `fact_commandes` | `date_commande`, `num_commande`, `code_client`, `ref_article`, `site`, `canal`, `quantite_demandee`, `quantite_servie_immediate` |
| `fact_stock` | `date_fin_mois`, `site`, `ref_article`, `quantite_stock`, `cout_unitaire_standard` |

Identité garantie par le générateur : `montant_net = quantite × prix_tarif_unitaire × (1 − taux_remise)`, au centime près.

## Additivité

- **oui** : s'additionne dans le temps et entre membres
- **ratio** : recalculée à chaque niveau, jamais additionnée
- **non (distinct)** : comptage distinct : ne s'additionne pas entre périodes
- **liste** : renvoie une liste d'éléments
- **non** : semi-additive (stock) : photo de fin de période, jamais additionnée dans le temps

## Chiffre d'affaires

### M01 · CA brut

`Σ fact_ventes.quantite × prix_tarif_unitaire`

CA au prix tarif, avant remises et avant retours.

**Unité** : € · **Additivité** : oui

**Alias** : CA brut, CA tarif, chiffre d'affaires brut

### M02 · Remises

`Σ fact_ventes.quantite × prix_tarif_unitaire × taux_remise`

Montant total accordé en remises. Identité : `M01 − M02 = M03`.

**Unité** : € · **Additivité** : oui

**Alias** : remises, montant des remises, remises accordées

### M03 · CA net facturé

`Σ fact_ventes.montant_net`

CA après remises, **avant** déduction des retours. C'est le montant facturé.

**Unité** : € · **Additivité** : oui · **Par défaut pour** : « facturé », « facturation »

**Alias** : CA net facturé, facturé, facturation, CA facturé, montant facturé

### M04 · Montant des retours

`Σ fact_retours.montant_rembourse (statut Accepté)`

Rattaché à la **date de retour**.

**Unité** : € · **Additivité** : oui

**Alias** : montant des retours, retours en euros, avoirs

### M05 · CA net

`M03 − M04`

Chiffre d'affaires de référence de Mécanova : remises et retours acceptés déduits. Quand un utilisateur dit « CA », « chiffre d'affaires » ou « ventes » sans autre précision, c'est **cette** mesure (règle R-CA-01).

**Unité** : € · **Additivité** : oui · **Par défaut pour** : « CA », « ventes »

**Alias** : CA, CA net, chiffre d'affaires, chiffre d'affaires net, chiffre, ventes, ventes en euros, revenus, omzet

### M06 · Montant des consignes

`Σ fact_ventes.montant_net où type_ligne = 'Consigne'`

Information seule : jamais inclus dans un CA.

**Unité** : € · **Additivité** : oui

**Alias** : consignes, montant des consignes


## Volumes

### M07 · Quantité facturée

`Σ fact_ventes.quantite`

Unités facturées, avant retours.

**Unité** : pièces · **Additivité** : oui

**Alias** : quantité facturée, unités facturées

### M08 · Quantité retournée

`Σ fact_retours.quantite_retournee (statut Accepté)`

**Unité** : pièces · **Additivité** : oui · **Par défaut pour** : « retours », « en volume »

**Alias** : retours, quantité retournée, pièces retournées, nombre de retours

### M09 · Quantité vendue nette

`M07 − M08`

**Unité** : pièces · **Additivité** : oui · **Par défaut pour** : « combien… vendu »

**Alias** : quantité vendue, quantité, volume, volumes, unités vendues, pièces vendues, ventes en volume, ventes en unités, combien vendu, vendus en quantité, besoin de pièces, besoin de plus de pièces

### M10 · Nombre de commandes

`COUNT(DISTINCT fact_ventes.num_commande)`

Commandes ayant donné lieu à au moins une ligne facturée sur la période.

**Unité** : commandes · **Additivité** : oui

**Alias** : nombre de commandes, commandes

### M11 · Nombre de lignes facturées

`COUNT(*) fact_ventes`

**Unité** : lignes · **Additivité** : oui

**Alias** : nombre de lignes, lignes facturées

### M28 · Prix tarif unitaire

`prix_tarif_unitaire de l'article (tarif en vigueur à la date)`

Prix catalogue d'un article, hors remise. Attribut de l'article : ne s'additionne jamais.

**Unité** : € · **Additivité** : non

**Alias** : prix tarif, prix catalogue, prix unitaire


## Marge

### M12 · Coût des ventes nettes

`Σ fact_ventes.quantite × cout_unitaire_standard − Σ fact_retours.quantite_retournee × coût standard de l'article`

Le coût standard d'un retour est celui de l'article pour l'année de la date de retour.

**Unité** : € · **Additivité** : oui

**Alias** : coût des ventes, coût, coût d'achat des ventes

### M13 · Marge brute

`M05 − M12`

**Unité** : € · **Additivité** : oui · **Par défaut pour** : « marge »

**Alias** : marge, marge brute, marge en euros, marge €

### M14 · Marge % (taux de marque)

`M13 / M05`

Part de la marge dans le prix de vente. **Convention Mécanova : tout le reporting interne affiche ce taux.**

**Unité** : % · **Additivité** : ratio · **Par défaut pour** : « marge % », « rentabilité »

**Alias** : marge %, % de marge, marge en pourcentage, taux de marque, rentabilité, rentable, rentables

### M15 · Taux de marge (sur coût)

`M13 / M12`

Définition comptable stricte du « taux de marge » : marge rapportée au coût d'achat. Utilisée seulement si l'utilisateur écrit exactement « taux de marge ». Voir la règle R-MRG-01 et le piège associé dans `glossaire.yaml`.

**Unité** : % · **Additivité** : ratio · **Par défaut pour** : « taux de marge », « exactement »

**Alias** : taux de marge, marge sur coût

### M16 · Taux de remise moyen

`M02 / M01`

**Unité** : % · **Additivité** : ratio

**Alias** : taux de remise, remise moyenne, taux de remise moyen


## Clients

### M17 · Panier moyen

`M03 / M10`

CA net facturé moyen par commande, **avant** retours (un retour n'est pas rattaché à une commande).

**Unité** : € · **Additivité** : ratio

**Alias** : panier moyen, panier, ticket moyen, valeur moyenne de commande

### M18 · Clients actifs

`COUNT(DISTINCT fact_ventes.code_client)`

Sur la période, **clients professionnels uniquement** (règle R-CLI-02).

**Unité** : clients · **Additivité** : non (distinct)

**Alias** : clients actifs, nombre de clients, clients qui achètent

### M19 · Clients inactifs

Clients professionnels ayant au moins une facture dans les **365 jours** précédant `data_as_of`, mais **aucune** dans les **90 derniers jours** (du 2026-07-03 au 2026-09-30 inclus).
Mesure de liste : elle renvoie les clients concernés, triés par CA net des 365 jours décroissant.

**Unité** : clients · **Additivité** : liste

**Alias** : clients inactifs, inactifs, clients dormants, clients qui décrochent, n'ont rien commandé depuis 90 jours

### M27 · CA par client actif

`M05 / M18`

Chiffre d'affaires net moyen par client actif sur la période.

**Unité** : € · **Additivité** : ratio

**Alias** : CA par client, CA moyen par client

### M29 · Clients au référentiel

`COUNT(DISTINCT dim_client.code_client), hors clients techniques particuliers`

Nombre de clients présents au référentiel à la date, qu'ils aient acheté ou non. À distinguer de M18 (clients actifs).

**Unité** : clients · **Additivité** : non (distinct)

**Alias** : clients au référentiel, nombre de clients au référentiel


## Retours

### M20 · Taux de retour

`M08 / M07`

Rapport des flux de la même période : retours datés à la date de retour, ventes à la date de facture. Approximation assumée (règle R-RET-02).

**Unité** : % · **Additivité** : ratio

**Alias** : taux de retour, taux de retours

### M21 · Taux de retour pour défaut

`Σ quantite_retournee (motif = 'Pièce défectueuse', Accepté) / M07`

**Unité** : % · **Additivité** : ratio

**Alias** : taux de retour pour défaut, taux de défaut


## Service

### M22 · Taux de service immédiat

`COUNT(lignes fact_commandes où quantite_servie_immediate = quantite_demandee) / COUNT(lignes fact_commandes)`

Part des lignes de commande servies **en totalité** dès la commande, depuis le stock de l'agence. Une ligne partiellement servie compte comme non servie.

**Unité** : % · **Additivité** : ratio

**Alias** : taux de service, taux de service immédiat, taux de dispo, taux de disponibilité, disponibilité, dispo


## Stock (mesures semi-additives)

Le stock est une **photo de fin de mois**. Il ne s'additionne **jamais** dans le temps. Sur une période de plusieurs mois, on prend la photo du **dernier mois** de la période (règle R-STK-01).

### M23 · Quantité en stock

`Σ fact_stock.quantite_stock`

À la dernière fin de mois de la période.

**Unité** : pièces · **Additivité** : non

**Alias** : quantité en stock, stock en quantité, pièces en stock

### M24 · Valeur du stock

`Σ fact_stock.quantite_stock × cout_unitaire_standard`

À la dernière fin de mois de la période.

**Unité** : € · **Additivité** : non · **Par défaut pour** : « stock »

**Alias** : stock, valeur du stock, stock en valeur, valeur stock

### M25 · Couverture de stock

`M24 / (M12 sur les 90 jours se terminant à cette fin de mois / 90)`

Nombre de jours de ventes que le stock permet de couvrir. Calculée sur le périmètre d'articles et de sites filtré.

**Unité** : jours · **Additivité** : non

**Alias** : couverture, couverture de stock, jours de stock

### M26 · Ruptures

Nombre de couples (site, article) tels que :
1. `quantite_stock = 0` à la dernière fin de mois de la période ;
2. l'article a été facturé au moins une fois par ce site dans les 90 jours précédant cette fin de mois.

L'entrepôt central est exclu (il ne facture pas).

**Unité** : couples site × article · **Additivité** : non

**Alias** : ruptures, articles en rupture, ruptures de stock, manquants


## Récapitulatif

| ID | Mesure | Unité | Additivité | Par défaut pour |
|---|---|---|---|---|
| M01 | CA brut | € | oui |  |
| M02 | Remises | € | oui |  |
| M03 | CA net facturé | € | oui | « facturé », « facturation » |
| M04 | Montant des retours | € | oui |  |
| M05 | CA net | € | oui | « CA », « ventes » |
| M06 | Montant des consignes | € | oui |  |
| M07 | Quantité facturée | pièces | oui |  |
| M08 | Quantité retournée | pièces | oui | « retours », « en volume » |
| M09 | Quantité vendue nette | pièces | oui | « combien… vendu » |
| M10 | Nombre de commandes | commandes | oui |  |
| M11 | Nombre de lignes facturées | lignes | oui |  |
| M12 | Coût des ventes nettes | € | oui |  |
| M13 | Marge brute | € | oui | « marge » |
| M14 | Marge % (taux de marque) | % | ratio | « marge % », « rentabilité » |
| M15 | Taux de marge (sur coût) | % | ratio | « taux de marge », « exactement » |
| M16 | Taux de remise moyen | % | ratio |  |
| M17 | Panier moyen | € | ratio |  |
| M18 | Clients actifs | clients | non (distinct) |  |
| M19 | Clients inactifs | clients | liste |  |
| M20 | Taux de retour | % | ratio |  |
| M21 | Taux de retour pour défaut | % | ratio |  |
| M22 | Taux de service immédiat | % | ratio |  |
| M23 | Quantité en stock | pièces | non |  |
| M24 | Valeur du stock | € | non | « stock » |
| M25 | Couverture de stock | jours | non |  |
| M26 | Ruptures | couples site × article | non |  |
| M27 | CA par client actif | € | ratio |  |
| M28 | Prix tarif unitaire | € | non |  |
| M29 | Clients au référentiel | clients | non (distinct) |  |
