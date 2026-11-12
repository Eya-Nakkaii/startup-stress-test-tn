"""Démarrer : python -m streamlit run app.py"""
from __future__ import annotations

import sys
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:  # imports locaux, quel que soit le dossier de lancement
    sys.path.insert(0, str(ROOT))

import altair as alt
import pandas as pd
import streamlit as st

from data_io import (
    BCT_FILE, TEMPLATE_FILE, DataError, bct_variations, load_bct, model_from_row,
    startup_variations, validate_startup_csv,
)
from finance import (
    Model, calculate, demo_model, extra_orders_to_balance, extra_price_to_balance,
    fmt_money, fmt_percent, scenario_matrix, val,
)

BCT_URL = 'https://www.bct.gov.tn/bct/siteprod/tableau_statistique.jsp?params=PL202020'
TIKTAK_URL = 'https://tiktakpro.com/blog/barometre-ecommerce-tunisie-2026'
INTIGO_URL = 'https://intigo.net/'
POSITIVE, NEGATIVE, SERIES = '#2a78d6', '#e34948', '#2a78d6'
MAX_ORDERS = 1_000_000
FR_NUMBER = "replace(format(datum.value, ',.0f'), /,/g, ' ')"  # 1 500 au lieu de 1,500


def fmt_int(n: int | None) -> str:
    return 'Non atteignable' if n is None else f'{n:,}'.replace(',', ' ')


def threshold_text(r) -> str:
    return fmt_int(r.breakeven) + ('' if r.breakeven is None else ' commandes')


st.set_page_config(page_title='Startup Stress-Test TN', page_icon='📊', layout='wide')
# Uniquement des réglages de mise en page : aucune couleur imposée, pour rester lisible en thème clair ET sombre.
st.markdown('<style>.block-container{padding-top:3.5rem;max-width:1250px;}</style>', unsafe_allow_html=True)

st.caption('MANAGEMENT DE L’INNOVATION · PROTOTYPE UNIVERSITAIRE · TUNISIE')
st.title('📊 Startup Stress-Test TN')
st.write('**Combien une startup e-commerce tunisienne perd-elle si la livraison coûte 2 DT de plus, '
         'si ses commandes baissent, ou les deux ?**')

try:
    bct = load_bct()
    bct_error = None
except DataError as exc:
    bct, bct_error = None, str(exc)

tab_a, tab_b, tab_c, tab_d = st.tabs(['A · Présentation', 'B · Données tunisiennes',
                                      'C · Simulations', 'D · Diagnostic financier'])

# ---------------------------------------------------------------- A. Présentation
with tab_a:
    demo = demo_model()
    base = calculate(demo)
    st.subheader('ShopTN Pilote : une boutique en ligne tunisienne fictive')
    st.write('ShopTN Pilote vend des produits en ligne, livrés à domicile par un transporteur. '
             'Le client paie le panier **et** des frais de livraison ; la boutique paie les produits, '
             'la publicité/emballage et le transporteur. Le stress-test mesure la résistance du '
             '**résultat mensuel** à deux risques : une hausse du coût de livraison et une baisse des commandes.')
    st.info('Cas d’étude fictif : seules les références TikTak PRO (panier) et INTIGO (tarif transport) '
            'proviennent de sources publiées. Les commandes et les coûts internes sont des **hypothèses de démonstration**. '
            'Le prototype calcule un résultat économique simplifié, pas un bénéfice comptable certifié.')
    st.markdown('##### Indicateurs du profil de démonstration (calculés par le moteur)')
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Marge par commande', fmt_money(base.unit_margin), border=True)
    c2.metric('Recettes mensuelles', fmt_money(base.revenue), border=True)
    c3.metric('Résultat mensuel', fmt_money(base.profit), border=True)
    c4.metric('Seuil de rentabilité (commandes)', fmt_int(base.breakeven), border=True)
    st.markdown('##### Hypothèses utilisées')
    st.dataframe(pd.DataFrame([
        ('Commandes livrées par mois', fmt_int(demo.orders), 'Hypothèse de démonstration'),
        ('Panier moyen (produits)', fmt_money(demo.basket), 'Référence publiée : TikTak PRO, janv.–juil. 2026'),
        ('Livraison facturée au client', fmt_money(demo.customer_delivery_fee), 'Hypothèse de démonstration'),
        ('Coût des produits / commande', fmt_money(demo.product_cost), 'Hypothèse de démonstration'),
        ('Publicité + emballage / commande', fmt_money(demo.marketing_packaging), 'Hypothèse de démonstration'),
        ('Coût payé au transporteur / commande', fmt_money(demo.carrier_cost), 'Référence publiée : INTIGO, palier 501–1 500 colis'),
        ('Charges fixes mensuelles', fmt_money(demo.fixed), 'Hypothèse de démonstration'),
    ], columns=['Paramètre', 'Valeur', 'Statut']), hide_index=True, width='stretch')
    st.caption('Les frais de livraison **facturés au client** (recette) sont distincts du coût **payé au transporteur** (charge).')

