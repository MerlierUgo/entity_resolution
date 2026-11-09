"""Outils partagés : normalisation (spec R-RES-02), écriture CSV déterministe, chemins."""
from __future__ import annotations

import csv
import os
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CAT = ROOT / "catalog"
CHAL = ROOT / "challenges"
REP = ROOT / "reports"
SPEC = ROOT / "spec"


def console_utf8() -> None:
    """Sortie console en UTF-8. Sous Windows, une sortie redirigée est en cp1252 et refuse « ← » ou « ── »."""
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="replace")


def env_utf8() -> dict:
    """Environnement des sous-processus Python : mode UTF-8 (fichiers et console), quelle que soit la plateforme."""
    return {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def load_yaml(path: Path):
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_mesures() -> list[dict]:
    """Mesures : source unique spec/mesures.yaml."""
    return load_yaml(SPEC / "mesures.yaml")["mesures"]
SEED = 20261102

STOP = {"de", "d", "du", "des", "la", "le", "les", "l", "a", "au", "aux", "en", "et"}
LATIN = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿĀ-žƀ-ɏ'’ .\-()&/]+$")


def normalize(s: str) -> str:
    """Normalisation de la spec (R-RES-02), identique pour le catalogue et pour les requêtes."""
    s = str(s).replace("%", " pourcent ").replace("€", " euros ").replace("’", "'")
    s = "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    toks = [t for t in s.split() if t not in STOP]
    toks = [t[:-1] if len(t) > 3 and t[-1] in "sx" and not t.endswith("ss") else t for t in toks]
    return " ".join(toks)


def code_key(s: str) -> str:
    return re.sub(r"[\s\-_./]", "", str(s)).upper()


def slug(s: str) -> str:
    return normalize(s).replace(" ", "-") or "x"


def write_csv(path: Path, rows: list[dict], fields: list[str], sort_keys: list[str] | None = None) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if sort_keys:
        rows = sorted(rows, key=lambda r: tuple(str(r.get(k, "")) for k in sort_keys))
    with path.open("w", newline="", encoding="utf-8-sig") as f:  # BOM : Excel détecte l UTF-8
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as f:  # lit avec ou sans BOM
        return list(csv.DictReader(f))
