"""
Rapport HTML autonome : reports/modele_saisie.html, depuis reports/mesure_saisies.json (modèle en vigueur, v0.3)
et les mesures des versions précédentes conservées (reports/mesure_saisies_v0_1.json, _v0_2.json).

    python -m engine.rapport_saisies

Sections : jeux générés, vérification du générateur contre l'échantillon réel (réel / v0.1 / v0.2 / v0.3, et pour
chaque indicateur : le réel tombe-t-il entre v0.1 et v0.3 ?), moteur à 0,88 (seuil fixe provisoire) sur le banc,
diagnostic des erreurs (banc et analyse), échantillon réel, sensibilité, calibration (R-RES-10) et, en section 8,
pourquoi certaines familles n'obtiennent pas de seuil (engine/rapport_familles.py). Rien n'est corrigé par ce script.
"""
from __future__ import annotations

import html
import json
import math
import sys

from engine import rapport_familles
from engine.calibration import borne_haute
from engine.catalogue import ROOT, console_utf8

ENTREE = ROOT / "reports" / "mesure_saisies.json"
PRECEDENTES = {"v0.1": ROOT / "reports" / "mesure_saisies_v0_1.json",
               "v0.2": ROOT / "reports" / "mesure_saisies_v0_2.json"}
COURANTE = "v0.3"
SORTIE = ROOT / "reports" / "modele_saisie.html"
CALIBRATION = ROOT / "reports" / "calibration.json"           # python -m engine.calibration
COMPARAISON = ROOT / "reports" / "comparaison_seuils.json"    # python -m engine.comparaison_seuils
ANALYSE_FAMILLES = ROOT / "reports" / "analyse_familles.json"  # python -m engine.analyse_familles

# Changements décidés par l'auteur (spec/modele_saisie.yaml · changements_v0_2 et _v0_3), rappelés pour lecture.
CHANGEMENTS = {
    "v0.2": ["faute de clavier « espace » (fusion 0,70, coupure 0,30), poids 0,10",
             "substitution et insertion : touche voisine 0,50, lettre quelconque 0,50",
             "plus de saisies très fautives, classe « 4 » en entendu",
             "oubli de mot par type (article 0,35, modèle 0,30, client 0,25, autres 0,02), × 1,5 en entendu",
             "règle phonétique « transcription_libre » (0,30)",
             "géographie du banc : moitié parmi les 300 lieux les plus peuplés",
             "réponse attendue : voisins bornés à 2 fautes ; collision exacte comptée à part"],
    "v0.3": ["clavier : omission 0,40, substitution 0,20, inversion 0,15, insertion 0,10, doublement 0,05, espace 0,10",
             "fautes : lu {0: 0,48, 1: 0,32, 2: 0,13, 3: 0,07}, entendu {0: 0,33, 1: 0,27, 2: 0,20, 3: 0,20}, sans classe 4",
             "transcription_libre 0,15 ; consonne_double réduite",
             "oubli de mot : article 0,25, modèle 0,20, client 0,15, autres 0,02 ; × 1,2 en entendu, plafond 0,6",
             "valeurs auparavant écrites en prose devenues des clés du YAML",
             "mots oubliés du généré notés à la génération (plus redétectés après coup)"],
}

e = html.escape


def pct(x, d=1):
    return "·" if x is None else f"{x:.{d}f} %".replace(".", ",")


def nb(x):
    return "·" if x is None else f"{x:,}".replace(",", " ")


def encadre(reel, v01, v03) -> str:
    """Le réel tombe-t-il entre v0.1 et v0.3 (bornes comprises) ?"""
    if reel is None or v01 is None or v03 is None:
        return "·"
    bas, haut = min(v01, v03), max(v01, v03)
    if bas <= reel <= haut:
        return '<span class="ok">oui</span>'
    return f'<span class="mal">non ({"en dessous" if reel < bas else "au-dessus"})</span>'


def ecart(a, b, d=1):
    """Écart b − a en points, signé."""
    if a is None or b is None:
        return "·"
    x = b - a
    return f"{'+' if x > 0 else ''}{x:.{d}f}".replace(".", ",")


def table(entetes, lignes, classes=None) -> str:
    th = "".join(f"<th>{e(h)}</th>" for h in entetes)
    corps = ["<tr>" + "".join(f"<td>{c}</td>" for c in l) + "</tr>" for l in lignes]
    return (f'<div class="tw"><table class="{classes or ""}"><thead><tr>{th}</tr></thead>'
            f'<tbody>{"".join(corps)}</tbody></table></div>')


def cell_sil(v: dict) -> str:
    sil = v.get("silencieux", 0)
    return f'<span class="{"mal" if sil else ""}">{nb(sil)} ({pct(v.get("silencieux_pct"), 2)})</span>'


def lignes_taux(d: dict) -> list:
    out = []
    for k, v in d.items():
        if not v.get("n"):
            continue
        nom = f"<b>{e(k)}</b>" if k == "TOTAL" else e(k)
        out.append([nom, nb(v["n"]), pct(v["ideal"]), pct(v["sur"]), cell_sil(v),
                    nb(v.get("dont_collision_exacte", "·") if "dont_collision_exacte" in v else None),
                    pct(v.get("silencieux_hors_collision_pct"), 2),
                    nb(v["trop_confiant"]), nb(v["incorrect"])])
    return out


ENTETES_TAUX = ["", "Cas", "Idéal", "Sûr", "Silencieux", "dont collision exacte", "Silencieux hors collision",
                "Trop confiant", "Incorrect"]


def barres(titre: str, series: list[tuple[str, str, dict]], cles) -> str:
    """Barres groupées (réel, v0.1, v0.2) ; valeur écrite au bout de chaque barre."""
    lignes = []
    for k in cles:
        bb = "".join(f'<div class="bb"><div class="bar {cl}" style="width:{(d.get(k) or 0)}%"></div>'
                     f'<span class="bv">{pct(d.get(k))}</span></div>' for _, cl, d in series)
        lignes.append(f'<div class="bl" style="--n:{len(series)}"><span class="bk">{e(k)}</span>{bb}</div>')
    return f'<figure class="barres"><figcaption>{e(titre)}</figcaption>{"".join(lignes)}</figure>'


LEGENDE = '<div class="leg"><span><i class="s1"></i>réel</span><span><i class="s0"></i>générateur v0.1</span>' \
          '<span><i class="s3"></i>générateur v0.2</span><span><i class="s2"></i>générateur v0.3</span></div>'


# ── sections ──────────────────────────────────────────────────────────────────────────────────────

