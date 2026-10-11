"""Period-specific macro contracts, quality flags and offline pagination."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import pytest
from bs4 import BeautifulSoup
from pypdf import PdfReader
from stock_reports.reports.macro_stocklens.data import normalize,period_meta,set_value
from stock_reports.reports.macro_stocklens.quality import inspect,validate_schema
from stock_reports.reports.macro_stocklens.render import render_html,render_pdf,number,selected_pages,PAGES
from stock_reports.reports.macro_stocklens.charts import chart,pmi_scale
from stock_reports.pipeline.macro_periods import parse_nso,fetch_pmi,fetch_licensed_json
from stock_reports.core.config import Settings

@pytest.fixture
def payload():
    d=normalize({'meta':{**period_meta('2026-9T'),'report_date':'2026-10-11','sources':[dict(id='primary',name='Nguồn kiểm thử',url='https://example.org/release',source_published_at='2026-10-03',retrieved_at='2026-10-11T09:00:00+07:00',groups=['gdp','iip','cpi','retail','trade','fdi','budget','public_investment','monetary','pmi','business'])]}})
    return d

def codes(d):return {r['code'] for r in inspect(d)['flags']}

def test_null_group_real_zero_missing_reason_and_no_invented_analysis(payload):
    payload['fdi']=None;payload['cpi']['month_mom']=0
    before=deepcopy(payload);html=render_html(payload)
    assert 'Chưa có' in html and '0,00' in html and 'chưa có chuỗi số liệu' in html.lower()
    assert 'KHẢ QUAN' not in html and 'PASS_SCREEN' not in html and 'Agriseco' not in html
    assert payload==before
    assert number(0)=='0,00' and number(None)=='Chưa có'
    assert number(1e18,0)=='1.000.000.000.000.000.000' and number(.00001,5)=='0,00001'

def test_signed_balances_backend_only_and_sources(payload):
    payload['trade']['ytd'].update(export_usd_bn=434.3,import_usd_bn=453.72)
    payload['trade'].update(domestic_balance_usd_bn=-34.28,fdi_balance_usd_bn=14.86)
    payload['budget']['month'].update(revenue=162.7,expenditure=256.8)
    payload['business'].update(new_and_returned_k=223.9,exited_k=172)
    d=normalize(payload)
    assert d['trade']['ytd']['balance_usd_bn']==-19.42
    assert d['budget']['month']['balance']==-94.1
    assert d['business']['exit_ratio_pct']==pytest.approx(172/223.9*100)
    assert 'identity_mismatch' not in codes(d)
    assert '†' in render_html(d) and 'XK − NK' in render_html(d)
    d['trade']['ytd']['balance_usd_bn']=19.42
    assert 'identity_mismatch' in codes(d)

def test_units_budget_gdp_and_table_chart_flags(payload):
    payload['units']['trade']='tỷ VND'
    payload['budget']['ytd'].update(revenue=2187.3,revenue_pct_plan=86.5,expenditure=1873.7,expenditure_pct_plan=59.3)
    payload['budget']['plan'].update(revenue=2530,expenditure=3200)
    payload['gdp']['sectors']=[dict(name='A',yoy=1,contribution_pct=60),dict(name='B',yoy=1,contribution_pct=50)]
    payload['comparisons']=[dict(path='budget.ytd.revenue_yoy',primary=12.1,other=12),dict(path='iip.ytd_yoy',primary=12,other=11)]
    assert {'unit_mismatch','budget_plan_mismatch','gdp_contribution','rounding_difference','metric_source_conflict'}<=codes(payload)

def test_known_design_outlier_detected_without_hardcoded_year(payload):
    payload['trade']['history_ytd']=[dict(year=2023,export_usd_bn=None,import_usd_bn=237.7),dict(year=2024,export_usd_bn=None,import_usd_bn=179.5),dict(year=2025,export_usd_bn=None,import_usd_bn=331.9)]
    assert 'history_outlier' in codes(payload)
    payload['trade']['history_ytd'][1]['explanation']='Đã kiểm tra với công bố gốc'
    assert 'history_outlier' not in codes(payload)

def test_period_future_date_and_malformed_numeric(payload):
    payload['gdp']['q']['label']='Q2/2025'
    payload['meta']['sources'][0]['source_published_at']='2026-10-12'
    assert {'period_mismatch','future_source'}<=codes(payload)
    payload['cpi']['month_mom']='0'
    with pytest.raises(ValueError,match='Macro JSON'):validate_schema(payload)
    payload['cpi']['month_mom']=float('nan')
    with pytest.raises(ValueError,match='finite'):validate_schema(payload)

@pytest.mark.parametrize('code',['2026-09','2026-Q3','2025'])
def test_period_changes_without_editing_template(payload,code):
    payload['meta'].update(period_meta(code));payload['meta']['report_date']='2026-10-11'
    payload['meta']['sources']=[]
    html=render_html(payload)
    assert payload['meta']['period_label'] in html and len(BeautifulSoup(html,'html.parser').select('section.page'))==8

def test_hide_empty_reorder_escape_long_names_and_preserve_json(payload):
    payload['gdp']['ytd'].update(label='9T/2026',yoy=9.01)
    assert selected_pages(payload,hide_empty=True)==('01_overview','02_production','08_conclusion')
    assert '2 / 2' in render_html(payload,pages=['02_production','01_overview'])
    name='Dự án '+'<script>alert(1)</script>'+'x'*240
    payload['fdi']['top_projects']=[dict(name=name,province=None,country=None,usd_bn=None)]*17
    html=render_html(payload,pages=['05_fdi'],project_limit=3)
    assert 'Còn 14 dòng' in html and 'xem thêm trong JSON' in html and '&lt;script&gt;' in html
    assert len(payload['fdi']['top_projects'])==17
    with pytest.raises(ValueError):render_html(payload,pages=['no-such-page'])

def test_chart_short_negative_outliers_gdp_polarity():
    svg=chart([dict(year=2025,v=-.1),dict(year=2026,v=1e12)],[('Series','v')])
    assert '#C9363E' in svg and '#0E8F5A' in svg and 'nan' not in svg.lower()
    assert chart([], [('x','v')]) is None
    assert '#C9363E' in chart([dict(year=2025,v=2),dict(year=2026,v=4)],[('GDP','v')],kind='line',gdp=True)
    assert '#C9363E' in chart([dict(year=2025,v=4)],[('CPI','v')],polarity='higher_bad')
    assert '50 · ngưỡng' in pmi_scale(51.9) and pmi_scale(None) is None

def test_severe_gate_blocks_and_writes_audit_draft_is_marked(payload,tmp_path):
    payload['units']['trade']='tỷ VND'
    target=tmp_path/'blocked.pdf'
    with pytest.raises(ValueError,match='chặn'):render_pdf(payload,target)
    assert not target.exists() and target.with_suffix('.quality_report.json').exists()
    assert 'BẢN NHÁP · CẦN KIỂM TRA' in render_html(payload,draft=True)

def test_pdf_exact_eight_pages_network_independent_and_snapshot(payload,tmp_path):
    payload['gdp']['ytd']['yoy']=9.01
    payload['cpi']['month_mom']=.62
    payload['fdi']['top_projects']=[dict(name='Dự án tên dài '+('công nghệ '*12),province='Hà Nội',country='Nhật Bản',usd_bn=.01)]
    target=tmp_path/'macro.pdf';render_pdf(payload,target)
    pdf=PdfReader(target)
    assert len(pdf.pages)==8
    text='\n'.join(p.extract_text() for p in pdf.pages)
    assert '9,01' in text and 'Chưacó' in ''.join(text.split()) and 'None' not in text
    html=target.with_suffix('.html').read_text(encoding='utf-8')
    assert 'data:font/woff2;base64,' in html and '<script' not in html
    assert json.loads(target.with_suffix('.json').read_text(encoding='utf-8'))['fdi']['top_projects']==payload['fdi']['top_projects']

def test_schema_missing_source_is_blocked(payload):
    payload['gdp']['ytd']['yoy']=9.01;payload['meta']['sources']=[]
    assert 'unsourced_value' in codes(payload)

def test_monthly_monetary_series_fit_same_eight_page_template(payload,tmp_path):
    payload['pmi'].update(value=51.9,previous=53.3,series=[dict(month=f'{m:02}/2026',value=50+m/10) for m in range(1,10)])
    for key in ('credit','usd_vnd','interbank'):
        payload['monetary']['series'][key]=[dict(month=f'{m:02}/2026',value=m if key!='usd_vnd' else 25000+m*10) for m in range(1,10)]
    payload['business']['exit_ratio_history']=[dict(year=2025,pct=78),dict(year=2026,pct=77)]
    render_pdf(payload,tmp_path/'monthly.pdf',pages=['07_monetary'])
    assert len(PdfReader(tmp_path/'monthly.pdf').pages)==1

def test_pmi_parser_rejects_moved_month(monkeypatch,tmp_path):
    import stock_reports.pipeline.macro_periods as module
    def fetch(settings,config,adapter,force):return adapter('<article>Vietnam PMI October 2026</article>','2026-10-11T00:00:00+07:00')
    monkeypatch.setattr(module,'_fetch_external',fetch)
    with pytest.raises(ValueError,match='chuyển kỳ'):fetch_pmi(Settings.from_root(tmp_path),dict(period='2026-9T',month='September',year=2026,url='https://www.cimigo.com/',published='2026-10-01'))

def test_licensed_bridge_requires_authorization(tmp_path):
    with pytest.raises(ValueError,match='quyền sử dụng'):fetch_licensed_json(Settings.from_root(tmp_path),dict(url='https://example.org/',period='2026-9T'))

def test_partial_row_keeps_missing_components_null(payload):
    payload['fdi']['top_projects']=[dict(name='Dự án có tên, thiếu vốn')]
    payload['trade']['history_ytd']=[dict(year=2025,export_usd_bn=3)]
    html=render_html(payload)
    assert 'Chưa có' in html and 'None' not in html
    assert normalize(payload)['fdi']['top_projects'][0]['usd_bn'] is None

def test_monthly_cpi_and_retail_fit_with_history(payload,tmp_path):
    payload['cpi']['history_ytd']=[dict(year=y,yoy=3) for y in range(2022,2027)]
    payload['retail']['history']=[dict(year=y,value_bn_vnd=5000000,yoy=10) for y in range(2022,2027)]
    payload['cpi']['monthly_series']=[dict(month=f'{m:02}',yoy=4) for m in range(1,10)]
    payload['retail']['monthly_series']=[dict(month=f'{m:02}',value_bn_vnd=500000) for m in range(1,10)]
    render_pdf(payload,tmp_path/'monthly-prices.pdf',pages=['03_prices'],draft=True)

def test_arbitrary_derived_tag_cannot_bypass_evidence(payload):
    payload['pmi']['value']=99;payload['meta']['sources']=[]
    payload['derived']['pmi.value']={'formula':'fabricated','inputs':[]}
    assert 'unsupported_derivation' in codes(payload)

def test_monthly_observations_cannot_leak_after_period(payload):
    payload['cpi']['monthly_series']=[dict(month='2026-11',yoy=4)]
    payload['monetary']['credit_as_of']='2026-10-10'
    assert {'future_observation','period_mismatch'}<=codes(payload)

def test_indicator_polarity_is_configurable_in_json(payload):
    payload['cpi']['ytd_avg_yoy']=4.52;payload['polarity']={'cpi.ytd_avg_yoy':'neutral'}
    html=render_html(payload,pages=['01_overview'])
    assert 'value neutral">+4,52' in html
    payload['polarity']['cpi.ytd_avg_yoy']='invalid'
    with pytest.raises(ValueError,match='Macro JSON'):render_html(payload)

def test_publication_is_independent_and_reuses_immutable_snapshot(payload,tmp_path,monkeypatch):
    from stock_reports.pipeline.research_reports import generate_reports,GenerationRequest,report_analysis
    config=tmp_path/'config';config.mkdir()
    (config/'macro_stocklens.json').write_text('{"enabled":true}',encoding='utf-8')
    settings=Settings.from_root(tmp_path)
    def forbidden(*a,**kw):pytest.fail('Macro must not consult legacy stock/annual analysis')
    monkeypatch.setattr('stock_reports.pipeline.research_reports.build_document',forbidden)
    monkeypatch.setattr('stock_reports.analysis.repository.ResearchRepository.macro',forbidden)
    monkeypatch.setattr('stock_reports.pipeline.macro_periods.load_period',lambda *a,**kw:payload)
    request=GenerationRequest(kind='macro',as_of=date(2026,10,11),macro_period='2026-9T')
    first=generate_reports(settings,request)[0];second=generate_reports(settings,request)[0]
    assert second['reused'] and first['report']['id']==second['report']['id']
    analysis=report_analysis(settings,first['report']['id'])
    assert analysis['page_count']==8 and analysis['document']['stocklens_data'] is None
    assert analysis['document']['macro_stocklens_data']['meta']['period_code']=='2026-9T'
    assert analysis['inputs']['quality_report']['status']=='passed_with_gaps'

def test_source_parser_ignores_summary_gdp_and_never_uses_consumption_as_iip():
    html='<article><h1>Báo cáo 9 tháng năm 2026</h1><p>GDP chín tháng năm 2026 ước tăng 9,01%.</p><p>Chỉ số tiêu thụ năm 2025 tăng 9,1%.</p><p>Khái quát GDP chín tháng 2026 tăng 9,95%.</p><p>'+('Nội dung nguồn. '*400)+'</p></article>'
    d=parse_nso(html,dict(period='2026-9T',url='https://www.nso.gov.vn/release',published='2026-10-03'),'2026-10-11T00:00:00+07:00')
    assert d['gdp']['ytd']['yoy']==9.01 and d['iip']['prev_ytd_yoy'] is None

def test_fdi_same_paragraph_near_qualifier_does_not_mix_registered_disbursed():
    html='<article><h1>Báo cáo 9 tháng năm 2023</h1><p>Tổng vốn đầu tư nước ngoài đăng ký vào Việt Nam tính đến ngày 20/9/2023 đạt gần 20,21 tỷ USD, tăng 7,7%. Vốn đầu tư trực tiếp nước ngoài thực hiện tại Việt Nam 9 tháng năm 2023 ước đạt 15,91 tỷ USD, tăng 2,2%.</p><p>'+('Nội dung nguồn. '*400)+'</p></article>'
    d=parse_nso(html,dict(period='2023-9T',url='https://www.nso.gov.vn/release',published='2023-09-29'),'2026-10-11T00:00:00+07:00')
    assert d['fdi']['registered_usd_bn']==20.21 and d['fdi']['disbursed_usd_bn']==15.91
    assert d['fdi']['registered_yoy']==7.7 and d['fdi']['disbursed_yoy']==2.2
    assert d['provenance']['fdi.registered_usd_bn']['observation_date']=='2023-09-20'
