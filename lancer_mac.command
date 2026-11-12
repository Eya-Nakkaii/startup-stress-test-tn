#!/bin/bash
# Double-clic depuis le Finder : crée l'environnement si besoin, installe les dépendances, lance l'app.
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install -q -r requirements.txt
.venv/bin/python -m streamlit run app.py
