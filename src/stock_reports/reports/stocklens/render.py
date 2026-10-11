"""Validate one JSON payload, format it, then print exactly ten Chromium pages."""
from collections import OrderedDict
from datetime import datetime
import base64
import hashlib
import json
import logging
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from jinja2 import Environment,FileSystemLoader,StrictUndefined,select_autoescape
from jsonschema import Draft202012Validator
from stock_reports.reports.stocklens.charts import line_chart,bar_chart

ROOT=Path(__file__).parent
PAGES=('01_summary','02_company','03_technical','04_indicators','05_financials','06_valuation','07_news','08_scenarios','09_monitoring','10_methodology')
LABELS=dict(short='Ngắn hạn',medium='Trung hạn',long='Dài hạn')
MISSING='Chưa có'


def number(value,places=2,signed=False):
    if value is None or value=='':return MISSING
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('Invalid numeric display value')
    return format(value,('+' if signed else '')+',.'+str(places)+'f')


def tone(value):
    return 'neutral' if value is None or value==0 else 'positive' if value>0 else 'negative'


def text(value):return MISSING if value is None or value=='' else str(value)


def validate(payload):
    schema=json.loads((ROOT/'schema.json').read_text(encoding='utf-8'))
    errors=sorted(Draft202012Validator(schema).iter_errors(payload),key=lambda e:str(e.path))
    if errors:raise ValueError('StockLens JSON: '+str(list(errors[0].path))+': '+errors[0].message)
    def finite(v):
        if isinstance(v,float) and not math.isfinite(v):raise ValueError('Non-finite JSON value')
        if isinstance(v,dict):
            for x in v.values():finite(x)
        if isinstance(v,list):
            for x in v:finite(x)
    finite(payload)
    for key,value in payload['scores'].items():
        if key not in ('pillars','ta_conditions') and value is not None and not 0<=value<=100:
            raise ValueError('Score outside 0..100: '+key)
    for key,value in payload['scores']['pillars'].items():
        if value is not None and not 0<=value<=100:raise ValueError('Pillar outside 0..100: '+key)
    if payload['methodology']['banking'] and any(v is not None for key in ('gross_margin','net_margin','ocf_to_ni') for v in payload['financials']['ratios'][key]):
        raise ValueError('Do not apply manufacturing ratios to banking')
    f=payload['financials'];length=len(f['years'])
    if f['years']!=sorted(f['years']):raise ValueError('Financial years must be chronological')
    for name in ('revenue','gross_profit','net_income','total_assets','liabilities','equity','operating_cash_flow'):
        if len(f[name])!=length:raise ValueError('Annual series length mismatch: '+name)
    for name in ('gross_margin','net_margin','roa','roe','ocf_to_ni'):
        if len(f['ratios'][name])!=length:raise ValueError('Annual ratio length mismatch: '+name)
    for a,l,e in zip(f['total_assets'],f['liabilities'],f['equity']):
        if all(v is not None for v in (a,l,e)) and a>0 and abs(a-l-e)>a*.005:
            raise ValueError('Annual balance identity mismatch')
    series=payload['price']['series_250'];dates=[r['date'] for r in series]
    if dates!=sorted(set(dates)):raise ValueError('Price dates must be unique and chronological')
    if any(r['date']>payload['meta']['report_date'] for r in series):raise ValueError('Price series exceeds report date')
    if any(r['close'] is None or r['close']<=0 for r in series):raise ValueError('Invalid EOD close')
    evidence_entries=[*payload['methodology']['statements'],*payload['alerts'],*[s for s in payload['scenarios'].values() if s]]
    for entry in evidence_entries:
            for path in entry['fields']:
                value=payload
                try:
                    for token in path.split('.'):value=value[int(token)] if isinstance(value,list) else value[token]
                except (IndexError,KeyError,TypeError,ValueError):raise ValueError('Statement has invalid evidence path: '+path)
                if value is None:raise ValueError('Statement cites missing evidence: '+path)
    if any(q['status']=='fail' for q in payload['methodology'].get('quality_checks',[])):
        raise ValueError('StockLens quality gate failed; no PDF exported')
    if payload['market']['vnindex_date'] and payload['market']['vnindex_date']!=payload['meta']['price_date']:
        raise ValueError('Benchmark and stock dates mismatch')
    val=payload['valuation'];eps=val['eps_ttm'];shares=val['shares_outstanding'];profit=val.get('parent_profit_ttm')
    if all(x is not None for x in (eps,shares,profit)) and (profit<=0 or abs(eps*shares-profit)>abs(profit)*.01):
        raise ValueError('EPS/share/parent TTM identity mismatch')
    if payload['methodology'].get('missing_reason') is not None:
        from stock_reports.reports.stocklens.evidence import null_paths
        if set(null_paths(payload))-set(payload['methodology']['missing_reason']):
            raise ValueError('A null cell has no missing_reason')
    return payload


