"""Independent industry schema, source gates, pagination and Chromium export."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import pytest
from bs4 import BeautifulSoup
from pypdf import PdfReader
from stock_reports.reports.industry_stocklens.data import normalize,period_meta
from stock_reports.reports.industry_stocklens.quality import inspect
from stock_reports.reports.industry_stocklens.render import render_html,render_pdf,page_plan,PAGES,asset_fingerprint
from stock_reports.reports.industry_stocklens.charts import columns,number,stacked,horizontal

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def sample():return json.loads((ROOT/'config/industry/periods/plastics/2025-12.json').read_text(encoding='utf-8'))

@pytest.fixture
def minimal():
    return {'meta':dict(industry_id='banking',industry_name='Ngành ngân hàng',period_code='2026-Q3',period_label='Quý 3/2026',report_date='2026-10-11',language='vi',sources=[],attribution={'publisher':'StockLens','license_status':'own'})}

def codes(payload):return {f['code'] for f in inspect(payload)['flags']}

def test_reference_acceptance_values_and_known_quality_flags(sample):
    o=sample['domestic']['overview'];assert (o['revenue'],o['gdp_share'],o['volume'],o['cagr_revenue'],o['yoy_volume'])==(31,6.5,11.7,13.4,15.7)
    assert sum(x['pct'] for x in o['output_structure'])==100
    assert sample['global']['value_chain']['price_forecast']['series'][0]['values'][4]==940
    rows={x['ticker']:x for x in sample['companies']['table']['rows']}
    assert len(rows)==19 and rows['BMP']['market_cap']==14408 and rows['NTP']['net_income']==790
    assert rows['DPC']['net_income_yoy'] is None and rows['DPC']['net_income_prior']==-1
    assert {'share_total','unit_mismatch','text_number_mismatch','license_unknown'}<=codes(sample)
    assert 'schema' not in codes(sample) and 'money_scale' not in codes(sample)
    assert len(page_plan(sample))==16
    assert o['export_structure'][4]['derived'] and o['export_structure'][4]['formula']

def test_no_sample_in_other_industry_and_hide_empty_profiles(minimal):
    html=render_html(minimal);soup=BeautifulSoup(html,'html.parser')
    assert [p['key'] for p in page_plan(minimal)]==['01_summary','13_views_risks']
    assert not soup.select('[data-page="15_profiles"]')
    assert 'Nhựa' not in html and 'FPTS' not in html and 'net_income' not in html
    assert 'Chưa có' in html and 'Nguồn chưa cung cấp' in html
    assert 'scores' not in html and 'PASS_SCREEN' not in html

def test_numeric_null_zero_sign_semantic_colors(minimal):
    d=normalize(minimal);d['summary']['kpis']=[dict(label='Hiệu suất',value=0,unit='%',polarity='higher_good'),dict(label='Rủi ro',value=2,unit='%',polarity='higher_bad')]
    html=render_html(d)
    assert number(None)=='Chưa có' and number(0)=='0' and number(-12.34,1,True)=='-12,3' and number(12,1,True)=='+12'
    assert number(1000000000,0)=='1.000.000.000'
    assert 'bad' in html and '>0<' in html
    svg=columns([dict(label='Q1',value=-13.6,status='A'),dict(label='Q2',value=5.9,status='F')])
    assert '#C9363E' in svg and 'forecast-hatch' in svg and 'Q2F' in svg
    assert columns([])=='' and columns([dict(label='Q1',value=None,status='A')])==''
    assert '-7,7' in horizontal([dict(label='CAGR',cagr=-7.7)],'cagr')
    bars=horizontal([dict(label='A',value=-10),dict(label='B',value=30)])
    assert 'width:25.0%' in bars and 'width:75.0%' in bars and 'left:25.0%' in bars

def test_source_owned_views_and_targets_only(sample):
    d=deepcopy(sample);d['summary']['stances']=[dict(segment='UNSOURCED_SEGMENT',horizon='long',rating='UNSOURCED_RATING')]
    d['companies']['profiles'][0]['trading']['target_source']={}
    html=render_html(d)
    assert 'UNSOURCED_RATING' not in html and 'UNSOURCED_SEGMENT' not in html
    assert '74.100' not in html and '169.000' in html
    assert {'stance_source','target_source'}<=codes(d)
    assert 'Quan điểm của' in html and 'không phải khuyến nghị của StockLens' in html
    assert 'chưa xác nhận bản quyền' in html

def test_share_gate_no_fake_remainder_and_cagr(minimal):
    d=normalize(minimal);d['domestic']['overview']['output_structure']=[dict(name='A',pct=70),dict(name='B',pct=29)]
    assert 'share_total' in codes(d) and stacked(d['domestic']['overview']['output_structure'])==''
    before=deepcopy(d);html=render_html(d)
    assert 'CẦN KIỂM TRA' in html and d==before
    d['domestic']['outlook']['output_forecast'].update(start_value=100,end_value=200,n_years=2,cagr=10)
    assert {'cagr_mismatch','forecast_source'}<=codes(d)
    d['domestic']['overview']['output_structure'][1].update(pct=30,derived=True)
    assert 'derived_formula' in codes(d)

def test_unit_yoy_date_period_and_exchange_gates(sample):
    d=deepcopy(sample);r=d['companies']['table']['rows'][0]
    r.update(revenue_prior=100,revenue_yoy=0,period='2024',price_as_of='2025-12-11')
    d['units']['companies.table.rows.0.revenue']='triệu USD'
    d['meta']['exchange_catalog']['AAA']='HNX'
    d['companies']['profiles'][0]['trading']['as_of']='2026-01-01'
    assert {'money_scale','yoy_mismatch','period_mismatch','valuation_date','ticker_exchange','future_date'}<=codes(d)

@pytest.mark.parametrize('period',['2026-Q3','2025-12','2025','2026-9T'])
def test_change_period_only_json(minimal,period):
    label,end=period_meta(period);minimal['meta'].update(period_code=period,period_label=label)
    assert label in render_html(minimal) and end.year==int(period[:4])

def test_short_series_and_forecast_source(sample):
    p=sample['global']['value_chain']['price_forecast'];p['years']=['2024A','2025F']
    for s in p['series']:s['values']=s['values'][:2]
    assert 'series_length' not in codes(sample)
    del p['source'];assert 'forecast_source' in codes(sample)
    p['series'][0]['values'].append(1);assert 'series_length' in codes(sample)

def test_40plus_rows_auto_pagination_no_lost_tickers(sample):
    d=deepcopy(sample);d['companies']['table']['rows']=[{**sample['companies']['table']['rows'][0], 'ticker':f'X{i:02}'} for i in range(43)]
    plan=page_plan(d);tables=[p for p in plan if p['key']=='14_companies']
    assert len(tables)==3 and sum(len(p['rows']) for p in tables)==43
    assert [r['ticker'] for p in tables for r in p['rows']]==[f'X{i:02}' for i in range(43)]

def test_page_enable_disable_reorder(minimal):
    pages=['13_views_risks','01_summary'];html=render_html(minimal,pages=pages)
    assert [x['data-page'] for x in BeautifulSoup(html,'html.parser').select('.page')]==pages
    with pytest.raises(ValueError):render_html(minimal,pages=['bad'])
    with pytest.raises(ValueError):render_html(minimal,pages=['01_summary','01_summary'])

def test_schema_fail_closed_not_arithmetic_crash(sample):
    sample['domestic']['overview']['volume']='11.7'
    assert 'schema' in codes(sample)
    with pytest.raises(ValueError,match='JSON ngành'):render_html(sample)

def test_pdf_sample16_pages_offline_fonts_and_no_overflow(sample,tmp_path):
    output=render_pdf(sample,tmp_path/'sample.pdf',draft=True)
    assert len(PdfReader(output).pages)==16
    q=json.loads(output.with_suffix('.quality_report.json').read_text(encoding='utf-8'))
    assert q['status']=='needs_review' and q['overflow']==[] and len(q['pages'])==16
    text='\n'.join(p.extract_text() for p in PdfReader(output).pages)
    assert 'N/A' in text and '11.117' in text
    assert 'chưaxácnhậnbảnquyền' in ''.join(text.split())
    assert 'data:font/woff2;base64' in output.with_suffix('.html').read_text(encoding='utf-8')

def test_pdf_43_rows_short_series_and_long_name(sample,tmp_path):
    d=deepcopy(sample);d['meta']['exchange_catalog']={};d['companies']['table']['rows']=[{**sample['companies']['table']['rows'][0],'ticker':f'X{i:02}'} for i in range(43)]
    d['companies']['profiles']=d['companies']['profiles'][-1:]
    d['companies']['profiles'][0]['name']='Công ty cổ phần dự án sản xuất và thương mại công nghiệp công nghệ xanh có tên dài để kiểm tra cách xuống dòng trong báo cáo'
    d['companies']['profiles'][0]['series'][0]['points']=d['companies']['profiles'][0]['series'][0]['points'][:2]
    d['summary']['stances']=[]
    output=render_pdf(d,tmp_path/'long.pdf',draft=True)
    assert len(PdfReader(output).pages)==len(page_plan(d))
    text='\n'.join(p.extract_text() for p in PdfReader(output).pages)
    assert all(f'X{i:02}' in text for i in range(43))

def test_overflow_abort_keeps_prior_pdf_and_audit(minimal,tmp_path):
    minimal['summary']={'hero':{'title':'Dự án rất dài '*300}}
    out=tmp_path/'report.pdf';out.write_bytes(b'previous')
    with pytest.raises(ValueError,match='Tràn nội dung'):render_pdf(minimal,out)
    assert out.read_bytes()==b'previous'
    q=json.loads(out.with_suffix('.quality_report.json').read_text(encoding='utf-8'))
    assert q['overflow'][0]['industry']=='banking'

def test_immutable_examples_not_allowed_real_loader(tmp_path):
    from stock_reports.pipeline.industry_periods import load_period
    from stock_reports.core.config import Settings
    with pytest.raises(ValueError,match='minh họa'):load_period(Settings.from_root(ROOT),'plastics','2025-12',as_of=date(2026,10,11))

def test_document_isolated_and_fingerprint_stable(minimal):
    from stock_reports.reports.industry_stocklens.document import build_document
    from stock_reports.pipeline.research_reports import document_fingerprint
    doc=build_document(minimal)
    assert doc.stocklens_data is None and doc.macro_stocklens_data is None and doc.kind.value=='industry'
    assert doc.template_sha256==asset_fingerprint()
    assert document_fingerprint(doc)==document_fingerprint(build_document(minimal))

def test_web_publish_api_and_reuse_independent_industry(minimal,tmp_path,monkeypatch):
    from stock_reports.core.config import Settings
    from stock_reports.pipeline.research_reports import generate_reports,GenerationRequest,report_analysis
    from stock_reports.web.app import create_app
    from fastapi.testclient import TestClient
    import stock_reports.pipeline.industry_periods as periods
    s=Settings.from_root(tmp_path);s=__import__('dataclasses').replace(s,news_auto_update=False)
    (tmp_path/'config').mkdir();(tmp_path/'config/industry_stocklens.json').write_text('{"enabled":true}',encoding='utf-8')
    monkeypatch.setattr(periods,'load_period',lambda *a,**kw:deepcopy(minimal))
    req=GenerationRequest(kind='industry',industry_id='banking',industry_period='2026-Q3',as_of=date(2026,10,11))
    first=generate_reports(s,req)[0];second=generate_reports(s,req)[0]
    assert not first['reused'] and second['reused'] and first['report']['id']==second['report']['id']
    payload=report_analysis(s,first['report']['id'])
    assert 'macro' not in payload['inputs'] and payload['document']['stocklens_data'] is None
    app=create_app(s);client=TestClient(app)
    for endpoint in ('industry-data','industry-quality','pdf'):
        response=client.get(f'/api/reports/{first["report"]["id"]}/{endpoint}');assert response.status_code==200
    assert 'industry-quality' in client.get('/reports/'+first['report']['id']).text

def test_missing_43_rows_paginate_and_render(minimal,tmp_path):
    d=normalize(minimal)
    d['companies']['table']['rows']=[dict(ticker=f'B{i:02}',exchange='HOSE',group='Ngân hàng',market_cap=None,total_assets=None,revenue=None,revenue_yoy=None,net_income=None,net_income_yoy=None) for i in range(43)]
    for i in range(43):d['missing_reasons'][f'companies.table.rows.{i}']='Chưa đối chiếu đơn vị BCTC'
    plan=page_plan(d);tables=[p for p in plan if p['key']=='14_companies']
    assert len(tables)>=4 and sum(len(p['rows']) for p in tables)==43
    output=render_pdf(d,tmp_path/'missing-banks.pdf')
    assert len(PdfReader(output).pages)==len(plan)

def test_immutable_raw_snapshots(minimal,tmp_path):
    from stock_reports.pipeline.industry_periods import _write_snapshot
    from stock_reports.core.config import Settings
    s=Settings.from_root(tmp_path)
    digest=_write_snapshot(s,'test','https://example.org/source',{'value':1},'2026-10-11T00:00:00Z')
    assert digest==_write_snapshot(s,'test','https://example.org/source',{'value':1},'2026-10-11T01:00:00Z')
    meta=json.loads((tmp_path/'var/industry/raw/test'/f'{digest}.source.json').read_text(encoding='utf-8'))
    assert meta['retrieved_at']=='2026-10-11T00:00:00Z'
    new=_write_snapshot(s,'test','https://example.org/source',{'value':2},'2026-10-11T01:00:00Z')
    assert new!=digest

def test_profile_index_scopes_do_not_match_10_as_1(minimal):
    d=normalize(minimal)
    d['companies']['profiles']=[dict(name=f'Doanh nghiệp {i}',ticker=f'C{i:02}',exchange='HOSE',trading={'as_of':'2026-10-09','price':100},business_points=[],series=[]) for i in range(12)]
    d['companies']['profiles'][10]['trading']['as_of']='2026-10-12'
    d['meta']['sources']=[dict(id='one',name='Nguồn riêng mã 1',url='https://example.org/one',retrieved_at='2026-10-11T00:00:00Z'),dict(id='ten',name='Nguồn riêng mã 10',url='https://example.org/ten',retrieved_at='2026-10-11T00:00:00Z')]
    for i,sid in [(1,'one'),(10,'ten')]:d['provenance'][f'companies.profiles.{i}.trading.price']={'source_id':sid,'unit':'VND/cp'}
    soup=BeautifulSoup(render_html(d),'html.parser');first=soup.select_one('[data-page="15_profiles"]')
    assert 'CẦN KIỂM TRA' not in first.get_text()
    assert 'Nguồn riêng mã 1' in first.select_one('footer').get_text()
    assert 'Nguồn riêng mã 10' not in first.select_one('footer').get_text()
