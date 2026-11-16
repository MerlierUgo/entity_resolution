# Étape approchée · comparaison A, B, C · dev, part eval

Généré par `python -m engine.comparaison`. 2133 cas (30 % de dev, hash du case_id). La partition test n'est pas lue.

- **A** : étape 1 seule (exact)
- **B** : SeuilFixe(0.88, 0.03)
- **C** : SeuilsCalibres par famille (SGR, r* = 0.005, δ = 0.05)
- **B−** : B sans index négatif
- **C−** : C sans index négatif

Idéal et sûr en %, silencieux en nombre de cas, fuzzy = part des cas rattrapés par l'approché (%).

| Famille | Cas | A idéal | A sûr | A sil. | A fuzzy | B idéal | B sûr | B sil. | B fuzzy | C idéal | C sûr | C sil. | C fuzzy | B− idéal | B− sûr | B− sil. | B− fuzzy | C− idéal | C− sûr | C− sil. | C− fuzzy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| clients | 287 | 86.1 | 100.0 | 0 | 0.0 | 86.1 | 100.0 | 0 | 0.0 | 86.1 | 100.0 | 0 | 0.0 | 86.1 | 100.0 | 0 | 0.0 | 86.1 | 100.0 | 0 | 0.0 |
| douane | 31 | 100.0 | 100.0 | 0 | 0.0 | 100.0 | 100.0 | 0 | 0.0 | 100.0 | 100.0 | 0 | 0.0 | 100.0 | 100.0 | 0 | 0.0 | 100.0 | 100.0 | 0 | 0.0 |
| geographie | 976 | 45.4 | 100.0 | 0 | 0.0 | 83.3 | 97.1 | 0 | 41.6 | 45.4 | 100.0 | 0 | 0.0 | 83.4 | 97.0 | 0 | 41.9 | 45.4 | 100.0 | 0 | 0.0 |
| marques | 53 | 94.3 | 100.0 | 0 | 0.0 | 100.0 | 100.0 | 0 | 5.7 | 94.3 | 100.0 | 0 | 0.0 | 100.0 | 100.0 | 0 | 5.7 | 94.3 | 100.0 | 0 | 0.0 |
| mixte | 16 | 62.5 | 100.0 | 0 | 0.0 | 87.5 | 100.0 | 0 | 37.5 | 62.5 | 100.0 | 0 | 0.0 | 87.5 | 100.0 | 0 | 37.5 | 62.5 | 100.0 | 0 | 0.0 |
| pieces | 281 | 82.2 | 100.0 | 0 | 0.0 | 98.6 | 100.0 | 0 | 16.4 | 93.2 | 100.0 | 0 | 11.0 | 98.6 | 100.0 | 0 | 16.4 | 93.2 | 100.0 | 0 | 11.0 |
| sans_entite | 235 | 100.0 | 100.0 | 0 | 0.0 | 100.0 | 100.0 | 0 | 0.0 | 100.0 | 100.0 | 0 | 0.0 | 57.0 | 57.0 | 36 | 43.0 | 100.0 | 100.0 | 0 | 0.0 |
| vehicules | 217 | 80.7 | 100.0 | 0 | 0.0 | 93.5 | 99.5 | 0 | 13.4 | 80.7 | 100.0 | 0 | 0.0 | 93.5 | 99.5 | 0 | 13.4 | 80.7 | 100.0 | 0 | 0.0 |
| vocabulaire_metier | 37 | 73.0 | 100.0 | 0 | 0.0 | 97.3 | 100.0 | 0 | 24.3 | 73.0 | 100.0 | 0 | 0.0 | 97.3 | 100.0 | 0 | 24.3 | 73.0 | 100.0 | 0 | 0.0 |
| **TOTAL** | 2133 | 67.9 | 100.0 | 0 | 0.0 | 89.5 | 98.6 | 0 | 23.4 | 69.4 | 100.0 | 0 | 1.4 | 84.8 | 93.9 | 36 | 28.3 | 69.4 | 100.0 | 0 | 1.4 |

## Cas perdus par C par rapport à B : 429

