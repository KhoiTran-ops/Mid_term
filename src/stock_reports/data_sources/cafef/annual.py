"""Download real annual statements with all original component rows."""
from dataclasses import asdict
import hashlib

from stock_reports.data_sources.cafef.client import CafeFError
from stock_reports.data_sources.cafef.parsers import parse_annual_financial_statement
from stock_reports.data_sources.cafef.sync import SyncResult, STATEMENT_TYPES


def sync_annual_financials(client, store, symbol, *, first_year=2021, last_year=2025, incremental=False):
    if first_year > last_year:
        raise ValueError('Invalid annual range')
    saved = rejected = requests = 0
    issues = []
    years = set(range(first_year, last_year + 1))
    available = {s: store.annual_statement_years(symbol,s) & years if incremental else set() for s in STATEMENT_TYPES}
    for statement in STATEMENT_TYPES:
        if available[statement] == years:continue
        # Both methods are kept separate, never summed. Do not fetch the alternate
        # presentation when one cash-flow method already covers the entire range.
        if statement == 'CashFlowDirect' and available['CashFlow'] == years:
            continue
        anchors=list(range(last_year, first_year - 1, -4))
        # Keep the oldest page's four-year window inside the requested range.
        # E.g. 2021-2025 needs anchors 2025 and 2024, not 2025 and 2021.
        # Older own-year routes may 404 while the same year exists as a
        # comparative column in the 2024 page. Never synthesize that column.
        oldest=min(last_year,first_year+3)
        anchors=list(dict.fromkeys(max(a,oldest) for a in anchors))
        attempted=set()
        while anchors:
            anchor=anchors.pop(0)
            if anchor in attempted:continue
            attempted.add(anchor)
            requests += 1
            try:
                html = client.get_annual_financial_html(symbol, statement, anchor)
            except (CafeFError, ValueError) as error:
                rejected += 1
                issues.append(dict(statement_type=statement, anchor_year=anchor,
                                   error_type=type(error).__name__,
                                   status_code=getattr(error, 'status_code', None)))
                continue
            facts = [{**f, 'values': {y: v for y, v in f['values'].items()
                                    if y in years and y not in available[statement]}}
                     for f in parse_annual_financial_statement(html)]
            numeric_years = {y for f in facts for y, pair in f['values'].items()
                             if pair[1] is not None}
            available[statement].update(numeric_years)
            if numeric_years:
                saved += store.replace_annual_statement(symbol, statement, facts,
                    source_url=('https://cafef.vn/du-lieu/BaoCaoTaiChinh_V2.aspx'
                        f'?quarter=0&symbol={symbol}&type={statement}&year={anchor}&showtype=1'),
                    response_sha256=hashlib.sha256(html.encode('utf-8')).hexdigest())
            else:
                rejected += 1
                issues.append(dict(statement_type=statement, anchor_year=anchor,
                                   error_type='NoAnnualNumericData'))
            if not anchors and available[statement]:
                # Four-year pages can omit an interior year's data even though
                # the same year is populated when requested as its own anchor.
                anchors.extend(sorted(years-available[statement]-attempted,reverse=True))
    return dict(symbol=symbol, **asdict(SyncResult('annual_financials', saved, rejected, requests,
        tuple(issues))), first_year=first_year, last_year=last_year,
        statement_years={s: sorted(v) for s, v in available.items()},
        missing_years={s: sorted(years-v) for s, v in {
            'BSheet': available['BSheet'], 'IncSta': available['IncSta'],
            'CashFlow': available['CashFlow'] | available['CashFlowDirect']}.items()})
