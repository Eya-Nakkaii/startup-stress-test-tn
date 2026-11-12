from decimal import Decimal as D

import pytest

from data_io import (DataError, bct_variations, load_bct, model_from_row, startup_variations,
                     validate_startup_csv)
from finance import apply_variation, calculate

HEADER = ('mois,commandes_livrees,panier_moyen_dt,livraison_facturee_dt,cout_produits_dt,'
          'publicite_emballage_dt,cout_transport_dt,charges_fixes_dt\n')


def test_bct_file_loads_in_month_order():
    df = load_bct()
    assert list(df['mois']) == ['2025-04', '2025-05', '2025-06']
    assert list(df['transactions_electroniques']) == [1549800, 1426500, 1404400]


def test_bct_variations_are_computed_from_file():
    v = {x['label']: x for x in bct_variations(load_bct())}
    assert set(v) == {'Avril → Mai 2025', 'Mai → Juin 2025', 'Avril → Juin 2025'}
    assert apply_variation(1000, v['Avril → Mai 2025']['variation']) == 920
    assert apply_variation(1000, v['Avril → Juin 2025']['variation']) == 906


def test_missing_bct_file(tmp_path):
    with pytest.raises(DataError, match='introuvable'):
        load_bct(tmp_path / 'absent.csv')


@pytest.mark.parametrize('content,msg', [
    ('', 'vide'),
    ('mois,autre\n2025-04,1\n', 'Colonnes manquantes'),
    ('mois,transactions_electroniques\n2025-04,1\n2025-05,2\n', 'exactement'),
    ('mois,transactions_electroniques\n2025-04,1\n2025-05,\n2025-06,3\n', 'entiers'),
    ('mois,transactions_electroniques,valeur_bct_en_milliers\n2025-04,1000,1\n2025-05,2000,9\n2025-06,3000,3\n', 'Incohérence'),
])
def test_invalid_bct_files(tmp_path, content, msg):
    p = tmp_path / 'bct.csv'
    p.write_text(content)
    with pytest.raises(DataError, match=msg):
        load_bct(p)


def test_valid_startup_csv_is_sorted_and_usable():
    raw = (HEADER + '2025-06,900,58,8,40,8,8,9000\n2025-05,1000,58,8,40,8,8,9000\n').encode()
    data = validate_startup_csv(raw)
    assert list(data['mois']) == ['2025-05', '2025-06']
    assert calculate(model_from_row(data.iloc[0])).profit == D('1000')
    assert startup_variations(data)[0]['variation'] == D('-0.1')


@pytest.mark.parametrize('body,msg', [
    ('', '0 ligne'),                                              # modèle vide (en-tête seul)
    ('2025-05,1000,58,8,40,8,8,9000\n', '1 ligne'),
    ('2025-05,1000,58,8,40,8,8,9000\n2025-05,900,58,8,40,8,8,9000\n', 'distincts'),
    ('2025-05,1000,58,8,40,8,8,9000\n2025-06,,58,8,40,8,8,9000\n', 'commandes_livrees'),
    ('2025-05,1000,58,8,40,8,8,9000\n2025-06,900,-5,8,40,8,8,9000\n', 'panier_moyen_dt'),
    ('2025-05,1000.5,58,8,40,8,8,9000\n2025-06,900,58,8,40,8,8,9000\n', 'entiers'),
])
def test_invalid_startup_csv(body, msg):
    with pytest.raises(DataError, match=msg):
        validate_startup_csv((HEADER + body).encode())


def test_startup_csv_missing_columns():
    with pytest.raises(DataError, match='Colonnes manquantes'):
        validate_startup_csv(b'mois,commandes_livrees\n2025-05,1\n2025-06,2\n')


def test_startup_variation_skips_zero_base():
    raw = (HEADER + '2025-05,0,58,8,40,8,8,9000\n2025-06,900,58,8,40,8,8,9000\n').encode()
    assert startup_variations(validate_startup_csv(raw)) == []
