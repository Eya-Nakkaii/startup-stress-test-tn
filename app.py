"""Startup Stress-Test TN — démarrer : python -m streamlit run app.py"""
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

from data_io import (
    BCT_FILE, TEMPLATE_FILE, DataError, bct_variations, load_bct, model_from_row,
    startup_variations, validate_startup_csv,
)
from diagnostic import SCENARIO_LABELS, SCENARIOS, breakeven_text, diagnose, fmt_orders, fmt_signed
from finance import Model, demo_model, fmt_money, fmt_percent, scenario_matrix, val
from report import ReportContext, build_report_html
from ui import (card, demand_chart, demand_chart_data, inject_css, kpi_card, nb, scenario_chart, scenario_chart_data,
                tone_of)

BCT_URL = 'https://www.bct.gov.tn/bct/siteprod/tableau_statistique.jsp?params=PL202020'
TIKTAK_URL = 'https://tiktakpro.com/blog/barometre-ecommerce-tunisie-2026'
INTIGO_URL = 'https://intigo.net/'
SOURCES_CHECKED = '12/11/2026'
SOURCES = [
    ('Banque Centrale de Tunisie', 'Nombre des transactions par moyens de paiement (en milliers), ligne « Paiements '
     'électroniques » (hors paiements auprès de la poste) : avril, mai, juin 2025.', BCT_URL),
    ('TikTak PRO — baromètre e-commerce 2026', 'Panier moyen de 58 DT observé sur les commandes de ses marchands, '
     'janvier–juillet 2026 (plateforme, pas le marché entier).', TIKTAK_URL),
    ('INTIGO — tarifs publics', '8,00 DT TTC (TVA 7 %) par petit colis, palier 501–1 500 colis sur 30 jours.', INTIGO_URL),
]
LIMITS = [
    'Les paiements électroniques BCT sont un indicateur national : ils ne prédisent pas les commandes d’une startup. '
    'Appliquer leur variation à ShopTN est une hypothèse de scénario.',
    'ShopTN Pilote est un cas fictif : commandes, coût des produits, autres coûts variables, frais facturés et charges fixes '
    'sont des hypothèses de démonstration.',
    'Le tarif INTIGO dépend du palier de volume sur 30 jours : il peut changer si le volume change.',
    'Résultat économique simplifié : TVA détaillée, retours, impôts et amortissements ne sont pas modélisés.',
    'Les simulations sont des calculs conditionnels, pas des prévisions ni des probabilités de faillite.',
]
DEFAULT_NAME = 'ShopTN Pilote'
DEFAULT_SHOCKS = {'s_delta': 2.0, 's_manual': 8.0, 's_scenario': 'C'}
PARAMS = [  # (clé, champ du modèle, libellé, pas)
    ('p_orders', 'orders', 'Commandes mensuelles', 10),
    ('p_basket', 'basket', 'Panier moyen (DT)', 1.0),
    ('p_product', 'product_cost', 'Coût des produits / commande (DT)', 1.0),
    ('p_fee', 'customer_delivery_fee', 'Frais de livraison facturés (DT)', 0.5),
    ('p_carrier', 'carrier_cost', 'Coût de transport payé (DT)', 0.5),
    ('p_other', 'marketing_packaging', 'Autres coûts variables (DT)', 0.5),
    ('p_fixed', 'fixed', 'Charges fixes mensuelles (DT)', 500.0),
]
DEMO_ORIGIN = {'basket': 'Référence TikTak PRO', 'carrier_cost': 'Référence INTIGO'}
MAX_ORDERS = 1_000_000

st.set_page_config(page_title='Startup Stress-Test TN', page_icon=':material/query_stats:', layout='wide')
inject_css()

# ---------------------------------------------------------------- Données sources (lecture seule)
try:
    bct = load_bct()
    bct_error = None
except DataError as exc:
    bct, bct_error = None, str(exc)
BCT_VARIATIONS = bct_variations(bct) if bct is not None else []


# ---------------------------------------------------------------- État des paramètres
def reference_model() -> Model:
    own = st.session_state.get('own')
    if own is not None:
        row = own.loc[own['mois'] == st.session_state.get('month')]
        if len(row):
            return model_from_row(row.iloc[0])
    return demo_model()


def apply_model(m: Model) -> None:
    for key, field, _, _ in PARAMS:
        v = getattr(m, field)
        st.session_state[key] = min(int(v), MAX_ORDERS) if field == 'orders' else float(v)


