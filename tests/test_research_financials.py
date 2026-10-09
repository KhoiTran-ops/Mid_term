from datetime import datetime, UTC
from decimal import Decimal

import pytest

from stock_reports.analysis.financials import FinancialData, FinancialReview, Fact, financial_metrics, ratio
from stock_reports.domain.research import SourceReference


SOURCE = SourceReference(source_name='Tài liệu gốc',url='https://example.org/financials.pdf',retrieved_at=datetime.now(UTC),locator='Trang 12')


def test_ytd_conversion_respects_year_boundary_missing_values_and_roe_average():
    periods = [(2025,4),(2025,3),(2025,2),(2025,1),(2024,4)]
    facts = lambda values: {p:Fact(Decimal(v),SOURCE,'X') for p,v in zip(periods,values)}
    review = FinancialReview(symbol='HPG',periods=tuple(f'{y}Q{q}' for y,q in periods),scope='consolidated',currency='VND',
        money_multiplier=1,income_basis='ytd',cash_flow_basis='ytd',source=SOURCE)
    data = FinancialData('HPG',periods,dict(net_profit=facts(['100','75','45','20','80']),
        equity=facts(['1000','900','850','800','600']),assets=facts(['2000','1900','1800','1700','1400'])),review,[])
    assert data.quarter_value('net_profit',(2025,1)) == 20
    assert data.quarter_value('net_profit',(2025,4)) == 25
    assert data.ttm('net_profit',(2025,4)) == 100
    metrics = {m['label']:m for m in financial_metrics(data,'manufacturing')}
    assert metrics['ROE TTM']['value'] == Decimal('12.5')
    data.series['net_profit'].pop((2025,2))
    assert data.ttm('net_profit',(2025,4)) is None
    assert ratio(1,0) is None and ratio(1,-1) is None


def test_financial_company_does_not_receive_manufacturing_debt_or_cfo_score():
    p=(2026,2)
    data=FinancialData('SSI',[p],{k:{p:Fact(Decimal(v),SOURCE,k)} for k,v in
        dict(loans=40,equity=20,fvtpl=10,revenue=10,net_profit=2,brokerage=3,loan_income=4).items()},None,[])
    metrics={m['label']:m for m in financial_metrics(data,'securities')}
    assert metrics['Cho vay / vốn chủ sở hữu']['value'] == 2
    assert metrics['Tỷ trọng lãi cho vay và phải thu']['value'] == 40
    assert metrics['ROE TTM']['value'] is None
    assert 'Vay tài chính / vốn chủ sở hữu' not in metrics
    assert 'CFO / LNST cùng quý' not in metrics


def test_inconsistent_balance_blocks_ratios_and_valuation_even_with_review():
    from stock_reports.analysis.financials import validate_balance
    from stock_reports.analysis.valuation import evaluate_scenarios
    from tests.test_research_reports import review,scenarios
    p=(2026,2)
    data=FinancialData('SSI',[p],{k:{p:Fact(Decimal(v),SOURCE,k)} for k,v in
        dict(assets=5,equity=100,liabilities=80,loans=40,revenue=10,net_profit=2).items()},review(),[])
    validate_balance(data)
    assert p in data.invalid_balance_periods
    metrics={m['label']:m for m in financial_metrics(data,'securities')}
    assert metrics['Cho vay / vốn chủ sở hữu']['value'] is None
    assert metrics['Biên lợi nhuận sau thuế']['value']==20
    assert evaluate_scenarios(data,'securities',20,scenarios())['rows']==[]
