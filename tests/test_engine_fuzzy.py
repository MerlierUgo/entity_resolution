"""Tests du moteur, étape 2 : Jaro-Winkler borné (engine/approche.py), ordre des mots et voisins en
distance d'édition (R-RES-11), calibration SGR (engine/calibration.py) et découpe calib / eval de dev. Lancer : python -m pytest tests

Les cas viennent du banc d'essai (challenges/cases.csv, partition dev), jamais des questions humaines.
"""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import Catalogue, ResolveurApproche, SeuilFixe, SeuilsCalibres  # noqa: E402
import yaml  # noqa: E402

from engine.approche import (MIXTE, SEUILS, IndexApproche, charger_familles, compatible, distance,  # noqa: E402
                             signature)
from engine.calibration import (CAS_ANALYSE, CAS_CERTIF, GRILLE, balayer, borne_risque, calibrer, ecrire,  # noqa: E402
                                n_minimum, perte, risque_seuil_fixe, sans_date, sgr, sha256)
from engine.evaluation import charger_cas, evaluer, sous_partition  # noqa: E402


@pytest.fixture(scope="module")
def cat():
    return Catalogue.charger()


@pytest.fixture(scope="module")
def r(cat):
    return ResolveurApproche(cat, SeuilFixe(0.88, 0.03))


def approche(res):
    return next((t for t in res.trace if t.get("regle") == "R-RES-03"), None)


# ── politiques de seuil

def test_seuil_fixe_valide():
    assert SeuilFixe().regle("ville") == (0.88, 0.03)
    with pytest.raises(ValueError):
        SeuilFixe(1.2, 0.03)
    with pytest.raises(ValueError):
        SeuilFixe(0.88, 0.5)


def test_seuils_calibres_par_famille(cat):
    pol = SeuilsCalibres(familles={"vehicules": None, "geographie": (0.9, 0.03), MIXTE: (0.9, 0.03)})
    res = ResolveurApproche(cat, pol).resoudre("500 HYBRuD")
    assert res.statut == "unknown" and "désactivé pour la famille vehicules" in res.trace[-1]["raison"]
    assert pol.regle("famille_jamais_calibree") is None  # prudence : une famille inconnue n'est pas approchée
    assert pol.regle(MIXTE) is None                      # jamais d'approché entre familles (R-RES-10)


def test_famille_de_la_proposition(cat):
    """« Liegge » : meilleurs noms de types différents (commune, province…) mais d'une seule famille."""
    res = ResolveurApproche(cat, SeuilFixe()).resoudre("Liegge")
    et = approche(res)
    assert et["type"] == "mixte" and et["famille"] == "geographie"


