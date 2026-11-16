"""
Sections « Diagnostic », « Calibration », « Risque de B », « Comparaison A/B/C » et « Exemples » du
rapport reports/etat_moteur_2.html.

    python -m engine.diagnostic_fuzzy [--variante avant|mots_tries|voisinage]
                                        → reports/diagnostic_fuzzy*.json (jeu d'analyse)
    python -m engine.calibration        → reports/calibration.json (jeu de certification)
    python -m engine.comparaison        → reports/fuzzy_dev.json (part eval de dev)
    python -m engine.rapport_calibration

reports/corrections_dev.json (effet des deux corrections de structure sur dev, configuration B) est lu
s'il existe.

Les sections sont générées depuis ces deux JSON et insérées entre deux marqueurs, juste après la
section « Étape 2 » : les sections existantes du rapport ne sont pas touchées, et relancer la commande
remplace seulement le bloc généré. Page autonome : SVG en ligne, aucune ressource externe.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from html import escape

from engine.approche import charger_familles
from engine.catalogue import Catalogue, console_utf8
from engine.evaluation import REP

RAPPORT = REP / "etat_moteur_2.html"
DEBUT, FIN = "<!-- calibration-familles:debut -->", "<!-- calibration-familles:fin -->"
NOTE_DEBUT, NOTE_FIN = "<!-- calibration-familles:note:debut -->", "<!-- calibration-familles:note:fin -->"
YMAX = 0.05                      # axe des risques : 0 à 5 % (au-delà, le point est posé sur le bord)
ORDRE = ["geographie", "pieces", "vehicules", "clients", "marques", "douane", "vocabulaire_metier", "mixte"]
NOMS = {"geographie": "Géographie", "pieces": "Pièces", "vehicules": "Véhicules", "clients": "Clients",
        "marques": "Marques", "douane": "Douane", "vocabulaire_metier": "Vocabulaire métier",
        "mixte": "Mixte (plusieurs familles)", "sans_entite": "Sans entité (attendu inconnu)", "TOTAL": "Total"}


def pct(x: float, d: int = 1) -> str:
    return f"{100 * x:.{d}f}".replace(".", ",") + " %"


def num(x) -> str:
    return f"{x:,}".replace(",", " ") if isinstance(x, int) else str(x).replace(".", ",")


def fr(x: float, d: int = 1) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def e(s) -> str:
    return escape(str(s), quote=True)


def ordre(cles) -> list[str]:
    return sorted(cles, key=lambda k: (ORDRE.index(k) if k in ORDRE else len(ORDRE), k))


# ── courbe risque-couverture d'une famille ───────────────────────────────────────────────────────

def courbe_svg(courbe: list[dict], cible: float, theta: float | None, nom: str) -> str:
    W, H, L, R, T, B = 340, 210, 44, 12, 12, 34
    x0, x1 = 0.80, 0.99
    X = lambda t: L + (t - x0) / (x1 - x0) * (W - L - R)  # noqa: E731
    Y = lambda r: T + (1 - min(r, YMAX) / YMAX) * (H - T - B)  # noqa: E731
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Risque et borne selon le seuil, {e(nom)}">']
    for r in (0, 0.01, 0.02, 0.03, 0.04, 0.05):
        out.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{Y(r):.1f}" y2="{Y(r):.1f}"/>'
                   f'<text class="tick" x="{L - 6}" y="{Y(r) + 3.5:.1f}" text-anchor="end">{fr(100 * r, 0)} %</text>')
    for t in (0.80, 0.85, 0.90, 0.95, 0.99):
        out.append(f'<text class="tick" x="{X(t):.1f}" y="{H - B + 15}" text-anchor="middle">{fr(t, 2)}</text>')
    out.append(f'<text class="tick lbl" x="{(L + W - R) / 2:.1f}" y="{H - 4}" text-anchor="middle">seuil θ</text>')
    out.append(f'<line class="cible" x1="{L}" x2="{W - R}" y1="{Y(cible):.1f}" y2="{Y(cible):.1f}"/>'
               f'<text class="tick lbl" x="{W - R}" y="{Y(cible) - 4:.1f}" text-anchor="end">r* = {fr(100 * cible)} %</text>')
    pts = [p for p in courbe if p["n"]]
    for cle, coul in (("borne", "var(--s2)"), ("risque", "var(--s1)")):
        if pts:
            d = " ".join(f"{X(p['seuil']):.1f},{Y(p[cle]):.1f}" for p in pts)
            out.append(f'<polyline class="ligne" style="stroke:{coul}" points="{d}"/>')
        for p in pts:
            titre = (f"θ = {fr(p['seuil'], 2)} · n = {p['n']} acceptés · k = {p['k']} pertes · "
                     f"risque {pct(p['risque'], 2)} · borne {pct(p['borne'], 2)}")
            out.append(f'<circle class="pt" r="3.2" cx="{X(p["seuil"]):.1f}" cy="{Y(p[cle]):.1f}" '
                       f'style="fill:{coul}"><title>{e(titre)}</title></circle>')
    if theta is not None:
        p = next(q for q in courbe if q["seuil"] == theta)
        out.append(f'<line class="cross" x1="{X(theta):.1f}" x2="{X(theta):.1f}" y1="{T}" y2="{H - B}"/>'
                   f'<circle class="anneau" r="7" cx="{X(theta):.1f}" cy="{Y(p["borne"]):.1f}"/>'
                   f'<text class="tick lbl" x="{X(theta) + 5:.1f}" y="{T + 10}">θ retenu {fr(theta, 2)}</text>')
    elif pts:
        out.append(f'<text class="tick lbl" x="{(L + W - R) / 2:.1f}" y="{T + 12}" text-anchor="middle">'
                   'aucun θ admissible : fuzzy désactivé</text>')
    else:
        out.append(f'<text class="tick lbl" x="{(L + W - R) / 2:.1f}" y="{(T + H - B) / 2:.1f}" '
                   'text-anchor="middle">aucun cas</text>')
    out.append(f'<line class="base" x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}"/></svg>')
    return "".join(out)


# ── sections ─────────────────────────────────────────────────────────────────────────────────────

def section_calibration(cal: dict, ent: Counter) -> str:
    res, courbes, cas = cal["resume"], cal["courbes"], cal["cas"]["attendue"]
    actives = [f for f, v in res.items() if v["fuzzy"] == "actif"]
    reelles = [f for f in res if f != "mixte"]
    lignes = []
    for f in ordre(res):
        v, c = res[f], cas.get(f, {})
        if v["fuzzy"] == "actif":
            statut = '<span class="pill ok">actif</span>'
            cel = (f"<td class='r'>{fr(v['seuil'], 2)}</td><td class='r'>{num(v['n'])}</td><td class='r'>{v['k']}</td>"
                   f"<td class='r'>{pct(v['borne'], 2)}</td><td class='r'>{pct(v['couverture'])}</td>")
        else:
            meilleur = min(courbes.get(f) or [{"borne": 1, "seuil": None, "n": 0, "k": 0}], key=lambda b: b["borne"])
            motif = "volume" if "il en faut" in v["raison"] else "mixte" if f == "mixte" else "risque"
            statut = f'<span class="pill no">désactivé · {motif}</span>'
            cel = ("<td class='r'>—</td>" +
                   (f"<td class='r mu'>{num(meilleur['n'])}</td><td class='r mu'>{meilleur['k']}</td>"
                    f"<td class='r mu'>{pct(meilleur['borne'], 2)} à {fr(meilleur['seuil'], 2)}</td>"
                    if meilleur["seuil"] is not None else "<td class='r'>·</td><td class='r'>·</td><td class='r'>·</td>")
                   + "<td class='r'>0 %</td>")
        lignes.append(f"<tr><td><strong>{e(NOMS.get(f, f))}</strong><br><span class='mu small'>"
                      f"{e(', '.join(cal['familles_types'].get(f, [])) or 'clé de repli')}</span></td>"
                      f"<td class='r'>{num(ent.get(f, 0)) if f != 'mixte' else '·'}</td>"
                      f"<td class='r'>{num(c.get('present', 0))}</td><td class='r'>{num(c.get('absent', 0))}</td>"
                      f"<td class='r'>{num(v['n_retenables'])}</td>{cel}<td>{statut}</td></tr>")
    facettes = []
    for f in ordre(courbes):
        if not courbes[f]:
            continue
        v = res[f]
        theta = v.get("seuil") if v["fuzzy"] == "actif" else None
        sous = (f"θ = {fr(theta, 2)} · n = {num(v['n'])} · k = {v['k']} · borne {pct(v['borne'], 2)}" if theta
                else f"{num(v['n_retenables'])} cas retenables · désactivé")
        facettes.append(f"<figure class='facet'><figcaption><strong>{e(NOMS.get(f, f))}</strong>"
                        f"<span>{e(sous)}</span></figcaption>{courbe_svg(courbes[f], cal['cible'], theta, NOMS.get(f, f))}"
                        "</figure>")
    a88 = {f: next((p for p in courbes.get(f, []) if p["seuil"] == 0.88), None) for f in reelles}
    return f"""
