"""
Rapport HTML autonome : reports/modele_saisie.html, depuis reports/mesure_saisies.json.

    python -m engine.rapport_saisies

Sections : jeux générés, vérification du générateur contre l'échantillon réel, moteur à 0,88 (seuil fixe
provisoire) sur le banc, diagnostic des erreurs sur le jeu d'analyse, échantillon réel, sensibilité.
Les écarts générateur / réel sont repérés automatiquement (ECART_SIGNALE points) ; les corrections du YAML
proposées sont écrites dans PROPOSITIONS : ce sont des propositions, le YAML n'est pas modifié.
"""
from __future__ import annotations

import html
import json
import sys

from engine.catalogue import ROOT, console_utf8

ENTREE = ROOT / "reports" / "mesure_saisies.json"
SORTIE = ROOT / "reports" / "modele_saisie.html"
ECART_SIGNALE = 5.0     # points de pourcentage

# Propositions de correction du YAML (rédigées après lecture de la vérification ; non appliquées).
PROPOSITIONS: list[tuple[str, str]] = [
    ("clavier.types : ajouter « espace »",
     "Environ 9 % des opérations réelles (lu et entendu) touchent un espace ou un trait d'union : « e-tron » → « etron », "
     "« rs 3 » → « rs3 », « bonnevoie » → « bonne voie ». Le générateur n'en produit presque jamais. Proposition : un "
     "type « espace » (fusionner deux mots, couper un mot, trait d'union → espace) d'environ 0,10, pris sur la substitution."),
    ("clavier.contraintes : substitution pas seulement voisine",
     "En mode lu, 16 % des opérations réelles sont des substitutions par une touche non voisine, contre 3 % de voisines ; le "
     "générateur fait l'inverse (21 % voisines, 5 % autres). Proposition : séparer substitution voisine (≈ 0,10) et "
     "substitution quelconque (≈ 0,15). À confirmer : 77 saisies lues seulement."),
    ("nombre_de_fautes.lu : plus de saisies à 3 fautes",
     "Saisies lues à distance 3 ou plus : 9,1 % réel contre 3,4 % généré ; à distance 2 : 6,5 % contre 12,7 %. "
     "Proposition : {0: 0.45, 1: 0.35, 2: 0.10, 3: 0.10}, plus proche de la mesure (10 % à 3 fautes) que l'arrondi actuel."),
    ("nombre_de_fautes.entendu : une classe « 4 et plus »",
     "Saisies entendues à distance 3 ou plus : 24,6 % réel contre 15,7 % généré. Proposition : {0: 0.30, 1: 0.25, 2: 0.20, "
     "3: 0.15, 4: 0.10}, ou laisser une règle phonétique réécrire un mot entier."),
    ("omissions_de_mots.probabilite : appliquée aux seuls types qui ont des omissions",
     "Mots oubliés : 14 % (lu) et 25 % (entendu) dans le réel, 6 % et 13 % dans le générateur. La probabilité du YAML est "
     "tirée pour toutes les saisies, mais seuls articles, clients et modèles ont une omission possible ; une partie de "
     "l'écart vient aussi du repérage (un mot très déformé à l'oreille compte comme oublié). Proposition : exprimer la "
     "probabilité par type (articles, clients, modèles), mesurée sur ces seuls types dans l'échantillon réel."),
    ("phonetique : motifs manquants en mode entendu",
     "Les règles du modèle n'expliquent qu'environ 11 % des opérations entendues réelles, contre 30 % des générées ; le "
     "réel est dominé par des insertions quelconques (33 %) : « mersedez », « fremin de merleback », « bosh ». "
     "Proposition : relire les saisies entendues pour ajouter des motifs (ch ↔ sh, mot coupé, consonne finale ajoutée), "
     "ou baisser phonetique de 0,80 à environ 0,60 en mode entendu."),
    ("attendu.regles.faute_avec_voisin : borner la distance",
     "Avec 3 fautes ou plus sur un nom court, « distance OSA ≤ celle du nom source » fait entrer des dizaines de noms "
     "(« rangie » pour Rongy : toutes les communes à 3 opérations). Une réponse juste du moteur devient alors "
     "« trop confiante ». Proposition : ne compter comme voisins que les noms à distance ≤ min(d, 2), ou à distance ≤ d "
     "ET au même score Jaro-Winkler à 0,03 près. Concerne 2 à 5 % des saisies fautives."),
]

