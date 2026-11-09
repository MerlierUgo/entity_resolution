"""
Questions humaines : un seul fichier source, human/questions.csv, que l'auteur remplit (Excel ou éditeur).

Principes
  - Le texte d'une question est IMMUABLE une fois enregistré : son empreinte SHA-256 est inscrite dans
    human/questions.lock. Pour changer une question, on la retire (etat = retiree) et on en ajoute une nouvelle.
  - Un identifiant n'est jamais réutilisé, même après retrait.
  - Toutes les références (entités, mesures, axes, lacunes) sont contrôlées contre le catalogue et la spec.

Commandes
  python build/human_questions.py check                 contrôle complet ; code de sortie 1 en cas d'erreur
  python build/human_questions.py add "texte" [--split test|dev] [--auteur NOM]
                                                        ajoute une question (identifiant suivant, empreinte enregistrée)
  python build/human_questions.py lock                  enregistre l'empreinte des questions ajoutées à la main
                                                        dans le fichier (les questions déjà enregistrées ne bougent pas)

Format du fichier : CSV UTF-8, séparateur « ; » (celui d'Excel en français). Le séparateur « , » est aussi
accepté en lecture. Dans Excel : Fichier > Enregistrer sous > « CSV UTF-8 (délimité par des virgules) ».
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "human" / "questions.csv"
LOCK = ROOT / "human" / "questions.lock"
ATTENDUS = ROOT / "human" / "attendus.yaml"

COLUMNS = ["id", "question", "etat", "split", "auteur", "date_ajout", "persona", "statut_attendu",
           "entites_attendues", "mesure", "axes", "periode", "intention_humaine", "lacunes_spec", "piege",
           "validation", "commentaire"]
REQUIRED = ["id", "question", "etat", "split", "auteur", "date_ajout"]

ETATS = {"active", "retiree"}
SPLITS = {"dev", "test"}
PERSONAS = {"P1", "P2", "P3"}
STATUTS = {"resolved", "ambiguous", "unknown", "out_of_scope"}
VALIDATIONS = {"", "ok", "a_revoir"}

ID_RE = re.compile(r"^H-\d{3,}$")
DATE = r"\d{4}-\d{2}-\d{2}"
PERIOD_PART = rf"(?:{DATE}\.\.{DATE}|photo {DATE}|\d{{4}})"
PERIOD_RE = re.compile(rf"^{PERIOD_PART}(?: vs {PERIOD_PART})?$")


# ---------------------------------------------------------------------------------------------- lecture / écriture
class FormatError(Exception):
    pass


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_questions(path: Path = QUESTIONS) -> list[dict]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise FormatError(f"{path.name} n'est pas en UTF-8. Dans Excel, enregistrer au format « CSV UTF-8 ».")
    if not text.strip():
        raise FormatError(f"{path.name} est vide")
    header = text.splitlines()[0]
    delim = ";" if header.count(";") >= header.count(",") else ","
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delim)
    missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
    if missing:
        raise FormatError(f"colonnes manquantes : {', '.join(missing)} (en-tête lu : {reader.fieldnames})")
    unknown = [c for c in reader.fieldnames if c not in COLUMNS]
    if unknown:
        raise FormatError(f"colonnes inconnues : {', '.join(unknown)}")
    rows = []
    for n, r in enumerate(reader, start=2):  # n = numéro de ligne dans Excel
        if None in r:
            raise FormatError(f"ligne {n} : plus de valeurs que de colonnes (un « ; » dans le texte doit être entre guillemets)")
        if not any((v or "").strip() for v in r.values()):
            continue  # ligne vide laissée par Excel
        row = {c: (r.get(c) or "") for c in COLUMNS}
        # le texte de la question n'est jamais retouché ; les étiquettes sont débarrassées des espaces parasites
        for c in COLUMNS:
            if c != "question":
                row[c] = row[c].strip()
        row["_ligne"] = n
        rows.append(row)
    return rows


def id_key(qid: str) -> tuple:
    """Tri numérique des identifiants ; un identifiant mal formé est rangé à la fin sans faire échouer l'écriture."""
    return (0, int(qid[2:]), "") if ID_RE.match(qid) else (1, 0, qid)


def write_questions(rows: list[dict], path: Path = QUESTIONS) -> None:
    rows = sorted(rows, key=lambda r: id_key(r["id"]))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter=";", extrasaction="ignore", lineterminator="\r\n",
                           quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(rows)


def read_lock(path: Path = LOCK) -> dict[str, str]:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            qid, digest = line.split("\t")
            out[qid] = digest
    return out