def section_jeux(d: dict, prec: dict) -> str:
    jeux = d["meta_jeux"]
    lignes = []
    for cle in ("banc", "analyse", "certif"):
        j = jeux.get(cle)
        if not j:
            continue
        pres = ", ".join(f"{f} {nb(n)}" for f, n in j["presents_par_famille"].items())
        absn = ", ".join(f"{k} {nb(n)}" for k, n in j["absents_par_sous_nature"].items())
        modes = ", ".join(f"{k} {nb(n)}" for k, n in j["modes"].items())
        avant = " ; ".join(f"{v} : {nb(x.get('meta_jeux', {}).get(cle, {}).get('graine'))}" for v, x in prec.items())
        lignes.append([f"<b>{cle}</b>", f"{nb(j['graine'])} <span class='note'>({avant})</span>",
                       nb(j["cas"]), pres, absn, modes, nb(j["absents_reportes_faute_de_stock"])])
    rejets = [[cle, e(k), nb(n)] for cle in ("banc", "analyse", "certif")
              for k, n in jeux.get(cle, {}).get("rejets", {}).items()]
    peuples = jeux.get("banc", {}).get("geographie_plus_peuples")
    geo = jeux.get("banc", {}).get("presents_par_famille", {}).get("geographie")
    mots = ", ".join(f"{e(w)} ({pct(100 * f, 1)})" for w, f in d.get("mots_clients_frequents_hors_listes", [])) or "aucun"
    ch = "".join(f"<li><b>{v}</b><ul>" + "".join(f"<li>{e(x)}</li>" for x in xs) + "</ul></li>"
                 for v, xs in CHANGEMENTS.items())
    return f"""
<section id="jeux"><h2>1. Les jeux générés (modèle {COURANTE}, figé)</h2>
<p>Trois jeux tirés de <code>spec/modele_saisie.yaml</code> {COURANTE} par <code>build/build_saisies.py</code>, avec de
nouvelles graines. Le modèle {COURANTE} est la dernière version avant le travail sur le moteur : l'objectif n'est plus de
coller au réel point par point, mais que le réel tombe entre v0.1 et {COURANTE} ; l'incertitude restante est couverte
par la sensibilité. Le <b>banc</b> imite le trafic : il suit la répartition par famille et garde les saisies sans
faute. L'<b>analyse</b> sert à concevoir. La <b>certification</b> a été régénérée mais n'est pas ouverte : elle servira une
seule fois, plus tard, à calculer un seuil. Les jeux de calibration ne gardent que des saisies fautives qui atteignent
l'étape approchée, au plus 3 par nom, sans terme normalisé commun entre eux.</p>
<details><summary>Changements de v0.2 et v0.3 (décidés par l'auteur)</summary><ul>{ch}</ul></details>
{table(["Jeu", "Graine", "Cas", "Présents par famille", "Absents par sous-nature", "Modes", "Absents reportés"], lignes)}
<p class="note">Géographie du banc : {nb(peuples)} saisies sur {nb(geo)} tirées parmi les lieux les plus peuplés
(dont ceux tirés « au hasard » qui en font partie).
« Absents reportés » : absents qui manquaient faute de stock (3 cas au plus par terme), reportés sur les lieux hors
périmètre puis sur les noms recombinés. Plusieurs familles restent sous 3 000 dans l'analyse (plafond de 3 cas par
nom, exclusion de la partition test).</p>
<details><summary>Saisies écartées pendant la génération</summary>{table(["Jeu", "Raison", "Nombre"], rejets)}</details>
<h3>Index négatif partagé en deux</h3>
<p>{nb(d["negatifs_retires"])} lieux de l'index négatif (même graine qu'en v0.1 et v0.2) sont écrits dans
<code>challenges/negatifs_retires.csv</code> et retirés de l'index <b>chargé</b> pendant l'évaluation des jeux générés
(<code>engine/mesure_saisies.py · charger_catalogue_jeux</code>) ; <code>catalog/negatifs.csv</code> n'est pas modifié.
L'échantillon réel est évalué avec l'index complet.</p>
<h3>Mots génériques des clients</h3>
<p>Mots présents dans plus de 1 % des noms de clients et absents des trois listes du modèle : {mots}.</p>
</section>"""


