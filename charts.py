"""Graphiques ST/TN (Altair). Chaque point est produit par le moteur `finance` ; rien n'est saisi à la main."""
from __future__ import annotations

from decimal import Decimal

import altair as alt
import pandas as pd

from diagnostic import Decomposition, fmt_signed
from finance import Model, apply_variation, calculate

TEAL, TEAL_INK, CORAL, CORAL_INK, MUTED = '#19B8A9', '#087D76', '#F16E83', '#C8435A', '#718383'
FR_NUMBER = "replace(format(datum.value, ',.0f'), /,/g, ' ')"   # 1 500 au lieu de 1,500
GRID = 'rgba(113,131,131,0.18)'


def _style(chart: alt.TopLevelMixin) -> alt.TopLevelMixin:
    return (chart.configure(background='transparent', padding={'left': 14, 'right': 8, 'top': 4, 'bottom': 4}).configure_view(strokeWidth=0, fill='transparent')
            .configure_axis(grid=True, gridColor=GRID, domain=False, ticks=False, labelColor=MUTED,
                            titleColor=MUTED, titleFontWeight='normal', titleFontSize=11, labelFontSize=11,
                            labelFont='IBM Plex Mono', labelPadding=6)
            .configure_legend(labelColor=MUTED, labelFontSize=11.5, symbolStrokeWidth=2.5, symbolSize=120,
                              columnPadding=22, labelOffset=6, labelLimit=0))


# ---------------------------------------------------------------- Courbe : résultat selon la baisse de demande

def curve_data(model: Model, delta: Decimal, max_drop: int = 50, step: Decimal = Decimal('0.5')) -> pd.DataFrame:
    """Résultat mensuel pour une baisse de 0 à `max_drop` %, au transport initial et après la hausse `delta`."""
    rows = []
    n = int(Decimal(max_drop) / step)
    for i in range(n + 1):
        drop = step * i
        orders = apply_variation(model.orders, -drop / 100)
        base = calculate(model, orders=orders)
        shock = calculate(model, orders=orders, carrier_increase=delta)
        rows.append({'Baisse (%)': float(drop), 'Commandes': orders,
                     'base': float(base.profit), 'choc': float(shock.profit),
                     'Résultat transport initial': fmt_signed(base.profit),
                     'Résultat transport + choc': fmt_signed(shock.profit)})
    return pd.DataFrame(rows)


def curve_chart(df: pd.DataFrame, base_label: str, shock_label: str,
                current_drop: float, current_profit: float, current_text: str) -> alt.TopLevelMixin:
    long = df.melt(id_vars=['Baisse (%)', 'Commandes'], value_vars=['base', 'choc'],
                   var_name='clé', value_name='Résultat (DT)')
    long['Série'] = long['clé'].map({'base': base_label, 'choc': shock_label})
    x = alt.X('Baisse (%):Q', title='Baisse de la demande', scale=alt.Scale(domain=[0, float(df['Baisse (%)'].max())], nice=False),
              axis=alt.Axis(labelExpr="datum.value == 0 ? '0 %' : '−' + datum.value + ' %'", values=list(range(0, 51, 5))))
    y = alt.Y('Résultat (DT):Q', title='Résultat mensuel (DT)', axis=alt.Axis(labelExpr=FR_NUMBER, tickCount=6))
    color = alt.Color('Série:N', scale=alt.Scale(domain=[base_label, shock_label], range=[TEAL, CORAL]),
                      legend=alt.Legend(title=None, orient='top', direction='horizontal'))

    hover = alt.selection_point(fields=['Baisse (%)'], nearest=True, on='pointerover', empty=False, clear='pointerout')
    lines = alt.Chart(long).mark_line(strokeWidth=2, interpolate='linear').encode(x=x, y=y, color=color)
    dots = alt.Chart(long).mark_point(filled=True, size=46).encode(
        x=x, y=y, color=color, opacity=alt.condition(hover, alt.value(1), alt.value(0)))
    tooltip = [alt.Tooltip('Baisse (%):Q', title='Baisse (%)', format='.1f'),
               alt.Tooltip('Commandes:Q', title='Commandes', format=',d'),
               alt.Tooltip('Résultat transport initial:N'), alt.Tooltip('Résultat transport + choc:N')]
    rule = alt.Chart(df).mark_rule(color=MUTED, strokeWidth=1).encode(
        x='Baisse (%):Q', opacity=alt.condition(hover, alt.value(0.55), alt.value(0)), tooltip=tooltip
    ).add_params(hover)
    zero = alt.Chart(pd.DataFrame({'y': [0]})).mark_rule(color=MUTED, strokeWidth=1, opacity=0.7).encode(y='y:Q')

    cur = pd.DataFrame([{'Baisse (%)': current_drop, 'Résultat (DT)': current_profit, 'txt': current_text}])
    cur_rule = alt.Chart(cur).mark_rule(color=CORAL_INK, strokeDash=[3, 3], strokeWidth=1).encode(x='Baisse (%):Q')
    cur_point = alt.Chart(cur).mark_point(shape='diamond', size=150, filled=True, color=CORAL_INK,
                                          stroke='white', strokeWidth=1.5).encode(x='Baisse (%):Q', y='Résultat (DT):Q')
    cur_text = alt.Chart(cur).mark_text(align='left', dx=10, dy=-12, font='IBM Plex Mono', fontSize=11.5,
                                        fontWeight=500, color=CORAL_INK).encode(x='Baisse (%):Q', y='Résultat (DT):Q', text='txt:N')
    return _style((zero + lines + cur_rule + rule + dots + cur_point + cur_text).properties(height=330))