def styles(accent='#1F5EFF'):
    if not re.fullmatch(r'#[a-fA-F0-9]{6}',accent):raise ValueError('Accent must be a six-digit hex color')
    css=(ROOT/'assets/fonts.css').read_text(encoding='utf-8')
    def embed(match):
        path=(ROOT/'assets'/match[1]).resolve()
        if not path.is_relative_to((ROOT/'assets/fonts').resolve()):raise ValueError('Invalid font path')
        return 'url("data:font/woff2;base64,'+base64.b64encode(path.read_bytes()).decode()+'")'
    css=re.sub(r'url\("([^"]+)"\)',embed,css)
    return css+'\n'+(ROOT/'tokens.css').read_text(encoding='utf-8')+'\n'+(ROOT/'components.css').read_text(encoding='utf-8')+'\n:root{--accent:'+accent+'}'


def asset_fingerprint():
    digest=hashlib.sha256()
    for path in sorted(p for p in ROOT.rglob('*') if p.is_file() and p.suffix in ('.css','.html','.json','.woff2','.py')):
        if '__pycache__' in path.parts:continue
        digest.update(str(path.relative_to(ROOT)).encode());digest.update(path.read_bytes())
    return digest.hexdigest()


def view_model(payload):
    price=payload['price'];t=payload['technical'];f=payload['financials'];bank=payload['methodology']['banking']
    series=price['series_250'];labels=[r['date'][5:] for r in series]
    charts={}
    if series:
        charts['price']=line_chart(labels,[(name,[r[key] for r in series]) for name,key in (('Giá','close'),('MA20','ma20'),('MA50','ma50'),('MA200','ma200'))],height=145)
        charts['rsi']=line_chart(labels,[('RSI',[r['rsi'] for r in series])],height=70,bands=(30,70))
        charts['macd']=line_chart(labels,[(key,[r[key] for r in series]) for key in ('macd','signal','hist')],height=70)
        charts['drawdown']=line_chart(labels,[('Sụt giảm',[r['drawdown'] for r in series])],height=65)
    charts['performance']=bar_chart(['1T','3T','6T','12T'],[('Hiệu suất',[price['change_'+str(n)+'m'] for n in (1,3,6,12)])],height=142,semantic=True)
    charts['revenue']=bar_chart(f['years'],[('Doanh thu',f['revenue'])],height=132)
    charts['profit']=bar_chart(f['years'],[('LNST',f['net_income'])],height=132)
    charts['margin']=line_chart(f['years'],[('Biên gộp',f['ratios']['gross_margin']),('Biên ròng',f['ratios']['net_margin'])],height=105,percent_axis=True) if not bank else None
    complete=[i for i in range(len(f['years'])) if f['liabilities'][i] is not None and f['equity'][i] is not None]
    charts['capital']=bar_chart([f['years'][i] for i in complete],[('Nợ phải trả',[f['liabilities'][i] for i in complete]),('Vốn chủ',[f['equity'][i] for i in complete])],height=155,stacked=True)
    valuation_rows=payload['valuation']['reported_metrics']
    if payload['valuation']['eps_ttm'] is not None:
        valuation_rows=[dict(label=label,value=payload['valuation'][key],unit=unit) for label,key,unit in (
            ('P/B cùng cơ sở †','pb','lần'),('BVPS vốn mẹ †','bvps','VND/cp'),('Cổ phiếu lưu hành','shares_outstanding','cp'),('Vốn hóa cùng ngày †','market_cap','VND'))]
    statements=payload['methodology']['statements'];opportunities=[s for s in statements if s['kind']=='opportunity'][:3];risks=[s for s in statements if s['kind']=='risk'][:3]
    financial_rows=[('Doanh thu / thu nhập hoạt động','revenue'),('Lợi nhuận gộp','gross_profit'),('Lợi nhuận sau thuế','net_income'),('Dòng tiền kinh doanh','operating_cash_flow')]
    if bank:financial_rows=[('Thu nhập hoạt động','revenue'),('Lợi nhuận sau thuế','net_income')]
    ratio_rows=[('Biên gộp (%)','gross_margin'),('Biên ròng (%)','net_margin'),('ROA bình quân (%)','roa'),('ROE bình quân (%)','roe'),('CFO / LNST (lần)','ocf_to_ni')]
    if bank:ratio_rows=[('ROA bình quân (%)','roa'),('ROE bình quân (%)','roe')]
    groups=OrderedDict()
    for i,s in enumerate(payload['methodology']['sources'],1):
        group='CafeF' if s['source'].startswith('CafeF') else s['source'].split(' · ')[0].split(' - ')[0].split(' BCTC ')[0]
        groups.setdefault(group,[]).append(dict(index=i,**s))
    horizon=payload['meta']['horizon'];order=dict(high=0,medium=1,low=2)
    alerts=sorted(payload['alerts'],key=lambda a:order[a['priority']])
    focus={k:['●'*n+'○'*(3-n) for n in payload['methodology']['focus'].get(k,[])] or ['Chưa có']*5 for k in LABELS}
    news_limit=2
    prioritized_news=[]
    for item in payload['news']:
        shown=dict(item); clipped=False
        for field,limit in (('title',200),('summary',420)):
            value=shown.get(field)
            if value and len(value)>limit:
                shown[field]=value[:limit].rsplit(' ',1)[0]+'…';clipped=True
        shown['excerpt_shortened']=clipped;prioritized_news.append(shown)
    return dict(charts=charts,opportunities=opportunities,risks=risks,statements=statements[:3],
        decision_label={'WATCH':'Theo dõi','EXCLUDED':'Loại khỏi sàng lọc','PASS_SCREEN':'Đạt bộ lọc'}.get(payload.get('decision',{}).get('status'),'Chưa có'),
        decision_reason={'SCORE_BELOW_ENTRY':'Điểm dưới ngưỡng vào','FA_EXCLUDED':'LNST hoặc vốn chủ không đạt điều kiện FA','ILLIQUID':'Thanh khoản chưa đạt ngưỡng','MARKET_DEFENSIVE':'Thị trường chưa đạt điều kiện xu hướng','ALL_CONDITIONS_MET':'Đạt các điều kiện cấu hình','MISSING_PRICE_HISTORY':'Thiếu giá điều chỉnh','STRATEGY_CONFIG_MISSING':'Thiếu cấu hình engine'}.get(payload.get('decision',{}).get('reason'),'Chưa có'),
        score_progress=payload['scores']['unified'],score_threshold=payload['scores']['entry_threshold'],
        technical_statements=[s for s in statements if any(p.startswith(('technical.','price.')) for p in s['fields'])],
        indicator_rows=[('MA20','ma20','VND/cp · SMA20'),('MA50','ma50','VND/cp · SMA50'),('MA200','ma200','VND/cp · SMA200'),('RSI(14)','rsi14','điểm · Wilder'),('MACD','macd','VND/cp'),('Signal','macd_signal','VND/cp'),('Histogram','macd_hist','VND/cp'),('Khối lượng / MA20','volume_vs_ma20','lần'),('Biến động 20 phiên','vol_20d','% năm hóa'),('Biến động 60 phiên','vol_60d','% năm hóa')],
        turnover_billions=t['turnover_value']/1e9 if t['turnover_value'] is not None else None,
        turnover_ma20_billions=t.get('turnover_ma20')/1e9 if t.get('turnover_ma20') is not None else None,
        liquidity_billions=t['liquidity_threshold']/1e9 if t['liquidity_threshold'] is not None else None,
        has_ttm=payload['valuation']['eps_ttm'] is not None or payload['valuation']['pe_ttm'] is not None,
        focus_rows=focus,impact_labels=dict(positive='Tích cực',negative='Tiêu cực',unclear='Chưa rõ',na='Không áp dụng'),priority_labels=dict(high='Cao',medium='Vừa',low='Thấp'),
        financial_rows=financial_rows,ratio_rows=ratio_rows,valuation_rows=valuation_rows,source_groups=groups,alerts=alerts[:8],alerts_omitted=max(0,len(alerts)-8),
        news=prioritized_news[:news_limit],news_omitted=max(0,len(payload['news'])-news_limit),profile_rows=payload['methodology']['profile_rows'][:8],
        profile_omitted=max(0,len(payload['methodology']['profile_rows'])-8),horizon_label=LABELS[horizon],
        financial_unit=payload['methodology']['financial_unit'],bank=bank,
        marks=[(name,value) for name,value in [('MA200',t['ma200']),('MA50',t['ma50']),('MA20',t['ma20']),('Giá tham chiếu',price['close']),('Đáy quan sát',price['trough_250'])] if value is not None])


