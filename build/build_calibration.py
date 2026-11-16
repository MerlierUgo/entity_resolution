"""
Jeux de cas dédiés à la calibration de l'étape approchée (R-RES-10), en deux fichiers séparés :

    python build/build_calibration.py

  challenges/calibration_analyse.csv  pour CONCEVOIR : diagnostic des pertes, règles de structure
                                      (python -m engine.diagnostic_fuzzy) ;
  challenges/calibration_certif.csv   pour CERTIFIER seulement : python -m engine.calibration y calcule θ.
                                      On n'en regarde jamais les erreurs, sinon la garantie de SGR ne
                                      vaut plus (le seuil serait réglé sur les données qui le certifient).

Les deux fichiers sont tirés par le même générateur avec deux graines différentes (GRAINE_ANALYSE,
GRAINE_CERTIF), le même volume visé, et aucun terme normalisé commun : le jeu d'analyse est construit
d'abord, ses termes sont exclus du jeu de certification. Les noms sources du catalogue, eux, peuvent
être les mêmes : les fautes futures porteront aussi sur des noms déjà vus.

Pourquoi un jeu dédié : le banc d'essai (cases.csv) n'a que quelques dizaines de fautes de frappe par
type, alors qu'une garantie r* = 0,5 % à 95 % demande ≈ 1 200 réponses approchées sans erreur par
famille (engine/calibration.py · n_minimum). Ce fichier ne remplace ni cases.csv ni split.csv, et ne
modifie pas le catalogue.

Deux natures de cas, par famille de spec/familles_fuzzy.yaml :

  present  un nom du catalogue avec 1 ou 2 fautes de frappe réalistes (substitution, omission,
           insertion, transposition, touche voisine AZERTY, lettre doublée, accent ou trait d'union
           manquant). Réponse attendue : celle du résolveur exact sur le nom d'origine (mêmes
           entités, même statut : une faute ne doit rien changer).
  absent   un terme qui n'est pas dans le catalogue : faute de frappe sur un terme de l'index
           négatif (« Pariss »), nom recombiné à partir de deux noms de la famille
           (« Saint-Georges-sur-Ourthe »), ou marque réelle absente du catalogue. Réponse attendue :
           unknown. Ce sont eux qui mesurent les noms acceptés à tort.

Chaque cas ATTEINT l'étape approchée : la recherche exacte (alias, mots triés) ne le trouve pas,
l'index négatif ne le contient pas, et les garde-fous d'entrée de R-RES-03 (4 caractères, pas un code,
au moins un nom comparable) le laissent passer. Sinon il ne servirait à rien pour calibrer.

Règles :
  - aucune entité de la partition test de split.csv (identifiants attendus des cas test seulement,
    ni texte ni question humaine) : ni dans la réponse attendue, ni comme matériau d'un absent ;
  - perturbations seulement sur des mots d'au moins 4 lettres sans chiffre, jamais sur un alias de
    type code (ALIAS_CODES) ;
  - au plus MAX_PAR_NOM cas par nom source, pour que les cas restent à peu près indépendants ;
  - graine fixe, sortie triée, CSV utf-8-sig.
"""
from __future__ import annotations

import math
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.approche import IndexApproche, charger_familles  # noqa: E402
from engine.catalogue import ALIAS_CODES, CAT, Catalogue, console_utf8, read_csv  # noqa: E402
from engine.resolveur import UNKNOWN, ResolveurExact  # noqa: E402
from common import write_csv  # noqa: E402

GRAINE = GRAINE_ANALYSE = 20261113
GRAINE_CERTIF = 20261127
PRESENTS_VISES = 3000      # par famille et par fichier, quand le catalogue le permet (≈ 1 200 acceptés sans erreur visés)
PRESENTS_MIN = 1300
PART_ABSENTS = 0.25        # part des absents dans le total d'une famille (au moins 20 %)
MAX_PAR_NOM = 3
ESSAIS = 8                 # tirages de perturbation par emplacement avant d'abandonner
ANALYSE = ROOT / "challenges" / "calibration_analyse.csv"
CERTIF = ROOT / "challenges" / "calibration_certif.csv"
SORTIES = {"analyse": (ANALYSE, GRAINE_ANALYSE), "certif": (CERTIF, GRAINE_CERTIF)}
CHAMPS = ["case_id", "famille", "entity_type_attendu", "terme", "attendu", "statut_attendu", "nature",
          "perturbation", "alias_source"]