e = html.escape


def pct(x, d=1):
    return "·" if x is None else f"{x:.{d}f} %".replace(".", ",")


def nb(x):
    return "·" if x is None else f"{x:,}".replace(",", " ")


def table(entetes, lignes, classes=None) -> str:
    th = "".join(f"<th>{e(h)}</th>" for h in entetes)
    corps = []
    for l in lignes:
        corps.append("<tr>" + "".join(f"<td>{c}</td>" for c in l) + "</tr>")
    return f'<div class="tw"><table class="{classes or ""}"><thead><tr>{th}</tr></thead><tbody>{"".join(corps)}</tbody></table></div>'


def lignes_taux(d: dict, nom_col="") -> list:
    out = []
    for k, v in d.items():
        if not v.get("n"):
            continue
        nom = f"<b>{e(k)}</b>" if k == "TOTAL" else e(k)
        sil = v["silencieux"]
        out.append([nom, nb(v["n"]), pct(v["ideal"]), pct(v["sur"]),
                    f'<span class="{"mal" if sil else ""}">{nb(sil)} ({pct(v["silencieux_pct"], 2)})</span>',
                    nb(v["trop_confiant"]), nb(v["incorrect"])])
    return out


ENTETES_TAUX = ["", "Cas", "Idéal", "Sûr", "Silencieux", "Trop confiant", "Incorrect"]


def barres(titre: str, reel: dict, gen: dict, cles) -> str:
    """Barres groupées réel / généré, valeurs écrites sur chaque barre."""
    lignes = []
    for k in cles:
        r, g = reel.get(k, 0) or 0, gen.get(k, 0) or 0
        lignes.append(
            f'<div class="bl"><span class="bk">{e(k)}</span><div class="bb">'
            f'<div class="bar s1" style="width:{r}%"></div><span class="bv">{pct(r)}</span></div>'
            f'<div class="bb"><div class="bar s2" style="width:{g}%"></div><span class="bv">{pct(g)}</span></div></div>')
    return f'<figure class="barres"><figcaption>{e(titre)}</figcaption>{"".join(lignes)}</figure>'


