"""Diagnostic de résistance financière, entièrement dérivé du moteur `finance`.

Aucun score arbitraire : le statut dépend uniquement du signe du résultat calculé,
et chaque texte est construit à partir des nombres renvoyés par le moteur.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

from finance import Result, extra_orders_to_balance, extra_price_to_balance, fmt_money, fmt_percent, val

D = Decimal
CENT = D('0.01')

SCENARIOS = {  # clé du scénario simulé → nom dans `scenario_matrix`
    'A': 'Transport plus cher',
    'B': 'Baisse des commandes',
    'C': 'Deux chocs simultanés',
}
SCENARIO_LABELS = {
    'Situation initiale': 'Situation initiale',
    'Transport plus cher': 'Transport augmenté',
    'Baisse des commandes': 'Demande diminuée',
    'Deux chocs simultanés': 'Chocs combinés',
}


def fmt_signed(x: object) -> str:
    """+1 000,00 DT / −1 640,00 DT (signe toujours explicite)."""
    n = val(x)
    if n == 0:
        return fmt_money(0)
    return ('+' if n > 0 else '−') + fmt_money(abs(n))


def fmt_orders(n: int | None) -> str:
    return 'non atteignable' if n is None else f'{n:,}'.replace(',', ' ')


@dataclass(frozen=True)
class Status:
    key: str      # 'profit' | 'breakeven' | 'loss'
    label: str
    tone: str     # couleur sémantique Streamlit : green / orange / red


def status_of(r: Result) -> Status:
    if r.profit > 0:
        return Status('profit', 'Activité bénéficiaire', 'green')
    if r.profit == 0:
        return Status('breakeven', 'Seuil de rentabilité atteint', 'orange')
    return Status('loss', 'Activité déficitaire', 'red')


@dataclass(frozen=True)
class Decomposition:
    """Écart de résultat = effet volume + effet marge unitaire + effet charges fixes (exact)."""
    volume_effect: Decimal   # (commandes simulées − initiales) × marge initiale
    margin_effect: Decimal   # commandes simulées × (marge simulée − marge initiale)
    fixed_effect: Decimal    # −(charges fixes simulées − initiales)
    total: Decimal


def decompose(initial: Result, simulated: Result) -> Decomposition:
    volume = D(simulated.orders - initial.orders) * initial.unit_margin
    margin = D(simulated.orders) * (simulated.unit_margin - initial.unit_margin)
    fixed = -(simulated.fixed - initial.fixed)
    total = simulated.profit - initial.profit
    assert volume + margin + fixed == total, 'Décomposition incohérente'
    return Decomposition(volume, margin, fixed, total)


@dataclass(frozen=True)
class Breakeven:
    unit_margin: Decimal
    threshold: int | None          # seuil de rentabilité (commandes), None si inatteignable
    orders: int
    gap: int | None                # commandes actuelles − seuil
    loss_buffer: int | None        # commandes pouvant être perdues sans passer en déficit
    loss_buffer_pct: Decimal | None
    max_cost_increase: Decimal | None  # hausse de coût unitaire supportable à volume constant


def breakeven_of(r: Result) -> Breakeven:
    gap = None if r.breakeven is None else r.orders - r.breakeven
    buffer = gap if gap is not None and gap >= 0 else None
    buffer_pct = D(buffer) / D(r.orders) if buffer is not None and r.orders > 0 else None
    max_cost = None
    if r.orders > 0 and r.profit >= 0:
        max_cost = (r.profit / D(r.orders)).quantize(CENT, rounding=ROUND_FLOOR)
    return Breakeven(r.unit_margin, r.breakeven, r.orders, gap, buffer, buffer_pct, max_cost)


@dataclass(frozen=True)
class Lever:
    title: str
    value: str
    detail: str
    validation: str   # ce qui doit être validé hors calcul


def recovery_levers(r: Result) -> list[Lever]:
    """Pistes chiffrées pour revenir à un résultat ≥ 0 (vide si déjà ≥ 0)."""
    if r.profit >= 0:
        return []
    levers = []
    extra = extra_orders_to_balance(r)
    if extra is None:
        levers.append(Lever('Volume de commandes', 'Insuffisant seul',
                            f'La marge par commande ({fmt_money(r.unit_margin)}) ne couvre pas les coûts variables : '
                            'aucun volume ne permet l’équilibre sans agir sur les prix ou les coûts.',
                            'Agir d’abord sur la marge unitaire.'))
    else:
        levers.append(Lever('Commandes supplémentaires', f'+{fmt_orders(extra)} commandes / mois',
                            f'Passer de {fmt_orders(r.orders)} à {fmt_orders(r.breakeven)} commandes, '
                            f'à marge constante de {fmt_money(r.unit_margin)}.',
                            'Validation commerciale : rien ne garantit que la demande suivra.'))
    per_order = extra_price_to_balance(r)
    if per_order is not None:
        unit_cost = r.variable_cost / D(r.orders)
        levers.append(Lever('Réduction du coût unitaire', f'−{fmt_money(per_order)} / commande',
                            f'Ramener les coûts variables de {fmt_money(unit_cost)} à '
                            f'{fmt_money(unit_cost - per_order)} par commande (produits, transport, emballage), '
                            f'à volume constant de {fmt_orders(r.orders)} commandes.',
                            'Validation opérationnelle : négociation fournisseurs / transporteur.'))
    gap = -r.profit
    price_note = (f' ou une hausse du prix facturé de {fmt_money(per_order)} par commande'
                  if per_order is not None else '')
    levers.append(Lever('Ajustement à volume constant', f'{fmt_money(gap)} / mois',
                        f'Montant mensuel à combler : réduction des charges fixes de {fmt_money(gap)}{price_note}.',
                        'Une hausse de prix suppose l’acceptation des clients : non garantie, à tester commercialement.'))
    return levers


@dataclass(frozen=True)
class Diagnosis:
    scenario: str
    initial: Result
    simulated: Result
    status: Status
    initial_status: Status
    decomposition: Decomposition
    change_text: str
    initial_breakeven: Breakeven
    simulated_breakeven: Breakeven
    levers: list[Lever]


def change_text(initial: Result, simulated: Result, decomposition: Decomposition) -> str:
    parts = []
    delta_cost = simulated.carrier_cost - initial.carrier_cost
    if delta_cost:
        verb = 'augmente' if delta_cost > 0 else 'diminue'
        parts.append(f'Le coût de transport {verb} de {fmt_money(abs(delta_cost))} par commande')
    if simulated.orders != initial.orders:
        pct = (D(simulated.orders) - D(initial.orders)) / D(initial.orders) if initial.orders else None
        pct_txt = f' ({fmt_percent(pct)})' if pct is not None else ''
        parts.append(f'le volume passe de {fmt_orders(initial.orders)} à {fmt_orders(simulated.orders)} commandes{pct_txt}')
    if not parts:
        return (f'Aucun choc appliqué : le résultat mensuel reste de {fmt_signed(initial.profit)}.')
    sentence = ' et '.join(parts)
    sentence = sentence[0].upper() + sentence[1:] + '. '
    if simulated.unit_margin != initial.unit_margin:
        sentence += f'La marge unitaire diminue de {fmt_money(initial.unit_margin)} à {fmt_money(simulated.unit_margin)}. ' \
            if simulated.unit_margin < initial.unit_margin else \
            f'La marge unitaire augmente de {fmt_money(initial.unit_margin)} à {fmt_money(simulated.unit_margin)}. '
    else:
        sentence += f'La marge unitaire reste de {fmt_money(initial.unit_margin)}. '
    sentence += (f'Le résultat mensuel passe de {fmt_signed(initial.profit)} à {fmt_signed(simulated.profit)} '
                 f'(effet volume {fmt_signed(decomposition.volume_effect)}, '
                 f'effet marge {fmt_signed(decomposition.margin_effect)}).')
    return sentence


def diagnose(results: dict[str, Result], scenario: str) -> Diagnosis:
    """`results` vient de `finance.scenario_matrix` ; `scenario` est 'A', 'B' ou 'C'."""
    initial = results['Situation initiale']
    simulated = results[SCENARIOS[scenario]]
    dec = decompose(initial, simulated)
    return Diagnosis(
        scenario=SCENARIOS[scenario],
        initial=initial,
        simulated=simulated,
        status=status_of(simulated),
        initial_status=status_of(initial),
        decomposition=dec,
        change_text=change_text(initial, simulated, dec),
        initial_breakeven=breakeven_of(initial),
        simulated_breakeven=breakeven_of(simulated),
        levers=recovery_levers(simulated),
    )


def breakeven_text(b: Breakeven, fixed: Decimal) -> list[str]:
    """Phrases de la question C, pour un scénario donné."""
    if b.threshold is None:
        return [f'Marge contributive de {fmt_money(b.unit_margin)} par commande : nulle ou négative, '
                f'elle ne peut pas couvrir {fmt_money(fixed)} de charges fixes. Aucun volume ne permet l’équilibre.']
    lines = [f'Marge contributive : {fmt_money(b.unit_margin)} par commande ; '
             f'seuil = plafond({fmt_money(fixed)} / {fmt_money(b.unit_margin)}) = {fmt_orders(b.threshold)} commandes.']
    if b.gap is not None and b.gap >= 0:
        lines.append(f'Volume actuel {fmt_orders(b.orders)} commandes : {fmt_orders(b.loss_buffer)} commandes '
                     f'({fmt_percent(b.loss_buffer_pct or 0).lstrip("+")} du volume) peuvent être perdues avant déficit.')
    else:
        lines.append(f'Volume actuel {fmt_orders(b.orders)} commandes : il manque {fmt_orders(-b.gap)} commandes '
                     'pour atteindre le seuil.')
    return lines