def section_verification(d: dict, prec: dict) -> str:
    v = d["verification"]
    ver = {k: x.get("verification", {}) for k, x in prec.items()}
    blocs, bilan = [], []
    entetes = ["Indicateur", "Réel", "v0.1", "v0.2", COURANTE, "Réel entre v0.1 et " + COURANTE + " ?"]
    for mode in ("lu", "entendu"):
        if mode not in v:
            continue
        r, g = v[mode]["reel"], v[mode]["genere"]
        g1, g2 = ver["v0.1"].get(mode, {}).get("genere", {}), ver["v0.2"].get(mode, {}).get("genere", {})
        cles = ["0", "1", "2", "3+"]
        blocs.append(f"<h3>Mode « {mode} » · {nb(r['n'])} saisies réelles, {nb(g['n'])} générées par version</h3>")
        blocs.append(barres(f"Distance OSA au nom source, après retrait des mots oubliés ({mode})",
                            [("réel", "s1", r["distance"]), ("v0.1", "s0", g1.get("distance", {})),
                             ("v0.2", "s3", g2.get("distance", {})), (COURANTE, "s2", g["distance"])], cles))

        def ligne(nom, rv, a, b, c, fmt=pct):
            bilan.append((mode, nom, rv, a, c))
            return [nom, fmt(rv), fmt(a), fmt(b), fmt(c), encadre(rv, a, c)]

        lignes = [ligne(f"Distance {k}", r["distance"].get(k), g1.get("distance", {}).get(k),
                        g2.get("distance", {}).get(k), g["distance"].get(k)) for k in cles]
        lignes.append(ligne("Mots oubliés", r["mots_oublies_pct"], g1.get("mots_oublies_pct"),
                            g2.get("mots_oublies_pct"), g["mots_oublies_pct"]))
        lignes.append(ligne("Opérations par saisie", r["fautes_par_saisie"], g1.get("fautes_par_saisie"),
                            g2.get("fautes_par_saisie"), g["fautes_par_saisie"],
                            lambda x: "·" if x is None else f"{x:.2f}".replace(".", ",")))
        blocs.append(table(entetes, lignes))
        tr, t1, t2, tg = (dict(r["types"]), dict(g1.get("types", [])), dict(g2.get("types", [])), dict(g["types"]))
        types = sorted(set(tr) | set(tg) | set(t1) | set(t2), key=lambda k: -(tr.get(k, 0) + tg.get(k, 0)))[:16]
        blocs.append(table(["Type de faute (part des opérations)"] + entetes[1:],
                           [ligne(e(k), tr.get(k, 0), t1.get(k), t2.get(k), tg.get(k, 0)) for k in types]))
    dedans = [x for x in bilan if x[2] is not None and x[3] is not None and x[4] is not None
              and min(x[3], x[4]) <= x[2] <= max(x[3], x[4])]
    dehors = [x for x in bilan if x not in dedans and None not in x[2:]]
    lst = "".join(f"<li>mode {e(m)} : {k}, réel {pct(rv)}, v0.1 {pct(a)}, {COURANTE} {pct(c)}</li>"
                  for m, k, rv, a, c in dehors if "Opérations" not in k) or "<li>aucun</li>"
    ex = [[e(x["mode"]), e(x["nom"]), f"<b>{e(x['reel'])}</b>", f"<b>{e(x['genere'])}</b>", e(x["perturbations"])]
          for x in v["exemples"]]
    det = v["detection_oublis_sur_genere"]
    return f"""
<section id="verification"><h2>2. Le générateur face à l'échantillon réel : réel, v0.1, v0.2, {COURANTE}</h2>
<p>Mêmes indicateurs pour toutes les colonnes, calculés par les mêmes fonctions. Réel : les saisies de
<code>human/echantillon_reel/saisies_combinees.csv</code> (« oreille » = entendu, « mémoire » = lu), sans les saisies
vides ou « ? ». Généré : un <b>miroir</b>, les mêmes noms dans le même mode, tapés 10 fois chacun par le générateur.
Distance OSA entre la saisie et le nom source privé des mots oubliés ; types de fautes par décomposition en règles
phonétiques du modèle puis en opérations de clavier.</p>
<p><b>Mots oubliés</b> : repérés par alignement de mots sur le réel ; sur le généré, notés à la génération en {COURANTE}
mais <b>redétectés par alignement en v0.1 et v0.2</b> (mesures conservées telles quelles). Le repérage inventait 1,6 %
d'oublis sur le généré v0.1 et 12 % sur le v0.2 : les colonnes v0.2 surestiment les oublis et faussent un peu les
distances.</p>
<p><b>Encadrement</b> : {len(dedans)} indicateurs mesurables sur {len(dedans) + len(dehors)} ont le réel entre v0.1 et {COURANTE}
(bornes comprises). « · » : type de faute hors des 12 premiers dans les mesures conservées de v0.1 ou v0.2, non comparable.</p>
{LEGENDE}
{"".join(blocs)}
<h3>Indicateurs où le réel sort de l'intervalle v0.1 – {COURANTE}</h3>
<p class="note">Signalés sans correction : le modèle est figé.</p><ul>{lst}</ul>
<p class="note">Contrôle du repérage par alignement (celui du réel), appliqué aux saisies générées {COURANTE} dont on connaît
la vérité : oubli réel repéré {nb(det["vrai_detecte"])}, manqué {nb(det["vrai_manque"])} ; faux oubli repéré
{nb(det["faux_detecte"])} sur {nb(det["faux_detecte"] + det["faux_ok"])} saisies sans oubli.</p>
<details open><summary>Exemples : saisie réelle et saisie générée ({COURANTE}) pour le même nom</summary>
{table(["Mode", "Nom source", "Réel", "Généré", "Perturbations du généré"], ex)}</details>
</section>"""


def comparaison(jeu: str, prec: dict, courant: dict) -> str:
    """Tableau v0.1 / v0.2 / v0.3 sur les notes globales et le risque du fuzzy seul."""
    lignes = []
    for ver, x in [*prec.items(), (COURANTE, courant)]:
        g = x.get("global", {})
        ra = x.get("risque_approche", {}).get("TOTAL", {})
        lignes.append([f"<b>{e(ver)}</b>", nb(g.get("n")), pct(g.get("ideal")), pct(g.get("sur")), cell_sil(g),
                       nb(g.get("dont_collision_exacte")) if "dont_collision_exacte" in g else "· (non séparé)",
                       f"{pct(ra.get('risque_pct'), 2)} ({nb(ra.get('silencieux'))} / {nb(ra.get('acceptes'))})",
                       nb(g.get("trop_confiant"))])
    return table([f"Version ({jeu})", "Cas", "Idéal", "Sûr", "Silencieux", "dont collision exacte",
                  "Fuzzy seul (silencieux / acceptés)", "Trop confiant"], lignes)


def table_risque(ra: dict) -> str:
    return table(["Famille", "Acceptés", "Silencieux", "Part"],
                 [[e(k), nb(v["acceptes"]), nb(v["silencieux"]), pct(v["risque_pct"], 2)] for k, v in ra.items()])


def section_banc(d: dict, prec: dict) -> str:
    b = d["banc"]
    return f"""
<section id="banc"><h2>3. Moteur actuel à 0,88 sur le banc</h2>
<p>Moteur : exact, puis index négatif (sans les absents inconnus), puis Jaro-Winkler à seuil fixe 0,88 et écart 0,03,
<b>provisoire</b>. Notation du modèle § 8 : <i>idéal</i> = réponse attendue exacte ; <i>sûr</i> = idéal ou réponse prudente
(ambiguous qui contient une entité attendue, unknown) ; <i>silencieux</i> = resolved hors de l'ensemble attendu ou sur
un absent ; <i>collision exacte</i> = silencieux d'une saisie fautive tombée exactement sur un autre nom réel (résolue
avant l'approché) ; <i>trop confiant</i> = resolved vers une seule des entités d'un attendu ambiguous.
« Fuzzy seul » : part d'erreurs silencieuses parmi les termes acceptés par l'approché seul, collisions exclues.</p>
<h3>v0.1 / v0.2 / {COURANTE}</h3>
{comparaison("banc", {k: x.get("banc", {}) for k, x in prec.items()}, b)}
<p class="note">Les versions n'ont ni les mêmes graines ni la même réponse attendue (voisins bornés à 2 depuis v0.2) :
la comparaison mesure l'effet du modèle entier, pas d'un seul changement.</p>
<h3>Par famille</h3>{table(ENTETES_TAUX, lignes_taux(b["par_famille"]))}
<h3>Par nature</h3>{table(ENTETES_TAUX, lignes_taux(b["par_nature"]))}
<h3>Par mode et par indice de type</h3>{table(ENTETES_TAUX, lignes_taux(b["par_mode"]) + lignes_taux(b["par_indice"]))}
<h3>Termes acceptés par l'approché seul</h3>{table_risque(b["risque_approche"])}
{bloc_diagnostic(b["diagnostic"], "banc")}
</section>"""


NOMS_DIAG = {"collision_exacte": "Collisions exactes (saisie fautive = autre nom réel)",
             "present_confondu": "Présents confondus par l'approché (resolved vers une autre entité)",
             "present_trop_confiant": "Présents trop confiants (une seule des entités attendues)",
             "absent_accepte": "Absents acceptés à tort (resolved)"}


