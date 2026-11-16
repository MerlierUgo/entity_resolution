"""
Étape 2 du moteur : correspondance approchée bornée (Jaro-Winkler, R-RES-03).

Elle n'intervient que si l'alias exact, les mots triés et l'index négatif n'ont rien donné.
Garde-fous, tous appliqués avant le moindre score :
  - jamais sur un code : les alias de type code (ALIAS_CODES) ne sont pas comparables, et les mots
    qui contiennent un chiffre doivent être identiques entre le terme et le nom (« 500 hybrud » ne
    se compare qu'aux noms qui contiennent exactement « 500 ») ; un terme fait seulement de mots à
    chiffres est un code ou un nombre : pas d'approché ;
  - jamais sous 4 caractères (espaces non comptés), et jamais sur un mot de moins de 4 lettres :
    les noms retenus doivent avoir le même nombre de mots que le terme et les mêmes mots courts
    (« st », « ste », « s », « sa »). Jaro-Winkler ne distingue rien sur deux lettres : sans ce
    garde-fou, « St.-Jan » donnait « T Jan » et « Ste-Cécile » donnait « Steil » (banc dev, C13) ;
  - borné au type indiqué quand l'étape intention en fournit un (R-RES-09).

On raisonne par nom, pas par entité : le meilleur nom donne le score κ ; tous les noms à moins de
l'écart du meilleur sont retenus et ramènent toutes leurs entités (homonymes) ; les règles de
contexte tranchent ensuite.

Ordre des mots (R-RES-02, point 6, comme l'exact) : le score d'un nom est le meilleur de deux
comparaisons, le terme contre le nom et les mots triés du terme contre les mots triés du nom. Les
noms trouvés par l'une ou l'autre forme sont réunis : une faute sur « Fiat Abarth 500 » retrouve
« fiat abarth 500 » et « fiat 500 abarth », que l'exact réunit aussi, et la réponse est ambiguë
comme celle de l'exact sur le nom juste.

Voisinage (R-RES-11) : un autre nom du même type, aussi proche du terme en distance d'édition (OSA :
substitution, omission, insertion, transposition de deux lettres voisines) que le meilleur nom, est
retenu avec lui. « Fresin » est à une faute de Fressin (κ = 0,97) et de Fretin (κ plus bas) : les deux
sont retenus et la réponse est ambiguë, pas Fressin. Voir IndexApproche.voisins_edition. Le seuil et l'écart viennent d'une politique injectée :
  SeuilFixe(0.88, 0.03)          même seuil pour toutes les familles (valeur initiale de R-RES-03) ;
  SeuilsCalibres.charger(cat)    un seuil par famille, calibré par engine/calibration.py (SGR, R-RES-10).

Le « type » d'une proposition est celui des entités des meilleurs noms (score égal à κ) : un seul
type → ce type ; plusieurs → « mixte ». Sa « famille » (spec/familles_fuzzy.yaml) est celle de ces
types : une seule famille → cette famille ; plusieurs → « mixte », toujours désactivé par
SeuilsCalibres. Les deux se calculent sans connaître la réponse.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import process
from rapidfuzz.distance import OSA, JaroWinkler

from engine.catalogue import ROOT, Catalogue, cle_triee

MIN_CARS = 4
ECART_MAX = 0.10          # borne de l'écart admis par une politique (recherche des voisins)
MIXTE = "mixte"
SEUILS = ROOT / "spec" / "seuils_fuzzy.yaml"
FAMILLES = ROOT / "spec" / "familles_fuzzy.yaml"


def a_chiffre(mot: str) -> bool:
    return any(c.isdigit() for c in mot)


def signature(norm: str) -> tuple[str, ...]:
    """Mots à chiffres d'une forme normalisée, triés : ils doivent être identiques pour comparer."""
    return tuple(sorted(m for m in norm.split() if a_chiffre(m)))


def mots_courts(norm: str) -> list[str]:
    return sorted(m for m in norm.split() if len(m) < MIN_CARS and not a_chiffre(m))


def compatible(norm: str, nom: str) -> bool:
    """Garde-fou : même nombre de mots et mêmes mots courts. Les mots longs seuls s'approchent."""
    return len(norm.split()) == len(nom.split()) and mots_courts(norm) == mots_courts(nom)


def distance(a: str, b: str) -> int:
    """Distance d'édition OSA entre deux formes normalisées : la plus petite entre l'ordre d'origine et
    les mots triés (R-RES-11)."""
    return min(OSA.distance(a, b), OSA.distance(cle_triee(a), cle_triee(b)))


def cle_type(types) -> str:
    types = set(types)
    return next(iter(types)) if len(types) == 1 else MIXTE


