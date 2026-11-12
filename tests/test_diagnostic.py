from decimal import Decimal as D

import pytest

from diagnostic import (breakeven_of, breakeven_text, decompose, diagnose, fmt_signed, recovery_levers,
                        status_of)
from finance import Model, calculate, demo_model, scenario_matrix, var_pct

SHOCK = var_pct(1549800, 1426500)  # BCT avril → mai 2025


def matrix(model=None):
    return scenario_matrix(model or demo_model(), SHOCK, D('2'))


@pytest.mark.parametrize('scenario,profit,breakeven,status', [
    ('A', '-1000', 1125, 'loss'),
    ('B', '200', 900, 'profit'),
    ('C', '-1640', 1125, 'loss'),
])
def test_diagnosis_per_scenario(scenario, profit, breakeven, status):
    d = diagnose(matrix(), scenario)
    assert d.initial.profit == D('1000') and d.initial.breakeven == 900
    assert d.simulated.profit == D(profit)
    assert d.simulated.breakeven == breakeven
    assert d.status.key == status
    assert d.decomposition.total == d.simulated.profit - d.initial.profit


def test_status_uses_only_sign_of_result():
    m = demo_model()
    assert status_of(calculate(m)).key == 'profit'
    assert status_of(calculate(m, orders=900)).key == 'breakeven'   # 900 × 10 − 9 000 = 0
    assert status_of(calculate(m, orders=899)).key == 'loss'


def test_combined_decomposition_is_exact():
    dec = decompose(*(matrix()[k] for k in ('Situation initiale', 'Deux chocs simultanés')))
    assert dec.volume_effect == D('-800')    # (920 − 1 000) × 10
    assert dec.margin_effect == D('-1840')   # 920 × (8 − 10)
    assert dec.total == D('-2640')


def test_change_text_uses_engine_numbers():
    text = diagnose(matrix(), 'C').change_text
    assert 'augmente de 2,00 DT par commande' in text
    assert 'de 1 000 à 920 commandes' in text
    assert 'diminue de 10,00 DT à 8,00 DT' in text
    assert 'de +1 000,00 DT à −1 640,00 DT' in text


def test_change_text_without_shock():
    r = scenario_matrix(demo_model(), D('0'), D('0'))
    assert diagnose(r, 'C').change_text.startswith('Aucun choc appliqué')


def test_breakeven_buffers():
    initial = breakeven_of(calculate(demo_model()))
    assert (initial.threshold, initial.gap, initial.loss_buffer) == (900, 100, 100)
    assert initial.loss_buffer_pct == D('0.1')
    assert initial.max_cost_increase == D('1.00')       # 1 000 DT / 1 000 commandes
    combined = breakeven_of(matrix()['Deux chocs simultanés'])
    assert combined.gap == -205 and combined.loss_buffer is None and combined.max_cost_increase is None
    assert 'il manque 205 commandes' in breakeven_text(combined, D('9000'))[1]


def test_recovery_levers_combined():
    levers = recovery_levers(matrix()['Deux chocs simultanés'])
    assert [l.value for l in levers] == ['+205 commandes / mois', '−1,79 DT / commande', '1 640,00 DT / mois']
    assert all(l.validation for l in levers)
    assert 'non garantie' in levers[2].validation


def test_no_levers_when_profitable():
    assert recovery_levers(matrix()['Baisse des commandes']) == []


def test_zero_or_negative_margin_is_handled():
    m = Model(100, D('10'), D('0'), D('20'), D('0'), D('0'), D('100'))   # marge −10 DT
    r = calculate(m)
    b = breakeven_of(r)
    assert b.threshold is None and b.gap is None
    assert 'Aucun volume' in breakeven_text(b, r.fixed)[0]
    assert recovery_levers(r)[0].value == 'Insuffisant seul'
    zero = calculate(Model(0, D('10'), D('0'), D('5'), D('0'), D('0'), D('100')))
    assert [l.title for l in recovery_levers(zero)] == ['Commandes supplémentaires', 'Ajustement à volume constant']


def test_signed_format():
    assert fmt_signed(D('1000')) == '+1 000,00 DT'
    assert fmt_signed(D('-1640')) == '−1 640,00 DT'
    assert fmt_signed(D('0')) == '0,00 DT'
