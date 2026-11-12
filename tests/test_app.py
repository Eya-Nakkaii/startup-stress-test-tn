"""Exécute l'application Streamlit sans navigateur : démarrage Okkis, curseurs, synchronisation, cas d'étude."""
import re
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


def run_app():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def rerun(at):
    """AppTest 1.50 lit la valeur d'un segmented_control comme une liste : on la fournit sous cette forme."""
    group = at.button_group[0]
    if group._value is None:
        group.set_value([at.session_state['case_sel']])
    elif not isinstance(group._value, list):
        group.set_value([group._value])
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def html(at) -> str:
    return ' '.join(h.proto.body for h in at.get('html')).replace(' ', ' ')


def strip(at) -> list[str]:
    """Valeurs de la bande « Synthèse financière » : résultat initial, simulé, variation, seuil."""
    body = next(h.proto.body for h in at.get('html') if 'sttn-strip' in h.proto.body).replace(' ', ' ')
    return [' '.join(re.sub(r'<[^>]+>', ' ', v).split()) for v in re.findall(r'sttn-kpi-value">(.*?)</div></div>', body)]


def test_okkis_is_loaded_at_startup():
    at = run_app()
    assert not at.error
    assert at.number_input(key='p_basket').value == 89.0
    assert at.number_input(key='p_orders').value == 1000
    assert at.number_input(key='p_carrier').value == 8.0
    assert at.slider(key='s_delta').value == 2.0
    assert at.slider(key='s_drop').value == 7.96
    assert at.selectbox(key='s_source').value.startswith('BCT · avril → mai 2025')
    assert strip(at) == ['+2 000 DT/mois', '−720 DT/mois', '−2 720 DT/mois', '1 000 commandes']
    body = html(at)
    assert 'Cas Okkis : indicateurs publics et hypothèses financières modifiables' in body
    assert 'Il manque' in body and '>80<' in body


def test_sliders_update_results_and_sync_source():
    at = run_app()
    at.slider(key='s_delta').set_value(0.0); rerun(at)
    assert strip(at)[1] == '+1 120 DT/mois'                          # 920 × 11 − 9 000
    at.slider(key='s_drop').set_value(0.0); rerun(at)
    assert at.selectbox(key='s_source').value == 'Hypothèse personnalisée'   # curseur déplacé → hypothèse
    assert strip(at)[1] == '+2 000 DT/mois'
    bct_april_june = next(o for o in at.selectbox(key='s_source').options if 'avril → juin' in o)
    at.selectbox(key='s_source').set_value(bct_april_june); rerun(at)
    assert at.slider(key='s_drop').value == 9.38
    assert not at.exception


def test_editing_cells_updates_immediately():
    at = run_app()
    at.number_input(key='p_fixed').set_value(5000.0); rerun(at)
    assert strip(at)[0] == '+6 000 DT/mois'                          # 1 000 × 11 − 5 000
    at.number_input(key='p_basket').set_value(95.0); rerun(at)
    assert 'Modifié' in html(at) and 'panier moyen' in html(at)


def test_switch_case_keeps_edits_and_never_invents_data():
    at = run_app()
    at.number_input(key='p_fixed').set_value(5000.0); rerun(at)
    at.button_group[0].set_value(['custom']); rerun(at)
    assert at.number_input(key='p_basket').value is None             # rien n'est inventé
    assert any('Complétez les 7 cellules' in i.value for i in at.info)
    at.button_group[0].set_value(['okkis']); rerun(at)
    assert at.number_input(key='p_fixed').value == 5000.0             # modifications conservées
    at.button[0].click(); rerun(at)                                         # Réinitialiser
    assert at.number_input(key='p_fixed').value == 9000.0
    assert not at.exception


def test_custom_case_full_entry_matches_shoptn_regression():
    at = run_app()
    at.button_group[0].set_value(['custom']); rerun(at)
    for key, v in [('p_orders', 1000), ('p_basket', 58.0), ('p_product', 40.0), ('p_fee', 8.0),
                   ('p_carrier', 8.0), ('p_other', 8.0), ('p_fixed', 9000.0)]:
        at.number_input(key=key).set_value(v)
        rerun(at)
    assert not at.exception
    assert strip(at)[:2] == ['+1 000 DT/mois', '−1 640 DT/mois']
