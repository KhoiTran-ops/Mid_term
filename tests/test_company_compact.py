from datetime import date
from decimal import Decimal
import json

import pytest
from pydantic import ValidationError

from stock_reports.analysis.company_compact import has_data, prune_table
from stock_reports.analysis.company_template import block
from stock_reports.analysis.contracts import ReportBlock
from stock_reports.analysis.financials import FinancialData, Fact, FinancialReview, load_financials, normalized_name
from stock_reports.analysis.repository import ResearchRepository
from stock_reports.analysis.valuation import evaluate_scenarios
from stock_reports.analysis.market_fundamentals import provider_number, provider_metrics, load_market_snapshot, market_quote
from stock_reports.analysis.company_compact import profile_financial_keys, valuation_method_text, build_compact_company_document
from stock_reports.core.config import Settings
from stock_reports.storage.market import MarketStore
from tests.test_research_financials import SOURCE


def test_pruning_preserves_zero_and_removes_only_empty_data_axes():
    table=block('Test',('Metric','2024','2025'), [('Empty','Chưa đủ dữ liệu','-'),('Real zero','Chưa đủ dữ liệu','0')])
    result=prune_table(table)
    assert result.headers==('Metric','2025')
    assert result.rows==(('Real zero','0'),)
    assert has_data('0') and not has_data('—')
    assert prune_table(block('Empty',('Metric','Year'),[('X','Chưa đủ dữ liệu')])) is None


def test_accounting_equations_and_net_inventory_are_not_missing_or_gross(tmp_path):
    store=MarketStore(tmp_path/'market.db');store.initialize()
    store.replace_financial_facts('HPG','IncSta',[dict(row_order=0,
        item_name='Tổng lợi nhuận kế toán trước thuế (50 = 30 + 40)',values={(2026,2):('20',20)})],source='https://cafef.vn/source')
    store.replace_financial_facts('HPG','BSheet',[
        dict(row_order=0,item_name='IV. Hàng tồn kho',values={(2026,2):('90',90)}),
        dict(row_order=1,item_name='1. Hàng tồn kho',values={(2026,2):('100',100)})],source='https://cafef.vn/source')
    data=load_financials(store.path,'HPG')
    assert data.value('pretax_profit',(2026,2))==20
    assert data.value('inventory',(2026,2))==90
    assert normalized_name('50. Lợi nhuận kế toán trước thuế (50=30+40)')=='loi nhuan ke toan truoc thue'


def test_mixed_cashflow_revisions_do_not_create_a_false_quarter_ratio():
    review=FinancialReview(symbol='HPG',periods=('2026Q1','2026Q2'),scope='consolidated',currency='VND',
        money_multiplier=1,income_basis='quarter',cash_flow_basis='ytd',cash_flow_quarters_comparable=False,source=SOURCE)
    data=FinancialData('HPG',[(2026,2),(2026,1)],{'cfo':{(2026,1):Fact(Decimal(10),SOURCE,'CFO'),(2026,2):Fact(Decimal(30),SOURCE,'CFO')}},review,[])
    assert data.value('cfo',(2026,2))==30
    assert data.quarter_value('cfo',(2026,1))==10
    assert data.quarter_value('cfo',(2026,2)) is None


def test_verified_bvps_does_not_require_an_unverified_market_price():
    review=FinancialReview(symbol='HPG',periods=('2026Q2',),scope='consolidated',currency='VND',
        money_multiplier=1,income_basis='quarter',source=SOURCE,parent_equity_vnd=10000,shares_outstanding=100)
    data=FinancialData('HPG',[(2026,2)],{},review,[])
    result=evaluate_scenarios(data,'manufacturing',20,None)
    assert [(m['label'],m['value']) for m in result['metrics']]==[('BVPS hiện tại',Decimal(100))]
    assert result['current'] is None and result['target'] is None


