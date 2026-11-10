"""
Étape 1 du moteur : résolveur exact (aucun LLM, aucune correspondance approchée).

Chaîne, pour un terme (R-RES-01, sans l'étape approchée) :

  1. normalisation (R-RES-02, `build/common.py · normalize()`) ;
  2. alias exact sur la forme normalisée, et alias exact sur les mots triés (R-RES-02, point 6) ;
     les deux ensembles sont réunis, comme pour la vérité terrain du banc d'essai ;
  3. si rien n'est trouvé : index négatif (R-RES-07) → unknown, avec la raison dans la trace ;
     une valeur du catalogue l'emporte toujours sur l'index négatif, qui n'est donc consulté qu'après ;
  4. règles de la spec (`build/rules.py · Rules.apply`) : R-GEO-02, R-CTX-05, R-ART-03, puis l'indice
     de type R-RES-09 ;
  5. statut : une entité → resolved, plusieurs → ambiguous, aucune → unknown (R-RES-05 : jamais de
     « candidat le plus probable »).

Chaque résolution porte une trace : la liste des étapes franchies, avec ce qu'elles ont trouvé,
ajouté ou retiré, et la règle appliquée.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engine.approche import IndexApproche, SeuilFixe, compatible
from engine.catalogue import Catalogue, cle_triee

RESOLVED, AMBIGUOUS, UNKNOWN = "resolved", "ambiguous", "unknown"


@dataclass(frozen=True)
class Resolution:
    terme: str
    norm: str
    statut: str
    ids: tuple[str, ...]          # triés : sortie déterministe
    trace: tuple[dict, ...] = field(default=())

    @property
    def etape(self) -> str:
        """Étape qui a décidé : exact, mots_tries, index_negatif, approche, absent ou vide."""
        return next((t["etape"] for t in self.trace if t.get("decisive")), "")


def _hint_set(hint) -> frozenset[str] | None:
    if not hint:
        return None
    return frozenset({hint} if isinstance(hint, str) else hint)


def _regle_de(eid: str, etype: str, ajoute: bool) -> str:
    """Règle responsable d'une entité ajoutée ou retirée par Rules.apply (sans indice de type)."""
    if etype == "site" and ajoute:
        return "R-CTX-05"
    if etype in ("localite_postale", "commune"):
        return "R-GEO-02"
    if etype == "categorie_piece" and not ajoute:
        return "R-ART-03"
    return "R-?"  # garde-fou : une règle nouvelle de rules.py n'est pas encore attribuée


def _diff_regles(cat: Catalogue, avant: set[str], apres: set[str], regle: str | None = None) -> list[dict]:
    """Étapes de trace décrivant ce qu'une passe de règles a ajouté ou retiré."""
    out = []
    for eid in sorted(apres - avant):
        out.append({"etape": "regle", "regle": regle or _regle_de(eid, cat.etype[eid], True),
                    "action": "ajoute", "id": eid})
    for eid in sorted(avant - apres):
        out.append({"etape": "regle", "regle": regle or _regle_de(eid, cat.etype[eid], False),
                    "action": "retire", "id": eid})
    return out


