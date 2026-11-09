"""
Couche 1 du catalogue : référentiels ouverts.
Produit catalog/open_entities.csv, open_aliases.csv, open_relations.csv, hors_perimetre.csv
et reports/source_issues.csv (anomalies relevées dans les sources).
"""
from __future__ import annotations

import csv
import gettext
import json
import re
from collections import Counter, defaultdict

import pycountry

from common import CAT, LATIN, RAW, REP, normalize, slug, write_csv

S = {
    "geonames": ("GeoNames cities500 via geonamescache 3.0.2", "CC BY 4.0"),
    "statbel": ("Statbel, découpage communal 2020 (via vandenbroucke/belgian_municipalities)", "Open data Statbel ; dépôt sans licence explicite"),
    "bpost": ("bpost, codes postaux 2015 (via spatie/belgian-cities-geocoded)", "MIT"),
    "iso": ("ISO 3166-1 et 3166-2, traductions iso-codes (via pycountry 26.2.16)", "LGPL-2.1"),
    "shopify": ("Shopify Standard Product Taxonomy", "MIT"),
    "eea": ("openvehicle-data 0.3.0 (EEA CO2 2025 Italie, Wikidata, RDW)", "CC BY 4.0"),
    "hs": ("Système harmonisé via datasets/harmonized-system (UN Comtrade)", "ODC-PDDL-1.0"),
    "rule": ("Règle de numérotation postale bpost (connaissance publique)", "n/a"),
}

E: dict[str, dict] = {}
A: list[dict] = []
R: list[dict] = []
ISSUES: list[dict] = []
OUT: list[dict] = []


def ent(eid, etype, domain, label, src, tier=1, **kw):
    if eid in E:
        raise ValueError(f"identifiant dupliqué {eid}")
    name, lic = S[src]
    E[eid] = {"entity_id": eid, "entity_type": etype, "domain": domain, "label": label,
              "source": name, "licence": lic, "tier": tier, **kw}
    alias(eid, label, kw.get("lang_label", ""), "libelle_canonique", src, tier)


def alias(eid, text, lang, atype, src, tier):
    text = str(text).strip()
    if not text:
        return
    n = normalize(text)
    if not n:
        return
    name, lic = S[src]
    A.append({"entity_id": eid, "alias": text, "alias_norm": n, "lang": lang, "alias_type": atype,
              "source": name, "licence": lic, "tier": tier})


def rel(s, p, o, src):
    R.append({"subject_id": s, "predicate": p, "object_id": o, "source": S[src][0]})


def issue(src, kind, detail):
    ISSUES.append({"source": S[src][0], "type": kind, "detail": detail})


def tr(domain, lang):
    return gettext.translation(domain, pycountry.LOCALES_DIR, languages=[lang], fallback=True).gettext


T1 = {l: tr("iso3166-1", l) for l in ("fr", "nl", "de")}
T2 = {l: tr("iso3166-2", l) for l in ("fr", "nl", "de")}

# ------------------------------------------------------------------ pays
COUNTRIES = ["BE", "FR", "LU", "NL"]
for cc in COUNTRIES:
    c = pycountry.countries.get(alpha_2=cc)
    labels = {"en": c.name, **{l: T1[l](c.name) for l in T1}}
    eid = f"geo:pays:{cc}"
    ent(eid, "pays", "geographie", labels["fr"], "iso", code=cc, country=cc,
        label_fr=labels["fr"], label_nl=labels["nl"], label_de=labels["de"], label_en=labels["en"], lang_label="fr")
    for l, v in labels.items():
        alias(eid, v, l, "traduction_officielle", "iso", 1)
    if getattr(c, "official_name", None):
        alias(eid, c.official_name, "en", "nom_officiel", "iso", 1)
        alias(eid, T1["fr"](c.official_name), "fr", "nom_officiel", "iso", 1)
    alias(eid, cc, "", "code_iso2", "iso", 1)
    alias(eid, c.alpha_3, "", "code_iso3", "iso", 1)