# ---------------------------------------------------------------- B. Données tunisiennes
with tab_b:
    st.subheader('Paiements électroniques nationaux — BCT, avril à juin 2025')
    st.warning('Indicateur **externe** : nombre de paiements électroniques en Tunisie publié par la Banque Centrale. '
               'Ce ne sont **pas** les commandes d’une startup. Appliquer ces variations à ShopTN est une hypothèse de scénario.')
    if bct is None:
        st.error(f'Données BCT indisponibles : {bct_error}\n\nFichier attendu : `{BCT_FILE}`. '
                 'Les simulations restent possibles avec une variation manuelle ou un CSV importé.')
    else:
        variations = bct_variations(bct)
        cols = st.columns(len(variations))
        for col, v in zip(cols, variations):
            col.metric(f'Variation {v["label"]}', fmt_percent(v['variation']), border=True,
                       help=f'({fmt_int(v["apres"])} − {fmt_int(v["avant"])}) / {fmt_int(v["avant"])} × 100')
        left, right = st.columns([3, 2])
        with left:
            chart_df = bct.assign(**{'Paiements (milliers)': bct['transactions_electroniques'] / 1000})
            line = alt.Chart(chart_df).encode(
                x=alt.X('label:N', sort=list(chart_df['label']), title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y('Paiements (milliers):Q', scale=alt.Scale(zero=False, nice=True),
                        title='Paiements (milliers)', axis=alt.Axis(labelExpr=FR_NUMBER)),
                tooltip=[alt.Tooltip('label:N', title='Mois'),
                         alt.Tooltip('Paiements (milliers):Q', format=',.1f')],
            )
            st.altair_chart((line.mark_line(color=SERIES, strokeWidth=2)
                             + line.mark_point(color=SERIES, filled=True, size=80)).properties(height=300))
            st.caption('Axe vertical non nul pour rendre visibles les écarts mensuels.')
        with right:
            table = bct[['label', 'transactions_electroniques']].copy()
            prev = table['transactions_electroniques'].shift()
            table['Variation vs mois précédent'] = [
                '—' if pd.isna(p) else fmt_percent((D(int(c)) - D(int(p))) / D(int(p)))
                for c, p in zip(table['transactions_electroniques'], prev)]
            table['transactions_electroniques'] = table['transactions_electroniques'].map(fmt_int)
            st.dataframe(table.rename(columns={'label': 'Mois', 'transactions_electroniques': 'Paiements'}),
                         hide_index=True, width='stretch')
            st.link_button('Voir la source BCT', BCT_URL)

# ---------------------------------------------------------------- C. Simulations
with tab_c:
    st.subheader('1. Profil économique')
    own = None
    with st.expander('Importer les données mensuelles de votre startup (facultatif)'):
        st.caption('Une ligne par mois, sans données clients. Les données importées ne sont vérifiées par aucune source publique.')
        if TEMPLATE_FILE.exists():
            st.download_button('Télécharger le modèle CSV', TEMPLATE_FILE.read_bytes(),
                               file_name=TEMPLATE_FILE.name, mime='text/csv')
        upload = st.file_uploader('Fichier CSV mensuel', type=['csv'])
        if upload is not None:
            try:
                own = validate_startup_csv(upload.getvalue())
                st.success(f'Fichier valide : {len(own)} mois.')
                st.dataframe(own.drop(columns='periode'), hide_index=True, width='stretch')
            except DataError as exc:
                st.error(f'CSV refusé : {exc}')

    reference_row, profile_key = None, 'demo'
    if own is not None:
        month = st.selectbox('Mois importé utilisé comme point de départ', own['mois'].tolist())
        reference_row = own.loc[own['mois'] == month].iloc[0]
        profile_key = f'csv-{month}'
        st.caption('Valeurs préremplies depuis le mois sélectionné : vous pouvez les ajuster.')
    else:
        st.caption('Mode démonstration (ShopTN Pilote). Toutes les valeurs sont modifiables.')

    ref = model_from_row(reference_row) if reference_row is not None else demo_model()

    def money_input(label: str, value: D, step: float, key: str) -> D:
        return D(str(st.number_input(label, min_value=0.0, value=float(value), step=step,
                                     format='%.2f', key=f'{profile_key}-{key}')))

    x, y, z = st.columns(3)
    with x:
        orders = int(st.number_input('Commandes livrées / mois', min_value=0, max_value=MAX_ORDERS,
                                     value=min(ref.orders, MAX_ORDERS), step=10, key=f'{profile_key}-orders'))
        basket = money_input('Panier moyen (DT)', ref.basket, 1.0, 'basket')
        customer_fee = money_input('Livraison facturée au client (DT)', ref.customer_delivery_fee, 0.5, 'fee')
    with y:
        product_cost = money_input('Coût des produits / commande (DT)', ref.product_cost, 1.0, 'product')
        marketing = money_input('Publicité + emballage / commande (DT)', ref.marketing_packaging, 0.5, 'mkt')
        carrier = money_input('Coût payé au transporteur / commande (DT)', ref.carrier_cost, 0.5, 'carrier')
    with z:
        fixed = money_input('Charges fixes mensuelles (DT)', ref.fixed, 500.0, 'fixed')
    model = Model(orders, basket, customer_fee, product_cost, marketing, carrier, fixed)

    st.subheader('2. Chocs à simuler')
    s1, s2 = st.columns(2)
    with s1:
        delta_carrier = D(str(st.slider('Hausse du coût du transport (DT par commande)', 0.0, 10.0, 2.0, 0.5)))
    with s2:
        options = {}
        if bct is not None:
            for v in bct_variations(bct):
                options[f'BCT {v["label"]} ({fmt_percent(v["variation"])})'] = ('bct', v['variation'])
        if own is not None:
            for v in startup_variations(own):
                options[f'CSV startup {v["label"]} ({fmt_percent(v["variation"])})'] = ('csv', v['variation'])
        options['Aucune variation de demande'] = ('none', D('0'))
        options['Variation manuelle (non observée)'] = ('manual', None)
        source = st.selectbox('Variation historique de la demande', list(options))
        kind, variation = options[source]
        if kind == 'manual':
            variation = -D(str(st.slider('Baisse hypothétique des commandes (%)', 0.0, 100.0, 8.0, 0.5))) / 100
    notes = {'bct': 'Variation des paiements électroniques nationaux appliquée **par hypothèse** aux commandes.',
             'csv': 'Variation calculée sur vos commandes importées (non vérifiées par un tiers).',
             'none': 'Seul le choc sur le coût du transport est appliqué.',
             'manual': 'Paramètre de stress choisi librement : ce n’est pas un fait observé.'}
    st.caption(notes[kind])

    results = scenario_matrix(model, variation, delta_carrier)
    initial, combined = results['Situation initiale'], results['Deux chocs simultanés']
    st.subheader('3. Effet immédiat')
    m1, m2, m3 = st.columns(3)
    m1.metric('Résultat initial', fmt_money(initial.profit), border=True)
    m2.metric('Résultat après simulation', fmt_money(combined.profit),
              delta=fmt_money(combined.profit - initial.profit), border=True)
    m3.metric('Commandes après choc', fmt_int(combined.orders),
              delta=f'{combined.orders - initial.orders:+,}'.replace(',', ' '), border=True)
    if initial.unit_margin <= 0:
        st.error('La marge par commande est nulle ou négative dès la situation initiale : '
                 'chaque commande supplémentaire aggrave la perte.')
    st.caption('Le diagnostic complet est dans l’onglet **D · Diagnostic financier**.')

# ---------------------------------------------------------------- D. Diagnostic financier
with tab_d:
    st.subheader('Diagnostic : situation initiale vs. deux chocs simultanés')
    st.caption(f'Hypothèses : transport {fmt_money(initial.carrier_cost)} → {fmt_money(combined.carrier_cost)} ; '
               f'demande {fmt_percent(variation)} — {source.split(" (")[0]}.')
    needed = extra_orders_to_balance(combined)
    d1, d2, d3, d4 = st.columns(4)
    d1.metric('Résultat initial', fmt_money(initial.profit), border=True)
    d2.metric('Résultat après simulation', fmt_money(combined.profit), border=True)
    d3.metric('Différence', fmt_money(combined.profit - initial.profit), border=True)
    d4.metric('Commandes pour l’équilibre', fmt_int(combined.breakeven), border=True,
              help='plafond(charges fixes / marge unitaire), avec la marge après simulation')

    if combined.profit < 0:
        if needed is None:
            st.error('Après simulation, chaque commande ne couvre plus ses coûts variables : '
                     'augmenter le volume ne suffit pas, il faut revoir prix ou coûts.')
        else:
            extra = extra_price_to_balance(combined)
            st.warning(f'Après simulation, il manque **{fmt_int(needed)} commandes** pour atteindre le seuil de '
                       f'{threshold_text(combined)} (marge constante). Autre levier : récupérer '
                       f'**{fmt_money(extra)} par commande** (prix ou économie unitaire) à volume inchangé.')
    else:
        st.success('Après simulation, le résultat mensuel reste positif ou nul.')

    st.markdown('##### Comparaison des quatre scénarios')
    order = list(results)
    chart = pd.DataFrame({
        'Scénario': order,
        'Résultat (DT)': [float(r.profit) for r in results.values()],
        'Libellé': [fmt_money(r.profit) for r in results.values()],
        'Signe': ['Bénéfice' if r.profit >= 0 else 'Perte' for r in results.values()],
    })
    enc = alt.Chart(chart).encode(
        x=alt.X('Scénario:N', sort=order, title=None, axis=alt.Axis(labelAngle=0, labelLimit=250)),
        y=alt.Y('Résultat (DT):Q', title='Résultat mensuel (DT)', axis=alt.Axis(labelExpr=FR_NUMBER)),
        tooltip=['Scénario', alt.Tooltip('Libellé:N', title='Résultat')],
    )
    bars = enc.mark_bar(cornerRadius=4, size=56).encode(
        color=alt.Color('Signe:N', scale=alt.Scale(domain=['Bénéfice', 'Perte'], range=[POSITIVE, NEGATIVE]),
                        legend=alt.Legend(title=None, orient='top')))
    above = enc.mark_text(dy=-10, fontWeight='bold').encode(text='Libellé:N').transform_filter('datum["Résultat (DT)"] >= 0')
    below = enc.mark_text(dy=12, fontWeight='bold').encode(text='Libellé:N').transform_filter('datum["Résultat (DT)"] < 0')
    labels = above + below
    zero = alt.Chart(pd.DataFrame({'y': [0]})).mark_rule(strokeWidth=1, opacity=0.6).encode(y='y:Q')
    st.altair_chart((bars + zero + labels).properties(height=340))

    st.dataframe(pd.DataFrame([{
        'Scénario': name,
        'Commandes': fmt_int(r.orders),
        'Coût transport': fmt_money(r.carrier_cost),
        'Marge / commande': fmt_money(r.unit_margin),
        'Recettes': fmt_money(r.revenue),
        'Coûts variables': fmt_money(r.variable_cost),
        'Charges fixes': fmt_money(r.fixed),
        'Résultat': fmt_money(r.profit),
        'Seuil de rentabilité': threshold_text(r),
    } for name, r in results.items()]), hide_index=True, width='stretch')

    with st.expander('Explication des calculs et des hypothèses'):
        st.code('Marge / commande = panier + livraison facturée − coût produits − coût transport − publicité/emballage\n'
                'Résultat mensuel  = commandes × marge / commande − charges fixes\n'
                'Variation (%)     = (volume après − volume avant) / volume avant × 100\n'
                'Commandes après   = arrondi(commandes initiales × (1 + variation))\n'
                'Seuil             = plafond(charges fixes / marge), si marge > 0', language=None)
        for name, r in results.items():
            st.markdown(f'**{name}** : {fmt_int(r.orders)} × {fmt_money(r.unit_margin)} − {fmt_money(r.fixed)} '
                        f'= **{fmt_money(r.profit)}**')
        st.markdown('- Recettes = commandes × (panier + livraison facturée) ; ce n’est pas un bénéfice.\n'
                    '- Le transport n’est compté qu’une fois, dans les coûts variables.\n'
                    '- Non inclus : TVA détaillée, retours, impôts, amortissements. Le modèle ne prédit ni faillite ni comportement client.\n'
                    f'- Sources : [BCT]({BCT_URL}) · [TikTak PRO]({TIKTAK_URL}) · [INTIGO]({INTIGO_URL}).')

    export = pd.DataFrame([{
        'Scenario': name, 'Orders': r.orders, 'Carrier_cost_DT': str(r.carrier_cost),
        'Unit_margin_DT': str(r.unit_margin), 'Revenue_DT': str(r.revenue),
        'Variable_cost_DT': str(r.variable_cost), 'Fixed_DT': str(r.fixed), 'Profit_DT': str(r.profit),
        'Break_even_orders': r.breakeven, 'Demand_shock_source': source,
        'Demand_variation': str(val(variation)), 'Cost_increase_DT': str(delta_carrier),
    } for name, r in results.items()])
    st.download_button('Exporter la comparaison (CSV)', export.to_csv(index=False).encode('utf-8-sig'),
                       file_name='stress_test_startup_tn.csv', mime='text/csv')