def bloc_diagnostic(diag: dict, jeu: str) -> str:
    resume, blocs = [], []
    for k, titre in NOMS_DIAG.items():
        c = diag.get(k)
        if c is None:
            continue
        resume.append([e(titre), nb(c["n"]), nb(c["avec_voisin_a_une_faute"]),
                       ", ".join(f"{f} {n}" for f, n in c["par_famille"].items()) or "·",
                       ", ".join(f"{f} {n}" for f, n in c["par_sous_nature"].items()) or "·",
                       ", ".join(f"{f} {n}" for f, n in c["par_mode"].items()) or "·"])
        ex = [[e(x["case_id"]), e(x["famille"]), e(x["mode"]), f"<b>{e(x['terme'])}</b>", e(x["nom_source"]),
               e(x["perturbations"] + (" ; oubli " + x["mots_oublies"] if x["mots_oublies"] else "")),
               e(x["indice"] or "·"), e(x["attendu"] + " " + " | ".join(x["attendu_labels"])),
               e(" | ".join(x["moteur_labels"])), f"{x['score']:.3f}".replace(".", ",") if x["score"] else "·",
               e(x["voisin_a_une_faute"] or "·")] for x in c["exemples"]]
        if ex:
            blocs.append(f"<details><summary>{e(titre)} ({jeu}) : {len(ex)} exemples</summary>"
                         + table(["Cas", "Famille", "Mode", "Tapé", "Nom source", "Fautes", "Indice", "Attendu",
                                  "Moteur", "κ", "Voisin à 1 faute"], ex, "petit") + "</details>")
    return (f"<h3>Diagnostic par famille et par nature ({jeu})</h3>"
            + table(["Catégorie", "Cas", "Avec voisin à 1 faute", "Par famille", "Par sous-nature", "Par mode"], resume)
            + f"<p class='note'>Absents répondus ambiguous (ni sûrs ni silencieux) : {nb(diag['absent_ambigu']['n'])}. "
              "Absents par sous-nature dans le jeu : "
            + ", ".join(f"{k} {nb(n)}" for k, n in diag["absents_total"].items()) + ".</p>" + "".join(blocs))


def section_diagnostic(d: dict, prec: dict) -> str:
    a = d["analyse"]
    diags = [x.get("analyse", {}).get("diagnostic", {}) for x in prec.values()] + [a["diagnostic"]]
    comp = [[e(NOMS_DIAG.get(k, k))] + [nb(dg[k]["n"]) if k in dg else "· (non séparé)" for dg in diags]
            for k in NOMS_DIAG]
    comp.append(["Absents répondus ambiguous"] + [nb(dg.get("absent_ambigu", {}).get("n")) for dg in diags])
    return f"""
<section id="diagnostic"><h2>4. Diagnostic des erreurs à 0,88 (jeu d'analyse)</h2>
<p>{nb(a["diagnostic"]["presents_total"])} présents fautifs et {nb(sum(a["diagnostic"]["absents_total"].values()))} absents,
tous arrivés jusqu'à l'étape approchée. « Voisin à 1 faute » : un autre nom réel du même type est à une seule faute
(OSA ≤ 1) du terme tapé (pour un absent : du type de l'entité acceptée).</p>
<h3>v0.1 / v0.2 / {COURANTE}</h3>
{comparaison("analyse", {k: x.get("analyse", {}) for k, x in prec.items()}, a)}
{table(["Catégorie", *prec, COURANTE], comp)}
<p class="note">En v0.1, les collisions exactes étaient comptées dans les présents confondus ou les absents acceptés.
Le jeu d'analyse ne garde que des saisies qui atteignent l'étape approchée : il ne contient donc aucune collision exacte
par construction. 10 exemples tirés au hasard par catégorie sont dépliables en bas de section.</p>
<h3>Termes acceptés par l'approché seul (risque observé de 0,88, collisions exclues)</h3>{table_risque(a["risque_approche"])}
<h3>Notes par famille</h3>{table(ENTETES_TAUX, lignes_taux(a["par_famille"]))}
<h3>Notes par sous-nature</h3>{table(ENTETES_TAUX, lignes_taux(a["par_nature"]))}
{bloc_diagnostic(a["diagnostic"], "analyse")}
</section>"""


def section_reel(d: dict, prec: dict) -> str:
    r = d["reel_moteur"]
    blocs = []
    for cle, titre in (("sans_indice", "sans indice de type"), ("avec_indice", "avec l'indice du type de l'entité")):
        x = r[cle]
        app = ", ".join(f"{m} : {v['silencieux']} silencieuses sur {v['acceptes']} acceptées, "
                        f"{v.get('collisions_exactes', 0)} collision(s) exacte(s)"
                        for m, v in x["approche_seule"].items())
        vers = [(k, p.get("reel_moteur", {}).get(cle, {}).get("par_mode", {}).get("TOTAL", {})) for k, p in prec.items()]
        vers.append((COURANTE, x["par_mode"].get("TOTAL", {})))
        cmp = " ; ".join(f"{k} : idéal {pct(t.get('ideal'))}, sûr {pct(t.get('sur'))}, {nb(t.get('silencieux'))} silencieuse(s)"
                         for k, t in vers)
        blocs.append(f"<h3>{titre}</h3>" + table(ENTETES_TAUX, lignes_taux(x["par_mode"]))
                     + f"<p class='note'>Approché seul : {e(app)}. Par version de la réponse attendue : {e(cmp)}.</p>")
    err = [[e(x["mode"]), e(x["nom"]), f"<b>{e(x['saisie'])}</b>", e(x["note"]),
            e(x["attendu"] + " " + " | ".join(x["attendu_labels"])), e(" | ".join(x["moteur_labels"])),
            f"{x['score']:.3f}".replace(".", ",") if x["score"] else "·"] for x in r["erreurs_sans_indice"]]
    lib = [[e(x["mode"]), f"<b>{e(x['saisie'])}</b>", e(x["statut"]), e(x["etape"]), e(" | ".join(x["labels"])),
            f"{x['score']:.3f}".replace(".", ",") if x["score"] else "·"] for x in r["libres"]]
    return f"""
<section id="reel"><h2>5. Moteur à 0,88 sur l'échantillon réel</h2>
<p>{nb(d["reel"]["n"])} saisies d'entités ({", ".join(f"{k} {v}" for k, v in d["reel"]["par_mode"].items())}),
réponse attendue selon le § 8 du modèle (mots oubliés repérés par alignement, voisins bornés à 2). Index négatif
complet. {nb(sum(d["reel"]["vides"].values()))} saisies vides ou « ? » sont exclues. Les saisies réelles ne changent
pas d'une version à l'autre : seule la réponse attendue a changé (en v0.2).</p>
{"".join(blocs)}
<details open><summary>Erreurs silencieuses, collisions exactes et réponses trop confiantes (sans indice)</summary>
{table(["Mode", "Nom", "Saisie", "Note", "Attendu", "Moteur", "κ"], err)}</details>
<details><summary>Termes libres (hors catalogue présumé) : {len(lib)}</summary>
{table(["Mode", "Saisie", "Statut", "Étape", "Entités", "κ"], lib)}</details>
</section>"""