# ------------------------------------------------------------------ subdivisions ISO
ISO_CORRECTIONS = {("fr", "Limburg"): "Limbourg"}


def subdiv(code):
    s = pycountry.subdivisions.get(code=code)
    out = {"local": s.name}
    for l in T2:
        v = T2[l](s.name)
        fix = ISO_CORRECTIONS.get((l, s.name))
        if fix and v != fix:
            issue("iso", "traduction_corrigee", f"{code} : traduction {l} « {v} » corrigée en « {fix} »")
            v = fix
        out[l] = v
    return s, out


SUB_SCOPE = {"BE": None, "LU": None, "FR": {"FR-HDF", "FR-GES"}, "NL": {"NL-LI", "NL-NB"}}
iso_sub = {}
for cc, keep in SUB_SCOPE.items():
    for s in pycountry.subdivisions.get(country_code=cc):
        if keep is not None and s.code not in keep:
            continue
        if cc == "FR" and "region" not in s.type.lower():
            continue
        iso_sub[s.code] = s

# Belgique : régions et provinces depuis Statbel (FR/NL), contrôlées contre ISO
mun = json.load(open(RAW / "be_municipalities_2020.json", encoding="utf-8"))
reg_be, prov_be, arr_be = {}, {}, {}
REG_CODE = {"Région flamande": "BE-VLG", "Région wallonne": "BE-WAL", "Région de Bruxelles-Capitale": "BE-BRU"}
PROV_CODE = {"Anvers": "BE-VAN", "Limbourg": "BE-VLI", "Flandre orientale": "BE-VOV", "Flandre-Orientale": "BE-VOV",
             "Brabant flamand": "BE-VBR", "Flandre occidentale": "BE-VWV", "Flandre-Occidentale": "BE-VWV",
             "Brabant wallon": "BE-WBR", "Hainaut": "BE-WHT", "Liège": "BE-WLG", "Luxembourg": "BE-WLX", "Namur": "BE-WNA"}
for m in mun:
    rc = REG_CODE[m["region_FR"]]
    reg_be.setdefault(rc, (m["region_FR"], m["region_NL"]))
    if m.get("province_FR"):
        pc = PROV_CODE[m["province_FR"]]
        prov_be.setdefault(pc, (m["province_FR"], m["province_NL"], rc))
    arr_be.setdefault((m["arrondissement_FR"], m["arrondissement_NL"]), (PROV_CODE.get(m.get("province_FR") or "", None), rc))

for rc, (fr, nl) in sorted(reg_be.items()):
    eid = f"geo:region:{rc}"
    _, iso = subdiv(rc)
    ent(eid, "region", "geographie", fr, "statbel", code=rc, country="BE", label_fr=fr, label_nl=nl,
        label_de=iso["de"], lang_label="fr", parent_id="geo:pays:BE")
    alias(eid, nl, "nl", "traduction_officielle", "statbel", 1)
    for l in ("local", "fr", "nl", "de"):
        alias(eid, iso[l], l if l != "local" else "", "traduction_iso", "iso", 2)
    rel(eid, "situe_dans", "geo:pays:BE", "statbel")

for pc, (fr, nl, rc) in sorted(prov_be.items()):
    eid = f"geo:province:{pc}"
    _, iso = subdiv(pc)
    ent(eid, "province", "geographie", fr, "statbel", code=pc, country="BE", label_fr=fr, label_nl=nl,
        label_de=iso["de"], lang_label="fr", parent_id=f"geo:region:{rc}")
    alias(eid, nl, "nl", "traduction_officielle", "statbel", 1)
    for l in ("fr", "nl", "de"):
        if normalize(iso[l]) not in {normalize(fr), normalize(nl)} and l in ("fr", "nl"):
            issue("iso", "traduction_divergente",
                  f"{pc} : traduction {l} iso-codes « {iso[l]} » ≠ Statbel « {fr if l == 'fr' else nl} » (non reprise)")
            continue
        alias(eid, iso[l], l, "traduction_iso", "iso", 2)
    rel(eid, "situe_dans", f"geo:region:{rc}", "statbel")