def charger_familles(cat: Catalogue | None = None, chemin: Path = FAMILLES) -> dict[str, str]:
    """entity_type → famille, lu dans spec/familles_fuzzy.yaml. Avec `cat`, vérifie que chaque type du
    catalogue a exactement une famille."""
    import yaml
    if not chemin.exists():
        raise FileNotFoundError(f"{chemin} introuvable : il définit les familles de l'étape approchée (R-RES-10).")
    doc = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    out: dict[str, str] = {}
    for fam, v in (doc.get("familles") or {}).items():
        if fam == MIXTE:
            raise ValueError(f"{chemin.name} : « {MIXTE} » est réservé, choisir un autre nom de famille.")
        for t in (v or {}).get("types") or []:
            if t in out:
                raise ValueError(f"{chemin.name} : le type {t} est dans deux familles ({out[t]} et {fam}) ; "
                                 "le laisser dans une seule.")
            out[t] = fam
    if cat is not None:
        manquants = sorted(set(cat.etype.values()) - set(out))
        if manquants:
            raise ValueError(f"{chemin.name} : type(s) du catalogue sans famille : {', '.join(manquants)} ; "
                             "les ajouter à une famille, puis recalibrer (python -m engine.calibration).")
    return out


def cle_famille(types, familles: dict[str, str]) -> str:
    """Famille commune à des types, ou « mixte » s'ils relèvent de plusieurs familles (ou d'aucune)."""
    fams = {familles.get(t, MIXTE) for t in types}
    return next(iter(fams)) if len(fams) == 1 else MIXTE


# ── politiques de seuil ──────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SeuilFixe:
    """Même seuil et même écart pour toutes les familles."""
    seuil: float = 0.88
    ecart: float = 0.03

    def __post_init__(self):
        _valider(self.seuil, self.ecart, "SeuilFixe")

    def regle(self, cle: str) -> tuple[float, float] | None:
        return self.seuil, self.ecart

    def decrire(self) -> str:
        return f"seuil fixe {self.seuil:g}, écart {self.ecart:g}"


@dataclass(frozen=True)
class SeuilsCalibres:
    """Un seuil par famille, lu dans spec/seuils_fuzzy.yaml (R-RES-10). Une famille absente ou désactivée,
    et la clé « mixte », n'ont pas d'approché."""
    familles: dict = field(default_factory=dict)   # famille → (seuil, ecart) ou None (désactivé)
    empreinte: str = ""
    source: str = ""

    def regle(self, cle: str) -> tuple[float, float] | None:
        return None if cle == MIXTE else self.familles.get(cle)

    def decrire(self) -> str:
        actifs = sum(v is not None for v in self.familles.values())
        return f"seuils calibrés ({actifs} familles actives sur {len(self.familles)}, {self.source})"

    @classmethod
    def charger(cls, cat: Catalogue | None = None, chemin: Path = SEUILS) -> "SeuilsCalibres":
        """Lit le fichier de seuils. Avec `cat`, refuse des seuils calibrés sur un autre catalogue."""
        import yaml
        if not chemin.exists():
            raise FileNotFoundError(f"{chemin} introuvable : lancer python -m engine.calibration.")
        doc = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
        emp = str(doc.get("empreinte_catalogue", ""))
        if cat is not None and emp != cat.empreinte:
            raise ValueError(f"{chemin.name} : seuils calibrés sur le catalogue {emp or '?'}, catalogue chargé "
                             f"{cat.empreinte}. Recalibrer : python -m engine.calibration.")
        if "familles" not in doc:
            raise ValueError(f"{chemin.name} : clé « familles » absente (ancien format par type ?). "
                             "Recalibrer : python -m engine.calibration.")
        familles = {}
        for cle, v in (doc.get("familles") or {}).items():
            if v.get("fuzzy") == "desactive":
                familles[cle] = None
            elif v.get("fuzzy") == "actif":
                _valider(v["seuil"], v["ecart"], f"{chemin.name} · {cle}")
                familles[cle] = (float(v["seuil"]), float(v["ecart"]))
            else:
                raise ValueError(f"{chemin.name} · {cle} : fuzzy doit valoir actif ou desactive, "
                                 f"pas « {v.get('fuzzy')} ».")
        return cls(familles=familles, empreinte=emp, source=chemin.name)


def _valider(seuil, ecart, ou: str):
    if not 0 < float(seuil) <= 1:
        raise ValueError(f"{ou} : seuil {seuil} hors de ]0, 1].")
    if not 0 <= float(ecart) <= ECART_MAX:
        raise ValueError(f"{ou} : écart {ecart} hors de [0, {ECART_MAX}].")


# ── recherche des noms proches ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Proposition:
    """Résultat de la recherche approchée, indépendant du seuil."""
    score: float                              # κ : score du meilleur nom
    cle: str                                  # type des meilleurs noms (ou « mixte »)
    famille: str                              # famille des meilleurs noms (ou « mixte »)
    voisins: tuple[tuple[str, float], ...]    # noms à moins de ECART_MAX du meilleur, triés


