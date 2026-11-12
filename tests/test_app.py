"""Exécute l'application Streamlit sans navigateur et vérifie qu'aucune exception n'est levée."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


def run_app():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def metric(at, label):
    return [m.value for m in at.metric if m.label == label]


def test_app_renders_reference_results():
    at = run_app()
    assert not at.error
    assert [t.label for t in at.tabs] == ['A · Présentation', 'B · Données tunisiennes',
                                          'C · Simulations', 'D · Diagnostic financier']
    # Valeurs produites par le moteur (BCT avril→mai et +2 DT par défaut)
    assert metric(at, 'Résultat initial') == ['1 000,00 DT', '1 000,00 DT']
    assert metric(at, 'Résultat après simulation') == ['-1 640,00 DT', '-1 640,00 DT']
    assert metric(at, 'Différence') == ['-2 640,00 DT']
    assert metric(at, 'Commandes pour l’équilibre') == ['1 125']


def test_app_reacts_to_inputs():
    at = run_app()
    at.slider[0].set_value(0.0)                      # pas de hausse de transport
    at.selectbox[0].set_value('Aucune variation de demande')
    at.run()
    assert not at.exception
    assert metric(at, 'Résultat après simulation') == ['1 000,00 DT', '1 000,00 DT']


def test_app_handles_zero_margin():
    at = run_app()
    at.number_input(key='demo-product').set_value(100.0).run()
    assert not at.exception
    assert metric(at, 'Commandes pour l’équilibre') == ['Non atteignable']