for (fr, nl), (pc, rc) in sorted(arr_be.items(), key=lambda x: x[0]):
    eid = f"geo:arrondissement:be-{slug(fr)}"
    parent = f"geo:province:{pc}" if pc else f"geo:region:{rc}"
    ent(eid, "arrondissement", "geographie", fr, "statbel", country="BE", label_fr=fr, label_nl=nl,
        lang_label="fr", parent_id=parent)
    alias(eid, nl, "nl", "traduction_officielle", "statbel", 1)
    rel(eid, "situe_dans", parent, "statbel")

# Communes belges
commune_by_norm = defaultdict(set)
commune_zip = defaultdict(set)
for m in mun:
    eid = f"geo:commune:BE-{m['NIS_code']}"
    arr = f"geo:arrondissement:be-{slug(m['arrondissement_FR'])}"
    ent(eid, "commune", "geographie", m["municipality_FR"], "statbel", code=str(m["NIS_code"]), country="BE",
        label_fr=m["municipality_FR"], label_nl=m["municipality_NL"], lang_label="fr", parent_id=arr,
        population=m["inhabitants"], postal_code=str(m["zip"]))
    alias(eid, m["municipality_NL"], "nl", "traduction_officielle", "statbel", 1)
    rel(eid, "situe_dans", arr, "statbel")
    for lab in {m["municipality_FR"], m["municipality_NL"]}:
        commune_by_norm[normalize(lab)].add(eid)
    commune_zip[str(m["zip"])].add(eid)

# Subdivisions ISO hors Belgique (FR régions, NL provinces, LU cantons)
for code, s in sorted(iso_sub.items()):
    cc = code[:2]
    if cc == "BE":
        continue
    _, iso = subdiv(code)
    etype = {"FR": "region", "NL": "province", "LU": "canton"}[cc]
    eid = f"geo:{etype}:{code}"
    label = iso["fr"]
    ent(eid, etype, "geographie", label, "iso", code=code, country=cc, label_fr=iso["fr"], label_nl=iso["nl"],
        label_de=iso["de"], lang_label="fr", parent_id=f"geo:pays:{cc}")
    for l in ("local", "nl", "de"):
        alias(eid, iso[l], l if l != "local" else "", "traduction_iso", "iso", 1)
    rel(eid, "situe_dans", f"geo:pays:{cc}", "iso")
for code, s in iso_sub.items():
    if code.startswith("NL-") and normalize(T2["fr"](s.name)) == normalize(s.name) and s.name == "Limburg":
        pass

# ------------------------------------------------------------------ GeoNames
gn = json.load(open(RAW / "gnc/geonamescache/data/cities500.json", encoding="utf-8")).values()
ADMIN = {"FR": {"32": "geo:region:FR-HDF", "44": "geo:region:FR-GES"},
         "NL": {"05": "geo:province:NL-LI", "06": "geo:province:NL-NB"}}


GN_OK = re.compile(r"^[A-ZÀ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’ .\-()]+$")
GN_TRANSLIT = re.compile(r"(kh|zh|dzh|tj|sj|jj|yy|ŭ|ă|ț|ș|w[iy])", re.I)
GN_STATS = Counter()


def latin_alts(x):
    """Variantes GeoNames plausibles pour un utilisateur FR/NL/DE/EN : alphabet latin-1, majuscule initiale,
    au moins 4 caractères, pas de translittération depuis un autre alphabet, pas de libellé composite."""
    out = []
    for a in x["alternatenames"]:
        ok = (GN_OK.match(a) and not GN_TRANSLIT.search(a) and len(a) >= 4 and "  " not in a
              and not re.fullmatch(r"[A-Z]{3,4}", a))
        GN_STATS["gardees" if ok else "ecartees"] += 1
        if ok:
            out.append(a)
    return sorted(set(out))