# Marques réelles plausibles pour un distributeur de pièces ; on ne garde que celles absentes du
# catalogue et de l'index négatif (vérifié à la construction).
MARQUES_REELLES = sorted({
    "Ajusa", "Ashika", "Banner", "Bilstein", "Blue Print", "Brembo", "Bridgestone", "Castrol", "Contitech",
    "Corteco", "Dayco", "Denso", "Dunlop", "Eibach", "Elring", "Febi", "Ferodo", "Fulmen", "Goodyear",
    "Hankook", "Japanparts", "Jurid", "Kayaba", "Koni", "Lesjofors", "Liqui Moly", "Magneti Marelli",
    "Meyle", "Mintex", "Monroe", "Motul", "Optibelt", "Osram", "Payen", "Philips", "Pirelli", "Ravenol",
    "Ridex", "Textar", "Timken", "Tudor", "Victor Reinz", "Yuasa", "Lancia", "Proton", "Mahindra",
    "Chery", "Geely", "Polestar", "Rivian", "Lucid", "Genesis", "Infiniti", "Acura", "Cadillac", "Buick",
    "Chrysler", "Lincoln", "Holden", "Vauxhall", "Daewoo", "Saab", "Rover", "Lada", "Tata", "Xpeng",
    "Zeekr", "Lynk", "Aiways", "Ssangyong", "Isuzu", "Daihatsu", "Uaz", "Wartburg", "Trabant",
})

# ── perturbations ────────────────────────────────────────────────────────────────────────────────

LETTRES = "abcdefghijklmnopqrstuvwxyz"
_RANGS = ["azertyuiop", "qsdfghjklm", "wxcvbn"]


def _voisins_azerty() -> dict[str, str]:
    pos = {c: (r, i) for r, rang in enumerate(_RANGS) for i, c in enumerate(rang)}
    out = {}
    for c, (r, i) in pos.items():
        cand = [(r, i - 1), (r, i + 1), (r - 1, i), (r - 1, i + 1), (r + 1, i), (r + 1, i - 1)]
        out[c] = "".join(_RANGS[a][b] for a, b in cand if 0 <= a < 3 and 0 <= b < len(_RANGS[a]))
    return out


AZERTY = _voisins_azerty()


def sans_accent(c: str) -> str:
    return "".join(x for x in unicodedata.normalize("NFKD", c) if not unicodedata.combining(x))


def _casse(modele: str, c: str) -> str:
    return c.upper() if modele.isupper() else c


def positions(texte: str) -> list[int]:
    """Indices des lettres perturbables : dans un mot (suite sans espace) sans chiffre et d'au moins
    4 lettres."""
    out = []
    for m in re.finditer(r"\S+", texte):
        mot = m.group()
        if any(c.isdigit() for c in mot) or sum(c.isalpha() for c in mot) < 4:
            continue
        out += [m.start() + i for i, c in enumerate(mot) if c.isalpha()]
    return out


def _subst(t, i, rng):
    c = rng.choice([x for x in LETTRES if x != sans_accent(t[i]).lower()])
    return t[:i] + _casse(t[i], c) + t[i + 1:]


def _omission(t, i, rng):
    return t[:i] + t[i + 1:]


def _insertion(t, i, rng):
    return t[:i] + _casse(t[i], rng.choice(LETTRES)) + t[i:]


def _doublee(t, i, rng):
    return t[:i] + t[i] + t[i:]


def _clavier(t, i, rng):
    base = sans_accent(t[i]).lower()
    if base not in AZERTY:
        return None
    return t[:i] + _casse(t[i], rng.choice(AZERTY[base])) + t[i + 1:]


def _transposition(t, i, rng):
    if i + 1 >= len(t) or not t[i + 1].isalpha() or t[i].lower() == t[i + 1].lower():
        return None
    return t[:i] + t[i + 1] + t[i] + t[i + 2:]


OPS_LETTRE = {"substitution": (_subst, 3), "omission": (_omission, 2), "insertion": (_insertion, 2),
              "transposition": (_transposition, 2), "clavier_azerty": (_clavier, 3),
              "lettre_doublee": (_doublee, 2)}