def section_sensibilite(d: dict, prec: dict) -> str:
    s = d["sensibilite"]
    lignes = []
    for jeu in ("banc", "analyse"):
        variantes = [("0,20", "0,10 (central)", [p.get(jeu, {}) for p in prec.values()] + [d[jeu]])]
        for cle, v in sorted(s.items()):
            if v["jeu"] == jeu:
                variantes.append((f"{v['part_entendu']:.2f}".replace(".", ","), f"{v['part_absents']:.2f}".replace(".", ","),
                                  [p.get("sensibilite", {}).get(cle, {}) for p in prec.values()] + [v]))
        for ent, ab, xs in variantes:
            gb = xs[-1]["global"]
            sil = [cell_sil(x.get("global", {})) if x.get("global") else "·" for x in xs]
            ris = [pct(x.get("risque_approche", {}).get("TOTAL", {}).get("risque_pct"), 2) for x in xs]
            lignes.append([f"<b>{jeu}</b>" if "central" in ab else jeu, ent, ab, nb(gb["n"]), pct(gb["ideal"]),
                           pct(gb["sur"]), *sil, nb(gb.get("dont_collision_exacte")), *ris])
    return f"""
<section id="sensibilite"><h2>6. Sensibilité</h2>
<p>Mêmes graines, une seule valeur changée à la fois : part d'« entendu » 0,10 / 0,20 / 0,40, part d'absents
0,05 / 0,10 / 0,25 (<code>--part-entendu</code>, <code>--part-absents</code>, sans modifier le YAML).
« Fuzzy seul » : part d'erreurs silencieuses parmi les termes acceptés par l'approché seul (collisions exclues).</p>
{table(["Jeu", "Entendu", "Absents", f"Cas {COURANTE}", f"Idéal {COURANTE}", f"Sûr {COURANTE}",
        *[f"Silencieux {k}" for k in [*prec, COURANTE]], f"dont collision {COURANTE}",
        *[f"Fuzzy seul {k}" for k in [*prec, COURANTE]]], lignes)}
</section>"""


# ── calibration SGR (R-RES-10) et comparaison A / B / C ──────────────────────────────────────────

NOMS_SCENARIOS = {"central": "modèle v0.3", "pessimiste": "pessimiste (v0.2)"}
COULEUR_SCENARIO = {"central": "var(--s1)", "pessimiste": "var(--s2)"}


def courbe_svg(famille: str, scen: dict, r_etoile: float, final) -> str:
    """Risque-couverture d'une famille : borne haute B* (trait plein) et risque observé k/n (pointillé) en
    fonction de la couverture, un point par θ ; ligne horizontale r* ; θ retenu (ou meilleur point) marqué."""
    W, H, G, D, Hh, B = 300, 190, 40, 10, 12, 30
    ymax = 10.0                                   # % : au-delà, les points sont posés sur le bord (écrêtés)
    x = lambda c: G + (W - G - D) * c
    y = lambda v: Hh + (H - Hh - B) * (1 - min(v, ymax) / ymax)
    el = [f'<line x1="{G}" y1="{y(0)}" x2="{W - D}" y2="{y(0)}" class="axe"/>',
          f'<line x1="{G}" y1="{y(r_etoile * 100):.1f}" x2="{W - D}" y2="{y(r_etoile * 100):.1f}" class="cible"/>',
          f'<text x="{W - D}" y="{y(r_etoile * 100) - 3:.1f}" text-anchor="end" class="t">r* {pct(r_etoile * 100)}</text>']
    for v in (0, 5, 10):
        el.append(f'<text x="{G - 4}" y="{y(v) + 3:.1f}" text-anchor="end" class="t">{v} %</text>')
    for c in (0, 0.5, 1):
        el.append(f'<text x="{x(c):.1f}" y="{H - B + 14}" text-anchor="middle" class="t">{int(c * 100)} %</text>')
    el.append(f'<text x="{(G + W - D) / 2}" y="{H - 4}" text-anchor="middle" class="t">couverture du fuzzy</text>')
    for sc, d in scen.items():
        pts = d["courbe"]
        col = COULEUR_SCENARIO.get(sc, "currentColor")
        borne = " ".join(f"{x(p['couverture']):.1f},{y(100 * p['borne']):.1f}" for p in pts if p["n"])
        obs = " ".join(f"{x(p['couverture']):.1f},{y(100 * p['risque_observe']):.1f}" for p in pts if p["n"])
        if borne:
            el.append(f'<polyline points="{borne}" fill="none" stroke="{col}" stroke-width="2"/>')
        if obs:
            el.append(f'<polyline points="{obs}" fill="none" stroke="{col}" stroke-width="1.5" stroke-dasharray="3 3"/>')
        c = d["choix"]
        mp = c if not c["desactive"] else c["meilleur_point"]
        if mp.get("theta") is not None and mp.get("n"):
            cx, cy = x(mp["couverture"]), y(100 * mp["borne"])
            el.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{col}" stroke="var(--bg)" stroke-width="2">'
                      f'<title>{e(NOMS_SCENARIOS.get(sc, sc))} : θ {mp["theta"]:.2f}, n {mp["n"]}, k {mp["k"]}, '
                      f'borne {pct(100 * mp["borne"], 2)}, couverture {pct(100 * mp["couverture"])}</title></circle>')
            el.append(f'<text x="{cx + 6:.1f}" y="{cy - 6:.1f}" class="t">θ {mp["theta"]:.2f}</text>')
    titre = f"{famille} : " + ("désactivé" if final is None else f"θ {final:.2f}")
    return (f'<figure class="mini"><figcaption>{e(titre)}</figcaption><svg viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="{e(titre)} ; borne haute et risque observé selon la couverture">{"".join(el)}</svg></figure>')


