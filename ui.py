"""Composants d'interface réutilisables : cartes, styles et graphiques.

Règle : aucune couleur de texte ni de fond n'est imposée (lisible en thème clair et sombre).
Les cartes sont éclaircies par `backdrop-filter`, qui donne un blanc pur sur le fond
#F5F7FB du thème clair et reste sombre en thème sombre.
"""
from __future__ import annotations

import re
from decimal import Decimal

import altair as alt
import pandas as pd
import streamlit as st

from diagnostic import SCENARIO_LABELS, fmt_signed
from finance import Result, fmt_money, fmt_percent

POSITIVE, NEGATIVE, SERIES, MUTED = '#16A34A', '#DC2626', '#2563EB', '#64748B'
FR_NUMBER = "replace(format(datum.value, ',.0f'), /,/g, ' ')"  # 1 500 au lieu de 1,500

CSS = """
<style>
.block-container {padding-top: 2.6rem; padding-bottom: 3rem; max-width: 1320px;}
[class*="st-key-card"] {
  backdrop-filter: brightness(1.05); -webkit-backdrop-filter: brightness(1.05);
  box-shadow: 0 1px 2px rgba(15, 23, 42, .05);
}
[class*="st-key-kpi"] h3 {padding: .1rem 0 0; font-size: 1.65rem; letter-spacing: -.01em;}
[class*="st-key-kpi"] [data-testid="stCaptionContainer"] p {margin-bottom: 0;}
section[data-testid="stSidebar"] h3 {font-size: .95rem; text-transform: uppercase; letter-spacing: .04em;}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def tone_of(x: Decimal) -> str:
    return 'green' if x > 0 else 'red' if x < 0 else 'orange'


def nb(text: str) -> str:
    """Espaces insécables dans les nombres (« 9 000,00 DT » ne se coupe pas en fin de ligne)."""
    return re.sub(r'(?<=\d) (?=\d|DT|%)', '\u00a0', text)


def kpi_card(key: str, icon: str, title: str, value: str, tone: str, note: str | None = None) -> None:
    """Carte KPI : titre, valeur colorée selon sa signification, courte explication."""
    with st.container(border=True, key=f'card-kpi-{key}'):
        st.markdown(f'{icon} **{title}**')
        st.subheader(f':{tone}[{nb(value)}]', anchor=False)
        if note:
            st.caption(nb(note))


def card(key: str):
    return st.container(border=True, key=f'card-{key}')


# ---------------------------------------------------------------- Graphique 1 : scénarios

def scenario_chart_data(results: dict[str, Result]) -> pd.DataFrame:
    """Une ligne par scénario, valeurs issues du moteur (aucune valeur saisie à la main)."""
    return pd.DataFrame([{
        'Scénario': SCENARIO_LABELS[name],
        'Résultat (DT)': float(r.profit),
        'Résultat': fmt_signed(r.profit),
        'Commandes': f'{r.orders:,}'.replace(',', ' '),
        'Marge / commande': fmt_money(r.unit_margin),
        'Statut': 'Bénéfice' if r.profit > 0 else 'Perte' if r.profit < 0 else 'Équilibre',
    } for name, r in results.items()])


def scenario_chart(df: pd.DataFrame) -> alt.LayerChart:
    order = list(df['Scénario'])
    base = alt.Chart(df).encode(
        x=alt.X('Scénario:N', sort=order, title=None,
                axis=alt.Axis(labelAngle=0, labelLimit=220, labelPadding=8, ticks=False, domain=False)),
        y=alt.Y('Résultat (DT):Q', title='Résultat mensuel (DT)',
                axis=alt.Axis(labelExpr=FR_NUMBER, tickCount=6, domain=False)),
        tooltip=['Scénario', 'Résultat', 'Commandes', 'Marge / commande'],
    )
    bars = base.mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4,
                         cornerRadiusBottomLeft=4, cornerRadiusBottomRight=4, size=46).encode(
        color=alt.Color('Statut:N', scale=alt.Scale(domain=['Bénéfice', 'Équilibre', 'Perte'],
                                                     range=[POSITIVE, '#D97706', NEGATIVE]),
                        legend=alt.Legend(title=None, orient='top', direction='horizontal')))
    above = base.mark_text(dy=-9, fontWeight=600, color=MUTED).encode(text='Résultat:N') \
        .transform_filter('datum["Résultat (DT)"] >= 0')
    below = base.mark_text(dy=11, fontWeight=600, color=MUTED).encode(text='Résultat:N') \
        .transform_filter('datum["Résultat (DT)"] < 0')
    zero = alt.Chart(pd.DataFrame({'y': [0]})).mark_rule(color=MUTED, strokeWidth=1.2).encode(y='y:Q')
    return (bars + zero + above + below).properties(height=330)


# ---------------------------------------------------------------- Graphique 2 : demande BCT

def demand_chart_data(bct: pd.DataFrame) -> pd.DataFrame:
    """Volumes lus dans le CSV BCT, ordre chronologique, variation vs mois précédent."""
    df = bct.sort_values('mois')[['mois', 'label', 'transactions_electroniques']].reset_index(drop=True)
    prev = df['transactions_electroniques'].shift()
    df['Paiements (milliers)'] = df['transactions_electroniques'] / 1000
    df['Paiements'] = df['transactions_electroniques'].map(lambda v: f'{int(v):,}'.replace(',', ' '))
    df['Variation'] = [
        '' if pd.isna(p) else fmt_percent((Decimal(int(c)) - Decimal(int(p))) / Decimal(int(p)))
        for c, p in zip(df['transactions_electroniques'], prev)]
    df['Étiquette'] = [f'{v:,.1f} k'.replace(',', ' ').replace('.', ',') for v in df['Paiements (milliers)']]
    return df


def demand_chart(df: pd.DataFrame) -> alt.LayerChart:
    order = list(df['label'])
    base = alt.Chart(df).encode(
        x=alt.X('label:N', sort=order, title=None, scale=alt.Scale(paddingOuter=0.45),
                axis=alt.Axis(labelAngle=0, ticks=False, domain=False, labelPadding=8)),
        y=alt.Y('Paiements (milliers):Q', title='Paiements électroniques (milliers)',
                scale=alt.Scale(zero=False, padding=44), axis=alt.Axis(labelExpr=FR_NUMBER, tickCount=5, domain=False)),
        tooltip=[alt.Tooltip('label:N', title='Mois'), alt.Tooltip('Paiements:N', title='Paiements'),
                 alt.Tooltip('Variation:N', title='Variation vs mois précédent')],
    )
    line = base.mark_line(color=SERIES, strokeWidth=2)
    points = base.mark_point(color=SERIES, filled=True, size=90)
    first = base.mark_text(dy=-16, fontWeight=600, color=MUTED).encode(text='Étiquette:N') \
        .transform_filter('datum.Variation == ""')
    values = base.mark_text(dy=18, fontWeight=600, color=MUTED).encode(text='Étiquette:N') \
        .transform_filter('datum.Variation != ""')
    changes = base.mark_text(dy=33, fontWeight=600, color=NEGATIVE).encode(text='Variation:N') \
        .transform_filter('datum.Variation != ""')
    return (line + points + first + values + changes).properties(height=330)