- geographie · famille geographie désactivée (risque) : 370
- vehicules · famille vehicules désactivée (risque) : 28
- pieces · κ sous θ pieces = 0.97 (B accepte dès 0,88) : 15
- vocabulaire_metier · famille vocabulaire_metier désactivée (volume) : 9
- mixte · famille geographie désactivée (risque) : 4
- marques · famille marques désactivée (volume) : 3

## Erreurs silencieuses : 36

- B− · ER-05793 « Arbusigny » → ['geo:ville:FR-3029477'] (attendu unknown)
- B− · ER-05809 « Beauvoisin » → ['geo:ville:FR-3033962'] (attendu unknown)
- B− · ER-05827 « Bizanet » → ['geo:localite:BE-7783-bizet'] (attendu unknown)
- B− · ER-05844 « Breteil » → ['geo:ville:FR-3030276'] (attendu unknown)
- B− · ER-05862 « Chalon-sur-Saône » → ['geo:ville:FR-3027487'] (attendu unknown)
- B− · ER-05869 « Charpont » → ['geo:ville:FR-3026553'] (attendu unknown)
- B− · ER-05885 « Coubron » → ['geo:ville:FR-3022770'] (attendu unknown)
- B− · ER-05916 « Eymoutiers » → ['geo:ville:FR-2991320'] (attendu unknown)
- B− · ER-05920 « Flachslanden » → ['geo:ville:FR-3018358'] (attendu unknown)
- B− · ER-05936 « Gesvres » → ['geo:commune:BE-92054'] (attendu unknown)
- B− · ER-05938 « Glomel » → ['geo:commune:BE-72020'] (attendu unknown)
- B− · ER-05966 « Hochstätten » → ['geo:ville:FR-3013248'] (attendu unknown)
- B− · ER-05997 « La Genevraye » → ['geo:ville:FR-3016290'] (attendu unknown)
- B− · ER-06032 « Lesches » → ['geo:ville:FR-3019810'] (attendu unknown)
- B− · ER-06035 « Lijnden » → ['geo:localite:BE-3210-linden'] (attendu unknown)
- B− · ER-06047 « Lügde » → ['geo:ville:FR-2997190'] (attendu unknown)
- B− · ER-06056 « Mansac » → ['geo:ville:FR-2996158'] (attendu unknown)
- B− · ER-06061 « Marcilly-sur-Vienne » → ['geo:ville:FR-2995941'] (attendu unknown)
- B− · ER-06079 « Modane » → ['geo:commune:BE-61041'] (attendu unknown)
- B− · ER-06087 « Montaudin » → ['geo:ville:FR-2992983'] (attendu unknown)
- B− · ER-06092 « Montfoort » → ['geo:ville:NL-2750624'] (attendu unknown)
- B− · ER-06098 « Mosbach » → ['geo:ville:FR-2991716'] (attendu unknown)
- B− · ER-06109 « Neuhausen » → ['geo:ville:FR-2990676'] (attendu unknown)
- B− · ER-06118 « Odenbach » → ['geo:ville:FR-2989145'] (attendu unknown)
- B− · ER-06136 « Pontcarré » → ['geo:ville:FR-2986300'] (attendu unknown)
- B− · ER-06145 « Reichersbeuern » → ['geo:ville:FR-2983648'] (attendu unknown)
- B− · ER-06152 « Rogerville » → ['geo:localite:BE-4950-robertville'] (attendu unknown)
- B− · ER-06168 « Saint-Barnabé » → ['geo:ville:FR-2980746'] (attendu unknown)
- B− · ER-06288 « Solingen » → ['geo:commune:LU-2960198'] (attendu unknown)
- B− · ER-06300 « Surberg » → ['geo:ville:FR-2973686'] (attendu unknown)
- B− · ER-06309 « Thune » → ['geo:ville:FR-2972655'] (attendu unknown)
- B− · ER-06338 « Wachenheim » → ['geo:ville:FR-3038715'] (attendu unknown)
- B− · ER-06342 « Waldems » → ['geo:localite:BE-2800-walem'] (attendu unknown)
- B− · ER-06358 « Wolde » → ['geo:ville:NL-2744227'] (attendu unknown)
- B− · ER-06360 « Workum » → ['geo:ville:NL-2744156'] (attendu unknown)
- B− · ER-06369 « Étrelles » → ['geo:ville:FR-3019369'] (attendu unknown)
