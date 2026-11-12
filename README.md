# Startup Stress-Test TN — version 2

Mini-prototype universitaire de stress testing financier pour une boutique e-commerce tunisienne.

## Ce que vous pourrez montrer

1. **Base tunisienne vérifiable** : trois observations mensuelles des paiements électroniques publiés par la Banque Centrale de Tunisie (BCT), avril–juin 2025.
2. **Données sectorielles réelles** : panier moyen de **58 DT** publié par TikTak PRO (janvier–juillet 2026) et tarif public **INTIGO : 8 DT** pour 501 à 1 500 petits colis sur 30 jours.
3. **Une boutique pilote fictive** : ShopTN Pilote. Les commandes (1 000/mois) et les coûts internes sont des hypothèses affichées.
4. **3 tests** : hausse du transport de +2 DT, baisse du volume de commandes (variation BCT choisie), et chocs simultanés. La situation de départ est affichée comme quatrième ligne de comparaison.
5. Calculs auditables : recettes, coûts variables, marge unitaire, résultat mensuel, seuil de rentabilité, commandes supplémentaires nécessaires.
6. Importation possible d'un CSV mensuel réel de l'entreprise (aucune donnée personnelle requise).

## Installer et lancer sur macOS (terminal VS Code)

```bash
cd ~/Downloads/startup_stress_test_tn_v2
python3 -m venv .venv                     # une seule fois
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Ouvrir `http://localhost:8501`. Arrêter avec `Ctrl+C`. Ou double-cliquer sur `lancer_mac.command`.

⚠️ Toujours lancer avec le Python du `.venv` : `python3 -m streamlit` sans activer le venv échoue
(`No module named streamlit`) car Streamlit n'est pas installé dans le Python système.

### Dépannage « page blanche »

- L'ancien CSS imposait un fond clair : en thème sombre (macOS, navigateur ou menu ⋮ → Settings de Streamlit),
  le texte devenait blanc sur blanc. Corrigé : aucune couleur imposée + thème clair par défaut (`.streamlit/config.toml`).
- Si la page reste vide : recharger sans cache (`Cmd+Shift+R`), vérifier que le terminal affiche
  « You can now view your Streamlit app », et que l'adresse correspond au port indiqué.

## Structure

- `app.py` : interface Streamlit (A. Présentation, B. Données tunisiennes, C. Simulations, D. Diagnostic).
- `finance.py` : moteur de calcul (Decimal, sans arrondi intermédiaire).
- `data_io.py` : chargement et validation des CSV, messages d'erreur explicites.
- `tests/` : tests du moteur, des données et de l'application (Streamlit AppTest).

## Résultats attendus — hypothèses de démonstration

- Panier : 58 DT (valeur de référence TikTak PRO)
- Livraison facturée au client : 8 DT **hypothèse**
- Coût produit : 40 DT **hypothèse**
- Publicité + emballage : 8 DT **hypothèse**
- Coût livraison prestataire : 8 DT (tarif public INTIGO applicable au palier décrit)
- Commandes par mois : 1 000 **hypothèse**
- Charges fixes par mois : 9 000 DT **hypothèse**

Marge unitaire : `(58 + 8) - (40 + 8 + 8) = 10 DT`.

| Scénario | Commandes | Coût transport | Résultat |
|---|---:|---:|---:|
| Situation initiale | 1 000 | 8 DT | +1 000 DT |
| Transport +2 DT | 1 000 | 10 DT | −1 000 DT |
| Baisse BCT avril→mai (−7,96 %) appliquée hypothétiquement | 920 | 8 DT | +200 DT |
| Deux chocs | 920 | 10 DT | −1 640 DT |

Après les deux chocs, le seuil est **1 125 commandes** ; il manque **205 commandes**. Avec les 920 commandes restantes, il faut une amélioration unitaire d'au moins **1,79 DT**, si la demande ne change pas. Ce sont des résultats mathématiques conditionnels, pas des prédictions.

## Importation de données d'une vraie startup

Télécharger et compléter `data/entreprise_3_mois_modele.csv` : une ligne par mois, sans données clients. Colonnes :

- `mois` : `AAAA-MM`
- `commandes_livrees` : nombre de commandes effectivement livrées
- `panier_moyen_dt` : moyenne du montant des produits par commande
- `livraison_facturee_dt` : montant moyen de livraison facturé au client
- `cout_produits_dt` : coût moyen des produits vendus par commande
- `publicite_emballage_dt` : coût variable publicitaire et emballage par commande
- `cout_transport_dt` : coût prestataire par commande
- `charges_fixes_dt` : charges fixes mensuelles

Le prototype acceptera les variations historiques de ce CSV comme scénarios supplémentaires. L'authenticité de ce fichier doit être vérifiée par l'équipe, car l'import n'est pas une preuve d'origine.

## Sources consultables

- BCT (table en milliers) : https://www.bct.gov.tn/bct/siteprod/tableau_statistique.jsp?params=PL202020
- TikTak PRO, baromètre 2026 : https://tiktakpro.com/blog/barometre-ecommerce-tunisie-2026
- INTIGO, tarif publié par palier : https://intigo.net/

## Limites méthodologiques

- Les paiements BCT sont un indicateur national : ils **ne sont pas** les commandes d'une startup, et le paiement à la livraison n'y est pas directement assimilable. Appliquer leur variation à ShopTN est une hypothèse de scénario.
- Le panier moyen TikTak PRO ne prouve pas que ShopTN vend au même montant ; la valeur sert de référence sectorielle.
- INTIGO facture selon le volume de colis sur les 30 derniers jours ; le tarif d'un scénario peut donc différer si le palier change. Le prototype conserve la valeur saisie pendant le test : elle doit être ajustée manuellement si les conditions de facturation changent.
- Les recettes et coûts sont traités comme flux unitaires simplifiés, sans ventilation détaillée de TVA, retours, amortissements, impôts ou acquisitions non incluses.
- Les simulations **ne prédisent ni faillite ni probabilité de succès**.

## Tests

```bash
source .venv/bin/activate
python -m pytest -q
```
