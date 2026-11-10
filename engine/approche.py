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
  SeuilFixe(0.88, 0.03)          même seuil pour tous les types (valeur initiale de R-RES-03) ;
  SeuilsCalibres.charger(cat)    un seuil par type, calibré par engine/calibration.py (SGR).

Le « type » d'une proposition est celui des entités des meilleurs noms (score égal à κ) : un seul
type → ce type ; plusieurs → « mixte ». Il se calcule sans connaître la réponse.
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
SEUILS = ROOT / "spec" / "seuils_fuzzy.yaml"


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

    def regle(self, cle: str) -> tuple[float, float] | None:
        return self.seuil, self.ecart

    def decrire(self) -> str:
        return f"seuil fixe {self.seuil:g}, écart {self.ecart:g}"


@dataclass(frozen=True)
class SeuilsCalibres:
    """Un seuil par type, lu dans spec/seuils_fuzzy.yaml. Un type absent ou désactivé : pas d'approché."""
    types: dict = field(default_factory=dict)   # cle → (seuil, ecart) ou None (désactivé)
    empreinte: str = ""
    source: str = ""

    def regle(self, cle: str) -> tuple[float, float] | None:
        return self.types.get(cle)

    def decrire(self) -> str:
        actifs = sum(v is not None for v in self.types.values())
        return f"seuils calibrés ({actifs} types actifs sur {len(self.types)}, {self.source})"

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
        types = {}
        for cle, v in (doc.get("types") or {}).items():
            if v.get("fuzzy") == "desactive":
                types[cle] = None
            elif v.get("fuzzy") == "actif":
                _valider(v["seuil"], v["ecart"], f"{chemin.name} · {cle}")
                types[cle] = (float(v["seuil"]), float(v["ecart"]))
            else:
                raise ValueError(f"{chemin.name} · {cle} : fuzzy doit valoir actif ou desactive, "
                                 f"pas « {v.get('fuzzy')} ».")
        return cls(types=types, empreinte=emp, source=chemin.name)


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
        return Proposition(s1, cle_type(tete), voisins), ""