def perturber(texte: str, rng: random.Random) -> tuple[str, str] | None:
    """1 perturbation (70 %) ou 2 (30 %). Renvoie (texte perturbé, noms des perturbations) ou None."""
    n = 1 if rng.random() < 0.7 else 2
    noms = []
    for _ in range(n):
        pos = positions(texte)
        if not pos:
            return None
        ops = list(OPS_LETTRE.items())
        accents = [i for i in pos if sans_accent(texte[i]) != texte[i]]
        if accents:
            ops.append(("accent_manquant", (None, 1)))
        tirets = [m.start() for m in re.finditer(r"(?<=[^\W\d_])-(?=[^\W\d_])", texte)]
        if tirets:
            ops.append(("trait_union_manquant", (None, 1)))
        nom = rng.choices([o for o, _ in ops], weights=[w for _, (_, w) in ops])[0]
        if nom == "accent_manquant":
            i = rng.choice(accents)
            nouveau = texte[:i] + sans_accent(texte[i]) + texte[i + 1:]
        elif nom == "trait_union_manquant":
            i = rng.choice(tirets)
            nouveau = texte[:i] + texte[i + 1:]       # « Saint-Georges » → « SaintGeorges »
        else:
            nouveau = OPS_LETTRE[nom][0](texte, rng.choice(pos), rng)
        if not nouveau or nouveau == texte:
            return None
        texte = nouveau
        noms.append(nom)
    return texte, "+".join(noms)


# ── données ──────────────────────────────────────────────────────────────────────────────────────

def entites_test(chal: Path = ROOT / "challenges") -> set[str]:
    """Identifiants d'entités attendus par les cas de la partition test (aucun texte n'est lu)."""
    split = {r["case_id"]: r["split"] for r in read_csv(chal / "split.csv")}
    out = set()
    for c in read_csv(chal / "cases.csv"):
        if split.get(c["case_id"]) == "test":
            out |= set(filter(None, c["expected_ids"].split("|")))
    return out


