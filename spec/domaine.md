# Domaine : Mécanova SA (entreprise fictive)

> Version 2.0.0 · statut : figée · date de référence des données (`data_as_of`) : **2026-09-30**
>
> Mécanova SA est une entreprise **entièrement fictive**, créée pour un POC. Toute ressemblance avec une entreprise existante est fortuite.
>
> **v2 :** les référentiels (géographie, catégories de pièces, marques de pièces et de véhicules, clients, articles, sites, commerciaux) sont dans le knowledge catalog (`catalog/`). Les marques sont de vraies marques, utilisées pour identifier des produits ; les ventes, clients et articles de Mécanova restent fictifs.

## 1. Activité

Mécanova SA distribue des **pièces de rechange automobiles** pour véhicules légers (voitures particulières et utilitaires légers). Elle achète auprès d'équipementiers, stocke, puis revend :

- principalement à des **professionnels de la réparation** : garages indépendants, concessions, centres auto, carrossiers, gestionnaires de flottes ;
- secondairement à des **particuliers**, au comptoir des agences et sur son site e-commerce.

Le métier repose sur trois promesses aux garagistes : **la bonne pièce** (compatibilité avec le véhicule), **tout de suite** (disponibilité immédiate en agence ou livraison dans la demi-journée) et **au bon prix** (remises négociées par compte).

## 2. Implantation

Le siège et l'**entrepôt central** sont situés à Namur (Belgique). L'entrepôt approvisionne neuf agences commerciales :

| Site | Pays | Type | Ouverture |
|---|---|---|---|
| Entrepôt central | Belgique | entrepôt (aucune vente) | 2008 |
| Agence Namur | Belgique | agence | 2008 |
| Agence Liège | Belgique | agence | 2010 |
| Agence Charleroi | Belgique | agence | 2012 |
| Agence Bruxelles | Belgique | agence | 2014 |
| Agence Arlon | Belgique | agence | 2016 |
| Agence Luxembourg | Luxembourg | agence | 2017 |
| Agence Lille | France | agence | 2018 |
| Agence Metz | France | agence | 2019 |
| Agence Maastricht | Pays-Bas | agence | **mars 2024** |

L'ouverture de l'agence Maastricht en mars 2024 est volontaire : elle crée une agence **sans historique** sur 2023, utile pour tester les comparaisons N/N-1.

Une vente est toujours rattachée à **l'agence qui facture**, y compris pour l'e-commerce : la commande web est affectée à l'agence la plus proche du client.

## 3. Clients

| Segment | Types de clients | Poids dans le CA |
|---|---|---|
| Professionnel | Garage indépendant, Concession, Centre auto, Carrossier, Flotte et loueur | ≈ 88 % |
| Particulier | Particulier | ≈ 12 % |

- Les **clients professionnels** ont un compte, un code client (`CL-` + 6 chiffres), une agence de rattachement, un commercial attitré et un taux de remise contractuel.
- Les **particuliers** ne sont jamais identifiés nominativement dans les données : ils sont regroupés en un client technique par agence (`Particuliers – Agence X`). Voir la règle R-CLI-02.

## 4. Offre produit

**2 520 articles**, rangés dans 50 catégories de la taxonomie (45 issues de Shopify, 5 ajoutées) et regroupés en 13 familles Mécanova. Chaque article a :

- une **référence Mécanova** (format `MN-XXX-00000`, par exemple `MN-PLQ-10234`) ;
- une **marque** parmi 37 marques réelles d'équipementiers et une marque propre, *Mécanova Select* ;
- une **gamme** (Premium, Standard, Éco) ;
- une **qualité** (Origine, Équivalent origine, Adaptable) ;
- une liste de **modèles de véhicules compatibles** (relation plusieurs-à-plusieurs, voir R-VEH-01) ;
- un **code douanier** (Système harmonisé), hérité de sa catégorie.

Certaines pièces lourdes (démarreurs, alternateurs, étriers) sont vendues en **échange standard** : le client paie une **consigne**, remboursée quand il rapporte la pièce usagée. Les consignes ne sont pas du chiffre d'affaires (règle R-CA-03).

## 5. Canaux de vente

| Groupe de canaux | Canal | Description |
|---|---|---|
| En agence | Comptoir | le client vient chercher la pièce en agence |
| En agence | Livraison garage | livraison par les tournées de l'agence, deux fois par jour |
| Digital | E-commerce pro | portail de commande réservé aux comptes professionnels |
| Digital | E-commerce particulier | site grand public |
| Téléphone | Téléphone | commande passée par téléphone au comptoir de l'agence |

## 6. Ordres de grandeur (cibles du générateur)

| Indicateur | Cible |
|---|---|
| Période couverte | 2023-01-01 → 2026-09-30 |
| CA net annuel | ≈ 85 M€ en 2025, croissance ≈ +6 %/an |
| Clients professionnels | 1 400 (catalogue), ≈ 1 250 actifs par an |
| Articles | 2 520 (catalogue) |
| Lignes de facture | ≈ 300 000 par an |
| Lignes de commande | ≈ 320 000 par an |
| Retours | ≈ 4 % des quantités facturées |
| Taux de service immédiat | ≈ 92 % en moyenne, plus bas à Maastricht la première année |
| Taux de remise moyen | ≈ 28 % chez les pros, 0 à 5 % chez les particuliers |
| Taux de marque moyen | ≈ 32 % |

Saisonnalités attendues dans les données :

- **Batteries** : pic de novembre à février (froid).
- **Essuyage** : pic d'octobre à décembre.
- **Refroidissement** : pic de juin à août.
- **Accessoires** (chaînes à neige) : pic de novembre à janvier.
- Creux général en **août** et la dernière semaine de décembre.

## 7. Sources de données simulées

| Table de faits | Grain | Date de référence |
|---|---|---|
| `fact_ventes` | une ligne de facture | date de facture |
| `fact_retours` | une ligne de retour | date de retour |
| `fact_commandes` | une ligne de commande | date de commande |
| `fact_stock` | un article × un site × une fin de mois | dernier jour du mois |

| Dimension | Contenu |
|---|---|
| `dim_date` | calendrier civil, semaines ISO |
| `dim_article` | référence, libellé, sous-famille, famille, marque, gamme, qualité, coût standard, échange standard (oui/non), référence de remplacement |
| `dim_client` | code, raison sociale, type, segment, ville, région, pays, agence de rattachement, commercial, taux de remise contractuel |
| `dim_site` | agences et entrepôt |
| `dim_canal` | canal et groupe de canaux |
| `dim_commercial` | commerciaux et leur agence |
| `bridge_compatibilite` | article × modèle de véhicule (plusieurs-à-plusieurs) |
| `dim_motif_retour` | motifs de retour |

## 8. Hors périmètre

Le POC ne couvre pas : les achats fournisseurs et les prix d'achat réels, les prévisions, la logistique détaillée (tournées, délais), les ressources humaines, la TVA, la comptabilité générale, ni les données personnelles des particuliers.