def section_jeux(d: dict) -> str:
    jeux = d["meta_jeux"]
    lignes = []
    for cle in ("banc", "analyse", "certif"):
        j = jeux.get(cle)
        if not j:
            continue
        pres = ", ".join(f"{f} {nb(n)}" for f, n in j["presents_par_famille"].items())
        absn = ", ".join(f"{k} {nb(n)}" for k, n in j["absents_par_sous_nature"].items())
        modes = ", ".join(f"{k} {nb(n)}" for k, n in j["modes"].items())
        lignes.append([f"<b>{cle}</b>", nb(j["graine"]), nb(j["cas"]), pres, absn, modes,
                       nb(j["absents_reportes_faute_de_stock"])])
    rejets = []
    for cle in ("banc", "analyse", "certif"):
        j = jeux.get(cle, {})
        for k, n in j.get("rejets", {}).items():
            rejets.append([cle, e(k), nb(n)])
    mots = ", ".join(f"{e(w)} ({pct(100 * f, 1)})" for w, f in d.get("mots_clients_frequents_hors_listes", [])) or "aucun"
    return f"""
<section id="jeux"><h2>1. Les jeux générés</h2>
<p>Trois jeux, tirés de <code>spec/modele_saisie.yaml</code> par <code>build/build_saisies.py</code>, chacun avec sa graine.
Le <b>banc</b> imite le trafic : il suit la répartition par famille du modèle et garde les saisies sans faute.
L'<b>analyse</b> sert à concevoir. La <b>certification</b> servira une seule fois, plus tard, à calculer un seuil :
ses erreurs ne sont pas ouvertes ici. Les deux jeux de calibration ne gardent que des saisies fautives qui
atteignent l'étape approchée, au plus 3 par nom, sans terme normalisé commun entre eux.</p>
{table(["Jeu", "Graine", "Cas", "Présents par famille", "Absents par sous-nature", "Modes", "Absents reportés"], lignes)}
<p class="note">« Absents reportés » : absents qui manquaient faute de stock (3 cas au plus par terme) et ont été
reportés sur les lieux hors périmètre, puis sur les noms recombinés. Pièces, véhicules, clients, marques, douane et
vocabulaire restent sous 3 000 dans l'analyse : plafond de 3 cas par nom (les articles partagent souvent le même
libellé) et exclusion des entités de la partition test.</p>
<details><summary>Saisies écartées pendant la génération</summary>{table(["Jeu", "Raison", "Nombre"], rejets)}</details>
<h3>Index négatif partagé en deux</h3>
<p>{nb(d["negatifs_retires"])} lieux de l'index négatif, tirés avec une graine fixe, sont écrits dans
<code>challenges/negatifs_retires.csv</code>. Pendant l'évaluation des jeux générés,
<code>engine/mesure_saisies.py · charger_catalogue_jeux</code> charge le catalogue normalement puis retire ces termes de
l'index négatif <b>en mémoire</b> : <code>catalog/negatifs.csv</code> n'est pas modifié, et le moteur en production
garde l'index complet. Les absents tirés de cette moitié (« lieu inconnu ») testent un lieu que personne n'a prévu ;
ceux de l'autre moitié (« lieu de l'index négatif ») testent l'index. L'échantillon réel est évalué avec l'index complet.</p>
<h3>Mots génériques des clients</h3>
<p>Mots présents dans plus de 1 % des noms de clients et absents des trois listes du modèle
(génériques, compléments familiaux, exclus) : {mots}.</p>
</section>"""


