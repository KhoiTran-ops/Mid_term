"""Annual metrics are separate from quarterly/YTD inputs and verification."""
from decimal import Decimal
from pathlib import Path
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from stock_reports.analysis.financials import ALIASES, normalized_name, VerifiedFact
from stock_reports.domain.research import SourceReference


class AnnualReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    symbol: str
    years: tuple[int,...]
    scope: Literal['consolidated','standalone']
    currency: Literal['VND']
    money_multiplier: Decimal=Field(gt=0,allow_inf_nan=False)
    sources: tuple[SourceReference,...]=Field(min_length=1)
    notes_reviewed: bool=False
    review_note: str=Field(min_length=8)
    verified_facts: tuple[VerifiedFact,...]=()
    opening_balances: tuple[VerifiedFact,...]=()


def load_annual_review(settings,symbol):
    path=settings.root/'var/annual_reviews'/f'{symbol}.json'
    if not path.exists():return None
    review=AnnualReview.model_validate_json(path.read_text(encoding='utf-8-sig'))
    if review.symbol.upper()!=symbol.upper():raise ValueError('Annual review symbol mismatch')
    return review


def income_scale_inconsistent(raw,key,year,value,review=None):
    """Quarantine extreme source-scale anomalies, never guess a correction.

    This is a source-quality guard, not a bound on plausible business margins.
    Reviewed issuer facts take precedence before this guard is reached.
    """
    if key not in ('pretax_profit','net_profit','gross_profit') or value is None:
        return False
    revenue,_=annual_value(raw,'revenue',year,review)
    return revenue is not None and revenue != 0 and abs(value)>abs(revenue)*1000


def annual_income_anomalies(raw,review=None):
    issues=[]
    for year in sorted({r['fiscal_year'] for r in raw}):
        for key in ('pretax_profit','net_profit','gross_profit'):
            value,matches=annual_value(raw,key,year,review)
            values={Decimal(str(r['value_numeric'])) for r in matches if r['value_numeric'] is not None}
            if value is None and len(values)==1 and income_scale_inconsistent(raw,key,year,next(iter(values)),review):
                issues.append((year,key))
    return issues


def annual_value(raw,key,year,review=None):
    if review:
        verified=[f for f in review.verified_facts if f.period==str(year) and f.key==key]
        if len(verified)>1:raise ValueError('Duplicate verified annual metric')
        if verified:
            f=verified[0]
            return f.value_vnd/review.money_multiplier,[dict(fiscal_year=year,metric=key,
                statement_type=ALIASES[key][0],value_numeric=str(f.value_vnd/review.money_multiplier),
                source_url=str(f.source.url),imported_at=f.source.retrieved_at.isoformat(),
                sheet_name='BCTC gốc',source_row=0,workbook_sha256=f.source.locator,
                verified_source=f.source.model_dump(mode='json'))]
    statement,patterns=ALIASES[key]
    permitted=[statement,'CashFlowDirect'] if statement=='CashFlow' else [statement]
    candidates=[r for r in raw if r['fiscal_year']==year and r['value_numeric'] is not None]
    # Search fresh rows before the legacy workbook, using the same ordered aliases
    # as the quarterly mapper. Never mix cash-flow adjustments with annual profit.
    for fresh in (True,False):
        rows=[r for r in candidates if (r.get('statement_type') in permitted if fresh else not r.get('statement_type'))]
        if key=='inventory':
            parents=[r for r in rows if re.match(r'^[IVXLCDM]+[.)]\s*',r['metric'],re.I)
                     and normalized_name(r['metric'])=='hang ton kho']
            if parents:rows=parents
        if key=='equity':
            parents=[r for r in rows if re.match(r'^[BCD][.)]\s*',r['metric'],re.I)
                     and normalized_name(r['metric'])=='von chu so huu']
            if parents:rows=parents
        for pattern in patterns:
            matches=[r for r in rows if re.search(pattern,normalized_name(r['metric']))]
            numbers={Decimal(str(r['value_numeric'])) for r in matches}
            if numbers:
                value=next(iter(numbers)) if len(numbers)==1 else None
                if income_scale_inconsistent(raw,key,year,value,review):
                    return None,matches
                if key=='assets' and value is not None:
                    debt,_=annual_value(raw,'liabilities',year,review)
                    equity,_=annual_value(raw,'equity',year,review)
                    if debt is not None and equity is not None and value>0 and abs(value-debt-equity)>value*Decimal('.005'):
                        return None,matches
                return value,matches
    return None,[]