def demand_options() -> dict[str, tuple[str, D | None]]:
    opts = {f'BCT {v["label"].replace(" 2025", "")} ({fmt_percent(v["variation"])})': ('bct', v['variation'])
            for v in BCT_VARIATIONS}
    own = st.session_state.get('own')
    if own is not None:
        for v in startup_variations(own):
            opts[f'Import {v["label"]} ({fmt_percent(v["variation"])})'] = ('csv', v['variation'])
    opts['Aucune variation de demande'] = ('none', D('0'))
    opts['Variation manuelle (non observée)'] = ('manual', None)
    return opts


def reset() -> None:
    apply_model(reference_model())
    st.session_state.update(DEFAULT_SHOCKS)
    st.session_state['s_demand'] = next(iter(demand_options()))


def on_upload() -> None:
    upload = st.session_state.get('upload')
    st.session_state['own'], st.session_state['import_error'] = None, None
    if upload is not None:
        try:
            own = validate_startup_csv(upload.getvalue())
            st.session_state['own'] = own
            st.session_state['month'] = own['mois'].iloc[-1]
        except DataError as exc:
            st.session_state['import_error'] = str(exc)
    reset()


def on_month() -> None:
    apply_model(reference_model())


if 'p_orders' not in st.session_state:
    st.session_state['startup_name'] = DEFAULT_NAME
    reset()

# ---------------------------------------------------------------- Sidebar : paramètres
with st.sidebar:
    st.markdown('### :material/storefront: Startup')
    st.text_input('Nom de la startup', key='startup_name', max_chars=60)
    with st.expander('Importer vos données (CSV)', icon=':material/upload_file:'):
        st.caption('Une ligne par mois, sans données clients. Les valeurs importées ne sont vérifiées par aucune source publique.')
        st.file_uploader('Fichier CSV mensuel', type=['csv'], key='upload', on_change=on_upload)
        if TEMPLATE_FILE.exists():
            st.download_button('Modèle CSV vide', TEMPLATE_FILE.read_bytes(), file_name=TEMPLATE_FILE.name,
                               mime='text/csv', icon=':material/download:')
    if st.session_state.get('import_error'):
        st.error(f'CSV refusé : {st.session_state["import_error"]}', icon=':material/error:')
    own = st.session_state.get('own')
    if own is not None:
        st.selectbox('Mois de référence', own['mois'].tolist(), key='month', on_change=on_month)

    st.markdown('### :material/tune: Modèle économique')
    for key, field, label, step in PARAMS:
        if field == 'orders':
            st.number_input(label, min_value=0, max_value=MAX_ORDERS, step=step, key=key)
        else:
            st.number_input(label, min_value=0.0, max_value=10_000_000.0, step=step, format='%.2f', key=key)

    st.markdown('### :material/bolt: Stress tests')
    st.number_input('Test A — hausse du transport (DT / commande)', min_value=0.0, max_value=50.0, step=0.5,
                    format='%.2f', key='s_delta')
    options = demand_options()
    if st.session_state.get('s_demand') not in options:
        st.session_state['s_demand'] = next(iter(options))
    st.selectbox('Test B — variation de la demande', list(options), key='s_demand',
                 help='Variations calculées sur le CSV BCT (ou sur votre import).')
    demand_kind, variation = options[st.session_state['s_demand']]
    if demand_kind == 'manual':
        st.slider('Baisse hypothétique des commandes (%)', 0.0, 100.0, step=0.5, key='s_manual')
        variation = -D(str(st.session_state['s_manual'])) / 100
    st.radio('Scénario simulé', list(SCENARIOS), key='s_scenario', horizontal=True,
             format_func=lambda k: {'A': 'A · Transport', 'B': 'B · Demande', 'C': 'C · Combinés'}[k],
             help='C applique simultanément les tests A et B.')
    st.button('Réinitialiser', icon=':material/restart_alt:', on_click=reset, width='stretch')

# ---------------------------------------------------------------- Calculs (moteur financier)
ss = st.session_state
model = Model(**{field: int(ss[key]) if field == 'orders' else D(str(ss[key])) for key, field, _, _ in PARAMS})
delta = D(str(ss['s_delta']))
results = scenario_matrix(model, variation, delta)
diag = diagnose(results, ss['s_scenario'])
initial, simulated = diag.initial, diag.simulated
name = re.sub(r'[\[\]*_`<>#|]', '', ss['startup_name']).strip() or DEFAULT_NAME
data_mode = (f'Données importées · {ss["month"]}' if own is not None else 'Données de démonstration')
demand_source = ss['s_demand']

