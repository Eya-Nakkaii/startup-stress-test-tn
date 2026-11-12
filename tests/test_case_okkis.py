"""Cas Okkis : données publiées + tarif de référence + hypothèses, et graphiques liés au moteur."""
import json
from decimal import Decimal as D

import pytest

from charts import curve_data, decomposition_data
from components import diagnosis_lines
from data_io import DataError, bct_variations, carrier_tier, case_model, load_bct, load_case
from diagnostic import breakeven_of, decompose, diagnose
from finance import apply_variation, calculate, scenario_matrix


def okkis():
    return case_model(load_case())


def bct_april_may():
    return next(v['variation'] for v in bct_variations(load_bct()) if v['label'] == 'Avril → Mai 2025')


def test_case_file_separates_facts_reference_and_hypotheses():
    case = load_case()
    assert case['nom'] == 'Okkis'
    assert case['publie']['panier_moyen_dt'] == 89
    assert case['publie']['taux_confirmation'] == 0.84
    assert case['publie']['source']['url'] == 'https://tiktakpro.com/blog/etude-de-cas-okkis-mode-tunisie'
    ref = case['reference_transport']
    assert ref['prix_retenu_dt'] == 8.0 and 'non un contrat' in ref['avertissement']
    assert [t['prix_dt'] for t in ref['paliers']] == [9.0, 8.0, 7.0, 6.5]
    assert 'ne représentent pas les finances réelles' in case['hypotheses']['note']
    # aucune donnée mensuelle Okkis inventée
    assert not any('historique' in k or 'mois' in k for k in case['publie'])


def test_okkis_model_uses_published_basket_and_reference_transport():
    m = okkis()
    assert (m.orders, m.basket, m.customer_delivery_fee, m.product_cost, m.carrier_cost, m.marketing_packaging,
            m.fixed) == (1000, D('89'), D('8'), D('70'), D('8'), D('8'), D('9000'))
    r = calculate(m)
    assert r.revenue / r.orders == D('97')           # 89 + 8
    assert r.variable_cost / r.orders == D('86')     # 70 + 8 + 8
    assert r.unit_margin == D('11')
    assert r.profit == D('2000')
    assert r.breakeven == 819                        # plafond(9 000 / 11)


@pytest.mark.parametrize('orders,increase,profit,breakeven', [
    (1000, '0', '2000', 819),
    (1000, '2', '0', 1000),
    (920, '0', '1120', 819),
    (920, '2', '-720', 1000),
])
def test_okkis_reference_scenarios(orders, increase, profit, breakeven):
    r = calculate(okkis(), orders=orders, carrier_increase=D(increase))
    assert r.profit == D(profit)
    assert r.breakeven == breakeven


def test_okkis_default_shock_matrix_and_diagnosis():
    results = scenario_matrix(okkis(), bct_april_may(), D('2'))
    assert [r.profit for r in results.values()] == [D('2000'), D('0'), D('1120'), D('-720')]
    d = diagnose(results, 'C')
    assert d.status.key == 'loss'
    lines = ' '.join(diagnosis_lines(d.simulated, d.simulated_breakeven))
    assert 'Déficit estimé' in lines and '720,00 DT' in lines
    assert '>80<' in lines                           # il manque 80 commandes (1 000 − 920)
    assert '+0,79 DT' in lines                  # 720 / 920 = 0,7826 → 0,79 (centime supérieur)


def test_transport_shock_alone_is_breakeven():
    d = diagnose(scenario_matrix(okkis(), D('0'), D('2')), 'C')
    assert d.status.key == 'breakeven'


def test_confirmation_rate_is_not_applied_to_volume():
    results = scenario_matrix(okkis(), D('0'), D('0'))
    assert results['Situation initiale'].orders == 1000


def test_carrier_tiers():
    tiers = load_case()['reference_transport']['paliers']
    assert carrier_tier(tiers, 500)['prix_dt'] == 9.0
    assert carrier_tier(tiers, 920)['prix_dt'] == 8.0
    assert carrier_tier(tiers, 1500)['prix_dt'] == 8.0
    assert carrier_tier(tiers, 1501)['prix_dt'] == 7.0
    assert carrier_tier(tiers, 20000)['prix_dt'] == 6.5


def test_curve_data_comes_from_engine():
    m = okkis()
    df = curve_data(m, D('2'))
    assert df['Baisse (%)'].iloc[0] == 0 and df['Baisse (%)'].iloc[-1] == 50 and len(df) == 101
    assert df['base'].iloc[0] == 2000 and df['choc'].iloc[0] == 0
    row = df[df['Baisse (%)'] == 8].iloc[0]           # 1 000 × 0,92 = 920 commandes
    assert row['Commandes'] == 920 and row['base'] == 1120 and row['choc'] == -720
    for _, r in df.sample(10, random_state=1).iterrows():
        n = apply_variation(1000, -D(str(r['Baisse (%)'])) / 100)
        assert r['choc'] == float(calculate(m, orders=n, carrier_increase=D('2')).profit)


def test_decomposition_data_sums_exactly():
    results = scenario_matrix(okkis(), bct_april_may(), D('2'))
    df = decomposition_data(decompose(results['Situation initiale'], results['Deux chocs simultanés']))
    assert list(df['Effet']) == ['Demande (1)', 'Transport (2)', 'Total']
    assert list(df['Montant (DT)']) == [-880, -1840, -2720]   # (920−1000)×11 ; 920×(9−11)
    assert df['Montant (DT)'][0] + df['Montant (DT)'][1] == df['Montant (DT)'][2]


def test_positive_diagnosis_shows_buffer():
    r = calculate(okkis())
    text = ' '.join(diagnosis_lines(r, breakeven_of(r)))
    assert 'Positif' in text and '>181<' in text      # 1 000 − 819


@pytest.mark.parametrize('mutate,msg', [
    (lambda c: c['publie'].pop('panier_moyen_dt'), 'Champ manquant'),
    (lambda c: c['hypotheses'].update(charges_fixes_dt=-1), 'invalides'),
    (lambda c: c['publie'].update(taux_confirmation=84), 'entre 0 et 1'),
])
def test_invalid_case_file(tmp_path, mutate, msg):
    case = load_case()
    mutate(case)
    p = tmp_path / 'cas.json'
    p.write_text(json.dumps(case))
    with pytest.raises(DataError, match=msg):
        load_case(p)


def test_missing_case_file(tmp_path):
    with pytest.raises(DataError, match='introuvable'):
        load_case(tmp_path / 'absent.json')