class IndexApproche:
    """Noms comparables du catalogue, rangés par signature de mots à chiffres. Chaque terme est cherché
    deux fois, dans l'ordre d'origine et en mots triés, et les noms trouvés sont réunis."""

    def __init__(self, cat: Catalogue, familles: dict[str, str] | None = None, mots_tries: bool = True):
        """`mots_tries=False` ne sert qu'aux mesures avant/après : recherche dans l'ordre d'origine seulement."""
        self.cat = cat
        self.familles = familles if familles is not None else charger_familles(cat)
        self.mots_tries = mots_tries
        par_sig = defaultdict(list)
        for nom in sorted(cat.noms):
            par_sig[signature(nom)].append(nom)
        self.par_sig = dict(par_sig)
        self.tri_par_sig = {k: [cle_triee(n) for n in v] for k, v in self.par_sig.items()}
        self._types: dict[str, frozenset[str]] = {}

    def types_de(self, nom: str) -> frozenset[str]:
        t = self._types.get(nom)
        if t is None:
            t = self._types[nom] = frozenset(self.cat.etype[e] for e in self.cat.noms[nom])
        return t

    def _pool(self, norm: str, hint=None) -> tuple[list[str], list[str]]:
        """Noms comparables (même signature, type indiqué) et leurs formes en mots triés."""
        sig = signature(norm)
        pool, tri = self.par_sig.get(sig, []), self.tri_par_sig.get(sig, [])
        if hint:
            garde = [i for i, n in enumerate(pool) if self.types_de(n) & set(hint)]
            pool, tri = [pool[i] for i in garde], [tri[i] for i in garde]
        return pool, tri

    def _formes(self, norm: str, pool: list[str], tri: list[str]) -> list[tuple[str, list[str]]]:
        """Les deux recherches : terme contre noms, et mots triés contre mots triés."""
        return [(norm, pool), (cle_triee(norm), tri)] if self.mots_tries else [(norm, pool)]

    def _scores(self, norm: str, pool: list[str], tri: list[str], cutoff: float) -> dict[str, float]:
        """Score de chaque nom du pool ≥ cutoff : le meilleur de l'ordre d'origine et des mots triés."""
        out: dict[str, float] = {}
        for q, choix in self._formes(norm, pool, tri):
            for _, s, i in process.extract(q, choix, scorer=JaroWinkler.normalized_similarity, limit=None,
                                           score_cutoff=cutoff):
                if s > out.get(pool[i], -1.0):
                    out[pool[i]] = s
        return out

    def voisins_edition(self, norm: str, prop: "Proposition", hint=None) -> tuple[int, list[str]]:
        """R-RES-11 : distance d'édition entre le terme et le meilleur nom, et les autres noms comparables,
        d'un type des meilleurs noms, à une distance inférieure ou égale (ordre d'origine ou mots triés)."""
        tete = [n for n, s in prop.voisins if s >= prop.score]
        dist = distance if self.mots_tries else OSA.distance
        d = min(dist(norm, n) for n in tete)
        types = set().union(*(self.types_de(n) for n in tete))
        pool, tri = self._pool(norm, hint)
        garde = [i for i, n in enumerate(pool) if self.types_de(n) & types]
        pool, tri = [pool[i] for i in garde], [tri[i] for i in garde]
        out = set()
        for q, choix in self._formes(norm, pool, tri):
            for _, _, i in process.extract(q, choix, scorer=OSA.distance, score_cutoff=d, limit=None):
                out.add(pool[i])
        return d, sorted(out - set(tete))

    def proposer(self, norm: str, hint=None) -> tuple[Proposition | None, str]:
        """Meilleurs noms pour `norm`, ou None avec la raison du refus."""
        mots = norm.split()
        if len(norm.replace(" ", "")) < MIN_CARS:
            return None, f"moins de {MIN_CARS} caractères : pas d'approché (R-RES-03)"
        if all(a_chiffre(m) for m in mots):
            return None, "code ou nombre : jamais d'approché (R-RES-03)"
        pool, tri = self._pool(norm, hint)
        if not pool:
            return None, "aucun nom comparable (mêmes nombres, type indiqué)"
        s1 = max(process.extractOne(q, choix, scorer=JaroWinkler.normalized_similarity)[1]
                 for q, choix in self._formes(norm, pool, tri))
        scores = self._scores(norm, pool, tri, max(0.0, s1 - ECART_MAX))
        voisins = tuple(sorted(scores.items(), key=lambda x: (-x[1], x[0])))
        tete = set().union(*(self.types_de(n) for n, s in voisins if s >= s1))
        return Proposition(s1, cle_type(tete), cle_famille(tete, self.familles), voisins), ""