report = build_report_html(ReportContext(name, data_mode, model, delta, demand_source, variation,
                                         results, diag, SOURCES, LIMITS))

# ---------------------------------------------------------------- En-tête
head, action = st.columns([4, 1], vertical_alignment='bottom')
with head:
    st.caption('DIAGNOSTIC FINANCIER · E-COMMERCE TUNISIE')
    st.title('Startup Stress-Test TN', anchor=False)
    st.markdown(':gray[Anticipez les risques. Mesurez leur impact. Prenez de meilleures décisions.]')
    mode_badge = f':green-badge[:material/upload_file: {data_mode}]' if own is not None \
        else f':orange-badge[:material/science: {data_mode}]'
    st.markdown(f':blue-badge[:material/storefront: {name}] {mode_badge} '
                f':gray-badge[:material/calendar_month: Référence BCT : avril – juin 2025] '
                f':violet-badge[:material/bolt: Scénario {ss["s_scenario"]} · {SCENARIO_LABELS[diag.scenario]}]')
with action:
    st.download_button('Télécharger le diagnostic', report.encode('utf-8'), type='primary',
                       file_name=f'diagnostic_{re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") or "startup"}.html',
                       mime='text/html', icon=':material/download:', width='stretch',
                       help='Rapport HTML imprimable (Fichier → Imprimer → Enregistrer en PDF).')

if model.orders and initial.unit_margin <= 0:
    st.error('La marge par commande est nulle ou négative dès la situation initiale : '
             'chaque commande supplémentaire aggrave la perte.', icon=':material/warning:')

tab_diag, tab_data = st.tabs([':material/monitoring: Diagnostic financier', ':material/dataset: Données & méthodologie'])

