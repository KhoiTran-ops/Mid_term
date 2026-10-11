from decimal import Decimal
import sqlite3

from stock_reports.analysis.annuals import annual_value, AnnualReview
from stock_reports.analysis.financials import load_financials, FinancialReview
from stock_reports.storage.market import MarketStore


SOURCE=dict(source_name='Issuer',url='https://www.vietcombank.com.vn/report.pdf',
    retrieved_at='2026-10-10T07:00:00Z',locator='Verified table')


def test_primary_cashflow_is_not_replaced_or_mixed_with_mislabelled_secondary(tmp_path):
    store=MarketStore(tmp_path/'data.db');store.initialize()
    for statement,name,number,source in [
        ('CashFlow','Lưu chuyển tiền thuần từ hoạt động kinh doanh',999,'https://cafef.vn/source'),
        ('CashFlowDirect','I. Tiền thuần từ/(sử dụng cho) hoạt động kinh doanh',106,'https://www.vietcombank.com.vn/report.pdf'),
        ('CashFlowDirect','Tiền thuần từ hoạt động kinh doanh trước những thay đổi về tài sản và vốn lưu động',26,'https://www.vietcombank.com.vn/report.pdf')]:
        order=1 if number==26 else 0
        # Save together to preserve both component rows in a statement.
        if order:continue
        rows=[dict(row_order=order,item_name=name,values={(2025,3):(str(number),number)})]
        if statement=='CashFlowDirect':rows.append(dict(row_order=1,
            item_name='Tiền thuần từ hoạt động kinh doanh trước những thay đổi về tài sản và vốn lưu động',values={(2025,3):('26',26)}))
        store.replace_financial_facts('VCB',statement,rows,source=source)
    assert load_financials(store.path,'VCB').value('cfo',(2025,3))==106
    store.replace_financial_facts('VCB','CashFlowDirect',[
        dict(row_order=0,item_name='Wrong',values={(2025,3):('888',888)})],source='https://cafef.vn/new')
    assert load_financials(store.path,'VCB').value('cfo',(2025,3))==106
    assert store.anomaly_count()==1


def test_annual_balance_error_is_not_scaled_by_guess_and_verified_override_has_provenance():
    raw=[dict(fiscal_year=2023,metric=name,statement_type='BSheet',value_numeric=value) for name,value in
         [('Tổng tài sản có','1839613198000000000000000'),('Tổng nợ phải trả','1674600532000000'),('Vốn chủ sở hữu','165012666000000')]]
    assert annual_value(raw,'assets',2023)[0] is None
    review=AnnualReview(symbol='VCB',years=(2023,),scope='consolidated',currency='VND',money_multiplier=1,
        sources=(SOURCE,),review_note='Core statement cross-checked; notes still pending',verified_facts=(dict(
            period='2023',key='assets',value_vnd='1839613198000000',source=SOURCE,reason='Read original audited PDF'),))
    value,rows=annual_value(raw,'assets',2023,review)
    assert value==Decimal('1839613198000000')
    assert rows[0]['verified_source']['source_name']=='Issuer'
    assert raw[0]['value_numeric']=='1839613198000000000000000'


def test_verified_quarter_metric_retains_source_raw_and_does_not_imply_notes_review(tmp_path):
    store=MarketStore(tmp_path/'data.db');store.initialize()
    store.replace_financial_facts('VCB','BSheet',[
        dict(row_order=0,item_name='Tổng nợ phải trả',values={(2026,2):('999',999)})],source='https://cafef.vn/source')
    review=FinancialReview(symbol='VCB',periods=('2026Q2',),scope='consolidated',currency='VND',money_multiplier=1,
        income_basis='quarter',source=SOURCE,verified_facts=(dict(period='2026Q2',key='liabilities',
        value_vnd=1004,source=SOURCE,reason='Issuer differs from secondary data'),))
    data=load_financials(store.path,'VCB',review=review)
    assert data.value('liabilities',(2026,2))==1004
    assert data.raw_rows[0]['value_numeric']==999
    assert data.fact('liabilities',(2026,2)).source.source_name=='Issuer'
    assert not data.review.notes_reviewed