def section_verification(d: dict) -> str:
    v = d["verification"]
    blocs, ecarts = [], []
    for mode in ("lu", "entendu"):
        if mode not in v:
            continue
        r, g = v[mode]["reel"], v[mode]["genere"]
        cles = ["0", "1", "2", "3+"]
        blocs.append(f"<h3>Mode « {mode} » · {nb(r['n'])} saisies réelles, {nb(g['n'])} générées</h3>")
        blocs.append(barres(f"Distance OSA au nom source, après retrait des mots oubliés ({mode})",
                            r["distance"], g["distance"], cles))
        lignes = [["Mots oubliés", pct(r["mots_oublies_pct"]), pct(g["mots_oublies_pct"])],
                  ["Opérations par saisie", f"{r['fautes_par_saisie']}".replace(".", ","),
                   f"{g['fautes_par_saisie']}".replace(".", ",")]]
        for k in cles:
            lignes.insert(0 + cles.index(k), [f"Distance {k}", pct(r["distance"].get(k)), pct(g["distance"].get(k))])
            dlt = (g["distance"].get(k) or 0) - (r["distance"].get(k) or 0)
            if abs(dlt) >= ECART_SIGNALE:
                ecarts.append(f"mode {mode} : distance {k}, réel {pct(r['distance'].get(k))}, généré "
                              f"{pct(g['distance'].get(k))} ({'+' if dlt > 0 else ''}{dlt:.1f} points)".replace(".", ","))
        dlt = (g["mots_oublies_pct"] or 0) - (r["mots_oublies_pct"] or 0)
        if abs(dlt) >= ECART_SIGNALE:
            ecarts.append(f"mode {mode} : mots oubliés, réel {pct(r['mots_oublies_pct'])}, généré "
                          f"{pct(g['mots_oublies_pct'])}".replace(".", ","))
        blocs.append(table(["Indicateur", "Réel", "Généré"], lignes))
        tr, tg = dict(r["types"]), dict(g["types"])
        types = sorted(set(tr) | set(tg), key=lambda k: -(tr.get(k, 0) + tg.get(k, 0)))[:12]
        blocs.append(table(["Type de faute (part des opérations)", "Réel", "Généré"],
                           [[e(k), pct(tr.get(k)), pct(tg.get(k))] for k in types]))
        for k in types:
            dlt = tg.get(k, 0) - tr.get(k, 0)
            if abs(dlt) >= ECART_SIGNALE:
                ecarts.append(f"mode {mode} : « {k} », réel {pct(tr.get(k, 0))}, généré {pct(tg.get(k, 0))}".replace(".", ","))
    ex = [[e(x["mode"]), e(x["nom"]), f"<b>{e(x['reel'])}</b>", f"<b>{e(x['genere'])}</b>", e(x["perturbations"])]
          for x in v["exemples"]]
    det = v["detection_oublis_sur_genere"]
    prop = "".join(f"<li><b>{e(k)}</b> : {e(t)}</li>" for k, t in PROPOSITIONS) or "<li>aucune</li>"
    ec = "".join(f"<li>{e(x)}</li>" for x in ecarts) or "<li>aucun écart de 5 points ou plus</li>"
    return f"""
<section id="verification"><h2>2. Le générateur face à l'échantillon réel</h2>
<p>Mêmes indicateurs des deux côtés, calculés par les mêmes fonctions. Côté réel : les saisies de
<code>human/echantillon_reel/saisies_combinees.csv</code> (« oreille » = entendu, « mémoire » = lu), sans les saisies
vides ou « ? ». Côté généré : un <b>miroir</b>, c'est-à-dire les mêmes noms, dans le même mode, tapés 10 fois chacun par
le générateur. Les mots oubliés sont repérés par alignement de mots ; la distance est la distance OSA entre la saisie et
le nom source privé de ces mots ; les types de fautes viennent d'une décomposition en règles phonétiques du modèle
puis en opérations de clavier.</p>
<div class="leg"><span><i class="s1"></i>réel</span><span><i class="s2"></i>généré</span></div>
{"".join(blocs)}
<h3>Écarts de {pct(ECART_SIGNALE, 0)} ou plus</h3><ul>{ec}</ul>
<h3>Corrections du YAML proposées (non appliquées)</h3><ul>{prop}</ul>
<p class="note">Contrôle du repérage des mots oubliés, sur les saisies générées dont on connaît la vérité : oubli réel
repéré {nb(det["vrai_detecte"])}, manqué {nb(det["vrai_manque"])} ; faux oubli repéré {nb(det["faux_detecte"])} sur
{nb(det["faux_detecte"] + det["faux_ok"])} saisies sans oubli.</p>
<details open><summary>Exemples : saisie réelle et saisie générée pour le même nom</summary>
{table(["Mode", "Nom source", "Réel", "Généré", "Perturbations du généré"], ex)}</details>
</section>"""


def section_banc(d: dict) -> str:
    b = d["banc"]
    ra = b["risque_approche"]
    return f"""
<section id="banc"><h2>3. Moteur actuel à 0,88 sur le banc</h2>
<p>Moteur : exact, puis index négatif (sans les absents inconnus), puis Jaro-Winkler à seuil fixe 0,88 et écart 0,03,
<b>provisoire</b>. Notation du modèle § 8 : <i>idéal</i> = réponse attendue exacte ; <i>sûr</i> = idéal ou réponse
prudente (ambiguous qui contient une entité attendue, unknown) ; <i>silencieux</i> = resolved hors de l'ensemble attendu
ou sur un absent ; <i>trop confiant</i> = resolved vers une seule des entités d'un attendu ambiguous.</p>
{table(ENTETES_TAUX, lignes_taux({"TOTAL": b["global"]}))}
<h3>Par famille</h3>{table(ENTETES_TAUX, lignes_taux(b["par_famille"]))}
<h3>Par nature</h3>{table(ENTETES_TAUX, lignes_taux(b["par_nature"]))}
<h3>Par mode et par indice de type</h3>{table(ENTETES_TAUX, lignes_taux(b["par_mode"]) + lignes_taux(b["par_indice"]))}
<h3>Termes acceptés par l'approché seul</h3>
{table(["Famille", "Acceptés", "Silencieux", "Part"], [[e(k), nb(v["acceptes"]), nb(v["silencieux"]), pct(v["risque_pct"], 2)] for k, v in ra.items()])}
</section>"""


