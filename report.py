"""Rapport de diagnostic autonome (HTML imprimable, « Enregistrer en PDF » depuis le navigateur)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape

from diagnostic import SCENARIO_LABELS, Diagnosis, breakeven_text, fmt_orders, fmt_signed
from finance import Model, Result, fmt_money, fmt_percent


@dataclass(frozen=True)
class ReportContext:
    startup: str
    data_mode: str            # « Données de démonstration » ou « Données importées (…) »
    model: Model
    transport_increase: object
    demand_source: str
    demand_variation: object
    results: dict[str, Result]
    diagnosis: Diagnosis
    sources: list[tuple[str, str, str]]   # (nom, description, url)
    limits: list[str]


CSS = """
body{font-family:Inter,-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#15243B;background:#F5F7FB;margin:0;}
main{max-width:900px;margin:32px auto;padding:32px 40px;background:#fff;border:1px solid #E2E8F0;border-radius:12px;}
h1{font-size:24px;margin:0 0 4px} h2{font-size:16px;margin:28px 0 10px;padding-bottom:6px;border-bottom:1px solid #E2E8F0}
.muted{color:#64748B;font-size:13px} table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid #EEF2F8} th{color:#64748B;font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:18px}
.kpi{border:1px solid #E2E8F0;border-radius:10px;padding:10px 12px}.kpi b{display:block;font-size:18px;margin-top:4px}
.pos{color:#15803D}.neg{color:#DC2626}.warn{color:#B45309}
.badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600;background:#EEF2F8}
li{margin:4px 0} @media print{body{background:#fff}main{border:0;margin:0;padding:0}}
"""


def _cls(x) -> str:
    return 'pos' if x > 0 else 'neg' if x < 0 else 'warn'


def build_report_html(ctx: ReportContext, generated: datetime | None = None) -> str:
    d, m = ctx.diagnosis, ctx.model
    when = (generated or datetime.now()).strftime('%d/%m/%Y %H:%M')
    e = escape
    params = [
        ('Commandes mensuelles', fmt_orders(m.orders)),
        ('Panier moyen', fmt_money(m.basket)),
        ('Frais de livraison facturés au client', fmt_money(m.customer_delivery_fee)),
        ('Coût des produits / commande', fmt_money(m.product_cost)),
        ('Coût de transport payé / commande', fmt_money(m.carrier_cost)),
        ('Autres coûts variables / commande', fmt_money(m.marketing_packaging)),
        ('Charges fixes mensuelles', fmt_money(m.fixed)),
    ]
    rows = ''.join(
        f'<tr><td>{e(SCENARIO_LABELS[n])}</td><td class="num">{fmt_orders(r.orders)}</td>'
        f'<td class="num">{fmt_money(r.carrier_cost)}</td><td class="num">{fmt_money(r.unit_margin)}</td>'
        f'<td class="num {_cls(r.profit)}">{fmt_signed(r.profit)}</td><td class="num">{fmt_orders(r.breakeven)}</td></tr>'
        for n, r in ctx.results.items())
    levers = ''.join(f'<li><b>{e(l.title)} : {e(l.value)}</b> — {e(l.detail)} <i>{e(l.validation)}</i></li>'
                     for l in d.levers) or '<li>Aucun ajustement nécessaire : le résultat simulé est positif ou nul.</li>'
    be = ''.join(f'<li>{e(t)}</li>' for t in breakeven_text(d.simulated_breakeven, d.simulated.fixed))
    ib = d.initial_breakeven
    tolerance = ''
    if ib.max_cost_increase is not None and ib.loss_buffer is not None:
        tolerance = (f'<li>Situation initiale : une hausse de coût de plus de {fmt_money(ib.max_cost_increase)} par commande '
                     f'ou une perte de plus de {fmt_orders(ib.loss_buffer)} commandes rend l’activité déficitaire.</li>')
    sources = ''.join(f'<li><b>{e(n)}</b> — {e(desc)} <span class="muted">{e(url)}</span></li>'
                      for n, desc, url in ctx.sources)
    limits = ''.join(f'<li>{e(t)}</li>' for t in ctx.limits)
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Diagnostic — {e(ctx.startup)}</title><style>{CSS}</style></head><body><main>
<p class="muted">Startup Stress-Test TN · rapport généré le {when}</p>
<h1>Diagnostic de résistance financière — {e(ctx.startup)}</h1>
<p><span class="badge">{e(ctx.data_mode)}</span> <span class="badge">Scénario simulé : {e(SCENARIO_LABELS[d.scenario])}</span>
<span class="badge {_cls(d.simulated.profit)}">{e(d.status.label)}</span></p>
<div class="kpis">
<div class="kpi"><span class="muted">Résultat initial</span><b class="{_cls(d.initial.profit)}">{fmt_signed(d.initial.profit)}</b></div>
<div class="kpi"><span class="muted">Résultat simulé</span><b class="{_cls(d.simulated.profit)}">{fmt_signed(d.simulated.profit)}</b></div>
<div class="kpi"><span class="muted">Impact financier</span><b class="{_cls(d.decomposition.total)}">{fmt_signed(d.decomposition.total)}</b></div>
<div class="kpi"><span class="muted">Seuil de rentabilité</span><b>{fmt_orders(d.simulated.breakeven)} commandes</b></div>
</div>
<h2>A. État actuel</h2><p>{e(d.status.label)} : résultat mensuel simulé de {fmt_signed(d.simulated.profit)}
(situation initiale : {e(d.initial_status.label.lower())}, {fmt_signed(d.initial.profit)}).</p>
<h2>B. Pourquoi la situation a changé</h2><p>{e(d.change_text)}</p>
<h2>C. Seuil de déficit</h2><ul>{be}{tolerance}</ul>
<h2>D. Comment retrouver l’équilibre</h2><ul>{levers}</ul>
<p class="muted">Pistes mathématiquement suffisantes, chacune prise isolément. Leur faisabilité doit être validée sur le terrain.</p>
<h2>Paramètres économiques</h2><table>{''.join(f'<tr><td>{e(k)}</td><td class="num">{v}</td></tr>' for k, v in params)}</table>
<h2>Stress tests appliqués</h2><table>
<tr><td>Test A — hausse du coût de transport</td><td class="num">+{fmt_money(ctx.transport_increase)} / commande</td></tr>
<tr><td>Test B — variation de la demande · {e(ctx.demand_source)}</td><td class="num">{fmt_percent(ctx.demand_variation)}</td></tr>
</table>
<h2>Scénarios simulés</h2><table><tr><th>Scénario</th><th class="num">Commandes</th><th class="num">Transport</th>
<th class="num">Marge / cde</th><th class="num">Résultat</th><th class="num">Seuil</th></tr>{rows}</table>
<h2>Sources et hypothèses</h2><ul>{sources}</ul><ul>{limits}</ul>
</main></body></html>"""