def write_lock(lock: dict[str, str], path: Path = LOCK) -> None:
    lines = ["# Empreintes SHA-256 du texte des questions humaines. Ne pas modifier à la main.",
             "# Une ligne enregistrée ne change plus : une question modifiée est une nouvelle question."]
    lines += [f"{k}\t{lock[k]}" for k in sorted(lock, key=id_key)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------------------------- référentiels
@dataclass
class Refs:
    entities: set[str] = field(default_factory=set)
    mesures: set[str] = field(default_factory=set)
    axes: set[str] = field(default_factory=set)
    lacunes: set[str] = field(default_factory=set)


def load_refs(root: Path = ROOT) -> Refs:
    import yaml
    with (root / "catalog" / "entities.csv").open(encoding="utf-8-sig") as f:
        entities = {r["entity_id"] for r in csv.DictReader(f)}
    g = yaml.safe_load((root / "spec" / "glossaire.yaml").read_text(encoding="utf-8"))
    mesures = {m["id"] for m in yaml.safe_load((root / "spec" / "mesures.yaml").read_text(encoding="utf-8"))["mesures"]}
    axes = {d["id"] for d in g["dimensions"]} | {a["id"] for a in g["axes_temporels"]}
    lacunes = {x["id"] for x in yaml.safe_load((root / "human" / "lacunes.yaml").read_text(encoding="utf-8"))["lacunes"]}
    return Refs(entities, mesures, axes, lacunes)


# ---------------------------------------------------------------------------------------------- contrôle
def valid_period(p: str) -> bool:
    if not PERIOD_RE.match(p):
        return False
    for a, b in re.findall(rf"({DATE})\.\.({DATE})", p):
        try:
            if dt.date.fromisoformat(a) > dt.date.fromisoformat(b):
                return False
        except ValueError:
            return False
    for d in re.findall(DATE, p):
        try:
            dt.date.fromisoformat(d)
        except ValueError:
            return False
    return True


def check(rows: list[dict], lock: dict[str, str], refs: Refs) -> tuple[list[str], list[str]]:
    """Renvoie (erreurs, avertissements). Une erreur rend le fichier inutilisable pour l'évaluation."""
    errors, warnings = [], []
    seen_ids, seen_text = {}, {}

    def err(r, msg):
        errors.append(f"ligne {r['_ligne']} ({r['id'] or 'sans id'}) : {msg}")

    for r in rows:
        qid, q = r["id"], r["question"]
        for c in REQUIRED:
            if not r[c].strip() if c == "question" else not r[c]:
                err(r, f"colonne « {c} » vide")
        if qid and not ID_RE.match(qid):
            err(r, f"identifiant « {qid} » invalide (format attendu : H-040)")
        if qid in seen_ids:
            err(r, f"identifiant en double (déjà ligne {seen_ids[qid]})")
        seen_ids[qid] = r["_ligne"]
        if "\n" in q or "\r" in q:
            err(r, "la question tient sur plusieurs lignes")
        key = q.strip().casefold()
        if key and key in seen_text and r["etat"] == "active":
            warnings.append(f"ligne {r['_ligne']} ({qid}) : même texte que la ligne {seen_text[key]}")
        if r["etat"] == "active":
            seen_text.setdefault(key, r["_ligne"])

        # immuabilité du texte
        if qid in lock:
            if sha(q) != lock[qid]:
                hint = ""
                if sha(unicodedata.normalize("NFC", q)) == lock[qid]:
                    hint = " (seul l'encodage des accents diffère : réenregistrer en CSV UTF-8)"
                elif sha(q.strip()) == lock[qid]:
                    hint = " (espaces ajoutés en début ou fin)"
                err(r, f"texte modifié depuis son enregistrement{hint}. Une question ne se corrige pas : "
                       "passer etat à « retiree » et ajouter une nouvelle question.")
        elif ID_RE.match(qid or ""):
            err(r, "question non enregistrée : lancer « python build/human_questions.py lock »")

        # valeurs contrôlées
        if r["etat"] and r["etat"] not in ETATS:
            err(r, f"etat « {r['etat']} » invalide ({' | '.join(sorted(ETATS))})")
        if r["split"] and r["split"] not in SPLITS:
            err(r, f"split « {r['split']} » invalide (dev | test)")
        if r["date_ajout"]:
            try:
                dt.date.fromisoformat(r["date_ajout"])
            except ValueError:
                err(r, f"date_ajout « {r['date_ajout']} » invalide (AAAA-MM-JJ ; dans Excel, format de cellule Texte)")
        if r["persona"] and r["persona"] not in PERSONAS:
            err(r, f"persona « {r['persona']} » invalide (P1 | P2 | P3)")
        if r["statut_attendu"] and r["statut_attendu"] not in STATUTS:
            err(r, f"statut_attendu « {r['statut_attendu']} » invalide ({' | '.join(sorted(STATUTS))})")
        if r["validation"] not in VALIDATIONS:
            err(r, f"validation « {r['validation']} » invalide (vide | ok | a_revoir)")
        for e in filter(None, r["entites_attendues"].split("|")):
            if e.strip() not in refs.entities:
                err(r, f"entité « {e} » absente du catalogue")
        if r["mesure"] and r["mesure"] not in refs.mesures:
            err(r, f"mesure « {r['mesure']} » absente du glossaire")
        for a in filter(None, r["axes"].split("|")):
            if a not in refs.axes:
                err(r, f"axe « {a} » absent du glossaire (dimensions ou axes_temporels)")
        if r["periode"] and not valid_period(r["periode"]):
            err(r, f"periode « {r['periode']} » invalide (AAAA-MM-JJ..AAAA-MM-JJ, photo AAAA-MM-JJ, AAAA, "
                   "ou deux périodes séparées par « vs »)")
        for g in filter(None, r["lacunes_spec"].split("|")):
            if g not in refs.lacunes:
                err(r, f"lacune « {g} » absente de human/lacunes.yaml")
        if r["statut_attendu"] == "out_of_scope" and (r["mesure"] or r["axes"]):
            err(r, "une question hors périmètre n'a ni mesure ni axe attendus")

        # la réponse attendue vit dans attendus.yaml ; les colonnes du CSV ne sont qu'une proposition
        if r["etat"] == "active":
            if r["validation"] == "a_revoir":
                warnings.append(f"ligne {r['_ligne']} ({qid}) : étiquetage marqué à revoir")

    for qid in sorted(set(lock) - set(seen_ids), key=id_key):
        errors.append(f"{qid} : enregistrée dans questions.lock mais absente du fichier (une question se retire avec "
                      "etat = retiree, elle ne se supprime pas)")
    return errors, warnings


def summary(rows: list[dict]) -> str:
    from collections import Counter
    act = [r for r in rows if r["etat"] == "active"]
    c = lambda k: ", ".join(f"{v or '—'} {n}" for v, n in sorted(Counter(r[k] for r in act).items()))
    val = Counter(r["validation"] or "à valider" for r in act)
    return (f"{len(act)} questions actives ({len(rows) - len(act)} retirées)\n"
            f"  split : {c('split')}\n  persona : {c('persona')}\n  statut proposé (csv) : {c('statut_attendu')}\n"
            f"  validation : {', '.join(f'{k} {v}' for k, v in sorted(val.items()))}\n"
            f"  auteurs : {c('auteur')}")


# ---------------------------------------------------------------------------------------------- réponses attendues
def read_attendus(path: Path = ATTENDUS) -> dict:
    """Lit attendus.yaml ; refuse les identifiants en double (YAML garderait silencieusement le dernier)."""
    import yaml

    class Loader(yaml.SafeLoader):
        pass

    def no_dup(loader, node, deep=False):
        keys = [loader.construct_object(k, deep=deep) for k, _ in node.value]
        dups = sorted({k for k in keys if keys.count(k) > 1}, key=str)
        if dups:
            raise FormatError(f"{path.name} : identifiant en double {dups} (ligne {node.start_mark.line + 1})")
        return loader.construct_mapping(node, deep=deep)

    Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, no_dup)
    if not path.exists():
        return {}
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=Loader)
    except yaml.YAMLError as e:
        raise FormatError(f"{path.name} : YAML invalide ({e})".replace("\n", " "))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise FormatError(f"{path.name} : une liste d'entrées « H-0xx: » est attendue")
    return data