def section_diagnostic(d: dict) -> str:
    a = d["analyse"]
    diag = a["diagnostic"]
    noms = {"present_confondu": "Présents confondus (resolved vers une autre entité)",
            "present_trop_confiant": "Présents trop confiants (une seule des entités attendues)",
            "absent_accepte": "Absents acceptés à tort (resolved)"}
    resume = []
    blocs = []
    for k, titre in noms.items():
        c = diag[k]
        resume.append([e(titre), nb(c["n"]), nb(c["avec_voisin_a_une_faute"]),
                       ", ".join(f"{f} {n}" for f, n in c["par_famille"].items()) or "·",
                       ", ".join(f"{f} {n}" for f, n in c["par_sous_nature"].items()) or "·",
                       ", ".join(f"{f} {n}" for f, n in c["par_mode"].items()) or "·"])
        ex = [[e(x["case_id"]), e(x["famille"]), e(x["mode"]), f"<b>{e(x['terme'])}</b>", e(x["nom_source"]),
               e(x["perturbations"] + (" ; oubli " + x["mots_oublies"] if x["mots_oublies"] else "")),
               e(x["indice"] or "·"), e(x["attendu"] + " " + " | ".join(x["attendu_labels"])),
               e(" | ".join(x["moteur_labels"])), f"{x['score']:.3f}".replace(".", ",") if x["score"] else "·",
               e(x["voisin_a_une_faute"] or "·")] for x in c["exemples"]]
        blocs.append(f"<details><summary>{e(titre)} : {len(ex)} exemples</summary>"
                     + table(["Cas", "Famille", "Mode", "Tapé", "Nom source", "Fautes", "Indice", "Attendu",
                              "Moteur", "κ", "Voisin à 1 faute"], ex, "petit") + "</details>")
    ra = a["risque_approche"]
    return f"""
<section id="diagnostic"><h2>4. Diagnostic des erreurs à 0,88 (jeu d'analyse)</h2>
<p>{nb(diag["presents_total"])} présents fautifs et {nb(sum(diag["absents_total"].values()))} absents, tous arrivés jusqu'à
l'étape approchée. « Voisin à 1 faute » : un autre nom réel du même type est à une seule faute (OSA ≤ 1) du terme tapé
(pour un absent : du type de l'entité acceptée). Absents répondus ambiguous (ni sûrs ni silencieux) :
{nb(diag["absent_ambigu"]["n"])}.</p>
{table(["Catégorie", "Cas", "Avec voisin à 1 faute", "Par famille", "Par sous-nature", "Par mode"], resume)}
<h3>Termes acceptés par l'approché seul (risque observé de 0,88)</h3>
{table(["Famille", "Acceptés", "Silencieux", "Part"], [[e(k), nb(v["acceptes"]), nb(v["silencieux"]), pct(v["risque_pct"], 2)] for k, v in ra.items()])}
<h3>Notes par famille</h3>{table(ENTETES_TAUX, lignes_taux(a["par_famille"]))}
<h3>Notes par sous-nature</h3>{table(ENTETES_TAUX, lignes_taux(a["par_nature"]))}
{"".join(blocs)}
</section>"""