def test_additional_chart_series_require_aligned_finite_values():
    ReportBlock(kind='chart',title='Actual',labels=('Q1','Q2'),values=(0,2),series=(('Profit',(None,1)),))
    with pytest.raises(ValidationError):
        ReportBlock(kind='chart',title='Wrong',labels=('Q1','Q2'),values=(0,2),series=(('Profit',(1,)),))
    with pytest.raises(ValidationError):
        ReportBlock(kind='chart',title='Wrong',labels=('Q1','Q2'),values=(0,2),series=(('Profit',(1,float('nan'))),))


def test_current_macro_respects_period_and_publication_cutoffs(tmp_path):
    (tmp_path/'config').mkdir()
    row=dict(metric='GDP_YOY',label='GDP',value=9.01,unit='%',period_label='9 tháng 2026',period_end='2026-09-30',
        source=SOURCE.model_copy(update={'published_at':SOURCE.retrieved_at.replace(year=2026,month=10,day=3)}).model_dump(mode='json'))
    (tmp_path/'config/macro_observations.json').write_text(json.dumps({'observations':[row]}),encoding='utf-8')
    settings=Settings.from_root(tmp_path)
    assert ResearchRepository(settings,date(2026,9,29)).macro_context()==[]
    assert ResearchRepository(settings,date(2026,10,2)).macro_context()==[]
    assert len(ResearchRepository(settings,date(2026,10,10)).macro_context())==1


def test_market_quote_displays_without_financial_review_or_recommendation():
    data=FinancialData('SSI',[(2026,2)],{},None,[])
    result=evaluate_scenarios(data,'securities',20,None,quote={'value_vnd':Decimal(20000)})
    assert result['current']==20000 and result['target'] is None
    assert len(result['metrics'])==1 and result['metrics'][0]['value']==20000


def test_external_price_unlocks_verified_book_multiple_not_a_target():
    review=FinancialReview(symbol='HPG',periods=('2026Q2',),scope='consolidated',currency='VND',
        money_multiplier=1,income_basis='quarter',source=SOURCE,parent_equity_vnd=10000,shares_outstanding=100)
    data=FinancialData('HPG',[(2026,2)],{},review,[])
    result=evaluate_scenarios(data,'manufacturing',20,None,quote={'value_vnd':Decimal(200)})
    assert next(m['value'] for m in result['metrics'] if m['label']=='P/B hiện tại')==2
    assert result['target'] is None


def test_provider_beta_code_is_pb_and_unknown_units_are_not_guessed():
    result=provider_metrics({'indicators':[
        {'Text':'P/B','Code':'Beta','Value':'1.21'},
        {'Text':'Beta','Code':'Beta','Value':'0.8'},
        {'Text':'EPS (nghìn đồng)','Code':'EPScoBan','Value':'-2.71'},
        {'Text':'BVPS','Code':'GiaTriSoSach','Value':'16.46'},
        {'Text':'Vốn hóa (tỷ đồng)','Code':'VonHoaThiTruong','Value':'171,822.83'}]})
    assert [(r['label'],r['value']) for r in result]==[
        ('P/B theo nguồn',Decimal('1.21')),('EPS cơ bản theo nguồn',Decimal(-2710)),
        ('Vốn hóa theo nguồn',Decimal('171822.83'))]
    assert provider_number('0')==0 and provider_number('-') is None
    assert provider_number('NaN') is None and provider_number('1,21') is None


def test_market_snapshot_cannot_be_backdated(tmp_path):
    folder=tmp_path/'var/market_fundamentals';folder.mkdir(parents=True)
    snapshot=dict(symbol='HPG',retrieved_at=SOURCE.retrieved_at.isoformat(),sources=[SOURCE.model_dump(mode='json')])
    (folder/'HPG.json').write_text(json.dumps(snapshot),encoding='utf-8')
    assert load_market_snapshot(Settings.from_root(tmp_path),'HPG',date(2000,1,1)) is None
    assert market_quote(None,ResearchRepository(Settings.from_root(tmp_path),date(2026,10,10)).cutoff) is None


