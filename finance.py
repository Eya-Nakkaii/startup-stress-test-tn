"""Calculs déterministes pour un e-commerce tunisien.

Aucune valeur financière de startup n'est présentée comme une observation réelle.
Tous les calculs sont en DT en Decimal, sans arrondir les étapes intermédiaires.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

D = Decimal


def val(x: object) -> Decimal:
    try:
        n = D(str(x))
    except Exception as exc:
        raise ValueError(f"Nombre invalide : {x}") from exc
    if not n.is_finite():
        raise ValueError("Les valeurs doivent être finies")
    return n


def fmt_money(x: object) -> str:
    n = val(x).quantize(D('0.01'), rounding=ROUND_HALF_UP)
    return f"{n:,.2f}".replace(',', ' ').replace('.', ',') + ' DT'


def fmt_percent(x: object) -> str:
    n = (val(x) * 100).quantize(D('0.01'), rounding=ROUND_HALF_UP)
    return f"{n:+.2f}".replace('.', ',') + ' %'


def var_pct(initial: int, final: int) -> Decimal:
    if initial <= 0 or final < 0:
        raise ValueError('Les volumes historiques doivent être valides')
    return (D(final) - D(initial)) / D(initial)


def apply_variation(orders: int, pct: object) -> int:
    if not isinstance(orders, int) or orders < 0:
        raise ValueError('Le nombre de commandes doit être un entier non négatif')
    pct = val(pct)
    if pct < -1:
        raise ValueError('Une baisse ne peut dépasser 100 %')
    return int((D(orders) * (1+pct)).quantize(D('1'), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class Model:
    """Profil unitaire mensuel. Les montants sont en DT par commande, sauf `fixed` (DT/mois)."""
    orders: int
    basket: Decimal
    customer_delivery_fee: Decimal
    product_cost: Decimal
    marketing_packaging: Decimal
    carrier_cost: Decimal
    fixed: Decimal

    def __post_init__(self):
        if not isinstance(self.orders, int) or self.orders < 0:
            raise ValueError('Nombre de commandes incorrect')
        for f in ('basket','customer_delivery_fee','product_cost','marketing_packaging','carrier_cost','fixed'):
            if val(getattr(self, f)) < 0:
                raise ValueError(f'Valeur négative : {f}')


@dataclass(frozen=True)
class Result:
    orders: int
    revenue: Decimal
    variable_cost: Decimal
    unit_margin: Decimal
    fixed: Decimal
    profit: Decimal
    breakeven: int | None
    carrier_cost: Decimal


def calculate(m: Model, orders: int | None = None, carrier_increase: object = 0) -> Result:
    count = m.orders if orders is None else orders
    if not isinstance(count, int) or count < 0:
        raise ValueError('Nombre de commandes incorrect')
    increase = val(carrier_increase)
    carrier = val(m.carrier_cost) + increase
    if carrier < 0:
        raise ValueError('Le coût du transport ne peut pas être négatif')
    price = val(m.basket) + val(m.customer_delivery_fee)
    unit_cost = val(m.product_cost) + val(m.marketing_packaging) + carrier
    margin = price - unit_cost
    revenue = D(count) * price
    variable = D(count) * unit_cost
    fixed = val(m.fixed)
    profit = revenue - variable - fixed
    if fixed == 0:
        breakeven = 0 if margin >= 0 else None
    elif margin > 0:
        breakeven = int((fixed/margin).to_integral_value(rounding=ROUND_CEILING))
    else:
        breakeven = None
    return Result(count, revenue, variable, margin, fixed, profit, breakeven, carrier)


def extra_orders_to_balance(r: Result) -> int | None:
    if r.breakeven is None:
        return None
    return max(0, r.breakeven-r.orders)


def extra_price_to_balance(r: Result) -> Decimal | None:
    """Hausse minimale par commande en centimes, en gardant le volume constant."""
    if r.orders <= 0:
        return None
    if r.profit >= 0:
        return D('0')
    return ((-r.profit) / D(r.orders)).quantize(D('0.01'), rounding=ROUND_CEILING)


def scenario_matrix(m: Model, historical_variation: object, delivery_delta: object) -> dict[str, Result]:
    """Les quatre scénarios, dans l'ordre d'affichage."""
    after = apply_variation(m.orders, historical_variation)
    return {
        'Situation initiale': calculate(m),
        'Transport plus cher': calculate(m, carrier_increase=delivery_delta),
        'Baisse des commandes': calculate(m, orders=after),
        'Deux chocs simultanés': calculate(m, orders=after, carrier_increase=delivery_delta),
    }


def demo_model() -> Model:
    """Profil de démonstration ShopTN Pilote (fictif).

    Panier 58 DT : référence TikTak PRO ; transport 8 DT : tarif public INTIGO.
    Toutes les autres valeurs sont des hypothèses de démonstration.
    """
    return Model(1000, D('58'), D('8'), D('40'), D('8'), D('8'), D('9000'))
