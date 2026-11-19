"""
Section 8 du rapport HTML (reports/modele_saisie.html) : « Pourquoi certaines familles ne passent pas ».

Lit reports/analyse_familles.json (python -m engine.analyse_familles : jeu d'analyse et catalogue seulement) et,
pour la conclusion, les comptes agrégés déjà publiés en section 7 (reports/calibration.json). Graphiques SVG faits
main, sans bibliothèque ; chaque graphique a son tableau.
"""
from __future__ import annotations

import html
import math

e = html.escape

ORDRE = ("clients", "douane", "pieces", "vehicules", "geographie", "marques", "vocabulaire_metier")
COUL_STATUT = {True: "var(--s1)", False: "var(--s2)"}          # famille calibrée / désactivée
ISSUES = (("resolved", "resolved", "var(--s1)", ""),
          ("ambiguous_voisins", "ambiguous : noms voisins", "var(--s2)", ""),
          ("ambiguous_homonymes", "ambiguous : homonymes d'un nom", "var(--s2)", "url(#hachure)"),
          ("unknown_garde_fou", "unknown : garde-fou ou règles", "var(--s3)", ""),
          ("unknown_sous_seuil", "unknown : sous le seuil", "var(--s0)", ""))


def pct(x, d=1):
    return "·" if x is None else f"{100 * x:.{d}f} %".replace(".", ",")


def num(x, d=3):
    return "·" if x is None else f"{x:.{d}f}".replace(".", ",")


def nb(x):
    return "·" if x is None else f"{x:,}".replace(",", " ")


def table(entetes, lignes) -> str:
    th = "".join(f"<th>{e(h)}</th>" for h in entetes)
    corps = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in l) + "</tr>" for l in lignes)
    return f'<div class="tw"><table class="petit"><thead><tr>{th}</tr></thead><tbody>{corps}</tbody></table></div>'


def familles_presentes(af: dict) -> list[str]:
    fs = set(af["longueurs"]["par_famille"]) | set(af["scores"])
    return [f for f in ORDRE if f in fs] + sorted(fs - set(ORDRE) - {"mixte"})


# ── graphiques ───────────────────────────────────────────────────────────────────────────────────

def boites(titre: str, lignes: list[tuple[str, dict, str]], x, ticks, refs, fmt, aria: str,
           moyenne: bool = False) -> str:
    """Boîtes à moustaches horizontales : moustaches p05–p95, boîte q1–q3, trait médian (et point moyen).
    lignes : (libellé, résumé, couleur) ; x : fonction valeur → abscisse ; refs : [(valeur, libellé)]."""
    G, D, Hh, pas = 132, 14, 10, 30
    W = 640
    H = Hh + pas * len(lignes) + 30
    el = []
    for v, lib in refs:
        el.append(f'<line x1="{x(v):.1f}" y1="{Hh - 4}" x2="{x(v):.1f}" y2="{H - 26}" class="ref"/>'
                  f'<text x="{x(v) + 3:.1f}" y="{Hh + 2}" class="t">{e(lib)}</text>')
    for v in ticks:
        el.append(f'<text x="{x(v):.1f}" y="{H - 12}" text-anchor="middle" class="t">{e(fmt(v))}</text>')
    el.append(f'<line x1="{G}" y1="{H - 26}" x2="{W - D}" y2="{H - 26}" class="axe"/>')
    for i, (lib, r, col) in enumerate(lignes):
        cy = Hh + pas * i + pas / 2 + 4
        el.append(f'<text x="{G - 8}" y="{cy + 4:.1f}" text-anchor="end" class="l">{e(lib)}</text>')
        if not r.get("n"):
            el.append(f'<text x="{G + 4}" y="{cy + 4:.1f}" class="t">aucune donnée</text>')
            continue
        x5, x1, xm, x3, x95 = (x(r[k]) for k in ("p05", "q1", "mediane", "q3", "p95"))
        info = (f"{lib} : n {nb(r['n'])}, p05 {fmt(r['p05'])}, q1 {fmt(r['q1'])}, médiane {fmt(r['mediane'])}, "
                f"q3 {fmt(r['q3'])}, p95 {fmt(r['p95'])}, moyenne {fmt(r['moyenne'])}")
        el.append(f'<g><title>{e(info)}</title>'
                  f'<line x1="{x5:.1f}" y1="{cy:.1f}" x2="{x95:.1f}" y2="{cy:.1f}" stroke="{col}" stroke-width="2"/>'
                  f'<line x1="{x5:.1f}" y1="{cy - 5:.1f}" x2="{x5:.1f}" y2="{cy + 5:.1f}" stroke="{col}" stroke-width="2"/>'
                  f'<line x1="{x95:.1f}" y1="{cy - 5:.1f}" x2="{x95:.1f}" y2="{cy + 5:.1f}" stroke="{col}" stroke-width="2"/>'
                  f'<rect x="{x1:.1f}" y="{cy - 9:.1f}" width="{max(x3 - x1, 2):.1f}" height="18" rx="4" fill="{col}" '
                  f'stroke="var(--bg)" stroke-width="2"/>'
                  f'<line x1="{xm:.1f}" y1="{cy - 9:.1f}" x2="{xm:.1f}" y2="{cy + 9:.1f}" stroke="var(--bg)" stroke-width="3"/>')
        if moyenne:
            el.append(f'<circle cx="{x(r["moyenne"]):.1f}" cy="{cy:.1f}" r="4" fill="var(--fg)" stroke="var(--bg)" stroke-width="2"/>')
        el.append("</g>")
    return (f'<figure class="graphe"><figcaption>{e(titre)}</figcaption><svg viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="{e(aria)}">{"".join(el)}</svg></figure>')