def test_business_models_do_not_inherit_steel_rows_or_methods():
    assert 'inventory' not in profile_financial_keys('banking')
    assert 'deposits' in profile_financial_keys('banking')
    assert 'brokerage' in profile_financial_keys('securities')
    assert 'gross_profit' not in profile_financial_keys('securities')
    assert 'NAV' in valuation_method_text('real_estate')
    assert 'ROE' in valuation_method_text('banking')


def test_available_metrics_show_in_valuation_without_scenarios(tmp_path):
    from tests.test_company_template import CompanyRepo
    class Repo(CompanyRepo):
        def macro_context(self):return []
    settings=Settings.from_root(tmp_path);repo=Repo(settings);p=(2026,2)
    review=FinancialReview(symbol='ABC',periods=('2026Q2',),scope='consolidated',currency='VND',
        money_multiplier=1,income_basis='quarter',source=SOURCE,parent_equity_vnd=10000,shares_outstanding=100)
    data=FinancialData('ABC',[p],{},review,[])
    company=dict(company_name='Công ty thử nghiệm',exchange='HOSE',source_url=str(SOURCE.url),
        retrieved_at=SOURCE.retrieved_at,industry=dict(name='Nguyên vật liệu',sector_id='15',slug='nguyen-vat-lieu'))
    value=evaluate_scenarios(data,'manufacturing',20,None)
    doc=build_compact_company_document(settings,repo,company,data,'manufacturing',[],[],value,None,[])
    valuation=next(s for s in doc.sections if s.kind.value=='valuation')
    assert any(any(row[0]=='BVPS hiện tại' for row in b.rows) for b in valuation.blocks)
    assert doc.assessment=='Chưa đủ cơ sở khuyến nghị'
    assert all('HPG' not in f.text for s in doc.sections for f in s.findings)


def test_equity_total_is_not_confused_with_roman_subtotal(tmp_path):
    store=MarketStore(tmp_path/'market.db');store.initialize()
    store.replace_financial_facts('FPT','BSheet',[
        dict(row_order=0,item_name='D.VỐN CHỦ SỞ HỮU',values={(2025,1):('100',100)}),
        dict(row_order=1,item_name='I. Vốn chủ sở hữu',values={(2025,1):('99',99)})],source='https://cafef.vn/source')
    assert load_financials(store.path,'FPT').value('equity',(2025,1))==100
    from stock_reports.analysis.annuals import annual_value
    rows=[dict(fiscal_year=2025,metric='D.VỐN CHỦ SỞ HỮU',statement_type='BSheet',value_numeric=100),
          dict(fiscal_year=2025,metric='I. Vốn chủ sở hữu',statement_type='BSheet',value_numeric=99)]
    assert annual_value(rows,'equity',2025)[0]==100


def test_annual_extreme_source_value_is_quarantined_not_rescaled():
    from stock_reports.analysis.annuals import annual_value, annual_income_anomalies
    rows=[dict(fiscal_year=2022,metric='Cộng doanh thu hoạt động',statement_type='IncSta',value_numeric=6335823060000),
          dict(fiscal_year=2022,metric='IX. TỔNG LỢI NHUẬN KẾ TOÁN TRƯỚC THUẾ',statement_type='IncSta',value_numeric=21097033900000000),
          dict(fiscal_year=2022,metric='XI. LỢI NHUẬN KẾ TOÁN SAU THUẾ TNDN',statement_type='IncSta',value_numeric=1697693170000)]
    assert annual_value(rows,'pretax_profit',2022)[0] is None
    assert annual_value(rows,'net_profit',2022)[0]==1697693170000
    assert annual_income_anomalies(rows)==[(2022,'pretax_profit')]
    assert rows[1]['value_numeric']==21097033900000000
