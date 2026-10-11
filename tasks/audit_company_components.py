"""Audit report components for every local issuer without filling missing values."""
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from stock_reports.analysis.annuals import annual_value, load_annual_review
from stock_reports.analysis.financials import load_financials, load_review
from stock_reports.analysis.profiles import detect_profile
from stock_reports.analysis.repository import ResearchRepository, VIETNAM
from stock_reports.core.config import Settings
from stock_reports.core.files import atomic_json

COMMON = ('assets', 'liabilities', 'equity', 'parent_equity', 'net_profit', 'parent_profit', 'cfo')
OPERATING = ('revenue', 'gross_profit', 'short_debt', 'long_debt', 'current_assets', 'current_liabilities')


def component_status(value, sources_verified):
    if value is None:
        return 'missing_or_conflicting'
    return 'source_verified' if sources_verified else 'available_needs_source_review'


def quarterly_value(data, key, period):
    value = data.value(key, period)
    if key == 'parent_equity' and value is None and period not in data.invalid_balance_periods:
        total = data.value('equity', period)
        minority = data.value('minority_equity', period)
        if total is not None and minority is not None:
            return total - minority
    if key in ('assets', 'equity', 'liabilities') and period in data.invalid_balance_periods:
        return None
    return value


def main():
    settings = Settings.from_root(ROOT)
    day = datetime.now(VIETNAM).date()
    counts = Counter(); companies = []
    with sqlite3.connect(settings.market_database, timeout=30) as db:
        universe = db.execute('SELECT symbol, MAX(company_name) FROM instruments GROUP BY symbol ORDER BY symbol').fetchall()
    for symbol, name in universe:
        try:
            quarterly_review_path = ROOT / 'var/financial_reviews' / f'{symbol}.json'
            review = load_review(quarterly_review_path) if quarterly_review_path.is_file() else None
            review_error = None
            try:
                data = load_financials(settings.market_database, symbol, review=review)
            except ValueError as error:
                review_error = type(error).__name__
                data = load_financials(settings.market_database, symbol)
                review = None
            profile = detect_profile(data, name or '')
            keys = list(COMMON)
            if profile == 'banking':
                keys.extend(('loans', 'deposits', 'interest_income_net', 'pretax_profit'))
            elif profile == 'securities':
                keys.extend(('revenue', 'brokerage', 'loan_income', 'investment_income', 'pretax_profit'))
            else:
                keys.extend(OPERATING)
            annual_review = load_annual_review(settings, symbol)
            repo = ResearchRepository(settings, day); raw = repo.annual(symbol)
            annual = []
            for year in range(2021, 2026):
                states = {}
                for key in keys:
                    value, matches = annual_value(raw, key, year, annual_review)
                    states[key] = component_status(value, bool(matches) and all(r.get('verified_source') for r in matches))
                annual.append(dict(year=year, components=states))
            quarterly = [dict(period=f'{year}Q{quarter}', components={key: component_status(quarterly_value(data, key, (year, quarter)), bool(review)) for key in keys})
                         for year, quarter in data.periods]
            annual_missing = sum(v == 'missing_or_conflicting' for row in annual for v in row['components'].values())
            quarter_missing = sum(v == 'missing_or_conflicting' for row in quarterly for v in row['components'].values())
            counts['companies'] += 1
            counts['annual_missing_components'] += annual_missing
            counts['quarterly_missing_components'] += quarter_missing
            counts['companies_with_all_required_annual_components'] += annual_missing == 0
            counts['companies_with_eight_quarters_and_all_required_components'] += len(quarterly) == 8 and quarter_missing == 0
            counts['companies_with_annual_source_review'] += annual_review is not None
            companies.append(dict(symbol=symbol, profile=profile, annual=annual, quarterly=quarterly,
                quarterly_review_error=review_error,
                annual_notes_reviewed=bool(annual_review and annual_review.notes_reviewed),
                quarterly_notes_reviewed=bool(review and review.notes_reviewed)))
        except Exception as error:
            companies.append(dict(symbol=symbol, error_type=type(error).__name__))
            counts['errors'] += 1
    payload = dict(checked_at=datetime.now(VIETNAM).isoformat(), summary=dict(counts),
        definition='Component presence and current mapping, not completeness of all statutory notes. Parent equity may use published equity minus published minority interest, as in report JSON. Bank/brokerage profiles exclude inapplicable industrial metrics. Published source zero is valid; missing/conflicting values remain missing.',
        companies=companies)
    atomic_json(settings.outputs_directory / 'COMPANY_COMPONENT_AUDIT.json', payload)
    print(json.dumps({k: v for k, v in payload.items() if k != 'companies'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