def texte_volume(v: dict) -> str:
    if v.get("theta") is None:
        return e(v.get("raison", "·"))
    pp = v.get("premier_palier") or {}
    fx = lambda x: str(round(x, 1)).replace(".", ",")
    return (f"passer {pp.get('theta', 0):.2f} : ≈ {nb(pp.get('saisies_approche_necessaires'))} saisies (× {fx(pp.get('facteur', 1))}) ; "
            f"atteindre θ {v['theta']:.2f} (taux observé {pct(100 * v['taux_observe'], 2)}) : ≈ "
            f"{nb(v['saisies_approche_necessaires'])} saisies passées par l'approché (× {fx(v['facteur'])})")


def section_calibration(cal: dict, comp: dict) -> str:
    p = cal["parametres"]
    r_etoile, delta = p["r_etoile"], p["delta"]
    lignes = []
    for f, final in cal["familles"].items():
        for sc, d in cal["scenarios"].items():
            fd = d["familles"][f]
            c = fd["choix"]
            ech = c.get("premier_echec")
            txt_ech = (f"θ {ech['theta']:.2f} (n {nb(ech['n'])}, k {nb(ech['k'])}, borne {pct(100 * ech['borne'], 2)})"
                       if ech else "aucun")
            if c["desactive"]:
                lignes.append([e(f), e(NOMS_SCENARIOS.get(sc, sc)), nb(fd["saisies_approche"]),
                               "<span class='mal'>désactivé</span>", "·", "·", "·", "·", txt_ech,
                               texte_volume(fd["volume_necessaire"])])
            else:
                lignes.append([e(f), e(NOMS_SCENARIOS.get(sc, sc)), nb(fd["saisies_approche"]), f"<b>{c['seuil']:.2f}</b>",
                               nb(c["n"]), nb(c["k"]), pct(100 * c["borne"], 2), pct(100 * c["couverture"]), txt_ech,
                               texte_volume(fd["volume_necessaire"])])
        lignes.append([f"<b>{e(f)}</b>", "<b>seuil final</b>", "", "<b>désactivé</b>" if final is None else f"<b>{final:.2f}</b>",
                       "", "", "", "", "", ""])
    n_min = math.log(1 / delta) / r_etoile
    courbes = "".join(courbe_svg(f, {sc: d["familles"][f] for sc, d in cal["scenarios"].items()}, r_etoile, final)
                      for f, final in cal["familles"].items())
    leg = "".join(f'<span><i style="background:{COULEUR_SCENARIO[sc]}"></i>{e(NOMS_SCENARIOS[sc])}</span>'
                  for sc in cal["scenarios"])
    comptes = " ; ".join(f"{NOMS_SCENARIOS.get(sc, sc)} ({nb(d.get('saisies'))} saisies) : "
                         f"{nb(d['comptes'].get('approche'))} passées par l'approché, "
                         f"{nb(d['comptes'].get('ambigues_hors_n', 0))} répondues ambiguous (hors de n), "
                         f"{nb(d['comptes'].get('familles_melangees', 0))} écartées (noms de plusieurs familles), "
                         f"{nb(d['comptes'].get('hors_approche', 0))} arrêtées avant"
                         for sc, d in cal["scenarios"].items())
    volumes = " ; ".join(f"{NOMS_SCENARIOS.get(sc, sc)} : " + ", ".join(f"{f} {nb(v)}" for f, v in d.get("presents_par_famille", {}).items())
                         for sc, d in cal["scenarios"].items())
    return f"""
<section id="calibration"><h2>7. Calibration des seuils par famille (R-RES-10)</h2>
<p>Garantie de risque sélectif (Geifman et El-Yaniv, 2017) : au plus r* = {pct(100 * r_etoile, 1)} d'erreurs silencieuses
parmi les noms que le fuzzy résout, avec une confiance de {pct(100 * (1 - delta), 0)}. <b>n</b> = saisies que le fuzzy
résout (resolved) ; un ambiguous n'est ni un choix ni une perte et sort de n ; <b>k</b> = pertes parmi elles.</p>
<p>Choix du seuil par <b>test en séquence fixe</b> (Angelopoulos et al., 2021, « Learn then Test », arXiv 2110.01052) :
θ testés dans un ordre fixé à l'avance, de {p['grille'][-1]:.2f} à {p['grille'][0]:.2f} ; chacun au niveau δ entier
({pct(100 * delta, 0)}) avec la borne binomiale exacte ; il passe si B*(k, n, δ) ≤ r* ; arrêt au premier échec, θ retenu =
le dernier qui a passé ; si {p['grille'][-1]:.2f} échoue, approché désactivé. Calcul sur les deux jeux de certification,
une fois chacun, en comptes agrégés seulement ; seuil final = le plus strict des deux. Écart inchangé
({str(p['ecart']).replace('.', ',')}). Seuils écrits dans <code>spec/seuils_fuzzy.yaml</code>.</p>
<p class="note">{e(comptes)}.</p>
<p class="note">Saisies fautives par famille dans les jeux de certification (cible 30 000 par famille et 110 000 en
géographie, sans plafond de cas par nom ; un terme présent dans le jeu d'analyse en est retiré) :
{e(volumes)}.</p>
<p><b>Volume minimal</b> : même sans aucune perte, un θ ne passe qu'avec au moins ln(1/δ) / r* ≈ {nb(round(n_min))} noms
résolus ; la séquence commençant à {p['grille'][-1]:.2f}, c'est d'abord le nombre de noms résolus au seuil le plus strict
qui compte. « Volume nécessaire » : estimation, si les taux d'erreur observés se maintiennent, en saisies de la famille passées par
l'approché (et facteur par rapport au jeu actuel) : pour passer le premier palier ({p['grille'][-1]:.2f}), qui seul
débloque la séquence, puis pour atteindre le θ le plus permissif dont tous les θ supérieurs ont un taux observé sous r*
(ce volume explose quand le taux observé approche r*).</p>
{table(["Famille", "Scénario", "Saisies passées par l'approché", "θ retenu", "n résolus", "k pertes", "Borne B*",
        "Couverture", "Premier échec", "Volume nécessaire estimé"], lignes)}
<h3>Courbes risque-couverture</h3>
<p class="note">Un point par θ de la grille, de droite (θ = {p['grille'][0]:.2f}, couverture maximale) à gauche. Trait plein :
borne haute B* ; pointillé : risque observé k/n ; ligne fine : r*. Le point marqué est le θ retenu, ou, pour une famille
désactivée, le meilleur point (borne la plus basse), donné pour information. Axe vertical écrêté à 10 %.</p>
<div class="leg">{leg}<span>trait plein : borne B*</span><span>pointillé : risque observé</span></div>
<div class="minis">{courbes}</div>
{section_comparaison(comp)}
</section>"""