<section id="calibration">
  <div class="head">
    <p class="eyebrow">Étape 2 · R-RES-10</p>
    <h2>Calibration par famille : r* = 0,5 %, garanti à 95 %</h2>
    <p>La première calibration (un seuil par type, r* = 5 %) n'activait le fuzzy que pour les villes : chaque type avait trop peu de cas. Elle est refaite sur le jeu de <strong>certification</strong>, <code>{e(cal.get('donnees', 'challenges/calibration_certif.csv'))}</code> : {num(sum(sum(c.values()) for c in cas.values()))} termes qui atteignent tous l'étape approchée (fautes de frappe sur des noms du catalogue, et termes absents), sans aucune entité de la partition test. Ce jeu sert seulement à calculer θ : on n'en regarde jamais les erreurs. Les règles ont été conçues sur l'autre jeu, <code>calibration_analyse.csv</code>, tiré avec une autre graine et sans terme commun. Le seuil est calibré par <strong>famille</strong> de types (<code>spec/familles_fuzzy.yaml</code>).</p>
  </div>
  <div class="configs">
    <div><b class="k kA">r*</b><span><strong>{pct(cal['cible'])} de pertes</strong> au plus parmi les termes que le fuzzy accepte. Perte « {e(cal['perte'])} » : le nom accepté mène à une entité qui n'est pas la bonne.</span></div>
    <div><b class="k kA">δ</b><span><strong>{pct(cal['delta'], 0)}</strong> : probabilité que cette garantie soit fausse. Bonferroni sur les 20 seuils : chaque borne est calculée au niveau δ/20.</span></div>
    <div><b class="k kA">θ</b><span><strong>Grille fixe 0,80 → 0,99</strong> (pas 0,01). On retient le θ le plus bas dont la borne B*(k, n, δ/20) est ≤ r*. Il faut au moins {num(cal['n_minimum'])} termes acceptés sans erreur.</span></div>
  </div>
  <div class="stats">
    <div class="stat"><b>{len(actives)}</b><span>famille(s) active(s) sur {len(reelles)}</span></div>
    <div class="stat"><b>{num(cal['n_minimum'])}</b><span>termes acceptés au minimum, sans erreur, pour garantir 0,5 %</span></div>
    <div class="stat"><b>{pct(a88['geographie']['risque']) if a88.get('geographie') else '·'}</b><span>pertes de B (0,88) en géographie, jeu de certification</span></div>
    <div class="stat"><b>{pct(a88['pieces']['risque']) if a88.get('pieces') else '·'}</b><span>pertes de B en pièces, jeu de certification</span></div>
    <div class="stat"><b>{pct(a88['vehicules']['risque']) if a88.get('vehicules') else '·'}</b><span>pertes de B en véhicules, jeu de certification</span></div>
  </div>
  <div class="scroll">
    <table>
      <thead><tr><th>Famille</th><th class="r">Entités</th><th class="r">Cas présents</th><th class="r">Cas absents</th><th class="r">Retenables</th><th class="r">θ</th><th class="r">n</th><th class="r">k</th><th class="r">Borne B*</th><th class="r">Couverture</th><th>Statut</th></tr></thead>
      <tbody>{''.join(lignes)}</tbody>
    </table>
  </div>
  <p class="cap">Présents et absents : par famille attendue du cas. Retenables, n, k : par famille des meilleurs noms trouvés, celle que le moteur utilise pour choisir le seuil (un terme de la famille « pièces » peut tomber sur un nom de lieu). Pour une famille désactivée, n, k et la borne en gris sont ceux du meilleur point de la grille, qui reste au-dessus de r*.</p>
  <div class="panel">
    <h3>Risque et borne selon le seuil, par famille</h3>
    <div class="legend"><span><i style="background:var(--s1)"></i>risque observé k/n</span><span><i style="background:var(--s2)"></i>borne B*(k, n, δ/20)</span><span><i class="tk"></i>r* = 0,5 %</span><span><i class="ring"></i>θ retenu</span></div>
    <div class="facets">{''.join(facettes)}</div>
    <p class="cap">Axe vertical de 0 à 5 % : une borne plus haute est posée sur le bord. Survoler un point donne n, k, le risque et la borne. Plus θ monte, moins de termes sont acceptés : la borne finit par remonter faute de cas, même quand le risque observé tombe à zéro.</p>
  </div>