# ---------------------------------------------------------------- Barres : décomposition de la variation

def decomposition_data(dec: Decomposition) -> pd.DataFrame:
    """Ordre de calcul : 1) demande à marge initiale, 2) transport sur le volume restant ; somme exacte."""
    rows = [('Demande (1)', dec.volume_effect), ('Transport (2)', dec.margin_effect), ('Total', dec.total)]
    return pd.DataFrame([{
        'Effet': name, 'Montant (DT)': float(v), 'Libellé': fmt_signed(v),
        'Type': ('Total ' if name == 'Total' else '') + ('gain' if v > 0 else 'perte' if v < 0 else 'nul'),
    } for name, v in rows])


def decomposition_chart(df: pd.DataFrame) -> alt.TopLevelMixin:
    """Barres horizontales : libellés à gauche, montants au bout des barres (pas de chevauchement)."""
    order = list(df['Effet'])
    lo, hi = min(0.0, df['Montant (DT)'].min()), max(0.0, df['Montant (DT)'].max())
    span = (hi - lo) or 1.0
    base = alt.Chart(df).encode(
        y=alt.Y('Effet:N', sort=order, title=None,
                axis=alt.Axis(grid=False, labelFont='DM Sans', labelFontSize=12, labelPadding=10,
                              minExtent=96, labelLimit=120)),
        x=alt.X('Montant (DT):Q', title=None, scale=alt.Scale(domain=[lo - .42 * span * (lo < 0), hi + .42 * span * (hi > 0)]),
                axis=alt.Axis(labelExpr=FR_NUMBER, tickCount=4)),
        tooltip=[alt.Tooltip('Effet:N'), alt.Tooltip('Libellé:N', title='Montant')],
    )
    bars = base.mark_bar(size=22, cornerRadius=2).encode(
        color=alt.Color('Type:N', legend=None, scale=alt.Scale(
            domain=['gain', 'perte', 'nul', 'Total gain', 'Total perte', 'Total nul'],
            range=[TEAL, CORAL, MUTED, TEAL_INK, CORAL_INK, MUTED])))
    pos = base.mark_text(align='left', dx=6, font='IBM Plex Mono', fontSize=11, color=MUTED).encode(text='Libellé:N') \
        .transform_filter('datum["Montant (DT)"] >= 0')
    neg = base.mark_text(align='right', dx=-6, font='IBM Plex Mono', fontSize=11, color=MUTED).encode(text='Libellé:N') \
        .transform_filter('datum["Montant (DT)"] < 0')
    zero = alt.Chart(pd.DataFrame({'x': [0]})).mark_rule(color=MUTED, strokeWidth=1, opacity=0.7).encode(x='x:Q')
    return _style((bars + zero + pos + neg).properties(height=170))