def render_html(payload,*,accent='#1F5EFF',pages=None,exported_at=None):
    validate(payload);selected=tuple(pages or PAGES)
    if len(set(selected))!=len(selected) or any(p not in PAGES for p in selected):raise ValueError('Invalid page order')
    env=Environment(loader=FileSystemLoader(ROOT),autoescape=select_autoescape(('html',)),undefined=StrictUndefined)
    env.filters.update(num=number,txt=text,tone=tone)
    stamp=(exported_at or datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))).astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M %Z')
    return env.get_template('base.html').render(d=payload,v=view_model(payload),styles=styles(accent),pages=selected,total=len(selected),exported_at=stamp)


OVERFLOW_JS="""() => Array.from(document.querySelectorAll('.page')).flatMap((page,index)=>{
 const content=page.querySelector('.page-content'),footer=page.querySelector('.page-footer'),box=page.getBoundingClientRect();
 const bad=[];
 for(const node of [content,...content.querySelectorAll('*')]){
  const r=node.getBoundingClientRect();
  if(r.width && r.height && (r.bottom>footer.getBoundingClientRect().top-8 || r.left<box.left+54 || r.right>box.right-54 || node.scrollWidth>node.clientWidth+2 && !['svg','path','polyline','text'].includes(node.tagName.toLowerCase())))bad.push(node.tagName+':'+node.className);
 }
 return bad.length?[{page:index+1,items:bad.slice(0,8)}]:[];
})"""


