"""ST/TN — Startup Stress-Test TN. Démarrer : python -m streamlit run app.py"""
from __future__ import annotations

import re
import sys
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:  # imports locaux, quel que soit le dossier de lancement
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from charts import curve_chart, curve_data, decomposition_chart, decomposition_data
from components import amount, brand, diagnosis_box, inject_styles, mono, nb, snapshot_strip, zone_label
from data_io import (
    TEMPLATE_FILE, DataError, bct_variations, carrier_tier, case_model, load_bct, load_case, model_from_row,
    startup_variations, validate_startup_csv,
)
from diagnostic import SCENARIO_LABELS, diagnose, fmt_orders, fmt_signed
from finance import Model, apply_variation, fmt_money, fmt_percent, scenario_matrix
from report import ReportContext, build_report_html

BCT_URL = 'https://www.bct.gov.tn/bct/siteprod/tableau_statistique.jsp?params=PL202020'
CASES = {'okkis': 'Okkis · cas documenté', 'custom': 'Mon entreprise'}
PARAMS = [  # (clé, champ du modèle, libellé, pas)
    ('p_orders', 'orders', 'Commandes / mois', 10),
    ('p_basket', 'basket', 'Panier moyen (DT)', 1.0),
    ('p_product', 'product_cost', 'Coût des produits (DT)', 1.0),
    ('p_fee', 'customer_delivery_fee', 'Livraison facturée (DT)', 0.5),
    ('p_carrier', 'carrier_cost', 'Coût du transport (DT)', 0.5),
    ('p_other', 'marketing_packaging', 'Autres coûts variables (DT)', 0.5),
    ('p_fixed', 'fixed', 'Charges fixes / mois (DT)', 500.0),
]
MARKS = {'basket': '◆', 'carrier_cost': '†'}   # cas Okkis ; tout le reste est une hypothèse (*)
CUSTOM_SHOCK = 'Hypothèse personnalisée'
DEFAULT_DELTA = 2.0
MAX_ORDERS = 1_000_000

st.set_page_config(page_title='ST/TN — Startup Stress-Test TN', page_icon=':material/query_stats:',
                   layout='wide', initial_sidebar_state='collapsed')
inject_styles()

# ---------------------------------------------------------------- Données locales (lecture seule)
try:
    bct, bct_error = load_bct(), None
except DataError as exc:
    bct, bct_error = None, str(exc)
try:
    case, case_error = load_case(), None
except DataError as exc:
    case, case_error = None, str(exc)
ss = st.session_state


# ---------------------------------------------------------------- État : paramètres, cas, chocs
def shock_options() -> dict[str, D]:
    """Baisses historiques (≤ 50 %) : BCT, puis import éventuel. Calculées depuis les fichiers."""
    opts = {}
    if bct is not None:
        for v in bct_variations(bct):
            opts[f'BCT · {v["label"].lower()} ({fmt_percent(v["variation"])})'] = v['variation']
    if ss.get('own') is not None:
        for v in startup_variations(ss['own']):
            opts[f'Import · {v["label"]} ({fmt_percent(v["variation"])})'] = v['variation']
    return {k: v for k, v in opts.items() if D('-0.5') <= v <= 0}


def drop_of(variation: D) -> float:
    return float(round(-variation * 100, 2))


def reference_model(case_key: str) -> Model | None:
    if case_key == 'okkis':
        return case_model(case) if case is not None else None
    own = ss.get('own')
    if own is not None:
        row = own.loc[own['mois'] == ss.get('month')]
        if len(row):
            return model_from_row(row.iloc[0])
    return None   # « Mon entreprise » sans données : champs vides, rien n'est inventé


def apply_params(m: Model | None) -> None:
    for key, field, _, _ in PARAMS:
        v = None if m is None else getattr(m, field)
        ss[key] = None if v is None else (min(int(v), MAX_ORDERS) if field == 'orders' else float(v))


def reset_shocks() -> None:
    ss['s_delta'] = DEFAULT_DELTA
    opts = shock_options()
    ss['s_source'] = next(iter(opts), CUSTOM_SHOCK)
    ss['s_drop'] = drop_of(opts[ss['s_source']]) if opts else 0.0


