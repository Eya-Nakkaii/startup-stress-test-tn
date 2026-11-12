"""Composants HTML légers de l'identité ST/TN (aucune couleur de texte ni de fond imposée)."""
from __future__ import annotations

import re
from decimal import Decimal
from html import escape
from pathlib import Path

import streamlit as st

from diagnostic import Breakeven, Status, fmt_orders, fmt_signed
from finance import Result, extra_orders_to_balance, extra_price_to_balance, fmt_money, fmt_percent

STYLES = Path(__file__).resolve().parent / 'styles.css'
NBSP = ' '


def inject_styles() -> None:
    st.html(f'<style>{STYLES.read_text(encoding="utf-8")}</style>')


def nb(text: str) -> str:
    """Espaces insécables dans les nombres (« 9 000,00 DT » ne se coupe pas)."""
    return re.sub(r'(?<=\d) (?=\d|DT|%)', NBSP, text)


def amount(x: Decimal, signed: bool = True) -> str:
    """Montant sans unité : « −1 640 » ; décimales affichées seulement si elles existent."""
    text = (fmt_signed(x) if signed else fmt_money(x)).removesuffix(' DT')
    if text.endswith(',00'):
        text = text[:-3]
    return mono(nb(text))


def mono(text: str) -> str:
    """Pour l'affichage en chasse fixe : espace fine entre groupes de chiffres (HTML)."""
    return re.sub(r'(?<=\d)[ \u00a0](?=\d)', '<span class="g"></span>', text)


def tone(x: Decimal) -> str:
    return 'sttn-pos' if x > 0 else 'sttn-neg' if x < 0 else ''


def brand(subtitle: str) -> None:
    st.html(f'<div class="sttn-brand"><span class="sttn-mark">ST<i>/</i>TN</span>'
            f'<span class="sttn-title">Financial Stress Analysis<small>{escape(subtitle)}</small></span></div>')


def zone_label(number: str, title: str, aside: str = '') -> None:
    st.html(f'<div class="sttn-zone"><span><b>{number}</b> — {escape(title)}</span><span>{aside}</span></div>')


def snapshot_strip(initial: Result, simulated: Result, status: Status, total: Decimal) -> None:
    tag_class = {'profit': 'sttn-pos', 'breakeven': '', 'loss': 'sttn-neg'}[status.key]
    tag = {'profit': 'Positif', 'breakeven': 'Équilibre', 'loss': 'Déficit'}[status.key]
    be = simulated.breakeven
    cells = [
        ('Résultat initial', '', f'<span class="{tone(initial.profit)}">{amount(initial.profit)}</span><small>DT/mois</small>'),
        ('Résultat simulé', f'<span class="sttn-tag {tag_class}">{tag}</span>',
         f'<span class="{tone(simulated.profit)}">{amount(simulated.profit)}</span><small>DT/mois</small>'),
        ('Variation financière', '', f'<span class="{tone(total)}">{amount(total)}</span><small>DT/mois</small>'),
        ('Seuil de rentabilité', f'<span>initial {nb(fmt_orders(initial.breakeven))}</span>',
         ('<span class="sttn-neg">non atteignable</span>' if be is None else
          f'<span class="{"sttn-pos" if simulated.orders >= be else "sttn-neg"}">{mono(fmt_orders(be))}</span>'
          f'<small>commandes</small>')),
    ]
    html = ''.join(f'<div class="sttn-kpi"><div class="sttn-kpi-label"><span>{label}</span>{aside}</div>'
                   f'<div class="sttn-kpi-value">{value}</div></div>' for label, aside, value in cells)
    st.html(f'<div class="sttn-strip" data-testid="sttn-strip">{html}</div>')


def diagnosis_lines(simulated: Result, b: Breakeven) -> list[str]:
    """Diagnostic court, entièrement calculé : état, résultat après chocs, commandes pour l'équilibre."""
    p = simulated.profit
    if p < 0:
        lines = [f'<b>Déficit estimé</b> : <span class="sttn-num sttn-neg">{nb(fmt_money(-p))}</span>/mois.']
        missing = extra_orders_to_balance(simulated)
        if missing is None:
            lines.append(f'Marge de {nb(fmt_money(simulated.unit_margin))} par commande : le volume seul ne peut pas '
                         'rétablir l’équilibre.')
        else:
            lines.append(f'Il manque <span class="sttn-num">{nb(fmt_orders(missing))}</span> commandes pour atteindre '
                         f'l’équilibre ({nb(fmt_orders(simulated.breakeven))}).')
        per_order = extra_price_to_balance(simulated)
        if per_order is not None:
            lines.append(f'Ou <span class="sttn-num">+{nb(fmt_money(per_order))}</span> de marge par commande, '
                         'à volume constant.')
    elif p == 0:
        lines = ['<b>Équilibre</b> : résultat nul.',
                 'Aucune commande ne peut être perdue sans passer en déficit.']
    else:
        lines = [f'<b>Positif</b> : <span class="sttn-num sttn-pos">{nb(fmt_signed(p))}</span>/mois.']
        if b.loss_buffer is not None:
            lines.append(f'Jusqu’à <span class="sttn-num">{nb(fmt_orders(b.loss_buffer))}</span> commandes '
                         f'({nb(fmt_percent(b.loss_buffer_pct or 0).lstrip("+"))}) peuvent être perdues avant déficit.')
    return lines


def diagnosis_box(simulated: Result, b: Breakeven) -> None:
    body = ''.join(f'<p>{line}</p>' for line in diagnosis_lines(simulated, b))
    st.html(f'<div class="sttn-diag">{body}</div>')
