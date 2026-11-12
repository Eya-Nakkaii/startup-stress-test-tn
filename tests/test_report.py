from datetime import datetime
from decimal import Decimal as D

from diagnostic import diagnose
from finance import demo_model, scenario_matrix, var_pct
from report import ReportContext, build_report_html


def test_report_contains_engine_results_and_sources():
    model = demo_model()
    results = scenario_matrix(model, var_pct(1549800, 1426500), D('2'))
    ctx = ReportContext('Ma <Startup>', 'Données de démonstration', model, D('2'), 'BCT avril → mai 2025',
                        var_pct(1549800, 1426500), results, diagnose(results, 'C'),
                        [('BCT', 'Paiements électroniques', 'https://www.bct.gov.tn/')], ['Limite 1'])
    html = build_report_html(ctx, generated=datetime(2026, 11, 12, 10, 0))
    assert html.startswith('<!doctype html>')
    assert 'Ma &lt;Startup&gt;' in html                  # nom échappé
    for expected in ['+1 000,00 DT', '−1 640,00 DT', '−2 640,00 DT', '1 125 commandes', '+205 commandes / mois',
                     '−1,79 DT / commande', 'Activité déficitaire', '-7,96 %', 'https://www.bct.gov.tn/',
                     'Limite 1', '12/11/2026 10:00']:
        assert expected in html, expected