class ResolveurExact:
    """Résolveur de l'étape 1. Pur et déterministe : même terme et même indice → même Resolution."""

    def __init__(self, catalogue: Catalogue):
        self.cat = catalogue

    def candidats_exacts(self, norm: str) -> tuple[set[str], list[dict]]:
        """Alias exact puis mots triés. Renvoie les candidats bruts et les étapes de trace."""
        exact = set(self.cat.index.get(norm, ()))
        trie = set(self.cat.index_trie.get(cle_triee(norm), ())) - exact
        trace = [{"etape": "exact", "trouves": len(exact)}]
        if trie:
            trace.append({"etape": "mots_tries", "cle": cle_triee(norm), "trouves": len(trie)})
        return exact | trie, trace

    def approcher(self, norm: str, hint, trace: list[dict]) -> set[str]:
        """Étape approchée : aucune à l'étape 1. Ajoute à la trace l'étape décisive « absent »."""
        trace.append({"etape": "absent", "decisive": True, "raison": "aucun alias du catalogue"})
        return set()

    def resoudre(self, terme: str, hint=None, index_negatif: bool = True) -> Resolution:
        """Résout un terme. `hint` : type d'entité attendu (str) ou ensemble de types (R-RES-09).

        `index_negatif=False` ne sert qu'à la calibration et aux tests de robustesse : il simule un
        terme hors périmètre que l'index négatif ne connaît pas encore."""
        hint = _hint_set(hint)
        norm = self.cat.normaliser(terme)
        trace: list[dict] = [{"etape": "normalisation", "norm": norm}]

        if not norm:
            trace.append({"etape": "vide", "decisive": True,
                          "raison": "terme vide après normalisation (mots vides ou ponctuation seule)"})
            return Resolution(terme, norm, UNKNOWN, (), tuple(trace))

        bruts, t = self.candidats_exacts(norm)
        trace += t
        if not bruts:
            neg = self.cat.negatifs.get(norm) if index_negatif else None
            if neg:
                trace.append({"etape": "index_negatif", "regle": "R-RES-07", "decisive": True,
                              "terme": neg[0], "ressemble_a": neg[1],
                              "raison": f"valeur plausible connue comme absente ({neg[1]})"})
                return Resolution(terme, norm, UNKNOWN, (), tuple(trace))
            bruts = self.approcher(norm, hint, trace)
            if not bruts:
                return Resolution(terme, norm, UNKNOWN, (), tuple(trace))
        else:
            trace[-1]["decisive"] = True
        trace.append({"etape": "candidats_bruts", "ids": sorted(bruts)})
        sans_hint = self.cat.regles.apply(set(bruts))
        trace += _diff_regles(self.cat, bruts, sans_hint)
        hits = sans_hint
        if hint:
            hits = self.cat.regles.apply(set(bruts), set(hint))
            trace += _diff_regles(self.cat, sans_hint, hits, "R-RES-09")
            if not {h for h in hits if self.cat.etype[h] in hint}:
                trace.append({"etape": "indice_type", "regle": "R-RES-09", "hint": sorted(hint),
                              "raison": "aucun candidat du type indiqué : indice ignoré"})
        statut = self.cat.regles.status(hits)
        trace.append({"etape": "statut", "statut": statut, "n": len(hits)})
        return Resolution(terme, norm, statut, tuple(sorted(hits)), tuple(trace))


class ResolveurApproche(ResolveurExact):
    """Résolveur de l'étape 2 : l'étape 1, puis Jaro-Winkler borné si rien n'est trouvé (R-RES-03).

    `politique` fixe le seuil et l'écart par type : SeuilFixe(0.88, 0.03) ou SeuilsCalibres."""

    def __init__(self, catalogue: Catalogue, politique=None, index: IndexApproche | None = None):
        super().__init__(catalogue)
        self.politique = politique if politique is not None else SeuilFixe()
        self.index = index or IndexApproche(catalogue)

    def approcher(self, norm: str, hint, trace: list[dict]) -> set[str]:
        prop, raison = self.index.proposer(norm, hint)
        if prop is None:
            trace.append({"etape": "absent", "decisive": True, "raison": f"aucun alias du catalogue ; {raison}"})
            return set()
        etape = {"etape": "approche", "regle": "R-RES-03", "score": prop.score, "type": prop.cle,
                 "meilleurs": [n for n, s in prop.voisins[:5]]}
        regle = self.politique.regle(prop.cle)
        if regle is None:
            trace.append({**etape, "etape": "absent", "decisive": True,
                          "raison": f"approché désactivé pour le type {prop.cle} ({self.politique.decrire()})"})
            return set()
        seuil, ecart = regle
        etape.update(seuil=seuil, ecart=ecart)
        if prop.score < seuil:
            trace.append({**etape, "etape": "absent", "decisive": True,
                          "raison": f"meilleur nom à {prop.score:.3f}, sous le seuil {seuil:g}"})
            return set()
        noms = [n for n, s in prop.voisins if s >= prop.score - ecart]
        refuses = [n for n in noms if not compatible(norm, n)]
        if refuses:
            trace.append({**etape, "etape": "absent", "decisive": True, "noms": noms,
                          "raison": f"garde-fou : « {refuses[0]} » n'a pas les mêmes mots courts ou le même "
                                    "nombre de mots (R-RES-03)"})
            return set()
        bruts = set().union(*(self.cat.noms[n] for n in noms))
        trace.append({**etape, "decisive": True, "noms": noms, "trouves": len(bruts)})
        return bruts