def section_reel(d: dict) -> str:
    r = d["reel_moteur"]
    blocs = []
    for cle, titre in (("sans_indice", "sans indice de type"), ("avec_indice", "avec l'indice du type de l'entité")):
        x = r[cle]
        app = ", ".join(f"{m} : {v['silencieux']} silencieuses sur {v['acceptes']} acceptées"
                        for m, v in x["approche_seule"].items())
        blocs.append(f"<h3>{titre}</h3>" + table(ENTETES_TAUX, lignes_taux(x["par_mode"]))
                     + f"<p class='note'>Approché seul : {e(app)}.</p>")
    err = [[e(x["mode"]), e(x["nom"]), f"<b>{e(x['saisie'])}</b>", e(x["note"]),
            e(x["attendu"] + " " + " | ".join(x["attendu_labels"])), e(" | ".join(x["moteur_labels"])),
            f"{x['score']:.3f}".replace(".", ",") if x["score"] else "·"] for x in r["erreurs_sans_indice"]]
    lib = [[e(x["mode"]), f"<b>{e(x['saisie'])}</b>", e(x["statut"]), e(x["etape"]), e(" | ".join(x["labels"])),
            f"{x['score']:.3f}".replace(".", ",") if x["score"] else "·"] for x in r["libres"]]
    return f"""
<section id="reel"><h2>5. Moteur à 0,88 sur l'échantillon réel</h2>
<p>{nb(d["reel"]["n"])} saisies d'entités ({", ".join(f"{k} {v}" for k, v in d["reel"]["par_mode"].items())}),
réponse attendue selon le § 8 du modèle (mots oubliés repérés par alignement). Index négatif complet.
{nb(sum(d["reel"]["vides"].values()))} saisies vides ou « ? » sont exclues.</p>
{"".join(blocs)}
<details open><summary>Erreurs silencieuses et réponses trop confiantes (sans indice)</summary>
{table(["Mode", "Nom", "Saisie", "Note", "Attendu", "Moteur", "κ"], err)}</details>
<details><summary>Termes libres (hors catalogue présumé) : {len(lib)}</summary>
{table(["Mode", "Saisie", "Statut", "Étape", "Entités", "κ"], lib)}</details>
</section>"""


def section_sensibilite(d: dict) -> str:
    s = d["sensibilite"]
    lignes = []
    centre = {"banc": d["banc"], "analyse": d["analyse"]}
    for jeu in ("banc", "analyse"):
        g, ra = centre[jeu]["global"], centre[jeu]["risque_approche"].get("TOTAL", {})
        lignes.append([f"<b>{jeu}</b>", "0,20", "0,10 (central)", nb(g["n"]), pct(g["ideal"]), pct(g["sur"]),
                       f"{nb(g['silencieux'])} ({pct(g['silencieux_pct'], 2)})", pct(ra.get("risque_pct"), 2)])
        for cle, v in sorted(s.items()):
            if v["jeu"] != jeu:
                continue
            g, ra = v["global"], v["risque_approche"].get("TOTAL", {})
            lignes.append([jeu, f"{v['part_entendu']:.2f}".replace(".", ","), f"{v['part_absents']:.2f}".replace(".", ","),
                           nb(g["n"]), pct(g["ideal"]), pct(g["sur"]),
                           f"{nb(g['silencieux'])} ({pct(g['silencieux_pct'], 2)})", pct(ra.get("risque_pct"), 2)])
    return f"""
<section id="sensibilite"><h2>6. Sensibilité</h2>
<p>Mêmes graines, une seule valeur changée à la fois : part d'« entendu » 0,10 / 0,20 / 0,40, part d'absents
0,05 / 0,10 / 0,25 (<code>--part-entendu</code>, <code>--part-absents</code>, sans modifier le YAML).
Dernière colonne : part d'erreurs silencieuses parmi les termes acceptés par l'approché seul.</p>
{table(["Jeu", "Entendu", "Absents", "Cas", "Idéal", "Sûr", "Silencieux", "Risque de l'approché"], lignes)}
</section>"""