def render_pdf(payload,destination,*,accent='#1F5EFF',qa_directory=None):
    from playwright.sync_api import sync_playwright,Error
    html=render_html(payload,accent=accent);destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        try:browser=pw.chromium.launch(headless=True)
        except Error:browser=pw.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page(viewport=dict(width=794,height=1123),device_scale_factor=1)
            page.route('**/*',lambda route:route.abort())  # Fonts/SVG are embedded. No external fetch or credentials.
            page.set_content(html,wait_until='load');page.evaluate('() => document.fonts.ready')
            problems=page.evaluate(OVERFLOW_JS)
            if problems:
                logging.getLogger(__name__).error('StockLens overflow ticker=%s pages=%s',payload['meta']['ticker'],problems)
                raise ValueError('StockLens nội dung tràn trang '+payload['meta']['ticker']+': '+json.dumps(problems,ensure_ascii=False))
            if qa_directory:
                qa_directory=Path(qa_directory);qa_directory.mkdir(parents=True,exist_ok=True)
                for i,node in enumerate(page.locator('.page').all(),1):node.screenshot(path=str(qa_directory/f'page-{i:02}.png'))
            temporary=destination.with_suffix('.pdf.tmp')
            page.pdf(path=str(temporary),width='794px',height='1123px',print_background=True,prefer_css_page_size=True)
            from pypdf import PdfReader
            if len(PdfReader(temporary).pages)!=10:temporary.unlink();raise ValueError('StockLens must output exactly 10 pages')
            temporary.replace(destination)
        finally:browser.close()
    from stock_reports.reports.stocklens.evidence import export_missing
    export_missing(payload,destination.with_suffix('.missing_report.json'))
    return destination