</section>"""


def _cellules(v: dict) -> str:
    return (f"<td class='r'>{fr(v['ideal'])}</td><td class='r'>{fr(v['sur'])}</td>"
            f"<td class='r'>{v['silencieux']}</td><td class='r'>{fr(v['couverture_fuzzy'])}</td>")


def section_comparaison(cmp_: dict) -> str:
    res, noms = cmp_["resultats"], cmp_["configurations"]
    tot = {k: res[k]["TOTAL"] for k in res}
    glob = "".join(f"<tr><td><b class='k {'kA' if k == 'A' else 'kB' if k.startswith('B') else 'kC'}'>{e(k)}</b></td>"
                   f"<td>{e(noms[k])}</td>{_cellules(tot[k])}</tr>" for k in res)
    fams = [f for f in ordre(res["A"]) if f != "TOTAL"] + ["TOTAL"]

    def tableau(cfgs):
        tete = "".join(f"<th class='r'>{k} idéal</th><th class='r'>{k} sûr</th><th class='r'>{k} sil.</th>"
                       f"<th class='r'>{k} fuzzy</th>" for k in cfgs)
        corps = "".join(f"<tr><td>{'<strong>Total</strong>' if f == 'TOTAL' else e(NOMS.get(f, f))}</td>"
                        f"<td class='r'>{num(res['A'][f]['n'])}</td>" + "".join(_cellules(res[k][f]) for k in cfgs)
                        + "</tr>" for f in fams)
        return (f"<div class='scroll'><table><thead><tr><th>Famille du cas</th><th class='r'>Cas</th>{tete}</tr></thead>"
                f"<tbody>{corps}</tbody></table></div>")

    perdus = cmp_["perdus_par_c"]
    raisons = "".join(f"<li><b>{num(r['n'])}</b> · {e(NOMS.get(r['famille'], r['famille']))} : {e(r['raison'])}</li>"
                      for r in perdus["raisons"])
    return f"""