class Generateur:
    def __init__(self, cat: Catalogue, interdits: set[str], graine: int = GRAINE, vus: set[str] | None = None):
        self.cat = cat
        self.familles = charger_familles(cat)
        self.exact = ResolveurExact(cat)
        self.index = IndexApproche(cat, self.familles)
        self.interdits = interdits
        self.graine = graine
        self.vus: set[str] = set() if vus is None else vus   # formes normalisées déjà utilisées (partagé entre fichiers)
        self.par_negatif: Counter = Counter()   # cas déjà tirés par terme de l'index négatif (tous appels confondus)
        self._sources()

    def _sources(self):
        """Par famille : noms sources (forme normalisée → texte d'origine), hors codes et hors test."""
        brut = defaultdict(set)
        for a in read_csv(CAT / "aliases.csv"):
            if a["alias_type"] not in ALIAS_CODES and a["alias_norm"] and a["tier"] in self.cat.tiers:
                brut[a["alias_norm"]].add(a["alias"])
        self.sources: dict[str, dict[str, str]] = defaultdict(dict)
        for norm, textes in sorted(brut.items()):
            ents = self.cat.noms.get(norm, frozenset())
            if not ents or ents & self.interdits or len(norm.replace(" ", "")) < 4:
                continue
            fams = {self.familles[self.cat.etype[e]] for e in ents}
            if len(fams) != 1:
                continue                         # nom partagé entre familles (Champion…) : famille ambiguë
            texte = next((t for t in sorted(textes) if positions(t)), None)
            if texte:
                self.sources[fams.pop()][norm] = texte

    def atteint_approche(self, norm: str) -> bool:
        if not norm or norm in self.vus or norm in self.cat.negatifs:
            return False
        if self.exact.candidats_exacts(norm)[0]:
            return False
        return self.index.proposer(norm)[0] is not None

    # ── présents
    def presents(self, famille: str, vise: int) -> list[dict]:
        rng = random.Random(f"{self.graine}:present:{famille}")
        noms = sorted(self.sources[famille])
        rng.shuffle(noms)
        attendus = {}
        out = []
        for _tour in range(MAX_PAR_NOM):
            for norm in noms:
                if len(out) >= vise:
                    return out
                if norm not in attendus:
                    res = self.exact.resoudre(self.sources[famille][norm])
                    ok = res.statut != UNKNOWN and not set(res.ids) & self.interdits
                    attendus[norm] = res if ok else None
                res = attendus[norm]
                if res is None:
                    continue
                for _ in range(ESSAIS):
                    p = perturber(self.sources[famille][norm], rng)
                    if p is None:
                        continue
                    terme, pert = p
                    n2 = self.cat.normaliser(terme)
                    if n2 != norm and self.atteint_approche(n2):
                        self.vus.add(n2)
                        out.append({"famille": famille, "terme": terme, "attendu": "|".join(res.ids),
                                    "statut_attendu": res.statut, "nature": "present", "perturbation": pert,
                                    "alias_source": self.sources[famille][norm],
                                    "entity_type_attendu": "|".join(sorted({self.cat.etype[e] for e in
                                                                             self.cat.noms[norm]}))})
                        break
        return out

    # ── absents
    def _absent(self, famille, terme, pert, source) -> dict:
        return {"famille": famille, "terme": terme, "attendu": "", "statut_attendu": UNKNOWN, "nature": "absent",
                "perturbation": pert, "alias_source": source, "entity_type_attendu": ""}

    def negatifs_de(self, famille: str) -> list[str]:
        cible = {"lieu": "geographie", "pays": "geographie", "marque": "marques", "site": "vocabulaire_metier"}
        return sorted({t for t, r in self.cat.negatifs.values() if cible.get(r) == famille and positions(t)})

    def fautes_negatif(self, famille: str, vise: int, rng: random.Random) -> list[dict]:
        termes = self.negatifs_de(famille)
        rng.shuffle(termes)
        out = []
        for _tour in range(MAX_PAR_NOM):
            for t in termes:
                if len(out) >= vise:
                    return out
                if self.par_negatif[(famille, t)] >= MAX_PAR_NOM:
                    continue          # fonction appelée deux fois par famille : la limite vaut pour les deux
                for _ in range(ESSAIS):
                    p = perturber(t, rng)
                    if p and self.atteint_approche(n2 := self.cat.normaliser(p[0])):
                        self.vus.add(n2)
                        self.par_negatif[(famille, t)] += 1
                        out.append(self._absent(famille, p[0], "faute_index_negatif:" + p[1], t))
                        break
        return out

    def recombines(self, famille: str, vise: int, rng: random.Random) -> list[dict]:
        """Remplace un mot (≥ 4 lettres, sans chiffre) d'un nom par un mot d'un autre nom de la famille."""
        textes = sorted(self.sources[famille].values())
        mots = sorted({m for t in textes for m in t.split() if positions(m) and len(positions(m)) == len(
            [c for c in m if c.isalpha()])})
        multi = [t for t in textes if len(t.split()) >= 2]
        rng.shuffle(multi)
        out = []
        if not mots:
            return out
        for _tour in range(MAX_PAR_NOM):
            for t in multi:
                if len(out) >= vise:
                    return out
                parts = t.split()
                cand = [i for i, m in enumerate(parts) if positions(m)]
                if not cand:
                    continue
                for _ in range(ESSAIS):
                    i, m = rng.choice(cand), rng.choice(mots)
                    if self.cat.normaliser(m) == self.cat.normaliser(parts[i]):
                        continue
                    terme = " ".join(parts[:i] + [m] + parts[i + 1:])
                    if self.atteint_approche(n2 := self.cat.normaliser(terme)):
                        self.vus.add(n2)
                        out.append(self._absent(famille, terme, "nom_recombine", f"{t} ⊕ {m}"))
                        break
        return out

    def marques_reelles(self, vise: int, rng: random.Random) -> list[dict]:
        out = []
        valides = [m for m in MARQUES_REELLES if self.atteint_approche(self.cat.normaliser(m))]
        for m in valides:
            if len(out) >= vise:
                return out
            self.vus.add(self.cat.normaliser(m))
            out.append(self._absent("marques", m, "marque_reelle_hors_catalogue", m))
        for _tour in range(MAX_PAR_NOM - 1):       # le nom exact compte pour un des MAX_PAR_NOM cas
            for m in valides:
                if len(out) >= vise:
                    return out
                for _ in range(ESSAIS):
                    p = perturber(m, rng)
                    if p and self.atteint_approche(n2 := self.cat.normaliser(p[0])):
                        self.vus.add(n2)
                        out.append(self._absent("marques", p[0], "marque_reelle_hors_catalogue:" + p[1], m))
                        break
        return out

    def absents(self, famille: str, vise: int) -> list[dict]:
        rng = random.Random(f"{self.graine}:absent:{famille}")
        out = []
        if self.negatifs_de(famille):
            out += self.fautes_negatif(famille, math.ceil(vise / 2), rng)
        if famille == "marques":
            out += self.marques_reelles(vise - len(out), rng)
        out += self.recombines(famille, vise - len(out), rng)
        if len(out) < vise and self.negatifs_de(famille):
            out += self.fautes_negatif(famille, vise - len(out), rng)   # compléter si la recombinaison manque
        return out[:vise]