gn_be_unmatched = 0
for x in sorted(gn, key=lambda r: r["geonameid"]):
    cc, a1 = x["countrycode"], x["admin1code"]
    if cc == "BE":
        hits = commune_by_norm.get(normalize(x["name"]), set())
        if len(hits) == 1:
            cid = next(iter(hits))
            for a in latin_alts(x):
                alias(cid, a, "", "variante_geonames", "geonames", 2)
            E[cid].setdefault("geonameid", x["geonameid"])
        else:
            gn_be_unmatched += 1
        continue
    in_scope = cc == "LU" or (cc in ADMIN and a1 in ADMIN[cc])
    if not in_scope:
        if cc in ("FR", "NL", "DE") and x["population"] >= 500:
            OUT.append({"geonameid": x["geonameid"], "name": x["name"], "name_norm": normalize(x["name"]),
                        "country": cc, "admin1": a1, "population": x["population"]})
        continue
    parent = f"geo:canton:LU-{a1}" if cc == "LU" else ADMIN[cc][a1]
    etype = "commune" if cc == "LU" else "ville"
    eid = f"geo:{etype}:{cc}-{x['geonameid']}"
    ent(eid, etype, "geographie", x["name"], "geonames", code=str(x["geonameid"]), country=cc,
        parent_id=parent, population=x["population"], lang_label="")
    for a in latin_alts(x):
        alias(eid, a, "", "variante_geonames", "geonames", 2)
    rel(eid, "situe_dans", parent, "geonames")

# ------------------------------------------------------------------ localités postales belges (bpost)
def province_from_postcode(pc: int) -> str:
    """Numérotation bpost : 1000-1299 Bruxelles, 1300-1499 Brabant wallon, 1500-1999 et 3000-3499 Brabant flamand,
    2000-2999 Anvers, 3500-3999 Limbourg, 4000-4999 Liège, 5000-5999 Namur, 6000-6599 et 7000-7999 Hainaut,
    6600-6999 Luxembourg, 8000-8999 Flandre occidentale, 9000-9999 Flandre orientale."""
    for lo, hi, code in [(1000, 1299, "geo:region:BE-BRU"), (1300, 1499, "geo:province:BE-WBR"),
                         (1500, 1999, "geo:province:BE-VBR"), (2000, 2999, "geo:province:BE-VAN"),
                         (3000, 3499, "geo:province:BE-VBR"), (3500, 3999, "geo:province:BE-VLI"),
                         (4000, 4999, "geo:province:BE-WLG"), (5000, 5999, "geo:province:BE-WNA"),
                         (6000, 6599, "geo:province:BE-WHT"), (6600, 6999, "geo:province:BE-WLX"),
                         (7000, 7999, "geo:province:BE-WHT"), (8000, 8999, "geo:province:BE-VWV"),
                         (9000, 9999, "geo:province:BE-VOV")]:
        if lo <= pc <= hi:
            return code
    raise ValueError(pc)


SPATIE_PROV = {"Waals-Brabant": "geo:province:BE-WBR", "Antwerpen": "geo:province:BE-VAN", "Limburg": "geo:province:BE-VLI", "Oost-Vlaanderen": "geo:province:BE-VOV",
               "Vlaams-Brabant": "geo:province:BE-VBR", "West-Vlaanderen": "geo:province:BE-VWV", "Brabant Wallon": "geo:province:BE-WBR",
               "Brabant wallon": "geo:province:BE-WBR", "Henegouwen": "geo:province:BE-WHT", "Hainaut": "geo:province:BE-WHT",
               "Luik": "geo:province:BE-WLG", "Liège": "geo:province:BE-WLG", "Luxemburg": "geo:province:BE-WLX",
               "Luxembourg": "geo:province:BE-WLX", "Namen": "geo:province:BE-WNA", "Namur": "geo:province:BE-WNA"}