def reset() -> None:
    apply_params(reference_model(ss['active_case']))
    reset_shocks()


def on_case() -> None:
    new = ss.get('case_sel')
    if new is None or new == ss['active_case']:   # le sélecteur ne peut pas être vidé
        ss['case_sel'] = ss['active_case']
        return
    ss['saved'][ss['active_case']] = {key: ss[key] for key, *_ in PARAMS}
    ss['active_case'] = new
    if new in ss['saved']:
        for key, value in ss['saved'][new].items():
            ss[key] = value
    else:
        apply_params(reference_model(new))


def on_upload() -> None:
    upload = ss.get('upload')
    ss['own'], ss['import_error'] = None, None
    if upload is None:
        return
    try:
        own = validate_startup_csv(upload.getvalue())
    except DataError as exc:
        ss['import_error'] = str(exc)
        return
    ss['own'], ss['month'] = own, own['mois'].iloc[-1]
    if ss['active_case'] != 'custom':
        ss['saved'][ss['active_case']] = {key: ss[key] for key, *_ in PARAMS}
    ss['active_case'] = ss['case_sel'] = 'custom'
    ss['saved'].pop('custom', None)
    apply_params(reference_model('custom'))


def on_month() -> None:
    apply_params(reference_model('custom'))


def on_source() -> None:
    opts = shock_options()
    if ss['s_source'] in opts:
        ss['s_drop'] = drop_of(opts[ss['s_source']])


def on_drop() -> None:
    opts = shock_options()
    if ss['s_source'] in opts and ss['s_drop'] != drop_of(opts[ss['s_source']]):
        ss['s_source'] = CUSTOM_SHOCK


if 'active_case' not in ss:   # premier affichage : cas Okkis préchargé
    ss['active_case'] = ss['case_sel'] = 'okkis' if case is not None else 'custom'
    ss['saved'] = {}
    reset()

# ---------------------------------------------------------------- En-tête compact
okkis = ss['active_case'] == 'okkis'
own = ss.get('own')
if okkis:
    subtitle = 'Cas Okkis : indicateurs publics et hypothèses financières modifiables'
elif own is not None:
    subtitle = f'Mon entreprise · données importées ({ss["month"]}), non vérifiées'
else:
    subtitle = 'Mon entreprise · données saisies'

head_l, head_r = st.columns([5, 7], vertical_alignment='center')
with head_l:
    brand(subtitle)
with head_r:
    c_case, c_imp, c_exp, c_reset = st.columns([3.0, 1.5, 1.5, 1.7], vertical_alignment='center')
    c_case.segmented_control('Cas étudié', list(CASES), format_func=CASES.get, key='case_sel',
                             on_change=on_case, label_visibility='collapsed', width='stretch')
    with c_imp.popover('Importer', icon=':material/upload_file:', width='stretch'):
        st.caption('CSV mensuel (une ligne par mois, sans données clients). Bascule en « Mon entreprise ».')
        st.file_uploader('Fichier CSV', type=['csv'], key='upload', on_change=on_upload,
                         label_visibility='collapsed')
        if own is not None:
            st.selectbox('Mois de référence', own['mois'].tolist(), key='month', on_change=on_month)
        if TEMPLATE_FILE.exists():
            st.download_button('Modèle CSV', TEMPLATE_FILE.read_bytes(), file_name=TEMPLATE_FILE.name,
                               mime='text/csv', icon=':material/download:')
    export_box = c_exp.popover('Exporter', icon=':material/download:', width='stretch')
    c_reset.button('Réinitialiser', icon=':material/restart_alt:', on_click=reset, width='stretch')

if ss.get('import_error'):
    st.error(f'CSV refusé : {ss["import_error"]}', icon=':material/error:')
if case_error:
    st.error(f'Cas Okkis indisponible : {case_error}', icon=':material/error:')

values = {field: ss[key] for key, field, _, _ in PARAMS}
model = None if any(v is None for v in values.values()) else Model(
    **{f: int(v) if f == 'orders' else D(str(v)) for f, v in values.items()})
reference = reference_model(ss['active_case'])