CSS = """
:root{--bg:#fcfcfb;--fg:#0b0b0b;--fg2:#52514e;--ligne:#e4e3df;--zebre:#f4f3f0;--s1:#2a78d6;--s2:#eb6834;--mal:#d03b3b;--code:#efeeea}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#1a1a19;--fg:#f0efec;--fg2:#c3c2b7;--ligne:#383835;--zebre:#222220;--s1:#3987e5;--s2:#d95926;--mal:#e66767;--code:#2a2a28}}
:root[data-theme="dark"]{--bg:#1a1a19;--fg:#f0efec;--fg2:#c3c2b7;--ligne:#383835;--zebre:#222220;--s1:#3987e5;--s2:#d95926;--mal:#e66767;--code:#2a2a28}
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
.bl{display:grid;grid-template-columns:3em 1fr;gap:2px 8px;margin-bottom:6px}.bk{grid-row:span 2;align-self:center;color:var(--fg2)}
.bb{display:flex;align-items:center;gap:6px;height:14px}.bar{height:12px;border-radius:0 4px 4px 0;min-width:1px}
.s1{background:var(--s1)}.s2{background:var(--s2)}.bv{font-size:.8rem;color:var(--fg2);white-space:nowrap}
.leg{display:flex;gap:16px;font-size:.88rem;color:var(--fg2)}.leg i{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:6px;vertical-align:-1px}
"""


def page(d: dict) -> str:
    b, a = d["banc"]["global"], d["analyse"]["global"]
    ra = d["analyse"]["risque_approche"].get("TOTAL", {})
    rb = d["banc"]["risque_approche"].get("TOTAL", {})
    reel = d["reel_moteur"]["sans_indice"]["par_mode"]
    cles = [(pct(b["ideal"]), "idéal sur le banc (trafic simulé)"),
            (f"{nb(b['silencieux'])} / {nb(b['n'])}", "erreurs silencieuses sur le banc"),
            (pct(ra.get("risque_pct"), 2), f"risque de l'approché sur l'analyse ({nb(ra.get('silencieux'))} / {nb(ra.get('acceptes'))})"),
            (f"{nb(reel.get('TOTAL', {}).get('silencieux'))} / {nb(reel.get('TOTAL', {}).get('n'))}",
             "erreurs silencieuses sur l'échantillon réel")]
    tuiles = "".join(f'<div class="cle"><b>{v}</b><span>{e(t)}</span></div>' for v, t in cles)
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Modèle de saisie</title><style>{CSS}</style></head><body><main>
<div class="eyebrow">POC Mécanova · entity resolution · moteur à seuil fixe 0,88 (provisoire)</div>
<h1>Modèle de saisie : jeux générés, vérification contre le réel, mesures du moteur à 0,88</h1>
<p class="lede">Les jeux de test viennent maintenant d'un modèle de saisie explicite (<code>spec/modele_saisie.yaml</code>).
Ce rapport vérifie le générateur contre 252 saisies réelles, puis mesure le moteur actuel, sans rien régler :
aucun seuil n'est calculé et le jeu de certification n'est pas ouvert.</p>
<div class="cles">{tuiles}</div>
<p class="note">Risque de l'approché sur le banc : {pct(rb.get("risque_pct"), 2)} ({nb(rb.get("silencieux"))} / {nb(rb.get("acceptes"))}).
Analyse : {nb(a["n"])} cas, idéal {pct(a["ideal"])}, {nb(a["silencieux"])} silencieuses.</p>
<nav><a href="#jeux">Jeux</a><a href="#verification">Vérification</a><a href="#banc">Banc</a><a href="#diagnostic">Diagnostic</a><a href="#reel">Réel</a><a href="#sensibilite">Sensibilité</a></nav>
{section_jeux(d)}{section_verification(d)}{section_banc(d)}{section_diagnostic(d)}{section_reel(d)}{section_sensibilite(d)}
<p class="note">Généré par <code>python -m engine.rapport_saisies</code> depuis <code>reports/mesure_saisies.json</code>
(<code>python -m engine.mesure_saisies</code>).</p>
</main></body></html>"""


def main() -> int:
    console_utf8()
    if not ENTREE.exists():
        raise SystemExit(f"{ENTREE} introuvable : lancer python -m engine.mesure_saisies.")
    d = json.loads(ENTREE.read_text(encoding="utf-8"))
    SORTIE.write_text(page(d), encoding="utf-8")
    print(f"→ {SORTIE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
