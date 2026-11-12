from decimal import Decimal as D
import pytest
from finance import (Model, calculate, demo_model, scenario_matrix, var_pct, apply_variation,
                     extra_orders_to_balance, extra_price_to_balance, fmt_money, fmt_percent)


def demo():
    return Model(1000,D('58'),D('8'),D('40'),D('8'),D('8'),D('9000'))


def test_demo_model_matches_reference_inputs():
    assert demo_model() == demo()


def test_reference_case():
    r = calculate(demo())
    assert (r.revenue,r.variable_cost,r.unit_margin,r.profit,r.breakeven) == (D('66000'),D('56000'),D('10'),D('1000'),900)


@pytest.mark.parametrize('orders,increase,profit,margin,breakeven', [
    (1000, '0', '1000', '10', 900),     # situation normale
    (1000, '2', '-1000', '8', 1125),    # transport +2 DT
    (920, '0', '200', '10', 900),       # 920 commandes
    (920, '2', '-1640', '8', 1125),     # 920 commandes et transport +2 DT
])
def test_reference_scenarios(orders, increase, profit, margin, breakeven):
    r = calculate(demo(), orders=orders, carrier_increase=D(increase))
    assert r.profit == D(profit)
    assert r.unit_margin == D(margin)
    assert r.breakeven == breakeven
    assert r.carrier_cost == D('8') + D(increase)
    # recettes - coûts variables - fixes = résultat (pas de mélange recettes/bénéfice)
    assert r.revenue - r.variable_cost - r.fixed == r.profit
    assert r.revenue == orders * D('66')


def test_3_scenarios():
    shock = var_pct(1549800,1426500)
    assert apply_variation(1000,shock) == 920
    results=scenario_matrix(demo(),shock,D('2'))
    assert list(results) == ['Situation initiale','Transport plus cher','Baisse des commandes','Deux chocs simultanés']
    assert results['Situation initiale'].profit == D('1000')
    assert results['Transport plus cher'].profit == D('-1000')
    assert results['Baisse des commandes'].profit == D('200')
    combined=results['Deux chocs simultanés']
    assert combined.profit == D('-1640')
    assert combined.breakeven == 1125
    assert extra_orders_to_balance(combined) == 205
    assert extra_price_to_balance(combined) == D('1.79')
    assert calculate(demo(), orders=920,carrier_increase=D('2')).revenue == D('60720')


def test_variation_formula():
    assert var_pct(100, 92) == D('-0.08')
    assert var_pct(100, 110) == D('0.1')
    with pytest.raises(ValueError):
        var_pct(0, 10)      # pas de division par zéro
    with pytest.raises(ValueError):
        var_pct(10, -1)


def test_other_historical_shocks():
    assert apply_variation(1000, var_pct(1426500, 1404400)) == 985
    assert apply_variation(1000, var_pct(1549800, 1404400)) == 906
    assert apply_variation(1000, D('-1')) == 0


def test_edge_cases():
    assert calculate(demo(), orders=0).profit == D('-9000')
    assert calculate(Model(100, D('10'), D('0'), D('10'), D('0'), D('0'), D('100'))).breakeven is None  # marge nulle
    assert calculate(Model(100, D('10'), D('0'), D('20'), D('0'), D('0'), D('100'))).breakeven is None  # marge négative
    assert calculate(Model(100, D('10'), D('0'), D('5'), D('0'), D('0'), D('0'))).breakeven == 0
    assert calculate(Model(0, D('10'), D('0'), D('5'), D('0'), D('0'), D('7'))).breakeven == 2  # plafond(7/5)
    with pytest.raises(ValueError):
        calculate(demo(), carrier_increase=D('-9'))
    with pytest.raises(ValueError):
        calculate(demo(), orders=-1)
    with pytest.raises(ValueError):
        apply_variation(10,D('-1.2'))
    with pytest.raises(ValueError):
        Model(100,D('-1'),D('8'),D('40'),D('8'),D('8'),D('9000'))
    with pytest.raises(ValueError):
        calculate(demo(), carrier_increase='nan')


def test_extra_orders_when_already_profitable():
    assert extra_orders_to_balance(calculate(demo())) == 0
    assert extra_price_to_balance(calculate(demo())) == D('0')


def test_formatting():
    assert fmt_money(D('-1640')) == '-1 640,00 DT'
    assert fmt_money(D('1.005')) == '1,01 DT'
    assert fmt_percent(var_pct(1549800, 1426500)) == '-7,96 %'
