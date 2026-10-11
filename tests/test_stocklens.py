"""StockLens contract, safe missing-data formatting and exact pagination."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pypdf import PdfReader
from stock_reports.reports.stocklens.render import ROOT,validate,render_html,render_pdf,number,view_model
from stock_reports.reports.stocklens.data import add_indicators,rsi,calendar_return

def empty(spec):
    if 'enum' in spec:return spec['enum'][0]
    kind=spec.get('type')
    if isinstance(kind,list) and 'null' in kind:return None
    if kind=='object':return {k:empty(spec['properties'][k]) for k in spec.get('required',[])}
    if kind=='array':return [empty(spec['items']) for _ in range(spec.get('minItems',0))]
    if kind=='boolean':return False
    if kind=='integer':return spec.get('minimum',0)
    if kind=='string':return ''
    if kind=='number':return 0

@pytest.fixture
def payload():
    d=empty(json.loads((ROOT/'schema.json').read_text(encoding='utf8')))
    d['meta'].update(ticker='TEST',company_name='Công ty thử nghiệm',report_date='2026-10-11',accent='#1F5EFF',profile='non_financial')
    d['methodology'].update(formula_text='Không có số liệu nguồn.',price_unit='VND/cp',financial_unit='tỷ VND',config_sha256='0'*64)
    return d

def test_missing_valuation_and_real_zero(payload):
    payload['price']['close']=0
    html=render_html(payload)
    assert 'Chưa đủ dữ liệu' in html and 'Chưa có' in html and 'N/A' not in html
    assert number(0)=='0.00' and number(None)=='Chưa có'
    assert '75.9' not in html and '113,800' not in html

def test_bank_rules_not_manufacturing(payload):
    payload['methodology']['banking']=True;payload['meta']['profile']='banking'
    assert view_model(payload)['charts']['margin'] is None
    assert 'Biên gộp / biên lợi nhuận ròng' not in render_html(payload)
    payload['financials']['years']=[2025]
    for key,value in payload['financials'].items():
        if isinstance(value,list) and key!='years':payload['financials'][key]=[None]
    for key,value in payload['financials']['ratios'].items():
        if isinstance(value,list):payload['financials']['ratios'][key]=[None]
    payload['financials']['ratios']['net_margin']=[1]
    with pytest.raises(ValueError,match='manufacturing'):validate(payload)

def test_less_than_four_years_keeps_missing(payload):
    f=payload['financials'];f['years']=[2024,2025]
    for key,value in f.items():
        if isinstance(value,list) and key!='years':f[key]=[0,None]
    for key,value in f['ratios'].items():
        if isinstance(value,list):f['ratios'][key]=[None,None]
    assert validate(payload)['financials']['revenue']==[0,None]
    assert '2022</th>' not in render_html(payload)
    f['revenue'].pop()
    with pytest.raises(ValueError,match='length mismatch'):validate(payload)

def test_large_small_and_nonfinite():
    assert number(10**18,0)=='1,000,000,000,000,000,000'
    assert number(.000001,6)=='0.000001'
    assert number(-3.5,2,True)=='-3.50'
    with pytest.raises(ValueError):number(float('nan'))

def test_long_company_and_html_injection(payload):
    name='Công ty Cổ phần '+('Công nghệ Việt Nam '*8)+'<script>alert(1)</script>'
    payload['meta']['company_name']=name
    html=render_html(payload)
    assert name not in html and '&lt;script&gt;' in html
    assert html.count('data-page=')==10


def test_daily_news_display_shortening_keeps_full_json_and_source_links(payload):
    payload['news']=[dict(source='CafeF · Doanh nghiệp',published_at='2026-10-11T09:00:00+07:00',
        title='TEST công bố lợi nhuận '+('doanh nghiệp '*40),summary='Thông tin nguồn '+('nội dung '*180),
        channel='Tin tài chính',impact='unclear',needs_verification=True,url='https://example.org/news')]
    payload['methodology']['sources']=[dict(item='Tin',source='CafeF · Doanh nghiệp',url='https://example.org/news',retrieved_at='2026-10-11T09:00:00+07:00',locator=None,published_at=None)]
    before=deepcopy(payload)
    shown=view_model(payload)
    assert len(shown['news'][0]['summary'])<=421
    assert shown['news'][0]['excerpt_shortened'] is True
    assert payload==before
    assert 'Trích đoạn rút gọn' in render_html(payload)
    assert 'https://example.org/news' in render_html(payload)

def test_trace_required_for_claim_and_alert(payload):
    payload['alerts']=[dict(priority='high',condition='Quan sát MA20',threshold='30',meaning='Mô tả',fields=['technical.ma20'])]
    with pytest.raises(ValueError,match='missing evidence'):validate(payload)
    payload['technical']['ma20']=30
    validate(payload)
    payload['alerts'][0]['fields']=['technical.fake']
    with pytest.raises(ValueError,match='invalid evidence'):validate(payload)

def test_invalid_score_and_future_dates(payload):
    payload['scores']['unified']=101
    with pytest.raises(ValueError,match='Score outside'):validate(payload)

def test_inconsistent_balance_is_not_charted(payload):
    f=payload['financials'];f['years']=[2023]
    for k,v in f.items():
        if isinstance(v,list) and k!='years':f[k]=[None]
    for k,v in f['ratios'].items():
        if isinstance(v,list):f['ratios'][k]=[None]
    f.update(total_assets=[100],liabilities=[10**15],equity=[30])
    with pytest.raises(ValueError,match='balance identity'):validate(payload)

def test_indicators_do_not_pad_or_estimate():
    rows=[dict(date=f'2026-10-{i:02}',close=100,volume=0) for i in range(1,20)]
    result=add_indicators(rows)
    assert len(result)==19 and result[-1]['ma20'] is None
    assert result[-1]['rsi']==50 and result[-1]['drawdown']==0
    assert calendar_return(rows,1) is None
    assert rsi([1,2,3])==[None,None,None]

def test_focus_horizon_and_offline_fonts(payload):
    payload['methodology']['focus']={k:v for k,v in [('short',[3,3,1,1,3]),('medium',[2,2,2,2,3]),('long',[1,2,3,3,2])]}
    a=render_html(payload)
    payload['meta']['horizon']='long';b=render_html(payload)
    assert 'Ngắn hạn' in a and 'Dài hạn' in b and a!=b
    assert 'data:font/woff2;base64,' in a and 'fonts.googleapis.com' not in a

def test_ten_page_pdf_and_overflow_log(payload,tmp_path,caplog):
    path=render_pdf(payload,tmp_path/'test.pdf')
    reader=PdfReader(path)
    assert len(reader.pages)==10
    assert all('khuyếnnghịmua/bán' in ''.join(page.extract_text().split()) for page in reader.pages)
    payload['methodology']['missing']=['Rà soát dữ liệu nguồn dài '*50]*30
    with pytest.raises(ValueError,match='tràn trang TEST'):render_pdf(payload,tmp_path/'overflow.pdf')
    assert 'ticker=TEST' in caplog.text and "'page': 10" in caplog.text
    assert not (tmp_path/'overflow.pdf').exists()