def _ids_of(answer: dict) -> tuple[set[str], set[str]]:
    """Entités et mesures citées par une réponse attendue (pour comparer à la proposition du CSV)."""
    ents, mes = set(), set()
    if answer.get("statut") == "resolved" and isinstance(answer.get("manifest"), dict):
        for c in answer["manifest"].get("champs") or []:
            if isinstance(c, dict):
                if c.get("role") == "filtre":
                    ents |= set(c.get("valeurs") or [])
                if c.get("role") == "mesure":
                    mes.add(c.get("ref"))
    if answer.get("statut") == "ambiguous":
        for x in answer.get("ambiguites") or []:
            if isinstance(x, dict):
                ents |= {c for c in x.get("candidats") or [] if isinstance(c, str) and ":" in c and not c.startswith("axe:")}
    return ents, mes


def check_attendus(rows: list[dict], attendus: dict, mrefs) -> tuple[list[str], list[str], list[str], int]:
    """Renvoie (erreurs, avertissements, écarts avec la proposition, nombre de réponses écrites)."""
    from manifest import validate_answer
    errors, warnings, ecarts = [], [], []
    by_id = {r["id"]: r for r in rows}
    written, todo = 0, []
    for qid, a in attendus.items():
        if qid not in by_id:
            errors.append(f"attendus.yaml · {qid} : absent de questions.csv")
            continue
        if a is None:
            if by_id[qid]["etat"] == "active":
                todo.append(qid)
            continue
        written += 1
        for e in validate_answer(a, mrefs):
            errors.append(f"attendus.yaml · {qid} : {e}")
        r = by_id[qid]
        if r["statut_attendu"] and isinstance(a, dict) and a.get("statut") and a["statut"] != r["statut_attendu"]:
            ecarts.append(f"{qid} : statut {a['statut']} (proposition : {r['statut_attendu']})")
        if isinstance(a, dict):
            ents, mes = _ids_of(a)
            prop = {x for x in r["entites_attendues"].split("|") if x}
            if a.get("statut") in ("resolved", "ambiguous") and prop and ents != prop:
                ecarts.append(f"{qid} : entités {sorted(ents)} (proposition : {sorted(prop)})")
            if a.get("statut") == "resolved" and r["mesure"] and mes and r["mesure"] not in mes:
                ecarts.append(f"{qid} : mesure {sorted(mes)} (proposition : {r['mesure']})")
    missing = [r["id"] for r in rows if r["etat"] == "active" and r["id"] not in attendus]
    if missing:
        warnings.append(f"attendus.yaml : questions sans entrée {missing}")
    if todo:
        warnings.append(f"attendus.yaml : {len(todo)} réponse(s) à écrire")
    return errors, warnings, ecarts, written