link_stats = Counter()
seen_loc = set()
for r in csv.DictReader(open(RAW / "be_postcodes.csv", encoding="utf-8")):
    codes = [c.strip() for c in r["postal"].split(",") if c.strip()]
    if len(codes) > 1:
        issue("bpost", "plusieurs_codes_postaux", f"{r['postal']} {r['name']} : premier code retenu")
    pc, raw_name = int(codes[0]), r["name"].strip()
    name = re.sub(r"(?<=[a-zà-ÿ])([À-Ý])", lambda m: m.group(1).lower(), raw_name)
    if name != raw_name:
        issue("bpost", "casse_corrigee", f"{pc} « {raw_name} » → « {name} »")
    eid = f"geo:localite:BE-{pc}-{slug(name)}"
    if eid in seen_loc:
        issue("bpost", "doublon", f"{pc} {name}")
        continue
    seen_loc.add(eid)
    prov = province_from_postcode(pc)
    declared = SPATIE_PROV.get(r["province"])
    if declared != prov:
        issue("bpost", "province_incoherente", f"{pc} {name} : province source « {r['province']} », code postal → {prov}")
    hits = commune_by_norm.get(normalize(name), set()) & commune_zip.get(str(pc), set())
    if not hits:
        hits = commune_by_norm.get(normalize(name), set())
        hits = {h for h in hits if province_from_postcode(int(E[h]["postal_code"])) == prov}
    if len(hits) == 1:
        parent, how = next(iter(hits)), "commune_meme_nom"
    elif len(commune_zip.get(str(pc), set())) == 1:
        parent, how = next(iter(commune_zip[str(pc)])), "commune_meme_code_postal"
    else:
        parent, how = prov, "province_seulement"
    link_stats[how] += 1
    ent(eid, "localite_postale", "geographie", name, "bpost", code=str(pc), country="BE", parent_id=parent,
        postal_code=str(pc), lang_label="", link_method=how)
    alias(eid, f"{pc} {name}", "", "code_postal_et_nom", "bpost", 1)
    if name != raw_name:
        alias(eid, raw_name, "", "variante_source_brute", "bpost", 2)
    rel(eid, "situe_dans", parent, "bpost" if how != "province_seulement" else "rule")

# ------------------------------------------------------------------ taxonomie des pièces (Shopify)
def read_tax(loc):
    out = {}
    for line in open(RAW / f"shopify/{loc}_categories.txt", encoding="utf-8"):
        if "TaxonomyCategory/vp-1-4" not in line:
            continue
        gid, path = line.split(":", 2)[1:] if line.startswith("gid") else (None, None)
        gid = line.split()[0].rsplit("/", 1)[1]
        path = line.split(" : ", 1)[1].strip()
        out[gid] = path.split(" > ")
    return out


tax = {l: read_tax(l) for l in ("en", "fr", "nl", "de")}
for gid in sorted(tax["en"], key=lambda g: [int(p) if p.isdigit() else p for p in g.split("-")]):
    labels = {l: tax[l][gid][-1] for l in tax}
    parent = gid.rsplit("-", 1)[0]
    level = len(gid.split("-")) - 3
    eid = f"piece:cat:{gid}"
    ent(eid, "categorie_piece", "produit", labels["fr"], "shopify", code=gid, label_fr=labels["fr"],
        label_nl=labels["nl"], label_de=labels["de"], label_en=labels["en"], lang_label="fr",
        parent_id=f"piece:cat:{parent}" if level > 0 else "", level=level, path_fr=" > ".join(tax["fr"][gid][3:]))
    for l in ("en", "nl", "de"):
        alias(eid, labels[l], l, "traduction_officielle", "shopify", 1)
    if level > 0:
        rel(eid, "sous_categorie_de", f"piece:cat:{parent}", "shopify")

# ------------------------------------------------------------------ véhicules (EEA)
brands = {}
for b in csv.DictReader(open(RAW / "ovd_rel/brands.csv", encoding="utf-8")):
    eid = f"veh:marque:{b['id'].removeprefix('brand_')}"
    brands[b["id"]] = eid
    ent(eid, "marque_vehicule", "vehicule", b["name"], "eea", code=b["id"], lang_label="")
    for a in re.split(r"\|", b["aliases"] or ""):
        for part in [a] + ([p.strip() for p in a.split(",")] if "," in a else []):
            if part.strip() and normalize(part) != normalize(b["name"]):
                alias(eid, part.strip(), "", "alias_source", "eea", 2)
