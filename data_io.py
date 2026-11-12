"""Chargement et validation des fichiers CSV (série BCT et import d'une startup).

Toutes les erreurs sont levées en `DataError` avec un message lisible par l'utilisateur.
"""
from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

import pandas as pd

from finance import Model, val, var_pct

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'data'
BCT_FILE = DATA_DIR / 'bct_paiements_2025_avril_juin.csv'
TEMPLATE_FILE = DATA_DIR / 'entreprise_3_mois_modele.csv'

BCT_MONTHS = {'2025-04': 'Avril 2025', '2025-05': 'Mai 2025', '2025-06': 'Juin 2025'}
STARTUP_FIELDS = ['mois', 'commandes_livrees', 'panier_moyen_dt', 'livraison_facturee_dt',
                  'cout_produits_dt', 'publicite_emballage_dt', 'cout_transport_dt', 'charges_fixes_dt']


class DataError(ValueError):
    """Fichier de données absent ou invalide."""


def _read_csv(source, name: str) -> pd.DataFrame:
    try:
        return pd.read_csv(source)
    except FileNotFoundError as exc:
        raise DataError(f'Fichier introuvable : {name}') from exc
    except pd.errors.EmptyDataError as exc:
        raise DataError(f'Le fichier {name} est vide.') from exc
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise DataError(f'Le fichier {name} n’est pas un CSV lisible (séparateur virgule, UTF-8).') from exc


def load_bct(path: Path = BCT_FILE) -> pd.DataFrame:
    """Série BCT avril–juin 2025, triée par mois, avec contrôles de cohérence."""
    df = _read_csv(path, Path(path).name)
    missing = {'mois', 'transactions_electroniques'} - set(df.columns)
    if missing:
        raise DataError(f'Colonnes manquantes dans {Path(path).name} : {", ".join(sorted(missing))}')
    df = df.copy()
    df['mois'] = df['mois'].astype(str).str.strip()
    if sorted(df['mois']) != sorted(BCT_MONTHS) or len(df) != len(BCT_MONTHS):
        raise DataError('La série BCT doit contenir exactement avril, mai et juin 2025 (2025-04, 2025-05, 2025-06).')
    values = pd.to_numeric(df['transactions_electroniques'], errors='coerce')
    if values.isna().any() or (values <= 0).any() or not (values % 1 == 0).all():
        raise DataError('Les volumes BCT doivent être des entiers strictement positifs.')
    df['transactions_electroniques'] = values.astype('int64')
    if 'valeur_bct_en_milliers' in df.columns:
        thousands = pd.to_numeric(df['valeur_bct_en_milliers'], errors='coerce')
        if thousands.isna().any() or ((thousands * 1000).round() != df['transactions_electroniques']).any():
            raise DataError('Incohérence BCT : la valeur en milliers × 1 000 ne correspond pas au volume.')
    df['label'] = df['mois'].map(BCT_MONTHS)
    return df.sort_values('mois').reset_index(drop=True)


def bct_variations(df: pd.DataFrame) -> list[dict]:
    """Variations mois → mois et sur toute la période, calculées depuis la série chargée."""
    rows = list(df.itertuples(index=False))
    pairs = [(rows[i - 1], rows[i]) for i in range(1, len(rows))] + [(rows[0], rows[-1])]
    return [{
        'label': f'{a.label.split()[0]} → {b.label}',
        'avant': int(a.transactions_electroniques),
        'apres': int(b.transactions_electroniques),
        'variation': var_pct(int(a.transactions_electroniques), int(b.transactions_electroniques)),
    } for a, b in pairs]


def validate_startup_csv(raw: bytes) -> pd.DataFrame:
    """Valide un CSV mensuel importé (2 à 36 mois, aucune valeur manquante ou négative)."""
    data = _read_csv(io.BytesIO(raw), 'importé')
    missing = [f for f in STARTUP_FIELDS if f not in data.columns]
    if missing:
        raise DataError('Colonnes manquantes : ' + ', '.join(missing))
    data = data[STARTUP_FIELDS].copy()
    if not 2 <= len(data) <= 36:
        raise DataError(f'Le fichier contient {len(data)} ligne(s) : il en faut entre 2 et 36 (une par mois).')
    period = pd.to_datetime(data['mois'].astype(str).str.strip() + '-01', format='%Y-%m-%d', errors='coerce')
    if period.isna().any() or period.duplicated().any():
        raise DataError('La colonne « mois » doit contenir des mois distincts au format AAAA-MM.')
    data['mois'] = period.dt.strftime('%Y-%m')
    data['periode'] = period
    data = data.sort_values('periode').reset_index(drop=True)
    for field in STARTUP_FIELDS[1:]:
        data[field] = pd.to_numeric(data[field], errors='coerce')
        bad = data[field].isna() | ~data[field].map(lambda x: abs(x) < float('inf')) | (data[field] < 0)
        if bad.any():
            months = ', '.join(data.loc[bad, 'mois'])
            raise DataError(f'Valeur manquante, non numérique ou négative dans « {field} » ({months}).')
    if not (data['commandes_livrees'] % 1 == 0).all():
        raise DataError('Les commandes livrées doivent être des nombres entiers.')
    data['commandes_livrees'] = data['commandes_livrees'].astype('int64')
    return data


def startup_variations(data: pd.DataFrame) -> list[dict]:
    """Variations des commandes d'un mois au suivant (mois de départ à 0 commande ignorés)."""
    out = []
    for i in range(1, len(data)):
        a, b = int(data.at[i - 1, 'commandes_livrees']), int(data.at[i, 'commandes_livrees'])
        if a > 0:
            out.append({'label': f"{data.at[i - 1, 'mois']} → {data.at[i, 'mois']}",
                        'avant': a, 'apres': b, 'variation': var_pct(a, b)})
    return out


def model_from_row(row) -> Model:
    def dec(field: str) -> Decimal:
        return val(row[field])
    return Model(int(row['commandes_livrees']), dec('panier_moyen_dt'), dec('livraison_facturee_dt'),
                 dec('cout_produits_dt'), dec('publicite_emballage_dt'), dec('cout_transport_dt'),
                 dec('charges_fixes_dt'))