# ================================================================ Onglet 1 : Diagnostic financier
with tab_diag:
    dec = diag.decomposition
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        kpi_card('initial', ':material/account_balance_wallet:', 'Résultat initial', fmt_signed(initial.profit),
                 tone_of(initial.profit),
                 f'{fmt_orders(initial.orders)} cdes × {fmt_money(initial.unit_margin)} − {fmt_money(initial.fixed)}')
    with k2:
        kpi_card('simulated', ':material/bolt:', 'Résultat simulé', fmt_signed(simulated.profit),
                 tone_of(simulated.profit),
                 f'{fmt_orders(simulated.orders)} cdes × {fmt_money(simulated.unit_margin)} − {fmt_money(simulated.fixed)}')
    with k3:
        kpi_card('impact', ':material/trending_down:' if dec.total < 0 else ':material/trending_up:',
                 'Impact financier', fmt_signed(dec.total), tone_of(dec.total),
                 f'Volume {fmt_signed(dec.volume_effect)} · marge {fmt_signed(dec.margin_effect)}')
    with k4:
        be = simulated.breakeven
        reached = be is not None and simulated.orders >= be
        kpi_card('breakeven', ':material/flag:', 'Seuil de rentabilité',
                 'Non atteignable' if be is None else fmt_orders(be),
                 'green' if reached else 'red',
                 'Marge par commande nulle ou négative' if be is None
                 else f'commandes / mois · volume simulé {fmt_orders(simulated.orders)} · '
                      f'seuil initial {fmt_orders(initial.breakeven)}')

    with card('diagnostic'):
        t1, t2 = st.columns([3, 1], vertical_alignment='center')
        t1.subheader(':material/health_and_safety: Diagnostic de résistance financière', anchor=False)
        t2.markdown(f':{diag.status.tone}-badge[{diag.status.label}]')
        a, b = st.columns(2, gap='medium')
        with a:
            with card('q-a'):
                st.markdown('**A · Quel est l’état actuel ?**')
                st.markdown(f':{diag.status.tone}-badge[{diag.status.label}] '
                            f'Résultat mensuel simulé : **{fmt_signed(simulated.profit)}**.')
                st.caption(f'Situation initiale : {diag.initial_status.label.lower()} ({fmt_signed(initial.profit)}). '
                           'Statut déterminé uniquement par le signe du résultat calculé.')
        with b:
            with card('q-b'):
                st.markdown('**B · Pourquoi la situation a-t-elle changé ?**')
                st.markdown(nb(diag.change_text))
                st.caption(f'Décomposition exacte : effet volume {fmt_signed(dec.volume_effect)} '
                           f'+ effet marge {fmt_signed(dec.margin_effect)} = {fmt_signed(dec.total)}.')
        c, d = st.columns(2, gap='medium')
        with c:
            with card('q-c'):
                st.markdown('**C · À partir de quand devient-elle déficitaire ?**')
                for line in breakeven_text(diag.simulated_breakeven, simulated.fixed):
                    st.markdown(f'- {nb(line)}')
                ib = diag.initial_breakeven
                if ib.max_cost_increase is not None and ib.loss_buffer is not None and initial.orders:
                    st.caption(f'Tolérance de la situation initiale : déficit si le coût unitaire augmente de plus de '
                               f'{fmt_money(ib.max_cost_increase)} par commande, ou si plus de '
                               f'{fmt_orders(ib.loss_buffer)} commandes '
                               f'({fmt_percent(ib.loss_buffer_pct or 0).lstrip("+")}) sont perdues.')
        with d:
            with card('q-d'):
                st.markdown('**D · Comment retrouver l’équilibre ?**')
                if not diag.levers:
                    st.markdown(':green[:material/check_circle:] Aucun ajustement nécessaire : '
                                'le résultat simulé est positif ou nul.')
                for lever in diag.levers:
                    st.markdown(nb(f'**{lever.value}** · {lever.title}  \n{lever.detail}  \n'
                                   f':orange[:material/info: {lever.validation}]'))
                if diag.levers:
                    st.caption('Chaque piste suffit à elle seule, mathématiquement. Elle reste une hypothèse '
                               'tant qu’elle n’est pas validée sur le terrain.')

    g1, g2 = st.columns([3, 2], gap='medium')
    with g1:
        with card('chart-scenarios'):
            st.markdown('**Comparaison financière des scénarios**')
            st.caption('Résultat mensuel en DT · survolez une barre pour la valeur exacte.')
            chart_df = scenario_chart_data(results)
            # Clé liée aux données : rendu complet à chaque changement (évite l'erreur Vega « Unrecognized data set »).
            st.altair_chart(scenario_chart(chart_df), key=f'scenarios-{hash(tuple(chart_df["Résultat (DT)"]))}')
    with g2:
        with card('chart-demand'):
            st.markdown('**Évolution de la demande — paiements électroniques BCT**')
            if bct is None:
                st.error(f'Données BCT indisponibles : {bct_error}', icon=':material/error:')
            else:
                st.caption('Volumes nationaux en milliers ; en rouge, variation vs mois précédent.')
                st.altair_chart(demand_chart(demand_chart_data(bct)))
            st.caption(':material/info: Indicateur externe national, **pas** les commandes réelles de la startup.')

    with st.expander('Détail des quatre scénarios', icon=':material/table_chart:'):
        st.dataframe(pd.DataFrame([{
            'Scénario': SCENARIO_LABELS[n], 'Commandes': fmt_orders(r.orders),
            'Transport / cde': fmt_money(r.carrier_cost), 'Marge / cde': fmt_money(r.unit_margin),
            'Recettes': fmt_money(r.revenue), 'Coûts variables': fmt_money(r.variable_cost),
            'Charges fixes': fmt_money(r.fixed), 'Résultat': fmt_signed(r.profit),
            'Seuil (cdes)': fmt_orders(r.breakeven),
        } for n, r in results.items()]), hide_index=True, width='stretch')