# ---------------------------------------------------------------- 01 Modèle économique · 02 Stress lab
z_model, z_lab = st.columns([7, 5], gap='small')
with z_model:
    with st.container(border=True, key='zone-model'):
        if okkis:
            pub = case['publie']
            aside = (f'◆ Okkis · panier {nb(fmt_money(pub["panier_moyen_dt"]))} · confirmation '
                     f'{round(pub["taux_confirmation"] * 100)} % · CA ×2 en 6 mois')
        else:
            aside = 'Valeurs saisies ou importées'
        zone_label('01', 'Modèle économique', aside)
        grid = [PARAMS[:4], PARAMS[4:]]
        for row in grid:
            cols = st.columns(4, gap='small')
            for col, (key, field, label, step) in zip(cols, row):
                mark = (MARKS.get(field, '*') if okkis else '')
                text = f'{label} {mark}'.strip()
                if field == 'orders':
                    col.number_input(text, min_value=0, max_value=MAX_ORDERS, step=step, key=key, placeholder='—')
                else:
                    col.number_input(text, min_value=0.0, max_value=10_000_000.0, step=step, format='%.2f',
                                     key=key, placeholder='—')
            if len(row) == 3:
                margin = '—' if model is None else nb(fmt_money(model.basket + model.customer_delivery_fee
                                                                - model.product_cost - model.carrier_cost
                                                                - model.marketing_packaging))
                cols[3].html(f'<div class="sttn-cell-ro-label">Marge / commande =</div>'
                             f'<div class="sttn-cell-ro">{margin}</div>')
        if okkis:
            changed = [label.split(' (')[0].lower() for key, field, label, _ in PARAMS
                       if reference is not None and model is not None
                       and field in MARKS and getattr(model, field) != getattr(reference, field)]
            st.html('<div class="sttn-legend"><b>◆</b> publié — TikTak PRO, étude de cas Okkis · '
                    '<b>†</b> tarif public INTIGO (24/10/2026, TTC, palier 501–1 500), pas un contrat Okkis · '
                    '<b>*</b> hypothèse de démonstration, pas une donnée Okkis. Montants tels que publiés, TVA non '
                    'isolée : modèle simplifié.'
                    + (f' <b>Modifié</b> : {", ".join(changed)} (devient une hypothèse).' if changed else '')
                    + '</div>')
        else:
            st.html('<div class="sttn-legend">Aucune valeur n’est complétée automatiquement : '
                    'saisissez les 7 cellules ou importez un CSV.</div>')

with z_lab:
    with st.container(border=True, key='zone-lab'):
        opts = shock_options()
        if ss.get('s_source') not in list(opts) + [CUSTOM_SHOCK]:
            ss['s_source'] = CUSTOM_SHOCK
        zone_label('02', 'Stress lab', 'Les deux chocs s’appliquent ensemble')
        t_col, d_col = st.columns(2, gap='medium')
        with t_col:
            st.slider('Transport — hausse par commande', 0.0, 5.0, step=0.1, key='s_delta', format='+%.2f DT')
            delta = D(str(ss['s_delta']))
            detail = '' if model is None else \
                f'{nb(fmt_money(model.carrier_cost))} → {nb(fmt_money(model.carrier_cost + delta))}'
            st.html(f'<div class="sttn-readout {"sttn-up" if delta else "sttn-zero"}">'
                    f'{mono("+" + fmt_money(delta))}<small>{detail}</small></div>')
        with d_col:
            st.slider('Demande — baisse des commandes', 0.0, 50.0, step=0.01, key='s_drop', format='−%.2f %%',
                      on_change=on_drop)
            historical = ss['s_source'] in opts
            variation = opts[ss['s_source']] if historical else -D(str(ss['s_drop'])) / 100
            after = None if model is None else apply_variation(model.orders, variation)
            detail = '' if model is None else f'{nb(fmt_orders(model.orders))} → {nb(fmt_orders(after))} cdes'
            st.html(f'<div class="sttn-readout {"sttn-down" if variation else "sttn-zero"}">'
                    f'{mono(fmt_percent(variation).replace("-", "−"))}<small>{detail}</small></div>')
        st.selectbox('Source du choc de demande', list(opts) + [CUSTOM_SHOCK], key='s_source', on_change=on_source)
        if historical and ss['s_source'].startswith('BCT'):
            note = ('Paiements électroniques nationaux (BCT), transposés par hypothèse : ce ne sont pas des '
                    'commandes ' + ('Okkis.' if okkis else 'de l’entreprise.'))
        elif historical:
            note = 'Variation de vos commandes importées (non vérifiées par un tiers).'
        else:
            note = 'Hypothèse personnalisée : paramètre de stress, pas une observation.'
        if okkis and model is not None:
            tiers = case['reference_transport']['paliers']
            t0, t1 = carrier_tier(tiers, model.orders), carrier_tier(tiers, after)
            if t0 and t1 and t0 != t1:
                note += (f' Palier INTIGO : à {nb(fmt_orders(after))} colis/30 j, le tarif de référence passerait à '
                         f'{nb(fmt_money(t1["prix_dt"]))} — non appliqué automatiquement.')
            elif t1:
                note += f' Palier INTIGO inchangé ({nb(fmt_money(t1["prix_dt"]))} à {nb(fmt_orders(after))} colis/30 j).'
        st.html(f'<div class="sttn-note">{note}</div>')