<section id="comparaison-abc">
  <div class="head">
    <p class="eyebrow">Étape 2 · dev, part eval</p>
    <h2>Comparaison A / B / C, avec et sans index négatif</h2>
    <p>{num(cmp_['n_cas_eval'])} cas : les 30 % de dev réservés à l'évaluation, même découpe par hash du <code>case_id</code> qu'avant. Le jeu de calibration n'en contient aucun. B− et C− : mêmes configurations, mais l'index négatif ne répond plus, comme pour un lieu réel qu'il ne connaîtrait pas encore.</p>
  </div>
  <div class="stats">
    <div class="stat"><b>{fr(tot['B']['ideal'])} %</b><span>idéal avec B (seuil fixe 0,88)</span></div>
    <div class="stat"><b>{fr(tot['C']['ideal'])} %</b><span>idéal avec C ({e(actives_txt(cmp_))}), contre {fr(tot['A']['ideal'])} % pour A</span></div>
    <div class="stat"><b class="good">{tot['A']['silencieux'] + tot['B']['silencieux'] + tot['C']['silencieux']}</b><span>erreur silencieuse pour A, B et C</span></div>
    <div class="stat"><b>{tot['B−']['silencieux']}</b><span>erreurs silencieuses pour B sans index négatif, contre {tot['C−']['silencieux']} pour C</span></div>
    <div class="stat"><b>{fr(tot['C']['sur'])} %</b><span>sûr avec C, contre {fr(tot['B']['sur'])} % pour B</span></div>
  </div>
  <div class="scroll"><table>
    <thead><tr><th></th><th>Configuration</th><th class="r">Idéal %</th><th class="r">Sûr %</th><th class="r">Silencieux</th><th class="r">Fuzzy %</th></tr></thead>
    <tbody>{glob}</tbody></table></div>
  <p class="cap">« Fuzzy % » : part des cas dont la réponse vient de l'étape approchée (les cas rattrapés). Silencieux : nombre de cas.</p>
  <h3>Par famille, avec index négatif</h3>
  {tableau(['A', 'B', 'C'])}
  <h3>Par famille, sans index négatif</h3>
  {tableau(['B−', 'C−'])}
  <div class="why">
    <p><strong>Pourquoi C reste sous B en idéal.</strong> C perd {num(perdus['total'])} cas que B résout correctement, et tous viennent de familles désactivées, jamais d'un θ plus haut que 0,88 :</p>
    <ul class="etapes">{raisons}</ul>
    <p>« Risque » : la famille a assez de cas, mais à aucun seuil de la grille la borne ne descend sous 0,5 %. Les deux corrections de structure (ordre des mots, voisins R-RES-11) ont retiré l'essentiel des présents confondus ; ce qui reste vient surtout de termes absents que l'approché accepte (voir le <a href="#diagnostic">diagnostic</a>). « Volume » : moins de {num(cmp_['seuils']['n_minimum'])} termes acceptés, même sans aucune erreur ce n'est pas assez pour garantir 0,5 %. « κ sous θ » : la famille est active, mais le score du terme est sous son seuil calibré.</p>
    <p>Sur la part eval, B ne fait aucune erreur silencieuse avec l'index négatif. Sans lui, il en fait {tot['B−']['silencieux']}, sur des lieux réels hors périmètre rapprochés d'un lieu du catalogue ({e(exemples_bm(cmp_))}). C en fait {tot['C−']['silencieux']}.</p>
  </div>
