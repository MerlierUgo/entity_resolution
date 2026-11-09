"""
Manifest : validation, forme canonique et empreinte (spec/manifest_schema.yaml).

  validate_answer(answer, refs)  contrôle une réponse attendue (statut + manifest | ambiguites | inconnus | hors_perimetre)
  validate_manifest(m, refs)     contrôle le cœur d'un Manifest
  canonical(m)                   forme canonique (dict)
  manifest_hash(m)               SHA-256 du JSON canonique

Les valeurs permises (intents, rôles, raisons…) sont lues dans le schéma : il est la source unique.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class ManifestRefs:
    schema: dict
    etype: dict[str, str]                      # entity_id -> entity_type
    mesures: set[str]                          # M01…M26
    dim_types: dict[str, set[str]]             # dimension -> types d'entités permis
    axes_temporels: set[str] = field(default_factory=set)


def load_manifest_refs(root: Path = ROOT) -> ManifestRefs:
    schema = yaml.safe_load((root / "spec" / "manifest_schema.yaml").read_text(encoding="utf-8"))
    g = yaml.safe_load((root / "spec" / "glossaire.yaml").read_text(encoding="utf-8"))
    with (root / "catalog" / "entities.csv").open(encoding="utf-8-sig") as f:
        etype = {r["entity_id"]: r["entity_type"] for r in csv.DictReader(f)}
    dim_types = {}
    for d in g["dimensions"]:
        dim_types[d["id"]] = set(d.get("catalogue") or []) | ({d["liste_metier"]} if d.get("liste_metier") else set())
    mesures = yaml.safe_load((root / "spec" / "mesures.yaml").read_text(encoding="utf-8"))["mesures"]
    return ManifestRefs(schema, etype, {m["id"] for m in mesures}, dim_types,
                        {a["id"] for a in g["axes_temporels"]})


# ---------------------------------------------------------------------------------------------- outils
def _date(v) -> str | None:
    """Accepte une date YAML (non citée) ou un texte AAAA-MM-JJ ; renvoie le texte ISO ou None."""
    if isinstance(v, dt.datetime):
        v = v.date()
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, str):
        try:
            return dt.date.fromisoformat(v).isoformat()
        except ValueError:
            return None
    return None


def _norm_dates(x):
    if isinstance(x, (dt.date, dt.datetime)):
        return _date(x)
    if isinstance(x, dict):
        return {k: _norm_dates(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_norm_dates(v) for v in x]
    return x


# ---------------------------------------------------------------------------------------------- validation
def validate_manifest(m, refs: ManifestRefs) -> list[str]:
    S = refs.schema
    e: list[str] = []
    if not isinstance(m, dict):
        return ["manifest : un objet est attendu"]
    extra = set(m) - set(S["cles_manifest"])
    if extra:
        e.append(f"manifest : clés inconnues {sorted(extra)} (permises : {', '.join(S['cles_manifest'])})")
    intent = m.get("intent")
    if intent not in S["intents"]:
        e.append(f"intent « {intent} » invalide ({' | '.join(S['intents'])})")
    champs = m.get("champs")
    if not isinstance(champs, list) or not champs:
        e.append("champs : liste non vide attendue")
        champs = []

    by_role: dict[str, list[dict]] = {}
    for i, c in enumerate(champs, 1):
        where = f"champ {i}"
        if not isinstance(c, dict) or "role" not in c:
            e.append(f"{where} : objet avec une clé « role » attendu")
            continue
        role = c["role"]
        spec = S["roles"].get(role)
        if spec is None:
            e.append(f"{where} : rôle « {role} » invalide ({' | '.join(S['roles'])})")
            continue
        keys = set(c) - {"role"}
        allowed = [set(spec["cles"])] + ([set(spec["ou"])] if "ou" in spec else [])
        if keys not in allowed:
            forms = " ou ".join("{" + ", ".join(sorted(a)) + "}" for a in allowed)
            e.append(f"{where} ({role}) : clés {sorted(keys)} ; attendu {forms}")
            continue
        by_role.setdefault(role, []).append(c)

        if role == "mesure" and c["ref"] not in refs.mesures:
            e.append(f"{where} : mesure « {c['ref']} » absente du glossaire")
        elif role == "filtre":
            dim, vals = c["dimension"], c["valeurs"]
            if dim not in refs.dim_types:
                e.append(f"{where} : dimension « {dim} » absente du glossaire")
            if not isinstance(vals, list) or not vals:
                e.append(f"{where} : valeurs doit être une liste non vide")
                continue
            for v in vals:
                t = refs.etype.get(v)
                if t is None:
                    e.append(f"{where} : « {v} » absent du catalogue")
                elif dim in refs.dim_types and t not in refs.dim_types[dim]:
                    e.append(f"{where} : « {v} » est de type {t}, la dimension {dim} attend "
                             f"{' | '.join(sorted(refs.dim_types[dim]))}")
            if len(set(vals)) != len(vals):
                e.append(f"{where} : valeur en double")
        elif role == "axe":
            if c["dimension"] not in refs.dim_types and c["dimension"] not in refs.axes_temporels:
                e.append(f"{where} : axe « {c['dimension']} » absent du glossaire (dimensions ou axes temporels)")
        elif role == "periode":
            if "photo" in c:
                if not _date(c["photo"]):
                    e.append(f"{where} : photo « {c['photo']} » n'est pas une date AAAA-MM-JJ")
            else:
                a, b = _date(c["debut"]), _date(c["fin"])
                if not a or not b:
                    e.append(f"{where} : debut et fin doivent être des dates AAAA-MM-JJ")
                elif a > b:
                    e.append(f"{where} : debut {a} postérieur à fin {b}")
        elif role == "comparaison":
            if c["type"] not in S["types_comparaison"]:
                e.append(f"{where} : type « {c['type']} » invalide ({' | '.join(S['types_comparaison'])})")
            a, b = _date(c["debut"]), _date(c["fin"])
            if not a or not b or a > b:
                e.append(f"{where} : debut et fin doivent être des dates AAAA-MM-JJ dans l'ordre")
        elif role == "seuil":
            if c["mesure"] not in refs.mesures:
                e.append(f"{where} : mesure « {c['mesure']} » absente du glossaire")
            if c["operateur"] not in S["operateurs_seuil"]:
                e.append(f"{where} : opérateur « {c['operateur']} » invalide ({' '.join(S['operateurs_seuil'])})")
            if isinstance(c["valeur"], bool) or not isinstance(c["valeur"], (int, float)):
                e.append(f"{where} : valeur doit être un nombre")

    # contraintes générales
    n = {r: len(v) for r, v in by_role.items()}
    if n.get("periode", 0) > 1:
        e.append("une seule période par Manifest")
    if n.get("comparaison", 0) > 1:
        e.append("une seule comparaison par Manifest")
    dims = [c["dimension"] for c in by_role.get("filtre", [])]
    for d in sorted({d for d in dims if dims.count(d) > 1}):
        e.append(f"dimension « {d} » filtrée deux fois : regrouper les valeurs dans un seul filtre")
    if intent != "detail":
        if not n.get("mesure"):
            e.append("au moins une mesure est requise")
        if not n.get("periode"):
            e.append("une période est requise")

    mesures = {c["ref"] for c in by_role.get("mesure", [])}
    tri = m.get("tri")
    if tri is not None:
        if not isinstance(tri, dict) or set(tri) != {"mesure", "ordre"}:
            e.append("tri : {mesure, ordre} attendu")
        else:
            if tri["mesure"] not in mesures:
                e.append(f"tri : la mesure {tri['mesure']} doit figurer parmi les champs mesure")
            if tri["ordre"] not in S["ordres_tri"]:
                e.append(f"tri : ordre « {tri['ordre']} » invalide (asc | desc)")
    lim = m.get("limite")
    if lim is not None and (isinstance(lim, bool) or not isinstance(lim, int) or lim < 1):
        e.append("limite : entier ≥ 1 attendu")

    # selon l'intent
    rule = (S["selon_intent"].get(intent) or {}) if intent in S["intents"] else {}
    present = {
        "axe": bool(n.get("axe")),
        "axe_temporel": any(c["dimension"] in refs.axes_temporels for c in by_role.get("axe", [])),
        "tri": tri is not None,
        "limite": lim is not None,
        "comparaison": bool(n.get("comparaison")),
        "filtre_multi_valeurs": any(isinstance(c["valeurs"], list) and len(c["valeurs"]) > 1
                                    for c in by_role.get("filtre", [])),
    }
    for r in rule.get("requis", []):
        if not present[r]:
            e.append(f"intent {intent} : {r.replace('_', ' ')} requis")
    for r in rule.get("interdit", []):
        if present[r]:
            e.append(f"intent {intent} : {r} interdit")
    if rule.get("requis_un_de") and not any(present[r] for r in rule["requis_un_de"]):
        e.append(f"intent {intent} : il faut {' ou '.join(r.replace('_', ' ') for r in rule['requis_un_de'])}")
    return e


def validate_answer(a, refs: ManifestRefs) -> list[str]:
    """Contrôle une réponse attendue. Renvoie la liste des erreurs (vide si valide)."""
    S = refs.schema
    if not isinstance(a, dict):
        return ["un objet {statut: …} est attendu"]
    statut = a.get("statut")
    if statut not in S["statuts"]:
        return [f"statut « {statut} » invalide ({' | '.join(S['statuts'])})"]
    attendu = S["statuts"][statut]["contient"]
    e = []
    extra = set(a) - {"statut", attendu, "commentaire"}
    if extra:
        e.append(f"statut {statut} : clés en trop {sorted(extra)} (attendu : statut, {attendu}, commentaire)")
    if attendu not in a:
        return e + [f"statut {statut} : la clé « {attendu} » est requise"]
    body = a[attendu]
    if statut == "resolved":
        e += validate_manifest(body, refs)
    elif statut == "ambiguous":
        if not isinstance(body, list) or not body:
            return e + ["ambiguites : liste non vide de {terme, candidats} attendue"]
        for i, x in enumerate(body, 1):
            if not isinstance(x, dict) or set(x) != {"terme", "candidats"}:
                e.append(f"ambiguïté {i} : {{terme, candidats}} attendu")
                continue
            cands = x["candidats"]
            if not isinstance(cands, list) or len(cands) < 2:
                e.append(f"ambiguïté {i} (« {x['terme']} ») : au moins deux candidats")
                continue
            for c in cands:
                ok = (c in refs.etype or c in refs.mesures
                      or (isinstance(c, str) and c.startswith("axe:")
                          and (c[4:] in refs.dim_types or c[4:] in refs.axes_temporels)))
                if not ok:
                    e.append(f"ambiguïté {i} (« {x['terme']} ») : candidat « {c} » inconnu")
    elif statut == "unknown":
        if not isinstance(body, list) or not body:
            return e + ["inconnus : liste non vide de {terme, raison} attendue"]
        for i, x in enumerate(body, 1):
            if not isinstance(x, dict) or set(x) != {"terme", "raison"}:
                e.append(f"inconnu {i} : {{terme, raison}} attendu")
            elif x["raison"] not in S["raisons_inconnu"]:
                e.append(f"inconnu {i} : raison « {x['raison']} » invalide ({' | '.join(S['raisons_inconnu'])})")
    elif statut == "out_of_scope":
        if not isinstance(body, dict) or set(body) != {"sujet"} or not body["sujet"]:
            e.append("hors_perimetre : {sujet: …} attendu")
    return e


# ---------------------------------------------------------------------------------------------- canonique
def canonical(m: dict, schema: dict | None = None) -> dict:
    """Forme canonique du cœur d'un Manifest supposé valide."""
    order = (schema or {}).get("ordre_roles") or ["mesure", "filtre", "axe", "periode", "comparaison", "seuil"]
    m = _norm_dates(m)
    champs = []
    for c in m.get("champs", []):
        c = {k: v for k, v in c.items() if v not in (None, "", [], {})}
        if "valeurs" in c:
            c["valeurs"] = sorted(c["valeurs"])
        champs.append(c)
    champs.sort(key=lambda c: (order.index(c["role"]) if c["role"] in order else 99,
                               json.dumps(c, sort_keys=True, ensure_ascii=False)))
    out = {"intent": m.get("intent"), "champs": champs}
    for k in ("tri", "limite"):
        if m.get(k) not in (None, "", {}):
            out[k] = m[k]
    return out


def manifest_hash(m: dict, schema: dict | None = None) -> str:
    s = json.dumps(canonical(m, schema), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