def construire(cat: Catalogue | None = None, vise: int = PRESENTS_VISES, graine: int = GRAINE,
               interdits: set[str] | None = None, vus: set[str] | None = None,
               prefixe: str = "CAL") -> tuple[list[dict], dict]:
    """Cas de calibration triés par case_id, et bilan par famille. `vus` : termes normalisés à exclure
    (ceux d'un autre fichier), complété au passage."""
    cat = cat or Catalogue.charger()
    g = Generateur(cat, entites_test() if interdits is None else interdits, graine, vus)
    lignes, bilan = [], {}
    for fam in sorted(set(g.familles.values())):
        pres = g.presents(fam, vise)
        n_abs = math.ceil(len(pres) * PART_ABSENTS / (1 - PART_ABSENTS))
        abs_ = g.absents(fam, n_abs)
        bilan[fam] = {"noms_sources": len(g.sources[fam]), "presents": len(pres), "absents": len(abs_),
                      "absents_vises": n_abs}
        cles = lambda r: (r["nature"], g.cat.normaliser(r["terme"]), r["terme"])  # noqa: E731
        lignes += sorted(pres, key=cles) + sorted(abs_, key=cles)
    for i, r in enumerate(lignes, 1):
        r["case_id"] = f"{prefixe}-{i:05d}"
    return lignes, bilan


def construire_tout(cat: Catalogue | None = None, vise: int = PRESENTS_VISES,
                    interdits: set[str] | None = None) -> dict[str, tuple[list[dict], dict]]:
    """Les deux jeux, analyse puis certification, sans terme normalisé commun."""
    cat = cat or Catalogue.charger()
    interdits = entites_test() if interdits is None else interdits
    vus: set[str] = set()
    return {nom: construire(cat, vise, graine, interdits, vus, "CAL-A" if nom == "analyse" else "CAL-C")
            for nom, (_, graine) in SORTIES.items()}


def main() -> int:
    console_utf8()
    for nom, (lignes, bilan) in construire_tout().items():
        chemin = SORTIES[nom][0]
        write_csv(chemin, lignes, CHAMPS, sort_keys=["case_id"])
        print(f"\n{len(lignes)} cas → {chemin.relative_to(ROOT)} (graine {SORTIES[nom][1]})")
        imprimer(lignes, bilan)
    return 0


def imprimer(lignes: list[dict], bilan: dict) -> None:
    print(f"{'famille':<20} {'noms':>6} {'présents':>9} {'absents':>8}  part abs.")
    for fam, b in bilan.items():
        tot = b["presents"] + b["absents"]
        alerte = "" if b["presents"] >= PRESENTS_MIN else f"  ⚠ sous {PRESENTS_MIN} présents : restera sans fuzzy"
        if b["absents"] < b["absents_vises"]:
            alerte += f"  ⚠ {b['absents']}/{b['absents_vises']} absents"
        print(f"{fam:<20} {b['noms_sources']:>6} {b['presents']:>9} {b['absents']:>8}  "
              f"{100 * b['absents'] / tot if tot else 0:5.1f} %{alerte}")
    pert = Counter(p for r in lignes if r["nature"] == "present" for p in r["perturbation"].split("+"))
    print("perturbations (présents) :", ", ".join(f"{k} {v}" for k, v in pert.most_common()))


if __name__ == "__main__":
    sys.exit(main())