</section>"""


def _trace(t: list[dict]) -> str:
    return e(json.dumps(t, ensure_ascii=False, indent=1))


def section_exemples(cmp_: dict) -> str:
    ex = cmp_["exemples"]
    if ex["rattrapes_c"]:
        rat = "".join(f"<tr><td class='mono'>{e(r['case_id'])}</td><td>{e(NOMS.get(r['famille'], r['famille']))}</td>"
                      f"<td class='mono'>{e(r['texte'])}</td><td class='mono'>{e(', '.join(r['ids']))}</td></tr>"
                      for r in ex["rattrapes_c"])
        rattrapes = (f"<div class='scroll'><table><thead><tr><th>Cas</th><th>Famille</th><th>Terme</th>"
                     f"<th>Réponse de C</th></tr></thead><tbody>{rat}</tbody></table></div>")
    else:
        rattrapes = ("<p class='cap'><strong>Aucun.</strong> C ne rattrape aucun cas par l'approché sur la part eval.</p>")
    per = "".join(f"<tr><td class='mono'>{e(r['case_id'])}</td><td>{e(NOMS.get(r['famille'], r['famille']))}</td>"
                  f"<td class='mono'>{e(r['texte'])}</td><td class='r'>{fr(r['kappa'], 3) if r['kappa'] else '·'}</td>"
                  f"<td class='mono'>{e(r['b_statut'])} · {e(', '.join(r['b_ids']))}</td>"
                  f"<td class='mono'>{e(r['statut'])}</td><td>{e(r['raison'])}</td></tr>" for r in ex["perdus_c"])
    sil = ex["silencieuses"]
    par_cfg = Counter(s["config"] for s in sil)
    details = "".join(f"<details><summary><span class='mono'>{e(s['config'])} · {e(s['case_id'])}</span> « {e(s['texte'])} » "
                      f"→ <span class='mono'>{e(', '.join(s['ids']))}</span> (attendu {e(s['attendus'] or s['attendu'])})"
                      f"</summary><pre class='trace'>{_trace(s['trace'])}</pre></details>" for s in sil)
    resume_sil = ", ".join(f"{k} : {v}" for k, v in sorted(par_cfg.items())) or "aucune"
    return f"""
<section id="exemples-calibration">
  <div class="head">
    <p class="eyebrow">Étape 2 · exemples</p>
    <h2>Exemples : rattrapés, perdus et erreurs silencieuses</h2>
  </div>
  <h3>Cas rattrapés par C ({num(ex['n_rattrapes_c'])})</h3>
  {rattrapes}
  <h3>Cas perdus par C par rapport à B (10 sur {num(cmp_['perdus_par_c']['total'])})</h3>
  <div class="scroll"><table>
    <thead><tr><th>Cas</th><th>Famille</th><th>Terme</th><th class="r">κ</th><th>Réponse de B (correcte)</th><th>C</th><th>Raison, lue dans la trace de C</th></tr></thead>
    <tbody>{per}</tbody></table></div>
  <h3>Erreurs silencieuses ({len(sil)} · {e(resume_sil)})</h3>
  <p class="cap">Par configuration : {e(resume_sil)}. Trace complète du moteur en dépliant chaque ligne.</p>
  <div class="silencieuses">{details}</div>
</section>"""


def encadre(cal: dict) -> str:
    return f"""
<section id="garantie">
  <div class="avenir">
    <h3>Ce que garantit C, et que B ne garantit pas</h3>
    <p><strong>B</strong> applique le même seuil 0,88 partout. Ce chiffre a été choisi à la main. Sur la part eval de dev, il ne fait aucune erreur silencieuse, mais rien ne dit combien il en ferait sur des termes nouveaux : il suffit de retirer l'index négatif pour qu'il en fasse {{b_moins}}.</p>
    <p><strong>C</strong> fait une promesse chiffrée, famille par famille : « parmi les termes que j'accepte par approximation, au plus {pct(cal['cible'])} mènent à une mauvaise entité, et je me trompe sur cette promesse au plus 5 fois sur 100 ». Quand les données ne permettent pas de tenir cette promesse, C ne devine pas : il répond « je ne sais pas » (unknown), et la question est reformulée.</p>
    <p>Aujourd'hui : {e(actives_phrase(cal))} Au seuil 0,88, B se trompe sur {pct(cal['risque_b']['TOTAL']['risque'])} des termes qu'il accepte dans le jeu de certification (borne {pct(cal['risque_b']['TOTAL']['borne'])} à 95 %) : son « 0 erreur silencieuse » sur la part eval de dev ne prouve pas sa sûreté. Pour activer d'autres familles, il faut refuser les termes absents que l'approché accepte encore (noms recombinés, voir le diagnostic), une cible moins stricte décidée par le métier, ou plus de données.</p>
  </div>