if model is None:
    export_box.caption('Rien à exporter : le modèle est incomplet.')
    st.info('Complétez les 7 cellules du modèle économique ou importez un CSV pour lancer le diagnostic.',
            icon=':material/edit_note:')
    st.stop()

# ---------------------------------------------------------------- Calculs (moteur financier)
results = scenario_matrix(model, variation, delta)
diag = diagnose(results, 'C')
initial, simulated, dec = diag.initial, diag.simulated, diag.decomposition

# ---------------------------------------------------------------- 03 Synthèse
with st.container(border=True, key='zone-snap'):
    zone_label('03', 'Synthèse financière',
               f'transport +{nb(fmt_money(delta))} · demande {nb(fmt_percent(variation).replace("-", "−"))}')
    snapshot_strip(initial, simulated, diag.status, dec.total)

# ---------------------------------------------------------------- 04 Visualisation · Diagnostic
g_main, g_side = st.columns([8, 4], gap='small')
with g_main:
    with st.container(border=True, key='zone-curve'):
        zone_label('04', 'Rentabilité selon la baisse de la demande', '◆ simulation actuelle')
        curve = curve_data(model, delta)
        chart = curve_chart(curve, f'Transport {fmt_money(model.carrier_cost)}',
                            f'Transport {fmt_money(model.carrier_cost + delta)}',
                            drop_of(variation), float(simulated.profit), fmt_signed(simulated.profit))
        st.altair_chart(chart, key=f'curve-{hash((tuple(curve["choc"]), drop_of(variation)))}')
with g_side:
    with st.container(border=True, key='zone-decomp'):
        zone_label('04', 'Décomposition de la variation')
        bars = decomposition_data(dec)
        st.altair_chart(decomposition_chart(bars), key=f'decomp-{hash(tuple(bars["Montant (DT)"]))}')
        st.html('<div class="sttn-note">Ordre de calcul : 1) baisse des commandes à marge initiale ; '
                '2) hausse du transport sur le volume restant. Somme exacte, sans double comptage.</div>')
    with st.container(border=True, key='zone-diag'):
        zone_label('05', 'Diagnostic', diag.status.label)
        diagnosis_box(simulated, diag.simulated_breakeven)

# ---------------------------------------------------------------- Méthode · sources
m_col, s_col = st.columns(2, gap='small')
with m_col.expander('Méthode de calcul', icon=':material/function:'):
    st.code('Marge / commande = panier + livraison facturée − produits − transport − autres coûts variables\n'
            'Résultat mensuel = commandes × marge − charges fixes\n'
            'Variation (%)    = (volume après − volume avant) / volume avant × 100\n'
            'Commandes après  = arrondi(commandes × (1 + variation))   ← arrondi au plus proche\n'
            'Seuil            = plafond(charges fixes / marge), si marge > 0\n'
            'Effet demande    = (commandes après − avant) × marge initiale\n'
            'Effet transport  = commandes après × (marge simulée − marge initiale)', language=None)
    st.caption('Calcul décimal exact, sans arrondi intermédiaire ; seul le nombre de commandes est arrondi à '
               'l’unité. Montants traités tels que saisis (TVA non isolée) : résultat économique simplifié, '
               'hors impôts, retours et amortissements. Le taux de confirmation n’est pas appliqué au volume.')