for m in csv.DictReader(open(RAW / "ovd_rel/models.csv", encoding="utf-8")):
    eid = f"veh:modele:{m['id'].removeprefix('model_')}"
    bid = brands[m["brand_id"]]
    ent(eid, "modele_vehicule", "vehicule", m["name"], "eea", code=m["id"], parent_id=bid,
        registrations=m["registrations"], lang_label="")
    for a in (m["aliases"] or "").split("|"):
        if a.strip():
            alias(eid, a.strip(), "", "alias_source", "eea", 2)
    alias(eid, f"{E[bid]['label']} {m['name']}", "", "marque_et_modele", "eea", 2)
    rel(eid, "modele_de", bid, "eea")

# ------------------------------------------------------------------ nomenclature douanière
HS_KEEP = ("2710", "3819", "3820", "4009", "4010", "4016", "6813", "7007", "7009", "7315", "7320", "8301", "8302", "8407", "8408",
           "8409", "8413", "8414", "8415", "8421", "8481", "8482", "8483", "8484", "8507", "8511", "8512", "8536",
           "8539", "8544", "8708", "9026", "9029", "9031", "9032", "9401", "9029")
for r in csv.DictReader(open(RAW / "hs.csv", encoding="utf-8")):
    code = r["hscode"]
    if len(code) not in (4, 6) or not code.startswith(HS_KEEP):
        continue
    eid = f"douane:sh:{code}"
    ent(eid, "code_douanier", "produit", r["description"], "hs", code=code, label_en=r["description"],
        parent_id=f"douane:sh:{r['parent']}" if len(code) == 6 else "", lang_label="en")
    dotted = f"{code[:4]}.{code[4:]}" if len(code) == 6 else code
    alias(eid, code, "", "code", "hs", 1)
    if dotted != code:
        alias(eid, dotted, "", "code_format_point", "hs", 1)
    if len(code) == 6:
        rel(eid, "sous_code_de", f"douane:sh:{r['parent']}", "hs")

# ------------------------------------------------------------------ export
for e in E.values():
    e.pop("lang_label", None)
FIELDS_E = ["entity_id", "entity_type", "domain", "label", "label_fr", "label_nl", "label_de", "label_en", "code",
            "country", "parent_id", "level", "population", "postal_code", "registrations", "geonameid", "link_method",
            "path_fr", "tier", "source", "licence"]
FIELDS_A = ["entity_id", "alias", "alias_norm", "lang", "alias_type", "tier", "source", "licence"]
FIELDS_R = ["subject_id", "predicate", "object_id", "source"]

uniq, seen = [], set()
for a in A:
    k = (a["entity_id"], a["alias_norm"])
    if k in seen:
        continue
    seen.add(k)
    uniq.append(a)

ne = write_csv(CAT / "open_entities.csv", list(E.values()), FIELDS_E, ["entity_id"])
na = write_csv(CAT / "open_aliases.csv", uniq, FIELDS_A, ["entity_id", "alias_norm"])
nr = write_csv(CAT / "open_relations.csv", R, FIELDS_R, ["subject_id", "predicate", "object_id"])
no = write_csv(CAT / "hors_perimetre_geonames.csv", OUT, ["geonameid", "name", "name_norm", "country", "admin1", "population"], ["geonameid"])
ni = write_csv(REP / "source_issues.csv", ISSUES, ["source", "type", "detail"], ["source", "type", "detail"])
print(f"entités {ne} · alias {na} · relations {nr} · hors périmètre {no} · anomalies {ni}")
print("types :", dict(Counter(e["entity_type"] for e in E.values())))
print("variantes GeoNames :", dict(GN_STATS))
print("rattachement des localités :", dict(link_stats), "· GeoNames BE non rattachés :", gn_be_unmatched)