</section>"""


# ── diagnostic (jeu d'analyse) et risque de B (jeu de certification) ─────────────────────────────

FICHIERS_DIAG = {"avant": REP / "diagnostic_fuzzy_avant.json", "mots_tries": REP / "diagnostic_fuzzy_mots_tries.json",
                 "voisinage": REP / "diagnostic_fuzzy_voisinage.json", "actuel": REP / "diagnostic_fuzzy.json"}
CORRECTIONS_DEV = REP / "corrections_dev.json"
VARIANTES_NOMS = {"avant": "sans correction", "mots_tries": "ordre des mots", "voisinage": "R-RES-11",
                  "actuel": "les deux"}
SORTES_NOMS = {"present_confondu": "présent confondu", "absent_accepte": "absent accepté"}
ORIGINES = {"nom_recombine": "noms recombinés", "faute_index_negatif": "fautes sur l'index négatif",
            "marque_reelle_hors_catalogue": "vraies marques hors catalogue", "faute_de_frappe": "faute de frappe"}


def court(t: str, n: int = 60) -> str:
    return t if len(t) <= n else t[:n - 1] + "…"


def actives_txt(cmp_: dict) -> str:
    act = [NOMS.get(f, f).lower() for f, v in (cmp_["seuils"].get("familles") or {}).items() if v.get("fuzzy") == "actif"]
    return ("famille active : " + ", ".join(act)) if act else "aucune famille active"


def actives_phrase(cal: dict) -> str:
    act = [(NOMS.get(f, f).lower(), v) for f, v in cal["resume"].items() if v["fuzzy"] == "actif"]
    if not act:
        return "aucune famille ne permet de tenir 0,5 % : C se comporte comme A."
    return ("seule(s) " + ", ".join(f"la famille {n} (θ = {fr(v['seuil'], 2)}, borne {pct(v['borne'], 2)})" for n, v in act)
            + " tient 0,5 %. Les autres restent sans approché : C répond « je ne sais pas » plutôt que de deviner.")


def exemples_bm(cmp_: dict) -> str:
    sil = [s["texte"] for s in cmp_["exemples"]["silencieuses"] if s["config"] == "B−"]
    return ", ".join(sil[:4]) or "aucun"


def section_diagnostic(diag: dict, dev: dict | None) -> str:
    if "actuel" not in diag:
        return ""
    act, avant = diag["actuel"], diag.get("avant")
    fams = [f for f in ordre(act["familles"])]

    def cel(d, f, nom, sorte, cle="n"):
        try:
            return d["familles"][f][nom]["par_sorte"][sorte].get(cle, 0)
        except (KeyError, TypeError):
            return "·"

    lignes = []
    for f in fams:
        a = act["familles"][f]
        cells = []
        for nom in ("meilleur", "b"):
            b = a[nom]
            pc_av = cel(avant, f, nom, "present_confondu") if avant else "·"
            cells.append(f"<td class='r'>{fr(b['seuil'], 2)}</td><td class='r'>{num(b['n'])}</td>"
                         f"<td class='r'>{pc_av} → <b>{b['par_sorte']['present_confondu']['n']}</b></td>"
                         f"<td class='r'>{b['par_sorte']['present_confondu'].get('avec_voisin_reel', 0)}</td>"
                         f"<td class='r'><b>{b['par_sorte']['absent_accepte']['n']}</b></td>"
                         f"<td class='r'>{pct(b['borne'], 2)}</td>")
        lignes.append(f"<tr><td><strong>{e(NOMS.get(f, f))}</strong></td><td class='r'>{num(a['n_retenables'])}</td>"
                      + "".join(cells) + "</tr>")

    # origines des absents acceptés à 0,88, toutes familles
    orig = Counter()
    for f in fams:
        orig.update(act["familles"][f]["b"]["par_sorte"]["absent_accepte"].get("par_origine", {}))
    total_abs = sum(orig.values())
    origines = ", ".join(f"{ORIGINES.get(k, k)} {num(v)} ({pct(v / total_abs, 0)})" for k, v in orig.most_common()) if total_abs else "aucun"

    # variantes : présents confondus et absents acceptés à 0,88, toutes familles
    var = ""
    if len(diag) > 1:
        tete = "".join(f"<th class='r'>{e(VARIANTES_NOMS[v])}</th>" for v in VARIANTES_NOMS if v in diag)

        def somme(v, sorte):
            return sum(x["b"]["par_sorte"][sorte]["n"] for x in diag[v]["familles"].values())
        corps = "".join(f"<tr><td>{e(SORTES_NOMS[s_])} (θ = 0,88)</td>"
                        + "".join(f"<td class='r'>{num(somme(v, s_))}</td>" for v in VARIANTES_NOMS if v in diag)
                        + "</tr>" for s_ in SORTES_NOMS)
        if dev:
            corps += ("<tr><td>dev entière, B : idéal / sûr / silencieux / trop confiant</td>"
                      + "".join(f"<td class='r'>{fr(dev[v]['ideal'])} / {fr(dev[v]['sur'])} / {dev[v]['silencieux']} / "
                                f"{dev[v]['trop_confiant']}</td>" for v in VARIANTES_NOMS if v in diag) + "</tr>")
        var = (f"<h3>Effet des deux corrections, une à une</h3><div class='scroll'><table><thead><tr><th>Mesure</th>{tete}"
               f"</tr></thead><tbody>{corps}</tbody></table></div>")

    def tab_ex(sorte):
        rows = []
        for f in fams:
            for x in act["familles"][f]["b"]["exemples"][sorte][:2]:
                vr = ", ".join(x.get("voisins_reels", [])[:3])
                rows.append(f"<tr><td>{e(NOMS.get(f, f))}</td><td class='mono'>{e(court(x['terme']))}</td>"
                            f"<td class='mono'>{e(court(x['source']))}</td><td class='r'>{fr(x['kappa'], 3)}</td>"
                            f"<td class='mono'>{e(court(', '.join(x['noms'][:3])))}</td><td class='mono'>{e(x['statut'])}</td>"
                            + (f"<td class='mono'>{e(vr) or '·'}</td>" if sorte == "present_confondu" else "") + "</tr>")
        tete = ("<th>Famille</th><th>Terme tapé</th><th>Origine</th><th class='r'>κ</th><th>Noms retenus</th><th>Réponse</th>"
                + ("<th>Voisin réel à 1 faute</th>" if sorte == "present_confondu" else ""))
        return f"<div class='scroll'><table><thead><tr>{tete}</tr></thead><tbody>{''.join(rows[:10])}</tbody></table></div>"

    return f"""