NOMS_JEUX = {"banc": "banc (v0.3)", "banc_pessimiste": "banc pessimiste", "reel_sans_indice": "échantillon réel, sans indice",
             "reel_avec_indice": "échantillon réel, avec indice", "banc_absents_0.05": "banc, absents 5 %",
             "banc_absents_0.25": "banc, absents 25 %", "analyse_absents_0.05": "analyse, absents 5 %",
             "analyse_absents_0.25": "analyse, absents 25 %"}


def lignes_abc(jeux: dict, cle_groupe=None) -> list:
    out = []
    for nom, cfg in jeux.items():
        for k, m in cfg.items():
            g = m["global"] if cle_groupe is None else m["par_famille"].get(cle_groupe)
            if not g or not g.get("n"):
                continue
            out.append([e(NOMS_JEUX.get(nom, nom)) if cle_groupe is None else e(cle_groupe), f"<b>{k}</b>", nb(g["n"]),
                        pct(g["ideal"]), pct(g["sur"]), cell_sil(g), nb(g["dont_collision_exacte"]),
                        pct(g["couverture_fuzzy"]), pct(g["risque_fuzzy_pct"], 2) + f" ({nb(g['silencieux_fuzzy'])} / {nb(g['acceptes_fuzzy'])})"])
    return out


ENTETES_ABC = ["Jeu", "Config.", "Cas", "Idéal", "Sûr", "Silencieux", "dont collision exacte", "Couverture du fuzzy",
               "Risque du fuzzy seul"]


def table_c_par_famille(comp: dict, seuils: dict) -> str:
    """Pour C : ce que chaque seuil rattrape, par famille (idéal A → C, couverture du fuzzy, erreurs silencieuses)."""
    lignes = []
    for nom in ("banc", "banc_pessimiste", "reel_sans_indice"):
        jeu = comp["jeux"].get(nom)
        if not jeu:
            continue
        for f in sorted(jeu["C"]["par_famille"]):
            a, b, c = jeu["A"]["par_famille"].get(f, {}), jeu["B"]["par_famille"].get(f, {}), jeu["C"]["par_famille"][f]
            if not c.get("n"):
                continue
            t = seuils.get(f, "·")
            lignes.append([e(NOMS_JEUX.get(nom, nom)), e(f), "désactivé" if t is None else (f"{t:.2f}" if t != "·" else "·"),
                           nb(c["n"]), pct(a.get("ideal")), pct(c["ideal"]), ecart(a.get("ideal"), c["ideal"]),
                           pct(b.get("ideal")), pct(c["couverture_fuzzy"]), cell_sil(c),
                           pct(c["risque_fuzzy_pct"], 2) + f" ({nb(c['silencieux_fuzzy'])} / {nb(c['acceptes_fuzzy'])})"])
    return table(["Jeu", "Famille", "θ (C)", "Cas", "Idéal A", "Idéal C", "C − A (points)", "Idéal B", "Couverture du fuzzy (C)",
                  "Silencieux (C)", "Risque du fuzzy seul (C)"], lignes)


def section_comparaison(comp: dict) -> str:
    pol = " ; ".join(f"<b>{k}</b> = {e(v)}" for k, v in comp["politiques"].items())
    familles = sorted({f for cfg in comp["jeux"].values() for m in cfg.values() for f in m["par_famille"]})
    blocs = []
    for nom in ("banc", "banc_pessimiste"):
        if nom in comp["jeux"]:
            lignes = [l for f in familles for l in lignes_abc({nom: comp["jeux"][nom]}, f)]
            blocs.append(f"<details><summary>Par famille : {e(NOMS_JEUX[nom])}</summary>"
                         + table(["Famille"] + ENTETES_ABC[1:], lignes) + "</details>")
    return f"""
<h3>Comparaison A / B / C (mesure « avant corrections »)</h3>
<p>{pol}. Les jeux de certification ne sont jamais évalués ici. « Couverture du fuzzy » : part des saisies passées par
l'étape approchée que le fuzzy résout (un ambiguous n'en fait pas partie) ; « risque du fuzzy seul » : erreurs silencieuses
parmi ces saisies résolues.</p>
{table(ENTETES_ABC, lignes_abc(comp["jeux"]))}
<h3>C par famille : ce que chaque seuil rattrape</h3>
<p class="note">Idéal de C comparé à A (exact seul) et à B (0,88), couverture du fuzzy sous le seuil calibré de la famille.</p>
{table_c_par_famille(comp, comp.get("seuils_c", {}))}
{"".join(blocs)}"""


CSS = """
:root{--bg:#fcfcfb;--fg:#0b0b0b;--fg2:#52514e;--ligne:#e4e3df;--zebre:#f4f3f0;--s1:#2a78d6;--s0:#a3a29b;--s3:#8c6bd1;--s2:#eb6834;--mal:#d03b3b;--ok:#1b8a5a;--code:#efeeea}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#1a1a19;--fg:#f0efec;--fg2:#c3c2b7;--ligne:#383835;--zebre:#222220;--s1:#3987e5;--s0:#6f6e68;--s3:#9d80e0;--s2:#d95926;--mal:#e66767;--ok:#3fb27f;--code:#2a2a28}}
:root[data-theme="dark"]{--bg:#1a1a19;--fg:#f0efec;--fg2:#c3c2b7;--ligne:#383835;--zebre:#222220;--s1:#3987e5;--s0:#6f6e68;--s3:#9d80e0;--s2:#d95926;--mal:#e66767;--ok:#3fb27f;--code:#2a2a28}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 64px}h1{font-size:1.6rem;line-height:1.25;margin:.2em 0 .4em}
h2{font-size:1.25rem;margin:2.2em 0 .5em;padding-top:.6em;border-top:1px solid var(--ligne)}h3{font-size:1.02rem;margin:1.6em 0 .4em}
.eyebrow{color:var(--fg2);font-size:.85rem;text-transform:uppercase;letter-spacing:.06em}.lede{color:var(--fg2);max-width:70ch}
p,li{max-width:80ch}.note{color:var(--fg2);font-size:.9rem}code{background:var(--code);padding:0 .3em;border-radius:3px;font-size:.88em}
.tw{overflow-x:auto;margin:.6em 0}table{border-collapse:collapse;font-size:.88rem;min-width:100%}
th,td{border-bottom:1px solid var(--ligne);padding:.35em .6em;text-align:left;vertical-align:top}th{color:var(--fg2);font-weight:600}
tbody tr:nth-child(even){background:var(--zebre)}td{font-variant-numeric:tabular-nums}table.petit{font-size:.8rem}
.mal{color:var(--mal);font-weight:600}details{margin:.8em 0}summary{cursor:pointer;color:var(--fg2)}
nav a{color:var(--fg2);margin-right:1em;font-size:.9rem}.cles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:1em 0}
.cle{border:1px solid var(--ligne);border-radius:6px;padding:10px 12px}.cle b{display:block;font-size:1.35rem}.cle span{color:var(--fg2);font-size:.85rem}
.barres{margin:.8em 0;max-width:640px}.barres figcaption{color:var(--fg2);font-size:.88rem;margin-bottom:.3em}
.bl{display:grid;grid-template-columns:3em 1fr;gap:2px 8px;margin-bottom:8px}.bk{grid-row:span var(--n,2);align-self:center;color:var(--fg2)}
.bb{display:flex;align-items:center;gap:6px;height:14px}.bar{height:12px;border-radius:0 4px 4px 0;min-width:1px}
.s1{background:var(--s1)}.s0{background:var(--s0)}.s3{background:var(--s3)}.s2{background:var(--s2)}.ok{color:var(--ok);font-weight:600}.bv{font-size:.8rem;color:var(--fg2);white-space:nowrap}
.minis{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px 20px;margin:.6em 0}
.mini{margin:0}.mini figcaption{font-size:.88rem;color:var(--fg2);margin-bottom:2px}.mini svg{width:100%;height:auto;color:var(--fg2)}
.mini .axe{stroke:var(--ligne);stroke-width:1}.mini .cible{stroke:var(--mal);stroke-width:1;stroke-dasharray:4 3}
.mini .t{font-size:10px;fill:var(--fg2)}
.leg{display:flex;flex-wrap:wrap;gap:16px;font-size:.88rem;color:var(--fg2)}.leg i{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:6px;vertical-align:-1px}
"""