def empile(titre: str, lignes: list[tuple[str, str, dict]], aria: str) -> str:
    """Barres empilées à 100 % : une ligne par (famille, θ)."""
    G, D, Hh, pas, W = 170, 60, 6, 24, 640
    H = Hh + pas * len(lignes) + 8
    L = W - G - D
    el = ['<defs><pattern id="hachure" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
          '<rect width="6" height="6" fill="var(--s2)"/><line x1="0" y1="0" x2="0" y2="6" stroke="var(--bg)" '
          'stroke-width="2.5"/></pattern></defs>']
    for i, (lib, sous, c) in enumerate(lignes):
        y = Hh + pas * i
        tot = sum(c.get(k, 0) for k, *_ in ISSUES)
        el.append(f'<text x="{G - 8}" y="{y + 14}" text-anchor="end" class="l">{e(lib)}'
                  f'<tspan class="t" dx="6">{e(sous)}</tspan></text>')
        xx = G
        for k, nom, col, motif in ISSUES:
            v = c.get(k, 0)
            if not v or not tot:
                continue
            w = L * v / tot
            el.append(f'<rect x="{xx:.1f}" y="{y + 2}" width="{max(w - 2, 0.5):.1f}" height="16" '
                      f'fill="{motif or col}"><title>{e(lib)} ({e(sous)}) · {e(nom)} : {nb(v)} / {nb(tot)} '
                      f'({pct(v / tot)})</title></rect>')
            xx += w
        res = c.get("resolved", 0)
        el.append(f'<text x="{W - D + 6}" y="{y + 14}" class="t">{pct(res / tot if tot else None, 0)} res.</text>')
    leg = "".join(f'<span><i style="background:{col}{";background-image:repeating-linear-gradient(45deg,var(--bg) 0 2px,transparent 2px 5px)" if motif else ""}"></i>{e(nom)}</span>'
                  for _, nom, col, motif in ISSUES)
    return (f'<figure class="graphe"><figcaption>{e(titre)}</figcaption><div class="leg">{leg}</div>'
            f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{e(aria)}">{"".join(el)}</svg></figure>')


# ── section ──────────────────────────────────────────────────────────────────────────────────────

def bornes_097(cal: dict, borne) -> dict:
    """Comptes agrégés de la section 7 au palier 0,97 (pour la conclusion) : famille → (n, k, borne) par scénario."""
    out = {}
    for sc, d in cal["scenarios"].items():
        for f, fd in d["familles"].items():
            p = next((p for p in fd["courbe"] if abs(p["theta"] - 0.97) < 1e-9), None)
            if p:
                out.setdefault(f, {})[sc] = (p["n"], p["k"], borne(p["k"], p["n"], cal["parametres"]["delta"]))
    return out


def section_pourquoi(af: dict, cal: dict, borne) -> str:
    fams = familles_presentes(af)
    calibree = {f: cal["familles"].get(f) is not None for f in fams}
    nom = lambda f: f + ("" if calibree[f] else " ✕")
    lo, sc, uf = af["longueurs"]["par_famille"], af["scores"], af["une_faute"]["par_tranche"]
    r_etoile = cal["parametres"]["r_etoile"]

    # 1. longueurs (échelle log 2)
    xl = lambda v: 132 + (640 - 132 - 14) * (math.log2(max(min(v, 256), 2)) - 1) / 7
    g1 = boites("Longueur des noms comparables du catalogue (caractères, forme normalisée, échelle logarithmique)",
                [(nom(f), lo.get(f, {}), COUL_STATUT[calibree[f]]) for f in fams], xl, (2, 4, 8, 16, 32, 64, 128, 256),
                [(8, "8"), (20, "20")], lambda v: f"{v:g}",
                "Longueur des noms par famille : géographie, marques et vocabulaire métier ont les noms les plus courts")
    t1 = table(["Famille", "Noms", "q1", "Médiane", "q3", "≤ 8 car.", "≥ 20 car."],
               [[e(nom(f)), nb(lo[f]["n"]), num(lo[f]["q1"], 0), f"<b>{num(lo[f]['mediane'], 0)}</b>", num(lo[f]["q3"], 0),
                 pct(lo[f]["part_le_8"]), pct(lo[f]["part_ge_20"])] for f in fams if f in lo])

    # 2. κ des saisies fautives
    xs = lambda v: 132 + (640 - 132 - 14) * (max(min(v, 1.0), 0.80) - 0.80) / 0.20
    g2 = boites("Meilleur score Jaro-Winkler κ des saisies fautives présentes qui atteignent l'approché (axe coupé à 0,80)",
                [(nom(f), sc[f]["score"], COUL_STATUT[calibree[f]]) for f in fams if f in sc], xs,
                (0.80, 0.85, 0.90, 0.95, 1.00), [(0.90, "0,90"), (0.95, "0,95"), (0.99, "0,99")], lambda v: num(v, 2),
                "Score κ par famille : les médianes sont proches, seule la queue au-dessus de 0,99 diffère")
    paliers = [f"{p:.2f}" for p in af["paliers"]]
    t2 = table(["Famille", "Fautives", "Avec score", "Médiane κ"] + [f"≥ {p.replace('.', ',')}" for p in paliers],
               [[e(nom(f)), nb(sc[f]["fautives"]), nb(sc[f]["avec_score"]), num(sc[f]["score"].get("mediane"))]
                + [(f"<b>{pct(sc[f]['part_ge'][p])}</b>" if p == "0.99" else pct(sc[f]["part_ge"][p])) for p in paliers]
                for f in fams if f in sc])

    # 3. issues
    def regroupe(c):
        c = dict(c)
        c["unknown_garde_fou"] = c.get("unknown_garde_fou", 0) + c.pop("unknown_regles", 0)
        return c
    lignes3 = []
    for f in fams:
        if f in sc:
            for th in ("0.80", "0.99"):
                lignes3.append((nom(f) if th == "0.80" else "", f"θ {th.replace('.', ',')}", regroupe(sc[f]["issues"][th])))
    g3 = empile("Issue des saisies fautives passées par le fuzzy, à θ 0,80 et à θ 0,99", lignes3,
                "Issue par famille : à 0,99 presque tout tombe sous le seuil en géographie, marques et vocabulaire")
    ent3 = ["Famille", "θ", "resolved", "ambiguous voisins", "ambiguous homonymes", "unknown règles",
            "unknown garde-fou", "unknown sous seuil"]
    l3 = []
    for f in fams:
        if f not in sc:
            continue
        for th in ("0.80", "0.95", "0.99"):
            c = sc[f]["issues"][th]
            tot = sum(c.values()) or 1
            l3.append([e(nom(f)) if th == "0.80" else "", th.replace(".", ",")]
                      + [f"{nb(c.get(k, 0))} ({pct(c.get(k, 0) / tot, 0)})" for k in
                         ("resolved", "ambiguous_voisins", "ambiguous_homonymes", "unknown_regles", "unknown_garde_fou",
                          "unknown_sous_seuil")])
    t3 = table(ent3, l3)

    # 4. une faute par longueur
    g4 = boites("κ d'une saisie à exactement une faute, par longueur du nom source (toutes familles ; point : moyenne)",
                [(t, v, "var(--s1)") for t, v in uf.items()], xs, (0.80, 0.85, 0.90, 0.95, 1.00),
                [(0.95, "0,95"), (0.99, "0,99")], lambda v: num(v, 2),
                "Score d'une saisie à une faute selon la longueur : 0,99 n'est atteint qu'au-delà de 15 caractères",
                moyenne=True)
    t4 = table(["Longueur du nom source", "Saisies", "κ moyen", "κ médian", "≥ 0,95", "≥ 0,99"],
               [[e(t), nb(v.get("n")), f"<b>{num(v.get('moyenne'))}</b>", num(v.get("mediane")), pct(v.get("part_ge_095")),
                 f"<b>{pct(v.get('part_ge_099'))}</b>"] for t, v in uf.items()])

    # conclusion (chiffres tirés des données)
    des = [f for f in fams if not calibree[f]]
    cal_ok = [f for f in fams if calibree[f] and f in sc]
    p99 = lambda f: sc[f]["part_ge"]["0.99"]
    court = [t for t, v in uf.items() if v.get("n") and not v.get("part_ge_099")]
    b97 = bornes_097(cal, borne)
    passeraient = [f for f in des if f in b97 and all(b <= r_etoile for _, _, b in b97[f].values())]
    def part80(f, *cles):
        """Part des saisies passées par le fuzzy à θ 0,80 dont l'issue est l'une des clés (None si famille absente)."""
        if f not in sc:
            return None
        c = sc[f]["issues"]["0.80"]
        return sum(c.get(k, 0) for k in cles) / max(1, sum(c.values()))
    vois = lambda f: part80(f, "ambiguous_voisins")
    autres_vois = max((vois(f) for f in fams if f in sc and f != "geographie"), default=None)
    gf = lambda f: part80(f, "unknown_garde_fou", "unknown_regles")
    p99_cal = [p99(f) for f in cal_ok] or [None]
    pieces97 = b97.get("pieces", {}).get("central")
    medianes_des = ", ".join(f"{f} {num(lo[f]['mediane'], 0)} car." for f in des if f in lo)
    lignes = [
        f"<b>Hypothèse confirmée pour le premier palier.</b> Une seule faute ne laisse un nom à 0,99 que s'il fait au moins "
        f"20 caractères (40 pour une substitution) : aucune des saisies à une faute sur un nom de {', '.join(court)} "
        f"caractères n'atteint 0,99.",
        f"Les familles désactivées ont les noms les plus courts (médianes {medianes_des}) et "
        f"{', '.join(pct(p99(f)) for f in des)} de saisies fautives à κ ≥ 0,99, contre {pct(min(p99_cal, key=lambda x: x or 0))} à "
        f"{pct(max(p99_cal, key=lambda x: x or 0))} pour les familles calibrées : trop peu de noms résolus pour passer le premier palier.",
        f"<b>Le risque n'est pas en cause.</b> Dans les comptes agrégés de la section 7, "
        + (f"{', '.join(passeraient)} ont, à 0,97, une borne sous r* dans les deux scénarios (central : "
           + " ; ".join(f"{f} : n {nb(b97[f]['central'][0])}, k {nb(b97[f]['central'][1])}, borne {pct(b97[f]['central'][2], 2)}"
                        for f in passeraient) + ") : c'est le premier palier de la séquence fixe (0,99), faute de volume, qui les "
           "bloque, pas leur risque aux paliers suivants."
           if passeraient else "aucune famille désactivée ne passerait 0,97 : le risque compte aussi."),
        f"<b>Ce qu'elle n'explique pas : les noms voisins.</b> En géographie, {pct(vois('geographie'))} des saisies passées par "
        f"le fuzzy finissent ambiguous par noms voisins à θ 0,80 (au plus {pct(autres_vois)} ailleurs) ; l'effet est réel aux "
        f"paliers bas, nul à 0,99.",
        f"<b>Ni les pièces ni les garde-fous.</b> Les pièces ont des noms longs mais leur risque explose sous 0,98"
        + (f" (0,97 : n {nb(pieces97[0])}, k {nb(pieces97[1])})" if pieces97 else "")
        + f" ; et les garde-fous (mots courts, nombre de mots) écartent avant tout seuil {pct(gf('clients'), 0)} des saisies "
        f"clients et {pct(gf('vehicules'), 0)} des véhicules passées par le fuzzy ; la longueur ne dit rien de cet effet.",
    ]
    concl = "<ol class='concl'>" + "".join(f"<li>{l}</li>" for l in lignes) + "</ol>"
    leg = (f'<div class="leg"><span><i style="background:{COUL_STATUT[True]}"></i>famille calibrée</span>'
           f'<span><i style="background:{COUL_STATUT[False]}"></i>famille désactivée (✕)</span>'
           '<span>boîte : q1–q3, trait : médiane ; moustaches : centiles 5 et 95</span></div>')
    return f"""
<section id="pourquoi"><h2>8. Pourquoi certaines familles ne passent pas</h2>
<p>Hypothèse : les noms courts perdent plus de score Jaro-Winkler par faute ; ils tombent sous les paliers stricts
(0,99…) que la séquence fixe teste en premier, d'où trop peu de noms résolus. Analyse descriptive sur le
<b>jeu d'analyse</b> ({nb(af["saisies_analyse"])} saisies, dont {nb(af["fautives_presentes"])} fautives présentes) et le
catalogue ; les jeux de certification ne sont pas lus. Rien n'est modifié (moteur, seuils). Famille d'une saisie : celle
du nom source. Le moteur tourne une fois à θ {num(af["theta_moteur"], 2)} ; l'issue à un θ plus strict s'en déduit.</p>
<h3>Conclusion</h3>
{concl}
<p class="note">Calcul : Jaro-Winkler = J + 4 × 0,1 × (1 − J) quand les 4 premiers caractères sont intacts, soit
1 − JW = 0,6 (1 − J). Une omission, une insertion ou une inversion sur un nom de L caractères donne 1 − J ≈ 1 / (3L), une
substitution 2 / (3L) : JW ≥ 0,99 exige L ≥ 20 dans le premier cas, L ≥ 40 dans le second. Une faute dans les
4 premiers caractères fait perdre le bonus de préfixe et baisse encore le score.</p>
{leg}
<h3>1. Longueur des noms</h3>
{g1}{t1}
<h3>2. Score des saisies fautives</h3>
{g2}{t2}
<h3>3. Issue des saisies passées par le fuzzy</h3>
<p class="note">resolved : un seul candidat après les règles ; ambiguous par noms voisins : plusieurs noms à moins de
l'écart (0,03) du meilleur ; ambiguous par homonymes : un seul nom, plusieurs entités ; unknown par garde-fou : score
suffisant mais noms refusés (mots courts, nombre de mots) ; unknown par règles : plus aucun candidat après les règles
de contexte ou l'indice ; unknown sous le seuil : κ &lt; θ.</p>
{g3}{t3}
<h3>4. Une faute, selon la longueur du nom</h3>
<p class="note">Saisies présentes à exactement une faute, sans mot oublié ni forme courte, toutes familles ;
{nb(af["une_faute"]["sans_score"])} autres n'atteignent pas l'approché (la faute tombe sur un autre alias exact, ou
aucun nom comparable).</p>
{g4}{t4}
</section>"""


CSS = """
.graphe{margin:.8em 0;max-width:720px}.graphe figcaption{color:var(--fg2);font-size:.88rem;margin-bottom:.3em}
.graphe svg{width:100%;height:auto}.graphe .t{font-size:10px;fill:var(--fg2)}.graphe .l{font-size:11px;fill:var(--fg)}
.graphe .axe{stroke:var(--ligne);stroke-width:1}.graphe .ref{stroke:var(--fg2);stroke-width:1;stroke-dasharray:3 3;opacity:.6}
.concl li{margin:.3em 0}
"""