# ================================================================ Onglet 2 : Données & méthodologie
with tab_data:
    l1, l2, l3 = st.columns(3)
    with l1:
        with card('legend-obs'):
            st.markdown(':blue-badge[:material/visibility: Données observées]')
            st.caption(f'Chiffres publiés par une source externe, contrôlés le {SOURCES_CHECKED}.')
    with l2:
        with card('legend-hyp'):
            st.markdown(':orange-badge[:material/science: Hypothèses de simulation]')
            st.caption('Valeurs choisies pour le cas d’étude ou saisies dans le panneau.')
    with l3:
        with card('legend-res'):
            st.markdown(':green-badge[:material/calculate: Résultats calculés]')
            st.caption('Produits par le moteur à partir des deux catégories précédentes.')

    with card('obs'):
        st.markdown(':blue-badge[Données observées] **Paiements électroniques — Banque Centrale de Tunisie**')
        if bct is None:
            st.error(f'{bct_error}\n\nFichier attendu : `{BCT_FILE}`', icon=':material/error:')
        else:
            df = demand_chart_data(bct)
            o1, o2 = st.columns([3, 2], gap='medium')
            with o1:
                published = (bct['valeur_bct_en_milliers'].map(lambda v: f'{v:,.1f}'.replace(',', ' ').replace('.', ','))
                             if 'valeur_bct_en_milliers' in bct else '—')
                st.dataframe(pd.DataFrame({
                    'Mois': df['label'], 'Paiements': df['Paiements'],
                    'Publié (milliers)': published,
                    'Variation': df['Variation'].replace('', '—'),
                }), hide_index=True, width='stretch')
            with o2:
                for v in BCT_VARIATIONS:
                    st.markdown(f'{v["label"]} : **{fmt_percent(v["variation"])}**  \n'
                                f':gray[({fmt_orders(v["apres"])} − {fmt_orders(v["avant"])}) / {fmt_orders(v["avant"])}]')
            st.caption('Ces paiements ne sont pas les commandes d’une startup ; leur variation est transposée par hypothèse. '
                       'Hors paiements électroniques effectués auprès de la poste (note BCT).')
            st.link_button('Ouvrir la source BCT', BCT_URL, icon=':material/open_in_new:')
        st.markdown('**Références sectorielles**')
        st.dataframe(pd.DataFrame([
            ('Panier moyen', '58,00 DT', 'TikTak PRO, janv.–juil. 2026', 'Moyenne des marchands de la plateforme'),
            ('Coût de livraison', '8,00 DT TTC', 'INTIGO, tarif public', 'Palier 501–1 500 petits colis / 30 jours'),
        ], columns=['Indicateur', 'Valeur', 'Source', 'Portée']), hide_index=True, width='stretch')
        st.caption(f'Valeurs contrôlées sur les pages sources le {SOURCES_CHECKED}. Elles peuvent évoluer.')

    with card('hyp'):
        st.markdown(':orange-badge[Hypothèses de simulation] **Paramètres utilisés dans le calcul**')
        ref = reference_model()
        rows = []
        for key, field, label, _ in PARAMS:
            current, base = getattr(model, field), getattr(ref, field)
            origin = f'Import CSV ({ss["month"]})' if own is not None else DEMO_ORIGIN.get(field, 'Hypothèse de démonstration')
            if val(current) != val(base):
                origin += ' → modifié dans la simulation'
            rows.append((label, fmt_orders(current) if field == 'orders' else fmt_money(current), origin))
        rows.append(('Test A — hausse du transport', f'+{fmt_money(delta)} / commande', 'Stress test'))
        rows.append(('Test B — variation de la demande', fmt_percent(variation), demand_source))
        st.dataframe(pd.DataFrame(rows, columns=['Paramètre', 'Valeur', 'Origine']), hide_index=True, width='stretch')

    with card('res'):
        st.markdown(':green-badge[Résultats calculés] **Sorties du moteur financier**')
        st.dataframe(pd.DataFrame([{
            'Scénario': SCENARIO_LABELS[n], 'Commandes': fmt_orders(r.orders),
            'Marge / cde': fmt_money(r.unit_margin), 'Recettes': fmt_money(r.revenue),
            'Résultat': fmt_signed(r.profit), 'Seuil (cdes)': fmt_orders(r.breakeven),
        } for n, r in results.items()]), hide_index=True, width='stretch')

    with st.expander('Formules utilisées', icon=':material/function:'):
        st.code('Marge / commande  = panier moyen + frais de livraison facturés\n'
                '                    − coût des produits − coût du transport − autres coûts variables\n'
                'Résultat mensuel  = commandes × marge / commande − charges fixes\n'
                'Variation (%)     = (volume après − volume avant) / volume avant × 100\n'
                'Commandes après   = arrondi(commandes initiales × (1 + variation))\n'
                'Seuil             = plafond(charges fixes / marge), si marge > 0', language=None)
        st.caption('Calculs en décimal exact (DT), sans arrondi intermédiaire. Les frais facturés au client sont une recette ; '
                   'le coût payé au transporteur est une charge, comptée une seule fois.')
    with st.expander('Décomposition de l’impact et pistes d’équilibre', icon=':material/account_tree:'):
        st.markdown('- **Effet volume** = (commandes simulées − initiales) × marge initiale\n'
                    '- **Effet marge** = commandes simulées × (marge simulée − marge initiale)\n'
                    '- Effet volume + effet marge = écart de résultat (identité exacte, charges fixes inchangées).\n'
                    '- **Commandes à perdre avant déficit** = commandes − seuil.\n'
                    '- **Hausse de coût supportable** = résultat / commandes (arrondi au centime inférieur).\n'
                    '- **Réduction de coût nécessaire** = déficit / commandes (arrondi au centime supérieur).')
    with st.expander('Limites de l’analyse', icon=':material/report:'):
        for item in LIMITS:
            st.markdown(f'- {item}')