def page(d: dict, prec: dict, cal: dict, comp: dict, af: dict) -> str:
    b, a = d["banc"]["global"], d["analyse"]["global"]
    ra = d["analyse"]["risque_approche"].get("TOTAL", {})
    rb = d["banc"]["risque_approche"].get("TOTAL", {})
    reel = d["reel_moteur"]["sans_indice"]["par_mode"].get("TOTAL", {})
    avant = ", ".join(f"{k} : {pct(p.get('banc', {}).get('global', {}).get('silencieux_pct'), 2)}" for k, p in prec.items())
    cles = [(f"{nb(b['silencieux'])} / {nb(b['n'])}",
             f"erreurs silencieuses sur le banc ({pct(b['silencieux_pct'], 2)} ; {avant}), "
             f"dont {nb(b.get('dont_collision_exacte'))} collision(s) exacte(s)"),
            (pct(rb.get("risque_pct"), 2), f"risque du fuzzy seul sur le banc ({nb(rb.get('silencieux'))} / {nb(rb.get('acceptes'))})"),
            (pct(ra.get("risque_pct"), 2), f"risque du fuzzy seul sur l'analyse ({nb(ra.get('silencieux'))} / {nb(ra.get('acceptes'))})"),
            (f"{nb(reel.get('silencieux'))} / {nb(reel.get('n'))}",
             f"erreurs silencieuses sur l'échantillon réel, dont {nb(reel.get('dont_collision_exacte'))} collision(s) exacte(s)")]
    tuiles = "".join(f'<div class="cle"><b>{v}</b><span>{e(t)}</span></div>' for v, t in cles)
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Modèle de saisie</title><style>{CSS}{rapport_familles.CSS}</style></head><body><main>
<div class="eyebrow">POC Mécanova · entity resolution · moteur à seuil fixe 0,88 (provisoire) · modèle de saisie {COURANTE} (figé)</div>
<h1>Modèle de saisie {COURANTE} : jeux générés, encadrement du réel, mesures du moteur à 0,88</h1>
<p class="lede">Les jeux de test viennent d'un modèle de saisie explicite (<code>spec/modele_saisie.yaml</code>,
{COURANTE}, dernière version avant le travail sur le moteur). Ce rapport vérifie que {nb(d["reel"]["n"])} saisies réelles
tombent entre les générateurs v0.1 et {COURANTE}, puis mesure le moteur actuel sans rien régler : aucun seuil n'est
calculé et le jeu de certification n'est pas ouvert.</p>
<div class="cles">{tuiles}</div>
<p class="note">Analyse : {nb(a["n"])} cas, idéal {pct(a["ideal"])}, {nb(a["silencieux"])} silencieuses dont
{nb(a.get("dont_collision_exacte"))} collision(s) exacte(s).</p>
<nav><a href="#jeux">Jeux</a><a href="#verification">Vérification</a><a href="#banc">Banc</a><a href="#diagnostic">Diagnostic</a><a href="#reel">Réel</a><a href="#sensibilite">Sensibilité</a><a href="#calibration">Calibration</a><a href="#pourquoi">Familles sans seuil</a></nav>
{section_jeux(d, prec)}{section_verification(d, prec)}{section_banc(d, prec)}{section_diagnostic(d, prec)}{section_reel(d, prec)}{section_sensibilite(d, prec)}{section_calibration(cal, comp)}{rapport_familles.section_pourquoi(af, cal, borne_haute)}
<p class="note">Généré par <code>python -m engine.rapport_saisies</code> depuis <code>reports/mesure_saisies.json</code>
(<code>python -m engine.mesure_saisies</code>) et les mesures conservées des versions précédentes
(<code>reports/mesure_saisies_v0_1.json</code>, <code>reports/mesure_saisies_v0_2.json</code>) ; calibration et comparaison
depuis <code>reports/calibration.json</code> (<code>python -m engine.calibration</code>) et
<code>reports/comparaison_seuils.json</code> (<code>python -m engine.comparaison_seuils</code>).</p>
</main></body></html>"""


def main() -> int:
    console_utf8()
    if not ENTREE.exists():
        raise SystemExit(f"{ENTREE} introuvable : lancer python -m engine.mesure_saisies.")
    manquants = [str(p) for p in PRECEDENTES.values() if not p.exists()]
    if manquants:
        raise SystemExit(f"mesures des versions précédentes introuvables : {manquants}.")
    d = json.loads(ENTREE.read_text(encoding="utf-8"))
    prec = {k: json.loads(p.read_text(encoding="utf-8")) for k, p in PRECEDENTES.items()}
    for chemin, cmd in ((CALIBRATION, "engine.calibration"), (COMPARAISON, "engine.comparaison_seuils"),
                        (ANALYSE_FAMILLES, "engine.analyse_familles")):
        if not chemin.exists():
            raise SystemExit(f"{chemin} introuvable : lancer python -m {cmd}.")
    cal = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    comp = json.loads(COMPARAISON.read_text(encoding="utf-8"))
    af = json.loads(ANALYSE_FAMILLES.read_text(encoding="utf-8"))
    SORTIE.write_text(page(d, prec, cal, comp, af), encoding="utf-8")
    print(f"→ {SORTIE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