# ---------------------------------------------------------------------------------------------- commandes
def cmd_check(path=QUESTIONS, lock_path=LOCK, root=ROOT, attendus_path=None) -> int:
    from manifest import load_manifest_refs
    attendus_path = attendus_path or (root / "human" / "attendus.yaml")
    try:
        rows = read_questions(path)
        attendus = read_attendus(attendus_path)
    except FormatError as e:
        print(f"ERREUR : {e}")
        return 1
    errors, warnings = check(rows, read_lock(lock_path), load_refs(root))
    e2, w2, ecarts, written = check_attendus(rows, attendus, load_manifest_refs(root))
    errors += e2
    warnings += w2
    print(summary(rows))
    n_act = sum(r["etat"] == "active" for r in rows)
    print(f"  réponses attendues écrites : {written} / {n_act}")
    for w in warnings:
        print(f"  avertissement · {w}")
    if ecarts:
        print(f"  écarts avec la proposition de départ ({len(ecarts)}, à arbitrer) :")
        for x in ecarts:
            print(f"    - {x}")
    for e in errors:
        print(f"  ERREUR · {e}")
    print(f"{'OK' if not errors else 'ÉCHEC'} · {len(errors)} erreur(s), {len(warnings)} avertissement(s)")
    return 1 if errors else 0


def next_id(rows: list[dict], lock: dict[str, str]) -> str:
    nums = [int(k[2:]) for k in list(lock) + [r["id"] for r in rows] if ID_RE.match(k)]
    return f"H-{max(nums, default=0) + 1:03d}"


def cmd_add(text: str, split: str, auteur: str, path=QUESTIONS, lock_path=LOCK) -> int:
    if not text.strip() or "\n" in text:
        print("ERREUR : la question doit tenir sur une ligne non vide")
        return 1
    if split not in SPLITS:
        print("ERREUR : split doit valoir dev ou test")
        return 1
    rows = read_questions(path) if path.exists() else []
    lock = read_lock(lock_path)
    qid = next_id(rows, lock)
    row = {c: "" for c in COLUMNS}
    row.update(id=qid, question=text, etat="active", split=split, auteur=auteur, date_ajout=dt.date.today().isoformat())
    rows.append(row)
    lock[qid] = sha(text)
    write_questions(rows, path)
    write_lock(lock, lock_path)
    att = path.parent / "attendus.yaml"
    if att.exists():
        with att.open("a", encoding="utf-8") as f:
            f.write(f"\n# {text}\n{qid}:\n")
    print(f"{qid} ajoutée ({split}). Réponse attendue à écrire dans attendus.yaml, étiquetage dans {path.name}.")
    return 0


def cmd_lock(path=QUESTIONS, lock_path=LOCK) -> int:
    rows = read_questions(path)
    lock = read_lock(lock_path)
    new = [r for r in rows if ID_RE.match(r["id"]) and r["id"] not in lock]
    for r in new:
        lock[r["id"]] = sha(r["question"])
    write_lock(lock, lock_path)
    print(f"{len(new)} question(s) enregistrée(s) : {', '.join(r['id'] for r in new) or 'aucune'}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Questions humaines du knowledge catalog")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    a = sub.add_parser("add")
    a.add_argument("texte")
    a.add_argument("--split", default="test")
    a.add_argument("--auteur", default="Ugo Merlier")
    sub.add_parser("lock")
    args = p.parse_args(argv)
    if args.cmd == "check":
        return cmd_check()
    if args.cmd == "add":
        return cmd_add(args.texte, args.split, args.auteur)
    return cmd_lock()


if __name__ == "__main__":
    sys.exit(main())