<section id="diagnostic">
  <div class="head">
    <p class="eyebrow">Étape 2 · jeu d'analyse</p>
    <h2>Diagnostic : d'où viennent les pertes de l'approché</h2>
    <p>Sur <code>{e(act['donnees'])}</code> ({num(act['n_cas'])} termes), pour chaque famille, au meilleur point de la grille (plus petite borne) puis au seuil 0,88 de B, les pertes parmi les termes acceptés sont réparties entre <strong>présents confondus</strong> (une faute sur un nom du catalogue mène à une autre entité) et <strong>absents acceptés</strong> (un terme hors catalogue est accepté). « Voisin réel » : un autre nom du même type est à une seule faute du terme tapé, comme Fressin pour « Fresin » (faute pour Fretin). La flèche donne le nombre de présents confondus avant puis après les deux corrections.</p>
  </div>
  <div class="scroll"><table>
    <thead><tr><th rowspan="2">Famille</th><th class="r" rowspan="2">Retenables</th><th colspan="6">Meilleur point de la grille</th><th colspan="6">Seuil 0,88 (B)</th></tr>
    <tr><th class="r">θ</th><th class="r">n</th><th class="r">Présents confondus</th><th class="r">dont voisin réel</th><th class="r">Absents acceptés</th><th class="r">Borne</th><th class="r">θ</th><th class="r">n</th><th class="r">Présents confondus</th><th class="r">dont voisin réel</th><th class="r">Absents acceptés</th><th class="r">Borne</th></tr></thead>
    <tbody>{''.join(lignes)}</tbody></table></div>
  <div class="why">
    <p><strong>À 0,88, la perte principale n'est pas la confusion entre deux noms réels, ce sont les termes absents acceptés.</strong> Origine de ces absents, toutes familles : {e(origines)}. Un nom recombiné garde tous ses mots sauf un (« nombre de Julie » pour « nombre de clients ») : sur une chaîne longue, Jaro-Winkler reste au-dessus de 0,9 malgré un mot entièrement faux. Ni l'ordre des mots ni R-RES-11 ne corrigent ce cas.</p>
    <p>Les deux corrections retirent en revanche l'essentiel des présents confondus. <strong>R-RES-11</strong> (voisins en distance d'édition) traite les fautes qui tombent à égale distance de deux lieux réels : en géographie, le meilleur nom n'est plus choisi seul. <strong>L'ordre des mots</strong> réunit, comme l'exact, « Fiat Abarth 500 » et « Fiat 500 Abarth » : les clients et les véhicules ne répondent plus « résolu » là où l'exact répond « ambigu ».</p>
  </div>
  {var}
  <details><summary>10 exemples de présents confondus à 0,88 (après corrections)</summary>{tab_ex('present_confondu')}</details>
  <details><summary>10 exemples d'absents acceptés à 0,88 (après corrections)</summary>{tab_ex('absent_accepte')}</details>
</section>"""


def section_risque_b(cal: dict) -> str:
    rb = cal.get("risque_b")
    if not rb:
        return ""
    lignes = "".join(f"<tr{' class=tot' if f == 'TOTAL' else ''}><td>{'<strong>Total</strong>' if f == 'TOTAL' else e(NOMS.get(f, f))}</td>"
                     f"<td class='r'>{num(v['n'])}</td><td class='r'>{num(v['k'])}</td><td class='r'>{pct(v['risque'], 2)}</td>"
                     f"<td class='r'>{pct(v['borne'], 2)}</td></tr>" for f, v in rb.items())
    t = rb["TOTAL"]
    return f"""
