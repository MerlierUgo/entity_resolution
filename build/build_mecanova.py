"""
Couche 2 du catalogue : compléments propres à Mécanova (entreprise fictive), générés avec une graine fixe
ou curatés à la main. Tout ce qui sort d'ici est marqué tier 3 et source « généré » ou « curation ».

Produit catalog/mecanova_entities.csv, mecanova_aliases.csv, mecanova_relations.csv
et reports/taxonomy_translation_issues.csv.
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict

from faker import Faker

from common import CAT, REP, SEED, normalize, read_csv, slug, write_csv

GEN = ("Généré Mécanova (graine 20261102)", "CC0 (données synthétiques)")
CUR = ("Curation manuelle, connaissance publique, à vérifier", "CC0")
rng = random.Random(SEED)
fk = {loc: Faker(loc) for loc in ("fr_BE", "nl_BE", "fr_FR", "nl_NL", "de_DE")}
for i, f in enumerate(fk.values()):
    f.seed_instance(SEED + i)

OE = {e["entity_id"]: e for e in read_csv(CAT / "open_entities.csv")}
by_code = defaultdict(dict)
for e in OE.values():
    by_code[e["entity_type"]][e["code"]] = e
E, A, R, TI = {}, [], [], []


def ent(eid, etype, domain, label, src=GEN, **kw):
    assert eid not in E and eid not in OE, eid
    E[eid] = {"entity_id": eid, "entity_type": etype, "domain": domain, "label": label, "tier": 3,
              "source": src[0], "licence": src[1], **kw}
    alias(eid, label, kw.pop("_lang", "fr"), "libelle_canonique", src)


def alias(eid, text, lang, atype, src=GEN):
    if text and normalize(text):
        A.append({"entity_id": eid, "alias": text, "alias_norm": normalize(text), "lang": lang,
                  "alias_type": atype, "tier": 3, "source": src[0], "licence": src[1]})


def rel(s, p, o, src=GEN):
    R.append({"subject_id": s, "predicate": p, "object_id": o, "source": src[0]})


def geo(etype, label, country):
    hits = [e for e in OE.values() if e["entity_type"] == etype and e["label"] == label and e["country"] == country]
    assert len(hits) == 1, (etype, label, country, len(hits))
    return hits[0]["entity_id"]


# ------------------------------------------------------------------ termes métier pour les traductions faibles
# Libellés Shopify (traduction automatique probable) qui ne correspondent pas au vocabulaire de l'atelier.
TRADE_TERMS = {
    "vp-1-4-14-2": ("Piles", ["batteries", "batterie de démarrage"]),
    "vp-1-4-6-9": ("Vannes", ["soupapes"]),
    "vp-1-4-1-2": ("Boosters de frein", ["servofreins", "servo-frein"]),
    "vp-1-4-6-3": ("Têtes de cylindres", ["culasses"]),
    "vp-1-4-17-5": ("Amortisseurs de chocs", ["amortisseurs", "amortos"]),
    "vp-1-4-17-3": ("Bras de contrôle", ["bras de suspension", "triangles de suspension"]),
    "vp-1-4-17-1": ("Joints à rotules", ["rotules"]),
    "vp-1-4-3-2": ("Condensateurs de climatisation", ["condenseurs de climatisation"]),
    "vp-1-4-3-8": ("Noyaux de chauffage", ["radiateurs de chauffage"]),
    "vp-1-4-19-15": ("Plaques de pression d'embrayage", ["mécanismes d'embrayage"]),
    "vp-1-4-6-7": ("Courroies crantées", ["courroies de distribution", "kits de distribution", "kit distri"]),
    "vp-1-4-14-5": ("Bougies de voiture", ["bougies d'allumage"]),
    "vp-1-4-22-7": ("Cols d'eau", ["boîtiers de sortie d'eau"]),
}
for gid, (shop_fr, terms) in TRADE_TERMS.items():
    eid = f"piece:cat:{gid}"
    assert OE[eid]["label_fr"] == shop_fr, (gid, OE[eid]["label_fr"])
    TI.append({"category": gid, "label_en": OE[eid]["label_en"], "label_fr_source": shop_fr,
               "terme_metier_fr": terms[0], "action": "alias métier ajouté (tier 3), libellé source conservé"})
    for t in terms:
        alias(eid, t, "fr", "terme_metier", CUR)

# ------------------------------------------------------------------ familles Mécanova et assortiment
FAMILLES = {
    "Freinage": (["freins"], {"vp-1-4-1-7": "PLQ", "vp-1-4-1-8": "DSQ", "vp-1-4-1-3": "ETR", "vp-1-4-1-11": "MCH",
                              "vp-1-4-1-9": "TBF", "vp-1-4-1-13": "FLX"}),
    "Filtration": (["filtres"], {"vp-1-4-5-5": "FHU", "vp-1-4-23-1": "FAI", "vp-1-4-10-3": "FCA", "NEW:Filtres d'habitacle": "FHA"}),
    "Allumage et démarrage": (["allumage", "démarrage", "électricité moteur"],
                              {"vp-1-4-14-5": "BGA", "vp-1-4-6-5-1": "BGP", "vp-1-4-14-6": "DEM", "vp-1-4-14-1": "ALT",
                               "vp-1-4-6-5-2": "BOB"}),
    "Batteries": ([], {"vp-1-4-14-2": "BAT"}),
    "Éclairage": (["lumière", "optique"], {"vp-1-4-12-4": "AMP", "vp-1-4-12-2": "PHA", "vp-1-4-12-7": "FEU", "vp-1-4-12-8": "CLI"}),
    "Suspension et direction": (["suspension", "direction", "train roulant"],
                                {"vp-1-4-17-5": "AMO", "vp-1-4-17-2": "RES", "vp-1-4-17-1": "ROT", "vp-1-4-17-3": "BRA",
                                 "vp-1-4-17-8": "BST"}),
    "Distribution": ([], {"vp-1-4-6-7": "KDI", "vp-1-4-6-8": "CHD"}),
    "Embrayage": ([], {"vp-1-4-19-2": "KEM", "vp-1-4-19-13": "VOL", "vp-1-4-19-16": "BUT"}),
    "Refroidissement": ([], {"vp-1-4-22-10": "RAD", "vp-1-4-22-12": "PEA", "vp-1-4-22-3": "THE", "vp-1-4-22-8": "VEX"}),
    "Échappement": ([], {"vp-1-4-8-5": "SIL", "vp-1-4-8-2": "CAT", "NEW:Filtres à particules": "FAP"}),
    "Huiles et liquides": (["lubrifiants", "liquides"], {"vp-1-4-1-4": "LFR", "vp-1-4-19-6": "LTR", "NEW:Huile moteur": "HUI",
                                                        "NEW:Liquide de refroidissement": "LRF"}),
    "Essuyage": (["visibilité"], {"vp-1-4-21-4-2": "BES", "vp-1-4-21-4-4": "MES"}),
    "Accessoires": ([], {"vp-1-4-11-3": "TAP", "NEW:Chaînes à neige": "CHN"}),
}
NEW_CAT_ALIASES = {"Filtres d'habitacle": ["filtres à pollen", "filtre habitacle"], "Filtres à particules": ["FAP"],
                   "Huile moteur": ["huile"], "Liquide de refroidissement": ["antigel"], "Chaînes à neige": ["chaînes"]}
HS = {"PLQ": "870830", "DSQ": "870830", "ETR": "870830", "MCH": "870830", "TBF": "870830", "FLX": "870830",
      "FHU": "842123", "FAI": "842131", "FCA": "842123", "FHA": "842139", "BGA": "851110", "BGP": "851180",
      "DEM": "851140", "ALT": "851150", "BOB": "851130", "BAT": "850710", "AMP": "853921", "PHA": "851220",
      "FEU": "851220", "CLI": "851220", "AMO": "870880", "RES": "732020", "ROT": "870880", "BRA": "870880",
      "BST": "870880", "KDI": "4010", "CHD": "731511", "KEM": "870893", "VOL": "848350", "BUT": "848210",
      "RAD": "870891", "PEA": "841330", "THE": "848180", "VEX": "870891", "SIL": "870892", "CAT": "870892",
      "FAP": "842139", "LFR": "381900", "LTR": "271019", "HUI": "271019", "LRF": "382000", "BES": "851240",
      "MES": "851240", "TAP": None, "CHN": None}
ECHANGE_STANDARD = {"ALT", "DEM", "ETR"}
cat_of_prefix, fam_of_prefix = {}, {}
for fam, (aliases_f, cats) in FAMILLES.items():
    fid = f"mecanova:famille:{slug(fam)}"
    ent(fid, "famille_mecanova", "produit", fam, CUR)
    for a in aliases_f:
        alias(fid, a, "fr", "synonyme_metier", CUR)
    for key, pfx in cats.items():
        if key.startswith("NEW:"):
            label = key[4:]
            cid = f"mecanova:cat:{slug(label)}"
            ent(cid, "categorie_piece", "produit", label, CUR, label_fr=label, code=pfx,
                note="Absente de la taxonomie Shopify : catégorie ajoutée")
            for a in NEW_CAT_ALIASES.get(label, []):
                alias(cid, a, "fr", "synonyme_metier", CUR)
        else:
            cid = f"piece:cat:{key}"
            assert cid in OE, cid
        rel(cid, "famille_mecanova", fid, CUR)
        if HS[pfx]:
            rel(cid, "code_douanier", f"douane:sh:{HS[pfx]}", CUR)
        cat_of_prefix[pfx], fam_of_prefix[pfx] = cid, fam

# ------------------------------------------------------------------ marques de pièces (curation)
BRANDS = [
    # (nom, alias, groupe, familles de spécialité)
    ("Bosch", ["Robert Bosch", "BOSCH"], "Robert Bosch GmbH", ["Freinage", "Allumage et démarrage", "Filtration", "Essuyage", "Batteries"]),
    ("Valeo", ["VALEO"], "Valeo", ["Embrayage", "Éclairage", "Essuyage", "Refroidissement", "Allumage et démarrage"]),
    ("Brembo", ["BREMBO"], "Brembo", ["Freinage"]),
    ("TRW", ["TRW Automotive", "ZF TRW"], "ZF Friedrichshafen", ["Freinage", "Suspension et direction"]),
    ("Sachs", ["ZF Sachs", "SACHS"], "ZF Friedrichshafen", ["Embrayage", "Suspension et direction"]),
    ("Lemförder", ["Lemforder", "Lemfoerder"], "ZF Friedrichshafen", ["Suspension et direction"]),
    ("ATE", ["Alfred Teves"], "Continental", ["Freinage", "Huiles et liquides"]),
    ("ContiTech", ["Conti Tech", "Continental ContiTech"], "Continental", ["Distribution"]),
    ("Textar", ["TEXTAR"], "TMD Friction", ["Freinage"]),
    ("Ferodo", ["FERODO"], "Tenneco", ["Freinage"]),
    ("Monroe", ["MONROE"], "Tenneco", ["Suspension et direction"]),
    ("Walker", ["WALKER"], "Tenneco", ["Échappement"]),
    ("Champion", ["CHAMPION"], "Tenneco", ["Allumage et démarrage", "Essuyage"]),
    ("Mann-Filter", ["Mann Filter", "MANN-FILTER", "Mann"], "Mann+Hummel", ["Filtration"]),
    ("Mahle", ["MAHLE", "Mahle Original"], "Mahle", ["Filtration", "Refroidissement"]),
    ("Knecht", ["KNECHT"], "Mahle", ["Filtration"]),
    ("Behr", ["BEHR", "Behr Hella Service"], "Mahle", ["Refroidissement"]),
    ("Purflux", ["PURFLUX"], "Sogefi", ["Filtration"]),
    ("NGK", ["NGK Spark Plug", "Niterra NGK"], "Niterra", ["Allumage et démarrage"]),
    ("Denso", ["DENSO"], "Denso", ["Allumage et démarrage", "Refroidissement"]),
    ("Varta", ["VARTA"], "Clarios", ["Batteries"]),
    ("Exide", ["EXIDE"], "Exide Technologies", ["Batteries"]),
    ("Gates", ["GATES"], "Gates Corporation", ["Distribution", "Refroidissement"]),
    ("Dayco", ["DAYCO"], "Dayco", ["Distribution"]),
    ("INA", ["Schaeffler INA"], "Schaeffler", ["Distribution"]),
    ("LuK", ["LUK", "Schaeffler LuK"], "Schaeffler", ["Embrayage"]),
    ("KYB", ["Kayaba"], "KYB Corporation", ["Suspension et direction"]),
    ("Bilstein", ["BILSTEIN"], "thyssenkrupp", ["Suspension et direction"]),
    ("febi bilstein", ["Febi", "FEBI BILSTEIN", "febi"], "Bilstein Group", ["Suspension et direction", "Refroidissement", "Distribution"]),
    ("Hella", ["HELLA"], "Forvia", ["Éclairage"]),
    ("Philips", ["PHILIPS"], "Lumileds", ["Éclairage"]),
    ("Osram", ["OSRAM"], "ams OSRAM", ["Éclairage"]),
    ("Nissens", ["NISSENS"], "Nissens", ["Refroidissement"]),
    ("Bosal", ["BOSAL"], "Bosal", ["Échappement"]),
    ("Castrol", ["CASTROL"], "BP", ["Huiles et liquides"]),
    ("TotalEnergies", ["Total", "TOTAL", "Total Quartz"], "TotalEnergies", ["Huiles et liquides"]),
    ("Liqui Moly", ["LiquiMoly", "LIQUI MOLY"], "Würth", ["Huiles et liquides"]),
    ("Mécanova Select", ["marque maison", "marque propre", "MDD", "Select"], "Mécanova SA (fictive)",
     list(FAMILLES)),
]
groups = {}
brands_by_family = defaultdict(list)
BRAND_SLUGS = {slug(b[0]) for b in BRANDS}
for name, als, group, fams in BRANDS:
    bid = f"piece:marque:{slug(name)}"
    ent(bid, "marque_piece", "produit", name, CUR if "Mécanova" not in name else GEN, _lang="")
    for a in als:
        alias(bid, a, "", "alias_marque", CUR)
    if slug(group) != slug(name):
        glabel = f"Groupe {group}" if slug(group) in BRAND_SLUGS else group
        gid = f"organisation:{slug(glabel)}"
        if gid not in groups:
            groups[gid] = glabel
            ent(gid, "groupe_industriel", "produit", glabel, CUR, _lang="")
        rel(bid, "appartient_au_groupe", gid, CUR)
    for f in fams:
        brands_by_family[f].append(bid)

# ------------------------------------------------------------------ formes juridiques (curation)
FORMS = [
    # (pays, forme canonique, variantes, ancienne forme ?)
    ("BE", "SRL", ["S.R.L.", "srl", "BV", "B.V."], False),
    ("BE", "SPRL", ["S.P.R.L.", "sprl", "BVBA", "B.V.B.A.", "bvba"], True),
    ("BE", "SA", ["S.A.", "NV", "N.V."], False),
    ("BE", "SC", ["S.C.", "CV", "C.V."], False),
    ("FR", "SARL", ["S.A.R.L.", "sarl"], False),
    ("FR", "SAS", ["S.A.S.", "sas"], False),
    ("FR", "EURL", ["E.U.R.L."], False),
    ("NL", "B.V.", ["BV", "bv"], False),
    ("NL", "V.O.F.", ["VOF", "vof"], False),
    ("LU", "S.à r.l.", ["SARL", "S.à.r.l.", "Sàrl"], False),
    ("LU", "S.A.", ["SA"], False),
]
for cc, form, variants, legacy in FORMS:
    fid = f"juridique:{cc}:{slug(form)}"
    ent(fid, "forme_juridique", "client", form, CUR, country=cc, legacy="oui" if legacy else "non", _lang="")
    for v in variants:
        alias(fid, v, "", "variante_forme", CUR)
rel("juridique:BE:sprl", "remplace_par", "juridique:BE:srl", CUR)

# ------------------------------------------------------------------ sites Mécanova
SITES = [("Entrepôt central", "commune", "Namur", "BE", "entrepôt"), ("Agence Namur", "commune", "Namur", "BE", "agence"),
         ("Agence Liège", "commune", "Liège", "BE", "agence"), ("Agence Charleroi", "commune", "Charleroi", "BE", "agence"),
         ("Agence Bruxelles", "commune", "Bruxelles", "BE", "agence"), ("Agence Arlon", "commune", "Arlon", "BE", "agence"),
         ("Agence Luxembourg", "commune", "Luxembourg", "LU", "agence"), ("Agence Lille", "ville", "Lille", "FR", "agence"),
         ("Agence Metz", "ville", "Metz", "FR", "agence"), ("Agence Maastricht", "ville", "Maastricht", "NL", "agence")]
site_ids = {}
for name, gt, city, cc, kind in SITES:
    sid = f"mecanova:site:{slug(name)}"
    site_ids[name] = sid
    ent(sid, "site", "organisation", name, GEN, country=cc, site_type=kind)
    rel(sid, "situe_dans", geo(gt, city, cc))
COMMERCIAUX = [("Sophie Lambert", "Agence Namur"), ("Thomas Renard", "Agence Charleroi"), ("Laura Fontaine", "Agence Liège"),
               ("Kevin Dubois", "Agence Liège"), ("Pieter Claes", "Agence Bruxelles"), ("Nadia El Amrani", "Agence Lille"),
               ("Hugo Schmit", "Agence Luxembourg"), ("Elise Marchal", "Agence Metz"), ("Bram Hendriks", "Agence Maastricht"),
               ("Julie Collard", "Agence Arlon")]
reps_by_site = defaultdict(list)
for nom, site in COMMERCIAUX:
    rid = f"mecanova:commercial:{slug(nom)}"
    ent(rid, "commercial", "organisation", nom, GEN, _lang="")
    rel(rid, "travaille_a", site_ids[site])
    reps_by_site[site].append(rid)
alias(site_ids["Entrepôt central"], "entrepôt", "fr", "synonyme_metier")
alias(site_ids["Entrepôt central"], "dépôt", "fr", "synonyme_metier")

# ------------------------------------------------------------------ clients professionnels
geo_pool = defaultdict(list)
for e in OE.values():
    if e["entity_type"] in ("commune", "ville") and e["population"]:
        geo_pool[e["country"]].append(e)
prov_of = {}
for r in read_csv(CAT / "open_relations.csv"):
    if r["predicate"] == "situe_dans":
        prov_of[r["subject_id"]] = r["object_id"]


def ancestor(eid, etypes):
    seen = 0
    while eid and seen < 8:
        eid = prov_of.get(eid)
        if eid and OE.get(eid, {}).get("entity_type") in etypes:
            return eid
        seen += 1
    return None


AGENCY_BY_PROV = {"BE-WLG": "Agence Liège", "BE-WNA": "Agence Namur", "BE-WHT": "Agence Charleroi", "BE-WLX": "Agence Arlon",
                  "BE-WBR": "Agence Bruxelles", "BE-VBR": "Agence Bruxelles", "BE-VLI": "Agence Liège"}
WEIGHT_BE = {"BE-WLG": 6, "BE-WNA": 6, "BE-WHT": 5, "BE-WLX": 3, "BE-WBR": 2, "BE-VBR": 1, "BE-VLI": 1, "BE-BRU": 4}


def pick_location(cc):
    pool = geo_pool[cc]
    if cc == "BE":
        weights = []
        for e in pool:
            p = ancestor(e["entity_id"], {"province", "region"})
            code = OE[p]["code"] if p else ""
            weights.append(WEIGHT_BE.get(code, 0) * (float(e["population"]) ** 0.5))
    else:
        weights = [float(e["population"]) ** 0.5 for e in pool]
    return rng.choices(pool, weights=weights, k=1)[0]


def agency_for(loc):
    cc = loc["country"]
    if cc == "LU":
        return "Agence Luxembourg"
    if cc == "NL":
        return "Agence Maastricht"
    if cc == "FR":
        return "Agence Lille" if prov_of.get(loc["entity_id"]) == "geo:region:FR-HDF" else "Agence Metz"
    p = ancestor(loc["entity_id"], {"province", "region"})
    return AGENCY_BY_PROV.get(OE[p]["code"], "Agence Bruxelles") if p else "Agence Bruxelles"


VEH_BRANDS = ["RENAULT", "PEUGEOT", "CITROEN", "VOLKSWAGEN", "TOYOTA", "FORD", "OPEL", "DACIA", "BMW", "AUDI",
              "SKODA", "KIA", "HYUNDAI", "FIAT", "NISSAN", "MERCEDES-BENZ"]
veh_brand_ids = {e["label"]: e["entity_id"] for e in OE.values() if e["entity_type"] == "marque_vehicule"}
assert all(b in veh_brand_ids for b in VEH_BRANDS), [b for b in VEH_BRANDS if b not in veh_brand_ids]
TYPES = [("Garage indépendant", 55), ("Carrossier", 15), ("Concession", 12), ("Flotte et loueur", 10), ("Centre auto", 8)]
for t, _ in TYPES:
    ent(f"mecanova:type_client:{slug(t)}", "type_client", "client", t, CUR)
FORM_W = {"BE": [("SRL", 55), ("SPRL", 15), ("SA", 25), ("SC", 5)], "FR": [("SARL", 50), ("SAS", 35), ("EURL", 15)],
          "NL": [("B.V.", 75), ("V.O.F.", 25)], "LU": [("S.à r.l.", 75), ("S.A.", 25)]}


def lang_for(loc):
    if loc["country"] == "NL":
        return "nl"
    if loc["country"] == "BE":
        reg = ancestor(loc["entity_id"], {"region"})
        return "nl" if reg == "geo:region:BE-VLG" else "fr"
    return "fr"


def name_for(ctype, loc, lang):
    f = fk["nl_BE" if lang == "nl" and loc["country"] == "BE" else "nl_NL" if lang == "nl" else
          "fr_FR" if loc["country"] in ("FR", "LU") else "fr_BE"]
    nom, city = f.last_name(), loc["label"]
    if ctype == "Garage indépendant":
        pats = (["Garage {n}", "Garage {n} & Zonen", "Autobedrijf {n}", "Autoservice {n}"] if lang == "nl" else
                ["Garage {n}", "Garage {n} & Fils", "Garage {n} Frères", "Auto {n}", "{n} Automobiles", "Garage de la Gare", "Garage du Centre"])
    elif ctype == "Carrossier":
        pats = ["Carrosserie {n}", "Carrosseriebedrijf {n}"] if lang == "nl" else ["Carrosserie {n}", "Carrosserie {c}", "{n} Carrosserie"]
    elif ctype == "Concession":
        b = rng.choice(VEH_BRANDS).title().replace("Mercedes-Benz", "Mercedes-Benz")
        pats = [f"{b} {{c}}", f"{b} {{n}}", f"Ets {{n}} – {b}", f"{{n}} {b} {{c}}"]
    elif ctype == "Flotte et loueur":
        pats = ["{n} Fleet Services", "{c} Lease", "Transports {n}", "{n} Logistics"] if lang == "fr" else \
               ["{n} Fleet Services", "{c} Lease", "Transport {n}", "{n} Logistiek"]
    else:
        pats = ["Centre Auto {c}", "{c} Auto Center", "Auto Center {n}"] if lang == "fr" else ["Autocenter {c}", "{c} Auto Center"]
    return rng.choice(pats).format(n=nom, c=city)


ctype_ids = {t: f"mecanova:type_client:{slug(t)}" for t, _ in TYPES}
form_ids = {(cc, form): f"juridique:{cc}:{slug(form)}" for cc, form, _, _ in FORMS}
form_variants = {(cc, form): v for cc, form, v, _ in FORMS}
N_CLIENTS = 1400
for i in range(N_CLIENTS):
    cc = rng.choices(["BE", "FR", "LU", "NL"], weights=[65, 15, 10, 10])[0]
    loc = pick_location(cc)
    ctype = rng.choices([t for t, _ in TYPES], weights=[w for _, w in TYPES])[0]
    lang = lang_for(loc)
    trade = name_for(ctype, loc, lang)
    form = rng.choices([f for f, _ in FORM_W[cc]], weights=[w for _, w in FORM_W[cc]])[0]
    legal = f"{trade} {form}"
    code = f"CL-{100000 + rng.randrange(0, 899999):06d}"
    while f"mecanova:client:{code}" in E:
        code = f"CL-{100000 + rng.randrange(0, 899999):06d}"
    cid = f"mecanova:client:{code}"
    ent(cid, "client", "client", legal, GEN, code=code, country=cc, client_type=ctype, trade_name=trade, legal_form=form,
        city=loc["label"], _lang=lang)
    alias(cid, code, "", "code_client")
    alias(cid, trade, lang, "nom_commercial")
    alias(cid, trade.upper(), lang, "variante_casse")
    if rng.random() < 0.5:
        alias(cid, f"{trade} {rng.choice(form_variants[(cc, form)])}", lang, "variante_forme_juridique")
    if form == "SRL" and rng.random() < 0.4:
        alias(cid, f"{trade} SPRL", lang, "ancienne_forme_juridique")
    if trade.startswith("Garage ") and rng.random() < 0.3:
        alias(cid, "Gar. " + trade[7:], lang, "abreviation")
    if " & " in trade:
        alias(cid, trade.replace(" & ", " et " if lang == "fr" else " en "), lang, "variante_esperluette")
    rel(cid, "situe_dans", loc["entity_id"])
    rel(cid, "type_de_client", ctype_ids[ctype])
    rel(cid, "forme_juridique", form_ids[(cc, form)])
    agence = agency_for(loc)
    rel(cid, "rattache_a", site_ids[agence])
    rel(cid, "suivi_par", rng.choice(reps_by_site[agence]))

# ------------------------------------------------------------------ articles
models_by_brand = defaultdict(list)
for e in OE.values():
    if e["entity_type"] == "modele_vehicule" and int(e["registrations"] or 0) >= 50:
        models_by_brand[e["parent_id"]].append(e)
POS = {"PLQ": ["avant", "arrière"], "DSQ": ["avant", "arrière"], "AMO": ["avant", "arrière"], "ETR": ["avant gauche", "avant droit"]}
GAMMES = [("Premium", 25), ("Standard", 50), ("Éco", 25)]
QUALITES = [("Origine", 15), ("Équivalent origine", 45), ("Adaptable", 40)]
for g, _ in GAMMES:
    ent(f"mecanova:gamme:{slug(g)}", "gamme", "produit", g, CUR)
for q, _ in QUALITES:
    ent(f"mecanova:qualite:{slug(q)}", "qualite", "produit", q, CUR)
for a, t in [("haut de gamme", "Premium"), ("entrée de gamme", "Éco"), ("premier prix", "Éco"), ("économique", "Éco"),
             ("milieu de gamme", "Standard")]:
    alias(f"mecanova:gamme:{slug(t)}", a, "fr", "synonyme_metier", CUR)
for a, t in [("OE", "Origine"), ("pièce d'origine", "Origine"), ("première monte", "Origine"), ("OES", "Équivalent origine"),
             ("aftermarket", "Adaptable"), ("IAM", "Adaptable")]:
    alias(f"mecanova:qualite:{slug(t)}", a, "", "synonyme_metier", CUR)

N_ART = 2400
weights = {p: (3 if p in ("PLQ", "DSQ", "FHU", "FAI", "BAT", "AMO", "BGA", "BES", "AMP", "KDI") else 1) for p in cat_of_prefix}
used_codes = set()
articles = []
for i in range(N_ART):
    pfx = rng.choices(list(weights), weights=list(weights.values()))[0]
    fam = fam_of_prefix[pfx]
    cid = cat_of_prefix[pfx]
    brand = rng.choice(brands_by_family[fam])
    num = rng.randrange(10000, 99999)
    while (pfx, num) in used_codes:
        num = rng.randrange(10000, 99999)
    used_codes.add((pfx, num))
    articles.append((pfx, num, cid, fam, brand))
# paires de références voisines (un seul chiffre d'écart), toutes deux valides
for pfx, num, cid, fam, brand in list(articles[:120]):
    near = num + rng.choice([1, 10, 50, 100])
    if (pfx, near) not in used_codes and near < 100000:
        used_codes.add((pfx, near))
        articles.append((pfx, near, cid, fam, brand))

PFX_LABEL = {"PLQ": "Plaquettes de frein", "DSQ": "Disques de frein", "ETR": "Étrier de frein", "MCH": "Mâchoires de frein",
             "TBF": "Tambour de frein", "FLX": "Flexible de frein", "FHU": "Filtre à huile", "FAI": "Filtre à air",
             "FCA": "Filtre à carburant", "FHA": "Filtre d'habitacle", "BGA": "Bougie d'allumage", "BGP": "Bougie de préchauffage",
             "DEM": "Démarreur", "ALT": "Alternateur", "BOB": "Bobine d'allumage", "BAT": "Batterie", "AMP": "Ampoule",
             "PHA": "Phare", "FEU": "Feu arrière", "CLI": "Clignotant", "AMO": "Amortisseur", "RES": "Ressort de suspension",
             "ROT": "Rotule", "BRA": "Bras de suspension", "BST": "Barre stabilisatrice", "KDI": "Kit de distribution",
             "CHD": "Kit chaîne de distribution", "KEM": "Kit d'embrayage", "VOL": "Volant moteur", "BUT": "Butée d'embrayage",
             "RAD": "Radiateur", "PEA": "Pompe à eau", "THE": "Thermostat", "VEX": "Vase d'expansion", "SIL": "Silencieux",
             "CAT": "Catalyseur", "FAP": "Filtre à particules", "LFR": "Liquide de frein", "LTR": "Huile de boîte de vitesses",
             "HUI": "Huile moteur", "LRF": "Liquide de refroidissement", "BES": "Balai d'essuie-glace",
             "MES": "Moteur d'essuie-glace", "TAP": "Tapis de sol", "CHN": "Chaînes à neige"}
assert set(PFX_LABEL) == set(cat_of_prefix)
for k, v in PFX_LABEL.items():
    alias(cat_of_prefix[k], v, "fr", "terme_catalogue_mecanova", CUR)
cat_label = PFX_LABEL
art_ids = []
for pfx, num, cid, fam, brand in sorted(articles):
    ref = f"MN-{pfx}-{num}"
    aid = f"mecanova:article:{ref}"
    gamme = rng.choices([g for g, _ in GAMMES], weights=[w for _, w in GAMMES])[0]
    qual = rng.choices([q for q, _ in QUALITES], weights=[w for _, w in QUALITES])[0]
    bname = E[brand]["label"]
    pos = f" {rng.choice(POS[pfx])}" if pfx in POS else ""
    label = f"{cat_label[pfx]}{pos} – {bname} {gamme}"
    mref = f"{slug(bname).upper().replace('-', '')[:3]}-{rng.randrange(100000, 999999)}"
    ent(aid, "article", "produit", label, GEN, code=ref, manufacturer_ref=mref, gamme=gamme, qualite=qual,
        echange_standard="oui" if pfx in ECHANGE_STANDARD else "non")
    alias(aid, ref, "", "reference_mecanova")
    alias(aid, ref.replace("-", ""), "", "reference_sans_tiret")
    alias(aid, ref.replace("-", " ").lower(), "", "reference_minuscules")
    alias(aid, mref, "", "reference_fabricant")
    rel(aid, "classe_dans", cid)
    rel(aid, "fabrique_par", brand)
    rel(aid, "gamme", f"mecanova:gamme:{slug(gamme)}")
    rel(aid, "qualite", f"mecanova:qualite:{slug(qual)}")
    if pfx not in ("LFR", "LTR", "HUI", "LRF", "TAP", "CHN", "AMP"):
        vb = veh_brand_ids[rng.choice(VEH_BRANDS)]
        for m in rng.sample(models_by_brand[vb], k=min(len(models_by_brand[vb]), rng.randint(1, 4))):
            rel(aid, "compatible_avec", m["entity_id"])
    art_ids.append(aid)
# références remplacées (supersession)
for aid in rng.sample(art_ids, k=int(len(art_ids) * 0.03)):
    new = rng.choice([a for a in art_ids if a != aid and a.split(":")[-1][:6] == aid.split(":")[-1][:6]] or [None])
    if new:
        rel(aid, "remplace_par", new)

# ------------------------------------------------------------------ export
FIELDS_E = ["entity_id", "entity_type", "domain", "label", "label_fr", "code", "country", "client_type", "trade_name",
            "legal_form", "city", "site_type", "manufacturer_ref", "gamme", "qualite", "echange_standard", "legacy", "note",
            "tier", "source", "licence"]
seen, uniq = set(), []
for a in A:
    k = (a["entity_id"], a["alias_norm"])
    if k not in seen:
        seen.add(k)
        uniq.append(a)
ne = write_csv(CAT / "mecanova_entities.csv", list(E.values()), FIELDS_E, ["entity_id"])
na = write_csv(CAT / "mecanova_aliases.csv", uniq, ["entity_id", "alias", "alias_norm", "lang", "alias_type", "tier", "source", "licence"], ["entity_id", "alias_norm"])
nr = write_csv(CAT / "mecanova_relations.csv", R, ["subject_id", "predicate", "object_id", "source"], ["subject_id", "predicate", "object_id"])
write_csv(REP / "taxonomy_translation_issues.csv", TI, ["category", "label_en", "label_fr_source", "terme_metier_fr", "action"], ["category"])
print(f"entités {ne} · alias {na} · relations {nr}")
print(dict(Counter(e["entity_type"] for e in E.values())))
