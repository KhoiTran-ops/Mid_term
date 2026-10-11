"""Audit the sourced HPG report inputs without collecting or changing source data."""
from collections import Counter
from datetime import datetime, UTC
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from stock_reports.analysis.annuals import load_annual_review, annual_value
from stock_reports.analysis.financials import load_review, load_financials
from stock_reports.core.config import Settings

QUARTER_KEYS = ('revenue', 'gross_profit', 'pretax_profit', 'net_profit',
                'assets', 'equity', 'short_debt', 'long_debt', 'inventory', 'cfo')
YEAR_KEYS = ('revenue', 'gross_profit', 'pretax_profit', 'net_profit',
             'assets', 'equity', 'liabilities')


def main():
    settings = Settings.from_root(ROOT)
    review = load_review(ROOT / 'var/financial_reviews/HPG.json')
    annual = load_annual_review(settings, 'HPG')
    data = load_financials(settings.market_database, 'HPG', period=(2026, 2), review=review)
    verified = {(f.period, f.key): f for f in review.verified_facts}
    missing = []
    quarters = []
    for period in sorted(data.periods):
        label = f'{period[0]}Q{period[1]}'
        values = {key: data.value(key, period) for key in QUARTER_KEYS}
        missing.extend(f'{label}:{key}' for key, value in values.items() if value is None)
        missing.extend(f'{label}:{key}:no_primary_fact' for key in QUARTER_KEYS
                       if (label, key) not in verified)
        assets, debt, equity = (data.value(key, period) for key in ('assets', 'liabilities', 'equity'))
        residual = assets - debt - equity
        quarters.append(dict(period=label, values_vnd=values,
            balance_residual_vnd=residual, balance_residual_pct=abs(residual)/assets*100,
            disclosure=review.period_disclosures[label]))
    years = []
    for year in range(2021, 2026):
        values = {key: annual_value([], key, year, annual)[0] for key in YEAR_KEYS}
        missing.extend(f'{year}:{key}' for key, value in values.items() if value is None)
        years.append(dict(year=year, values_vnd=values,
            balance_residual_vnd=values['assets']-values['liabilities']-values['equity']))
    duplicate_facts = [f'{period}:{key}' for (period, key), count in
        Counter((f.period, f.key) for f in review.verified_facts).items() if count > 1]
    manifest = json.loads((ROOT / 'var/issuer_disclosures/HPG/manifest.json').read_text(encoding='utf-8'))
    audit = dict(symbol='HPG', audited_at=datetime.now(UTC).isoformat(),
        scope='Main displayed financial indicators; not a full audit of all statement notes.',
        official_archived_documents=len(manifest),
        verified_quarter_facts=len(review.verified_facts), verified_annual_facts=len(annual.verified_facts),
        displayed_quarter_cells=len(QUARTER_KEYS)*len(quarters),
        displayed_annual_cells=len(YEAR_KEYS)*len(years),
        missing_displayed_financial_inputs=missing, duplicate_quarter_facts=duplicate_facts,
        invalid_balance_periods=sorted(data.invalid_balance_periods),
        quarters=quarters, annuals=years, shares_outstanding=review.shares_outstanding,
        bvps_vnd=review.parent_equity_vnd/review.shares_outstanding,
        cash_flow_basis=review.cash_flow_basis,
        cash_flow_quarters_comparable=review.cash_flow_quarters_comparable,
        notes_fully_reviewed=review.notes_reviewed and annual.notes_reviewed,
        price_unit_confirmed=review.price_multiplier is not None,
        eps_ttm_confirmed=review.eps_ttm_vnd is not None,
        remaining_groups=['Price units and valuation multiples/EPS', 'Full financial statement notes',
            'Independent operating forecasts 2026F-2028F', 'Cost of capital and terminal growth',
            'Comparable steel-company valuation and scenarios'])
    output = ROOT / 'outputs/HPG_REPORT_DATA_AUDIT.json'
    output.write_text(json.dumps(audit, ensure_ascii=False, indent=2,
        default=lambda value: str(value) if isinstance(value, Decimal) else value)+'\n', encoding='utf-8')
    print(json.dumps({k: audit[k] for k in ('official_archived_documents', 'verified_quarter_facts',
        'verified_annual_facts', 'displayed_quarter_cells', 'displayed_annual_cells',
        'missing_displayed_financial_inputs', 'duplicate_quarter_facts', 'invalid_balance_periods')},
        ensure_ascii=False))
    if missing or duplicate_facts or data.invalid_balance_periods:
        raise SystemExit('HPG displayed financial input audit failed')


if __name__ == '__main__':
    main()
