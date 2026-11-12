"""Exécute l'application Streamlit sans navigateur et vérifie qu'aucune exception n'est levée."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


def run_app():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def kpis(at):
    """Valeurs des quatre cartes KPI (sous-titres colorés), dans l'ordre."""
    return [s.value for s in at.subheader if s.value.startswith(':')][:4]


def test_app_layout_and_reference_kpis():
    at = run_app()
    assert not at.error
    assert len(at.tabs) == 2
    assert kpis(at) == [':green[+1\u00a0000,00\u00a0DT]', ':red[−1\u00a0640,00\u00a0DT]', ':red[−2\u00a0640,00\u00a0DT]', ':red[1\u00a0125]']
    md = ' '.join(m.value for m in at.markdown)
    assert 'Données de démonstration' in md and 'ShopTN Pilote' in md
    assert 'de 1\u00a0000 à 920 commandes' in md


def test_each_scenario_and_reset():
    at = run_app()
    at.radio(key='s_scenario').set_value('A').run()
    assert kpis(at)[1] == ':red[−1\u00a0000,00\u00a0DT]'
    at.radio(key='s_scenario').set_value('B').run()
    assert kpis(at)[1] == ':green[+200,00\u00a0DT]'
    assert kpis(at)[3] == ':green[900]'
    at.number_input(key='s_delta').set_value(0.0).run()
    at.selectbox(key='s_demand').set_value('Aucune variation de demande').run()
    assert kpis(at)[1] == ':green[+1\u00a0000,00\u00a0DT]'
    at.button[0].click().run()   # Réinitialiser
    assert not at.exception
    assert at.radio(key='s_scenario').value == 'C'
    assert kpis(at)[1] == ':red[−1\u00a0640,00\u00a0DT]'


def test_zero_margin_and_name():
    at = run_app()
    at.text_input(key='startup_name').set_value('Ma Boutique').run()
    at.number_input(key='p_product').set_value(100.0).run()
    assert not at.exception
    assert kpis(at)[3] == ':red[Non atteignable]'
    assert any('Ma Boutique' in m.value for m in at.markdown)


def test_manual_demand_drop():
    at = run_app()
    at.selectbox(key='s_demand').set_value('Variation manuelle (non observée)').run()
    at.slider(key='s_manual').set_value(50.0).run()
    assert not at.exception
    # 500 commandes × 8 DT − 9 000 DT
    assert kpis(at)[1] == ':red[−5\u00a0000,00\u00a0DT]'