<section id="risque-b">
  <div class="head">
    <p class="eyebrow">Étape 2 · jeu de certification</p>
    <h2>Risque de B (seuil fixe 0,88) sur le jeu de certification</h2>
    <p>Le seuil 0,88 a été choisi à la main, pas sur ces données : sa borne se calcule au niveau δ = 5 %, sans correction de grille. Sur {num(t['n'])} termes que B accepte, {num(t['k'])} mènent à une mauvaise entité ou sont des absents acceptés : <strong>{pct(t['risque'])}</strong>, borne {pct(t['borne'])} à 95 %. C'est {fr(t['risque'] / cal['cible'], 0)} fois la cible r* = 0,5 %.</p>
  </div>
  <div class="scroll"><table>
    <thead><tr><th>Famille de la proposition</th><th class="r">Acceptés n</th><th class="r">Pertes k</th><th class="r">Risque k/n</th><th class="r">Borne B*(k, n, δ)</th></tr></thead>
    <tbody>{lignes}</tbody></table></div>
  <p class="cap">On ne regarde que ces totaux : les erreurs du jeu de certification ne sont jamais examinées une à une.</p>
</section>"""


def generer() -> str:
    cal = json.loads((REP / "calibration.json").read_text(encoding="utf-8"))
    cmp_ = json.loads((REP / "fuzzy_dev.json").read_text(encoding="utf-8"))
    cat = Catalogue.charger()
    fams = charger_familles(cat)
    ent = Counter(fams[t] for t in cat.etype.values())
    style = """
<style>
.small { font-size: 12px; } .mu { color: var(--ink-3); }
#calibration table td, #comparaison-abc table td, #exemples-calibration table td { vertical-align: top; }
.silencieuses { display: grid; gap: 4px; }
.silencieuses details { background: var(--surface); border: 1px solid var(--line); border-radius: 4px; padding: 6px 10px; font-size: 13.5px; }
.silencieuses summary { cursor: pointer; }
pre.trace { font: 12px/1.45 var(--mono); white-space: pre-wrap; overflow-wrap: anywhere; background: var(--sunken); padding: 10px; border-radius: 4px; margin: 8px 0 2px; max-height: 360px; overflow: auto; }
#calibration .configs .k, #calibration .configs .kA { color: var(--ink); }
</style>"""
    tot = cmp_["resultats"]["B−"]["TOTAL"]["silencieux"]
    diag = {v: json.loads(f.read_text(encoding="utf-8")) for v, f in FICHIERS_DIAG.items() if f.exists()}
    dev = json.loads(CORRECTIONS_DEV.read_text(encoding="utf-8")) if CORRECTIONS_DEV.exists() else None
    corps = (section_diagnostic(diag, dev) + section_calibration(cal, ent) + section_risque_b(cal)
             + encadre(cal).replace("{b_moins}", str(tot))
             + section_comparaison(cmp_) + section_exemples(cmp_))
    return f"{DEBUT}{style}{corps}\n{FIN}"


def inserer(html: str, bloc: str) -> str:
    if DEBUT in html:
        a, b = html.index(DEBUT), html.index(FIN) + len(FIN)
        html = html[:a] + bloc + html[b:]
    else:
        ancre = '<section id="acquis"'
        if ancre not in html:
            raise ValueError(f"{RAPPORT.name} : section « acquis » introuvable pour placer le bloc de calibration.")
        i = html.index(ancre)
        html = html[:i] + bloc + "\n\n" + html[i:]
    note = (f"{NOTE_DEBUT}<p class=\"cap\"><strong>Mise à jour :</strong> cette section décrit la première "
            "calibration, un seuil par type avec r* = 5 %. Elle est remplacée par la calibration par famille "
            "(r* = 0,5 %) des sections <a href=\"#calibration\">Calibration</a> et "
            f"<a href=\"#comparaison-abc\">Comparaison A / B / C</a> ci-dessous.</p>{NOTE_FIN}")
    if NOTE_DEBUT in html:
        a, b = html.index(NOTE_DEBUT), html.index(NOTE_FIN) + len(NOTE_FIN)
        html = html[:a] + note + html[b:]
    else:
        ancre = '<h2>Étape 2 : Jaro-Winkler borné, trois configurations comparées</h2>'
        if ancre in html:
            html = html.replace(ancre, ancre + "\n    " + note, 1)
    return html


def main() -> int:
    console_utf8()
    html = RAPPORT.read_text(encoding="utf-8")
    RAPPORT.write_text(inserer(html, generer()), encoding="utf-8")
    print(f"→ {RAPPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