def test_familles_couvrent_le_catalogue(cat, tmp_path):
    fams = charger_familles(cat)
    assert set(cat.etype.values()) <= set(fams)
    assert fams["ville"] == fams["commune"] == "geographie"
    f = tmp_path / "familles.yaml"
    f.write_text("familles:\n  a: {types: [ville]}\n  b: {types: [ville]}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="deux familles"):
        charger_familles(None, f)
    f.write_text("familles:\n  a: {types: [ville]}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sans famille"):
        charger_familles(cat, f)


def test_seuils_calibres_empreinte(cat, tmp_path):
    f = tmp_path / "seuils.yaml"
    f.write_text("empreinte_catalogue: autre\nfamilles:\n  geographie: {fuzzy: actif, seuil: 0.9, ecart: 0.03}\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="Recalibrer"):
        SeuilsCalibres.charger(cat, f)
    f.write_text(f"empreinte_catalogue: {cat.empreinte}\nfamilles:\n  geographie: {{fuzzy: peut-etre}}\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="actif ou desactive"):
        SeuilsCalibres.charger(cat, f)
    f.write_text(f"empreinte_catalogue: {cat.empreinte}\ntypes:\n  ville: {{fuzzy: desactive}}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="familles"):
        SeuilsCalibres.charger(cat, f)                   # ancien format par type : recalibrer


def test_seuils_du_depot_a_jour(cat):
    """spec/seuils_fuzzy.yaml doit correspondre au catalogue et au jeu de calibration : sinon, recalibrer."""
    pol = SeuilsCalibres.charger(cat)
    assert pol.empreinte == cat.empreinte and pol.familles
    doc = yaml.safe_load(SEUILS.read_text(encoding="utf-8"))
    assert doc["donnees"] == "challenges/calibration_certif.csv"     # θ calculé sur le jeu de certification
    assert doc["sha256_donnees"] == sha256(CAS_CERTIF), "calibration_certif.csv a changé : python -m engine.calibration"
    assert doc["cible_risque"] == 0.005 and doc["delta"] == 0.05      # décisions métier de R-RES-10
    assert set(doc["familles"]) >= set(charger_familles(cat).values())


# ── résolution approchée

def test_faute_de_frappe_resolue(r):
    res = r.resoudre("500 HYBRuD")  # ER-03049
    assert res.statut == "resolved" and res.ids == ("veh:modele:fiat-500-hybrid",)
    assert res.etape == "approche" and approche(res)["score"] >= 0.88


def test_exact_avant_approche(r):
    res = r.resoudre("Liège")
    assert res.etape == "exact" and approche(res) is None


def test_jamais_sur_un_code(r):
    for code in ("MN-AMO-70514", "MN-ANO-70513", "2710.21"):
        res = r.resoudre(code)
        assert res.statut == "unknown", code
        assert approche(res) is None, code
    assert signature("500 hybrud") == ("500",)


def test_jamais_sous_quatre_caracteres(r):
    res = r.resoudre("abc")
    assert res.statut == "unknown" and "4 caractères" in res.trace[-1]["raison"]


def test_index_negatif_avant_approche(r):
    res = r.resoudre("Aalen")  # proche de « aarlen » (JW 0,956)
    assert res.statut == "unknown" and res.etape == "index_negatif" and approche(res) is None
    simule = r.resoudre("Aalen", index_negatif=False)
    assert approche(simule) is not None  # sans l'index négatif, l'approché s'en mêlerait


def test_garde_fou_mots_courts(r):
    for terme in ("St.-Jan", "Ste-Cécile"):  # donnaient « t jan » et « steil »
        res = r.resoudre(terme)
        assert res.statut == "unknown" and "garde-fou" in res.trace[-1]["raison"], terme
    assert compatible("woluwe st lambert", "woluwe st lambert")
    assert not compatible("st jan", "t jan") and not compatible("ste cecile", "steil")


def test_ecart_rend_ambigu(cat):
    res = ResolveurApproche(cat, SeuilFixe(0.88, 0.03)).resoudre("Alije")  # ER-03117
    assert res.statut == "ambiguous" and len(approche(res)["noms"]) >= 2
    # Sans R-RES-11 : l'écart seul. (Avec R-RES-11, « alvije » reste retenu : à une faute, comme « alijen ».)
    serre = ResolveurApproche(cat, SeuilFixe(0.88, 0.0), voisinage=False).resoudre("Alije")
    assert len(approche(serre)["noms"]) < len(approche(res)["noms"])


def test_seuil_refuse(cat):
    res = ResolveurApproche(cat, SeuilFixe(0.999, 0.03)).resoudre("500 HYBRuD")
    assert res.statut == "unknown" and "sous le seuil" in res.trace[-1]["raison"]


def test_determinisme(r):
    assert r.resoudre("ARyURA SPIDER") == r.resoudre("ARyURA SPIDER")


# ── R-RES-11 (voisins en distance d'édition) et ordre des mots

def test_distance_edition():
    assert distance("fresin", "fretin") == distance("fresin", "fressin") == 1
    assert distance("abarth fiat 500", "fiat 500 abarth") == 0          # mots triés
    assert distance("fiat abarht 500", "fiat 500 abarth") == 1          # transposition : une seule faute


def test_voisinage_rend_ambigu(cat, r):
    """« Fresin » (faute pour Fretin) : Fressin a le meilleur score (0,97), Fretin est aussi à une faute."""
    res = r.resoudre("Fresin")
    et = approche(res)
    assert res.statut == "ambiguous"
    assert {"fressin", "fretin"} <= set(et["noms"])
    assert et["voisinage"]["regle"] == "R-RES-11" and et["voisinage"]["distance"] == 1
    assert "fretin" in et["voisinage"]["ajoutes"]
    sans = ResolveurApproche(cat, SeuilFixe(0.88, 0.03), index=r.index, voisinage=False).resoudre("Fresin")
    assert "fretin" not in approche(sans)["noms"]                          # sans la règle, Fretin manque


def test_voisinage_meme_type_seulement(r):
    """Les voisins ajoutés sont du type des meilleurs noms : « frein » (pièce) n'est pas ajouté par R-RES-11."""
    et = approche(r.resoudre("Fresin"))
    for n in et["voisinage"]["ajoutes"]:
        assert r.index.types_de(n) & r.index.types_de(et["meilleurs"][0]), n


def test_ordre_des_mots(cat, r):
    """Une faute sur « Fiat Abarth 500 » retrouve aussi « fiat 500 abarth », comme l'exact les réunit."""
    exact = r.resoudre("FIAT ABARTH 500")
    assert exact.etape in ("exact", "mots_tries") and exact.statut == "ambiguous"
    res = r.resoudre("FIAT ABAXRTH 500")
    assert res.statut == "ambiguous" and set(res.ids) == set(exact.ids)
    assert {"fiat abarth 500", "fiat 500 abarth"} <= set(approche(res)["noms"])
    idx = IndexApproche(cat, mots_tries=False)
    seul = ResolveurApproche(cat, SeuilFixe(0.88, 0.03), index=idx, voisinage=False).resoudre("FIAT ABAXRTH 500")
    assert seul.statut == "resolved"                                       # sans les mots triés : trop confiant


def test_diagnostic_refuse_le_jeu_de_certification():
    from engine.diagnostic_fuzzy import main as diagnostic
    with pytest.raises(SystemExit, match="calculer θ"):
        diagnostic(["--cas", str(CAS_CERTIF)])
    assert CAS_ANALYSE != CAS_CERTIF


# ── découpe calib / eval

def test_sous_partition():
    dev = charger_cas("dev")
    calib, ev = charger_cas("dev", "calib"), charger_cas("dev", "eval")
    assert len(calib) + len(ev) == len(dev)
    assert not {c["case_id"] for c in calib} & {c["case_id"] for c in ev}
    assert 0.68 < len(calib) / len(dev) < 0.72
    assert sous_partition("ER-00001") == sous_partition("ER-00001")
    with pytest.raises(ValueError):
        charger_cas("test", "calib")


# ── SGR

def test_borne_binomiale():
    assert borne_risque(0, 100, 0.05) == pytest.approx(1 - 0.05 ** (1 / 100), abs=1e-9)
    assert borne_risque(2, 100, 0.05) > borne_risque(1, 100, 0.05) > borne_risque(0, 100, 0.05)
    assert borne_risque(5, 5, 0.05) == 1.0


def test_borne_k0_connue():
    """k = 0 : B* = 1 − δ^(1/n) ≈ ln(1/δ)/n (lemme 3.1)."""
    for n, d in ((1300, 0.05 / 20), (5000, 0.05), (200, 0.01)):
        assert borne_risque(0, n, d) == pytest.approx(1 - d ** (1 / n), abs=1e-9)
        if n >= 1000:                                          # l'approximation n'est bonne que pour n grand
            assert borne_risque(0, n, d) == pytest.approx(math.log(1 / d) / n, rel=0.01)


def test_n_minimum():
    n = n_minimum(0.005, 0.05)
    d = 0.05 / len(GRILLE)                                    # Bonferroni sur la grille, plus ⌈log2 n⌉
    assert borne_risque(0, n, d) <= 0.005 < borne_risque(0, n - 1, d)
    assert 1150 < n < 1250                                     # ≈ ln(400) / 0,005
    assert n_minimum(0.05, 0.05, n_seuils=1) == 59             # 1 − 0,05^(1/59) ≤ 0,05


def test_grille():
    assert len(GRILLE) == 20 and GRILLE[0] == 0.80 and GRILLE[-1] == 0.99


def test_sgr_plus_bas_seuil_admissible():
    # 3000 cas sains à partir de 0,86, 120 pertes entre 0,80 et 0,859 : le premier θ admissible est 0,86.
    pts = [(0.86 + (i % 140) / 1000, 0) for i in range(3000)] + [(0.80 + (i % 60) / 1000, 1) for i in range(120)]
    ch = sgr(pts, 0.005, 0.05)
    assert ch is not None and ch.seuil == 0.86 and ch.erreurs == 0 and ch.retenus == 3000
    bal = balayer(pts, 0.05)
    assert all(b["borne"] > 0.005 for b in bal if b["seuil"] < 0.86)  # aucun plus bas ne passe
    assert ch.borne == pytest.approx(math.log(20 / 0.05) / 3000, rel=0.01)


def test_sgr_aucun_seuil():
    sains = [(0.80 + i / 10000, 0) for i in range(500)]       # trop peu de cas pour r* = 0,5 %
    assert sgr(sains, 0.005, 0.05) is None
    assert sgr(sains, 0.05, 0.05) is not None                  # suffit pour une cible plus large


def test_calibrer_desactive_petite_famille():
    pts = [{"famille": "marques", "kappa": 0.95, "perte": 0, "retenu": True}] * 10
    pts += [{"famille": "geographie", "kappa": 0.80 + i / 20000, "perte": 0, "retenu": True} for i in range(3000)]
    pts += [{"famille": MIXTE, "kappa": 0.80 + i / 20000, "perte": 0, "retenu": True} for i in range(3000)]
    fams, courbes = calibrer(pts, 0.005, 0.05, 0.03, ["geographie", "marques", "clients"])
    assert fams["marques"]["fuzzy"] == "desactive" and "au moins" in fams["marques"]["raison"]
    assert fams["clients"]["fuzzy"] == "desactive" and fams["clients"]["n_cas"] == 0   # famille sans aucun cas
    assert fams[MIXTE]["fuzzy"] == "desactive"                                         # même avec assez de cas
    g = fams["geographie"]
    assert g["fuzzy"] == "actif" and g["seuil"] == 0.80 and g["k"] == 0 and g["couverture"] == 1.0
    assert len(courbes["geographie"]) == len(GRILLE)


def test_calibration_deterministe(tmp_path):
    """Même données → même fichier de seuils, la date mise à part : elle n'entre pas dans la comparaison."""
    pts = [{"famille": "geographie", "kappa": 0.80 + (i * 7 % 200) / 1000, "perte": int(i % 997 == 0),
            "retenu": True} for i in range(3000)]
    docs = []
    for i, jour in enumerate(("2026-11-13", "2027-01-02")):
        f = tmp_path / f"s{i}.yaml"
        fams, _ = calibrer(list(pts), 0.005, 0.05, 0.03, ["geographie"])
        ecrire(fams, 0.005, 0.05, 0.03, False, "x", "cas.csv", "sha", 3000, date=jour, chemin=f)
        docs.append(yaml.safe_load(f.read_text(encoding="utf-8")))
    assert docs[0]["date"] != docs[1]["date"] and sans_date(docs[0]) == sans_date(docs[1])
    # Relancer sans date sur un fichier au contenu identique garde sa date : le fichier ne change pas.
    f = tmp_path / "s0.yaml"
    avant = f.read_bytes()
    fams, _ = calibrer(list(pts), 0.005, 0.05, 0.03, ["geographie"])
    ecrire(fams, 0.005, 0.05, 0.03, False, "x", "cas.csv", "sha", 3000, chemin=f)
    assert f.read_bytes() == avant


def test_risque_seuil_fixe():
    pts = [{"famille": "geographie", "kappa": 0.90, "perte": 1, "retenu": True},
           {"famille": "geographie", "kappa": 0.95, "perte": 0, "retenu": True},
           {"famille": "pieces", "kappa": 0.87, "perte": 1, "retenu": True},      # sous 0,88 : non accepté
           {"famille": "pieces", "kappa": 0.99, "perte": 1, "retenu": False}]     # garde-fou : non accepté
    r = risque_seuil_fixe(pts, 0.88, 0.05)
    assert r["geographie"]["n"] == 2 and r["geographie"]["k"] == 1 and r["geographie"]["risque"] == 0.5
    assert "pieces" not in r and r["TOTAL"]["n"] == 2
    assert r["geographie"]["borne"] == pytest.approx(borne_risque(1, 2, 0.05), abs=1e-6)  # pas de Bonferroni


def test_perte():
    cas = {"expected_ids": "a", "accepted": "unknown", "expected_status": "resolved"}
    assert perte(cas, "resolved", ("b",)) == 1                       # erreur silencieuse
    assert perte(cas, "ambiguous", ("a", "b")) == 0                  # demande, avec la bonne entité
    assert perte(cas, "ambiguous", ("a", "b"), "non_sure") == 1      # non accepté par le banc
    assert perte(cas, "ambiguous", ("b", "c")) == 1


# ── banc d'essai : SeuilFixe(0.88, 0.03) sur tout dev

def test_banc_dev_seuil_fixe(r):
    res = evaluer(r, charger_cas("dev"))
    total = res["comptes"]["TOTAL"]
    assert total.get("erreur_silencieuse", 0) == 0, [e for e in res["echecs"] if e["note"] == "erreur_silencieuse"][:5]
    assert total["correct"] / sum(total.values()) > 0.85
