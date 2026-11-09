# Qualité des sources ouvertes : ce qu'on a trouvé

Open source ne veut pas dire propre. Chaque anomalie ci-dessous a été détectée par le script de construction, puis corrigée, contournée ou conservée volontairement comme défi. Le détail ligne par ligne est dans `source_issues.csv` et `taxonomy_translation_issues.csv`.

## Anomalies détectées automatiquement

| Source | Anomalie | Cas | Traitement |
|---|---|---:|---|
| iso-codes (pycountry) | Traduction française « Limourg » au lieu de « Limbourg », pour la province belge **et** la province néerlandaise | 2 | Corrigée, tracée dans `source_issues.csv` |
| bpost (via spatie) | Les 22 localités bruxelloises sont rattachées à la province « Vlaams-Brabant » | 22 | Province recalculée à partir du code postal (règle de numérotation bpost) |
| bpost (via spatie) | Majuscules accentuées en milieu de mot : « LiÈge », « HÉlÉcine », « GrÂce-Hollogne » | 28 | Libellé corrigé ; la forme brute est gardée comme alias tier 2 |
| bpost (via spatie) | Plusieurs codes postaux dans un seul champ (« 2870,2890 Puurs-Sint-Amands ») | 7 | Premier code retenu, signalé |
| bpost (via spatie) | Lignes en double | 5 | Dédoublonnées |
| GeoNames | 12 047 variantes sur 22 758 inutilisables pour un utilisateur francophone ou néerlandophone : translittérations (« Lijezh »), codes aéroport (« LGG »), libellés composites | 12 047 | Écartées par filtre (alphabet latin-1, majuscule initiale, ≥ 4 caractères, pas de marqueur de translittération) |
| EEA (openvehicle-data) | Alias orthographiés différemment de la marque : « SSANGJONG » pour SSANGYONG, « VOLKSWAGEN, VW » dans un seul champ | — | Conservés : c'est exactement la variabilité réelle qu'un moteur doit absorber |

## Traductions automatiques de la taxonomie Shopify

La taxonomie Shopify est traduite en français, mais visiblement de façon automatique pour une partie des catégories. Le libellé source est conservé (c'est la source), et le terme d'atelier est ajouté comme alias tier 3.

| Catégorie (EN) | Libellé source (FR) | Terme d'atelier |
|---|---|---|
| Batteries | **Piles** | batteries |
| Valves | **Vannes** | soupapes |
| Brake Boosters | Boosters de frein | servofreins |
| Cylinder Heads | Têtes de cylindres | culasses |
| Shock Absorbers | Amortisseurs de chocs | amortisseurs |
| Control Arms | Bras de contrôle | bras de suspension |
| Ball Joints | Joints à rotules | rotules |
| AC Condensers | Condensateurs de climatisation | condenseurs |
| Heater Cores | Noyaux de chauffage | radiateurs de chauffage |
| Clutch Pressure Plates | Plaques de pression d'embrayage | mécanismes d'embrayage |
| Timing Belts | Courroies crantées | courroies de distribution |
| Spark Plugs | Bougies de voiture | bougies d'allumage |
| Water Necks | Cols d'eau | boîtiers de sortie d'eau |

Effet de bord intéressant : « Vannes » (catégorie mal traduite) entre en collision avec une ville du catalogue. Une erreur de traduction dans une source crée une ambiguïté dans une autre dimension.

## Limites connues, non corrigées

- **Découpage communal 2020.** Les fusions de communes flamandes du 1er janvier 2025 n'y sont pas. Les anciennes communes restent valides comme localités, mais un utilisateur qui cite une commune fusionnée en 2025 ne la trouvera pas.
- **Rattachement des localités postales.** 797 localités sur 2 782 ne sont rattachées qu'à leur province : le fichier bpost utilisé ne donne pas la commune, et ni le nom ni le code postal ne permettent de la retrouver sans ambiguïté. Le fichier officiel bpost (non accessible depuis cet environnement) le permettrait.
- **GeoNames et communes belges.** 1 719 entrées GeoNames belges (sections de communes) ne correspondent à aucune commune Statbel par le nom ; elles ne servent pas.
- **Véhicules.** Les modèles proviennent des immatriculations 2025 en Italie : la couverture européenne est bonne pour les marques, moins pour les modèles propres à d'autres marchés.
- **Dépôt Statbel.** Le dépôt GitHub qui republie le découpage Statbel n'a pas de licence explicite. Les données d'origine sont des données ouvertes Statbel ; pour un usage au-delà du POC, il faut repartir du fichier Statbel officiel.
- **Couche Mécanova.** Marques de pièces, groupes industriels et codes douaniers par catégorie viennent d'une curation manuelle (connaissance publique). Ils sont marqués tier 3 et « à vérifier ».

## Collisions entre domaines trouvées dans les données

Le catalogue contient 1 685 formes normalisées partagées par plusieurs entités, dont 738 entre types différents. Huit traversent deux domaines. Ce sont les plus instructives, parce qu'elles viennent de trois mécanismes différents :

| Terme saisi | Entités en collision | Mécanisme |
|---|---|---|
| Champion | marque de pièces Champion · localité Champion (province de Namur) | homonymie réelle |
| Bayon | modèle Hyundai BAYON · commune de Bayon (Grand Est) | homonymie réelle |
| Tivoli | modèle TIVOLI sous SSANGYONG **et** sous KG MOBILITY · Tivoli (Brabant-Septentrional) | homonymie réelle + changement de nom de marque (SsangYong devenu KG Mobility) présent deux fois dans la source |
| Malle | commune et localité de Malle (Anvers) · catégorie « Malles » | le pluriel ramené au singulier par la normalisation |
| Chery | marque CHERY · variante GeoNames de Chéry-lès-Pouilly | variante GeoNames abrégée |
| Vannes | catégorie « Vannes » (traduction fautive de *valves*) · variante GeoNames de Vannes-le-Châtel | traduction automatique fautive + variante abrégée |
| Seres | marque SERES · « Sere », variante GeoNames de Seraing | la normalisation (singulier) fabrique la collision |
| Portes | catégorie « Portes » · « L'Porte », variante GeoNames du Portel | la normalisation (suppression de « l' ») fabrique la collision |

Les deux dernières lignes sont un résultat en soi : la règle de normalisation de la spec (R-RES-02) crée des collisions qui n'existent pas dans les textes d'origine. C'est un argument pour borner la correspondance par type d'entité dès l'étape exacte, et pas seulement à l'étape approchée.
