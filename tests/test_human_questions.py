"""Tests du fichier unique de questions humaines (build/human_questions.py). Lancer : python -m pytest tests"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "build"))
import human_questions as hq  # noqa: E402

REFS = hq.Refs(entities={"geo:pays:BE", "geo:pays:FR"}, mesures={"M05", "M24"}, axes={"pays", "mois"},
               lacunes={"G01"})
Q = "combien de ca en belgique ?"


def make(tmp_path, rows, lock=True):
    full = []
    for r in rows:
        base = {c: "" for c in hq.COLUMNS}
        base.update(etat="active", split="test", auteur="A", date_ajout="2026-11-04")
        base.update(r)
        full.append(base)
    f, lk = tmp_path / "q.csv", tmp_path / "q.lock"
    hq.write_questions(full, f)
    hq.write_lock({r["id"]: hq.sha(r["question"]) for r in full} if lock else {}, lk)
    return f, lk


def run(f, lk):
    return hq.check(hq.read_questions(f), hq.read_lock(lk), REFS)


def test_fichier_valide(tmp_path):
    f, lk = make(tmp_path, [dict(id="H-001", question=Q, statut_attendu="resolved", entites_attendues="geo:pays:BE",
                                 mesure="M05", periode="2026-01-01..2026-09-30", validation="ok")])
    assert run(f, lk) == ([], [])


def test_texte_modifie_detecte(tmp_path):
    f, lk = make(tmp_path, [dict(id="H-001", question=Q)])
    f.write_text(f.read_text(encoding="utf-8-sig").replace("belgique", "Belgique"), encoding="utf-8-sig")
    errors, _ = run(f, lk)
    assert any("texte modifié" in e for e in errors)


def test_espaces_ajoutes_diagnostiques(tmp_path):
    f, lk = make(tmp_path, [dict(id="H-001", question=Q)])
    f.write_text(f.read_text(encoding="utf-8-sig").replace(Q, Q + " "), encoding="utf-8-sig")
    errors, _ = run(f, lk)
    assert any("espaces ajoutés" in e for e in errors)


def test_fautes_conservees_au_caractere_pres(tmp_path):
    q = "quelle ville à le plus grand ca ; et  pourquoi ?"   # point-virgule et double espace dans le texte
    f, lk = make(tmp_path, [dict(id="H-001", question=q)])
    assert hq.read_questions(f)[0]["question"] == q
    assert run(f, lk)[0] == []


def test_question_supprimee_interdite(tmp_path):
    f, lk = make(tmp_path, [dict(id="H-001", question=Q), dict(id="H-002", question="autre ?")])
    hq.write_questions([r for r in hq.read_questions(f) if r["id"] == "H-001"], f)
    errors, _ = run(f, lk)
    assert any("H-002" in e and "absente" in e for e in errors)


def test_question_non_enregistree(tmp_path):
    f, lk = make(tmp_path, [dict(id="H-001", question=Q)], lock=False)
    errors, _ = run(f, lk)
    assert any("non enregistrée" in e for e in errors)


@pytest.mark.parametrize("champ,valeur,attendu", [
    ("entites_attendues", "geo:pays:XX", "absente du catalogue"),
    ("mesure", "M99", "absente du glossaire"),
    ("axes", "planete", "absent du glossaire"),
    ("lacunes_spec", "G99", "lacunes.yaml"),
    ("statut_attendu", "peut-etre", "statut_attendu"),
    ("persona", "P9", "persona"),
    ("split", "train", "split"),
    ("validation", "oui", "validation"),
    ("periode", "2026-09-30..2026-01-01", "periode"),
    ("periode", "2026-02-30..2026-03-31", "periode"),
    ("periode", "le mois dernier", "periode"),
    ("date_ajout", "04/11/2026", "date_ajout"),
])
def test_valeurs_controlees(tmp_path, champ, valeur, attendu):
    f, lk = make(tmp_path, [dict(id="H-001", question=Q, **{champ: valeur})])
    errors, _ = run(f, lk)
    assert any(attendu in e for e in errors), errors


@pytest.mark.parametrize("periode", ["2026-01-01..2026-09-30", "photo 2026-09-30", "2024 vs 2025",
                                     "2026-01-01..2026-09-30 vs 2025-01-01..2025-09-30"])
def test_periodes_valides(tmp_path, periode):
    f, lk = make(tmp_path, [dict(id="H-001", question=Q, periode=periode)])
    assert run(f, lk)[0] == []


def test_identifiant_double_et_format(tmp_path):
    f, lk = make(tmp_path, [dict(id="H-001", question=Q), dict(id="H-001", question="b ?"), dict(id="Q1", question="c ?")])
    errors, _ = run(f, lk)
    assert any("double" in e for e in errors) and any("invalide" in e for e in errors)


def test_hors_perimetre_sans_mesure(tmp_path):
    f, lk = make(tmp_path, [dict(id="H-001", question=Q, statut_attendu="out_of_scope", mesure="M05")])
    assert any("hors périmètre" in e for e in run(f, lk)[0])


def test_excel_virgule_crlf_et_lignes_vides(tmp_path):
    f, lk = make(tmp_path, [dict(id="H-001", question=Q)])
    text = f.read_text(encoding="utf-8-sig").replace(";", ",") + ",,,,,,,,,,,,,,,,\r\n"
    f.write_text(text, encoding="utf-8-sig")
    rows = hq.read_questions(f)
    assert len(rows) == 1 and rows[0]["question"] == Q


def test_encodage_windows_refuse(tmp_path):
    f = tmp_path / "q.csv"
    f.write_bytes(";".join(hq.COLUMNS).encode() + "\nH-001;é\n".encode("cp1252"))
    with pytest.raises(hq.FormatError, match="UTF-8"):
        hq.read_questions(f)


def test_colonne_inconnue_refusee(tmp_path):
    f = tmp_path / "q.csv"
    f.write_text(";".join(hq.COLUMNS + ["note"]) + "\n", encoding="utf-8")
    with pytest.raises(hq.FormatError, match="inconnues"):
        hq.read_questions(f)


def test_add_attribue_le_suivant_sans_toucher_aux_autres(tmp_path):
    f, lk = make(tmp_path, [dict(id="H-001", question=Q), dict(id="H-007", question="b ?", etat="retiree")])
    before = hq.read_lock(lk)
    assert hq.cmd_add("nouvelle  question", "dev", "B", f, lk) == 0
    rows = {r["id"]: r for r in hq.read_questions(f)}
    assert rows["H-008"]["question"] == "nouvelle  question" and rows["H-008"]["split"] == "dev"
    lock = hq.read_lock(lk)
    assert {k: lock[k] for k in before} == before and run(f, lk)[0] == []


def test_id_retire_jamais_reutilise(tmp_path):
    f, lk = make(tmp_path, [dict(id="H-001", question=Q)])
    lock = hq.read_lock(lk) | {"H-005": "x"}
    assert hq.next_id(hq.read_questions(f), lock) == "H-006"


def test_fichier_reel_du_projet():
    """Le fichier livré passe le contrôle complet contre le vrai catalogue."""
    assert hq.cmd_check() == 0