with s_col.expander('Sources & données', icon=':material/database:'):
    if case is not None:
        pub, ref = case['publie'], case['reference_transport']
        st.markdown(f'**◆ Okkis** — [{pub["source"]["nom"]}]({pub["source"]["url"]}), vérifié le '
                    f'{case["verifie_le"]}. Panier {fmt_money(pub["panier_moyen_dt"])} (TTC/HT non précisé), '
                    f'confirmation {round(pub["taux_confirmation"] * 100)} %, {pub["croissance_ca"].lower()}. '
                    f'{pub["source"]["note"]}')
        st.markdown(f'**† INTIGO** — [{ref["source"]["nom"]}]({ref["source"]["url"]}), barème du '
                    f'{ref["source"]["date"]} ({ref["unite"]}). {ref["regle"]}')
        st.dataframe(pd.DataFrame([{'Colis / 30 jours': f'{t["min"]:,} – {t["max"]:,}'.replace(',', ' ')
                                    if t['max'] else f'plus de {t["min"] - 1:,}'.replace(',', ' '),
                                    'Prix': fmt_money(t['prix_dt'])} for t in ref['paliers']]),
                     hide_index=True, width='stretch')
    if bct is not None:
        st.markdown(f'**BCT** — [paiements électroniques nationaux]({BCT_URL}) (hors poste), en nombre :')
        st.dataframe(pd.DataFrame({'Mois': bct['label'], 'Paiements': bct['transactions_electroniques']
                                   .map(lambda v: fmt_orders(int(v)))}), hide_index=True, width='stretch')
    else:
        st.error(f'Données BCT indisponibles : {bct_error}')

# ---------------------------------------------------------------- Export
name = 'Okkis' if okkis else 'Mon entreprise'
sources = []
if case is not None:
    sources += [(case['publie']['source']['nom'], 'Panier moyen 89 DT, taux de confirmation 84 %, CA doublé en six '
                 'mois (volumes non communiqués par la marque).', case['publie']['source']['url']),
                (case['reference_transport']['source']['nom'], 'Tarif public de référence 8 DT TTC (palier '
                 '501–1 500 colis sur 30 jours) ; pas un contrat Okkis.', case['reference_transport']['source']['url'])]
sources.append(('Banque Centrale de Tunisie', 'Paiements électroniques nationaux avril–juin 2025 (hors poste).', BCT_URL))
limits = ['Hypothèses de démonstration (commandes, coûts, frais facturés, charges fixes) : elles ne représentent pas '
          'les finances réelles d’Okkis ; le résultat n’est pas le bénéfice réel de la marque.' if okkis else
          'Données saisies ou importées par l’utilisateur, non vérifiées par une source publique.',
          'Variation BCT : paiements électroniques nationaux transposés par hypothèse aux commandes.',
          'Modèle simplifié : TVA non isolée, impôts, retours et amortissements non modélisés ; '
          'le palier INTIGO peut évoluer avec le volume.']
report = build_report_html(ReportContext(name, subtitle, model, delta, ss['s_source'], variation,
                                         results, diag, sources, limits))
csv = pd.DataFrame([{'Scenario': SCENARIO_LABELS[n], 'Commandes': r.orders, 'Transport_DT': str(r.carrier_cost),
                     'Marge_DT': str(r.unit_margin), 'Recettes_DT': str(r.revenue),
                     'Couts_variables_DT': str(r.variable_cost), 'Charges_fixes_DT': str(r.fixed),
                     'Resultat_DT': str(r.profit), 'Seuil_commandes': r.breakeven}
                    for n, r in results.items()]).to_csv(index=False).encode('utf-8-sig')
slug = re.sub(r'[^A-Za-z0-9]+', '_', name).strip('_').lower()
with export_box:
    st.download_button('Diagnostic (HTML imprimable)', report.encode('utf-8'), file_name=f'sttn_diagnostic_{slug}.html',
                       mime='text/html', icon=':material/description:', width='stretch')
    st.download_button('Scénarios (CSV)', csv, file_name=f'sttn_scenarios_{slug}.csv', mime='text/csv',
                       icon=':material/table:', width='stretch')
