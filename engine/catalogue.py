"""
Chargement du catalogue fusionné, une seule fois, en index en mémoire.

Le moteur ne lit que `catalog/entities.csv`, `aliases.csv`, `relations.csv` (via `Rules`) et
`negatifs.csv`. Les couches avant fusion (open_*, mecanova_*, glossaire_*) ne sont jamais lues.

La normalisation et les règles viennent de `build/` (R-RES-02 : la même normalisation partout) :
elles sont importées, jamais réimplémentées.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
if str(BUILD) not in sys.path:
    sys.path.insert(0, str(BUILD))

from common import CAT, console_utf8, normalize, read_csv  # noqa: E402, F401  (console_utf8 : réexport)
from rules import Rules  # noqa: E402

TIERS = frozenset({"1", "2", "3"})


def cle_triee(norm: str) -> str:
    """Forme « mots triés » d'un terme normalisé (R-RES-02, point 6)."""
    return " ".join(sorted(norm.split()))


@dataclass
class Catalogue:
    """Index du catalogue : forme normalisée → entités, mots triés → entités, index négatif."""
    etype: dict[str, str]
    label: dict[str, str]
    index: dict[str, frozenset[str]]
    index_trie: dict[str, frozenset[str]]
    negatifs: dict[str, tuple[str, str]]  # terme_norm → (terme, ressemble_a)
    regles: Rules
    tiers: frozenset[str] = field(default=TIERS)

    @classmethod
    def charger(cls, dossier: Path = CAT, tiers=TIERS) -> "Catalogue":
        """Charge le catalogue. `tiers` restreint les alias chargés (ex. {"1"} pour l'officiel seul)."""
        tiers = frozenset(str(t) for t in tiers)
        inconnus = tiers - TIERS
        if inconnus:
            raise ValueError(f"Tier inconnu {sorted(inconnus)} : valeurs permises 1, 2, 3 (colonne tier de aliases.csv).")
        ents = read_csv(dossier / "entities.csv")
        etype = {e["entity_id"]: e["entity_type"] for e in ents}
        label = {e["entity_id"]: e["label"] for e in ents}

        idx = defaultdict(set)
        for a in read_csv(dossier / "aliases.csv"):
            if a["tier"] not in tiers or not a["alias_norm"]:
                continue
            if a["entity_id"] not in etype:
                raise ValueError(f"aliases.csv : l'alias « {a['alias']} » renvoie à l'entité inconnue "
                                 f"{a['entity_id']} ; reconstruire le catalogue (build/build_merge.py).")
            idx[a["alias_norm"]].add(a["entity_id"])
        trie = defaultdict(set)
        for k, v in idx.items():
            trie[cle_triee(k)] |= v

        neg = {}
        for n in read_csv(dossier / "negatifs.csv"):
            if n["terme_norm"]:  # « Au » se normalise en vide : inutilisable
                neg.setdefault(n["terme_norm"], (n["terme"], n["ressemble_a"]))

        return cls(etype=etype, label=label,
                   index={k: frozenset(v) for k, v in idx.items()},
                   index_trie={k: frozenset(v) for k, v in trie.items()},
                   negatifs=neg, regles=Rules(dossier), tiers=tiers)

    @staticmethod
    def normaliser(texte: str) -> str:
        return normalize(texte)
