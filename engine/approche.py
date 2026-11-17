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
contexte tranchent ensuite. Le seuil et l'écart viennent d'une politique injectée :
  SeuilFixe(0.88, 0.03)          même seuil pour tous les types (valeur initiale de R-RES-03, provisoire) ;
  SeuilsCalibres.charger()       seuil par famille lu dans spec/seuils_fuzzy.yaml (calibration SGR, R-RES-10,
                                 engine/calibration.py) ; famille désactivée ou noms de plusieurs familles :
                                 pas d'approché ;
  AucunApproche()                jamais d'approché (configuration « exact seul », pour comparer).
Seul le choix du seuil change d'une politique à l'autre : recherche, écart, garde-fous et règles sont les mêmes.

Le « type » d'une proposition est celui des entités des meilleurs noms (score égal à κ) : un seul
type → ce type ; plusieurs → « mixte ». Il se calcule sans connaître la réponse. La proposition garde aussi
l'ensemble de ces types : une politique par famille en a besoin (deux types d'une même famille, comme
commune et localité postale, ne sont pas un mélange de familles).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import process
from rapidfuzz.distance import JaroWinkler

from engine.catalogue import ROOT, Catalogue

MIN_CARS = 4
ECART_MAX = 0.10          # borne de l'écart admis par une politique (recherche des voisins)
MIXTE = "mixte"


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


def cle_type(types) -> str:
    types = set(types)
    return next(iter(types)) if len(types) == 1 else MIXTE


# ── politiques de seuil ──────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SeuilFixe:
    """Même seuil et même écart pour tous les types."""
    seuil: float = 0.88
    ecart: float = 0.03

    def __post_init__(self):
        _valider(self.seuil, self.ecart, "SeuilFixe")

    def regle(self, cle: str, types: frozenset[str] = frozenset()) -> tuple[float, float] | None:
        return self.seuil, self.ecart

    def decrire(self) -> str:
        return f"seuil fixe {self.seuil:g}, écart {self.ecart:g}"


@dataclass(frozen=True)
class AucunApproche:
    """Jamais d'approché : configuration « exact seul » (exact, mots triés, index négatif)."""

    def regle(self, cle: str, types: frozenset[str] = frozenset()) -> tuple[float, float] | None:
        return None

    def decrire(self) -> str:
        return "exact seul (approché désactivé)"


SEUILS_FUZZY = ROOT / "spec" / "seuils_fuzzy.yaml"
FAMILLES_FUZZY = ROOT / "spec" / "familles_fuzzy.yaml"


@dataclass(frozen=True)
class SeuilsCalibres:
    """Seuil par famille (R-RES-10), lu dans spec/seuils_fuzzy.yaml (écrit par engine/calibration.py).

    La famille d'une proposition est celle des types des meilleurs noms (spec/familles_fuzzy.yaml) ;
    plusieurs familles, un type hors famille ou une famille désactivée (seuil null) → pas d'approché."""
    seuils: dict = field(default_factory=dict)       # famille → seuil (None : désactivée)
    ecart: float = 0.03
    famille_de: dict = field(default_factory=dict)   # type → famille

    def __post_init__(self):
        for f, t in self.seuils.items():
            if t is not None:
                _valider(t, self.ecart, f"SeuilsCalibres · {f}")

    @classmethod
    def charger(cls, chemin: Path = SEUILS_FUZZY, familles: Path = FAMILLES_FUZZY) -> "SeuilsCalibres":
        import yaml
        if not chemin.exists():
            raise FileNotFoundError(f"{chemin} introuvable : lancer python -m engine.calibration.")
        y = yaml.safe_load(chemin.read_text(encoding="utf-8"))
        fam = yaml.safe_load(familles.read_text(encoding="utf-8"))["familles"]
        famille_de = {t: f for f, ts in fam.items() for t in ts}
        seuils = {}
        for f, v in y["familles"].items():
            if f not in fam:
                raise ValueError(f"{chemin.name} : famille « {f} » absente de {familles.name}.")
            seuils[f] = v["seuil_final"]
        manquantes = set(fam) - set(seuils)
        if manquantes:
            raise ValueError(f"{chemin.name} : famille(s) sans seuil {sorted(manquantes)} ; relancer la calibration.")
        return cls(seuils=seuils, ecart=float(y["parametres"]["ecart"]), famille_de=famille_de)

    def famille(self, types) -> str | None:
        fams = {self.famille_de.get(t) for t in types}
        return next(iter(fams)) if len(fams) == 1 and None not in fams else None

    def regle(self, cle: str, types: frozenset[str] = frozenset()) -> tuple[float, float] | None:
        f = self.famille(types or ({cle} if cle != MIXTE else set()))
        if f is None or self.seuils.get(f) is None:
            return None
        return self.seuils[f], self.ecart

    def decrire(self) -> str:
        return "seuils calibrés par famille (R-RES-10) : " + ", ".join(
            f"{f} {'désactivé' if t is None else f'{t:g}'}" for f, t in sorted(self.seuils.items()))


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
    voisins: tuple[tuple[str, float], ...]    # noms à moins de ECART_MAX du meilleur, triés
    types: frozenset = frozenset()            # types des meilleurs noms (pour une politique par famille)


class IndexApproche:
    """Noms comparables du catalogue, rangés par signature de mots à chiffres."""

    def __init__(self, cat: Catalogue):
        self.cat = cat
        par_sig = defaultdict(list)
        for nom in sorted(cat.noms):
            par_sig[signature(nom)].append(nom)
        self.par_sig = dict(par_sig)

    def types_de(self, nom: str) -> set[str]:
        return {self.cat.etype[e] for e in self.cat.noms[nom]}

    def proposer(self, norm: str, hint=None) -> tuple[Proposition | None, str]:
        """Meilleurs noms pour `norm`, ou None avec la raison du refus."""
        mots = norm.split()
        if len(norm.replace(" ", "")) < MIN_CARS:
            return None, f"moins de {MIN_CARS} caractères : pas d'approché (R-RES-03)"
        if all(a_chiffre(m) for m in mots):
            return None, "code ou nombre : jamais d'approché (R-RES-03)"
        pool = self.par_sig.get(signature(norm), [])
        if hint:
            pool = [n for n in pool if self.types_de(n) & set(hint)]
        if not pool:
            return None, "aucun nom comparable (mêmes nombres, type indiqué)"
        _, s1, _ = process.extractOne(norm, pool, scorer=JaroWinkler.normalized_similarity)
        res = process.extract(norm, pool, scorer=JaroWinkler.normalized_similarity, limit=None,
                              score_cutoff=max(0.0, s1 - ECART_MAX))
        voisins = tuple(sorted(((n, s) for n, s, _ in res), key=lambda x: (-x[1], x[0])))
        tete = set().union(*(self.types_de(n) for n, s in voisins if s >= s1))
        return Proposition(s1, cle_type(tete), voisins, frozenset(tete)), ""
