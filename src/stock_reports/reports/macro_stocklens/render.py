"""Source-aware offline HTML/Chromium export with strict quality/overflow gates."""
import base64
from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from jinja2 import Environment,FileSystemLoader,StrictUndefined,select_autoescape
from .data import normalize,get,FIELDS
from .quality import inspect
from .charts import chart,pmi_scale,fmt

ROOT=Path(__file__).parent
PAGES=('01_overview','02_production','03_prices','04_trade','05_fdi','06_budget','07_monetary','08_conclusion')
GROUPS=dict(zip(PAGES,[tuple(FIELDS),('gdp','iip'),('cpi','retail'),('trade',),('fdi',),('budget','public_investment'),('monetary','pmi','business'),tuple(FIELDS)]))
TITLES=dict(zip(PAGES,['Tổng quan','GDP và sản xuất công nghiệp','CPI và bán lẻ','Xuất nhập khẩu','Đầu tư trực tiếp nước ngoài','Ngân sách và đầu tư công','Lãi suất, tỷ giá, PMI, doanh nghiệp','Kết luận']))
HEADINGS=dict(zip(PAGES,['Kinh tế Việt Nam · các chỉ tiêu trọng tâm','Tăng trưởng và động lực sản xuất','Giá tiêu dùng và sức mua trong nước','Thương mại hàng hóa và cán cân','Dòng vốn FDI đăng ký và thực hiện','Thu, chi ngân sách và giải ngân đầu tư','Tiền tệ và hoạt động doanh nghiệp','Đánh giá chung, cơ hội và rủi ro']))
CHARTS={
 'gdp':('gdp.history',[('GDP','ytd_yoy')],'line','higher_good'),
 'iip':('iip.history',[('IIP','ytd_yoy')],'bar','higher_good'),
 'cpi':('cpi.history_ytd',[('CPI','yoy')],'bar','higher_bad'),
 'cpi_monthly':('cpi.monthly_series',[('CPI','yoy')],'bar','higher_bad'),
 'retail':('retail.history',[('Bán lẻ','value_bn_vnd')],'bar','neutral'),
 'retail_monthly':('retail.monthly_series',[('Bán lẻ','value_bn_vnd')],'bar','neutral'),
 'trade':('trade.history_ytd',[('Xuất khẩu','export_usd_bn'),('Nhập khẩu','import_usd_bn')],'bar','neutral'),
 'trade_quarter':('trade.quarterly_yoy',[('Kim ngạch','yoy')],'bar','higher_good'),
 'fdi':('fdi.history_ytd',[('Đăng ký','registered'),('Thực hiện','disbursed')],'bar','neutral'),
 'business':('business.exit_ratio_history',[('Tỷ lệ rút lui','pct')],'bar','higher_bad'),
 'investment_monthly':('public_investment.monthly_series',[('Giải ngân','value')],'bar','higher_good'),
 'credit':('monetary.series.credit',[('Tín dụng','value')],'line','neutral'),
 'fx':('monetary.series.usd_vnd',[('USD/VND','value')],'line','neutral'),
 'interbank':('monetary.series.interbank',[('Lãi suất','value')],'line','neutral'),
 'pmi_monthly':('pmi.series',[('PMI','value')],'line','neutral'),
}

def number(value,places=2,signed=False):
    if value is None:return 'Chưa có'
    if isinstance(value,bool) or not isinstance(value,(float,int)):raise ValueError('Macro display requires numeric values')
    return ('+' if signed and value>0 else '−' if value<0 else '')+fmt(abs(value),places)

def styles(accent):
    if not re.fullmatch(r'#[a-fA-F0-9]{6}',accent):raise ValueError('Accent must be a hex color')
    assets=ROOT.parent/'stocklens/assets'
    css=(assets/'fonts.css').read_text(encoding='utf-8')
    def embed(m):
        p=(assets/m[1]).resolve()
        if not p.is_relative_to((assets/'fonts').resolve()):raise ValueError('Invalid font path')
        return 'url("data:font/woff2;base64,'+base64.b64encode(p.read_bytes()).decode()+'")'
    return re.sub(r'url\("([^"]+)"\)',embed,css)+'\n'+(ROOT/'tokens.css').read_text(encoding='utf-8')+'\n'+(ROOT/'components.css').read_text(encoding='utf-8')+'\n:root{--accent:'+accent+'}'

def asset_fingerprint():
    digest=hashlib.sha256()
    for p in sorted(p for p in ROOT.rglob('*') if p.is_file() and p.suffix in ('.py','.html','.css','.json')):
        digest.update(str(p.relative_to(ROOT)).encode());digest.update(p.read_bytes())
    digest.update((ROOT.parent/'stocklens/assets/fonts.css').read_bytes())
    for path in sorted((ROOT.parent/'stocklens/assets/fonts').glob('*.woff2')):digest.update(path.read_bytes())
    return digest.hexdigest()

def source_names(d,groups):
    refs={v.get('source_id') for k,v in d['provenance'].items() if k.split('.')[0] in groups}
    names=[s['name'] for s in d['meta']['sources'] if isinstance(s,dict) and (s.get('id') in refs or set(s.get('groups',())).intersection(groups))]
    return ', '.join(dict.fromkeys(names)) or 'Chưa có nguồn xác nhận'

def selected_pages(d,pages=None,hide_empty=False):
    chosen=tuple(PAGES if pages is None else pages)
    if not chosen or len(set(chosen))!=len(chosen) or any(p not in PAGES for p in chosen):raise ValueError('Invalid macro page order')
    def present(x):
        if isinstance(x,dict):return any(present(v) for k,v in x.items() if k not in ('label','disclaimer'))
        if isinstance(x,list):return any(present(v) for v in x)
        return x is not None and x!=''
    if hide_empty:chosen=tuple(p for p in chosen if any(present(d[g]) for g in GROUPS[p]))
    if not chosen:raise ValueError('Không có trang có dữ liệu')
    return chosen

def render_html(payload,*,accent='#1F5EFF',pages=None,hide_empty=False,draft=False,exported_at=None,project_limit=10):
    quality=inspect(payload);d=normalize(payload)
    if quality['status']=='blocked' and not draft:raise ValueError('Cổng chất lượng vĩ mô chặn xuất: '+', '.join(f['code'] for f in quality['flags'] if f['severity']=='error'))
    if not 1<=project_limit<=15:raise ValueError('Project row limit must be 1..15')
    charts={}
    monthly_monetary=any(get(d,p) for p in ('monetary.series.credit','monetary.series.usd_vnd','monetary.series.interbank','pmi.series'))
    for key,(path,metrics,kind,polarity) in CHARTS.items():
        rows=get(d,path)
        if key.startswith('retail'):rows=[{**r,'value_bn_vnd':r['value_bn_vnd']/1000 if r.get('value_bn_vnd') is not None else None} for r in rows]
        height=80 if monthly_monetary and key in ('business','credit','fx','interbank','pmi_monthly') else 115 if key in ('cpi_monthly','retail_monthly') else 156
        if (d['cpi']['monthly_series'] or d['retail']['monthly_series']) and key in ('cpi','cpi_monthly','retail','retail_monthly'):height=100
        half=key in ('iip','cpi','cpi_monthly','fdi','trade_quarter','credit','fx','interbank','pmi_monthly','retail_monthly') or key=='retail' and bool(d['retail']['monthly_series'])
        charts[key]=chart(rows,metrics,kind=kind,polarity=d.get('polarity',{}).get(path,polarity),gdp=key=='gdp',height=height,width=315 if half else 650)
    chosen=selected_pages(d,pages,hide_empty)
    # Display-unit conversion only; business identities were calculated in data.py.
    display_values={p:get(d,p)/1000 if get(d,p) is not None else None for p in ('retail.q.value_bn_vnd','retail.ytd.value_bn_vnd')}
    def cell(path,places=2,signed=False):return number(display_values[path] if path in display_values else get(d,path),places,signed)+('†' if path in d['derived'] else '')
    def tone(path,polarity='higher_good'):
        polarity=d.get('polarity',{}).get(path,polarity)
        value=get(d,path)
        if value is None or value==0 or polarity=='neutral':return 'neutral'
        return 'good' if (value>0)==(polarity=='higher_good') else 'bad'
    stamp=(exported_at or datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))).astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M %z')
    env=Environment(loader=FileSystemLoader(ROOT),autoescape=select_autoescape(('html',)),undefined=StrictUndefined)
    env.filters.update(num=number,datevn=lambda x:'/'.join(reversed(x[:10].split('-'))),clamp=lambda x:max(0,min(100,x)),zfill=lambda x:x.zfill(2))
    env.globals['monthly_monetary']=monthly_monetary
    def reason(path):
        while path:
            if path in d['missing_reasons']:return d['missing_reasons'][path]
            path=path.rpartition('.')[0]
        return 'Nguồn chưa cung cấp dữ liệu được xác nhận cho kỳ này'
    return env.get_template('base.html').render(d=d,quality=quality,styles=styles(accent),pages=chosen,total=len(chosen),titles=TITLES,headings=HEADINGS,page_groups=GROUPS,charts=charts,chart_paths={k:v[0] for k,v in CHARTS.items()},pmi=pmi_scale(d['pmi']['value']),draft=draft,exported_at=stamp,cell=cell,tone=tone,missing=lambda p:get(d,p) is None,reason=reason,sources=lambda groups:source_names(d,groups),projects=d['fdi']['top_projects'][:project_limit],projects_omitted=max(0,len(d['fdi']['top_projects'])-project_limit),countries=d['fdi']['top_countries'][:7],countries_omitted=max(0,len(d['fdi']['top_countries'])-7),trade_rows=[('Tổng kim ngạch','trade.q.total_usd_bn','tỷ USD'),('Tổng · so cùng kỳ','trade.q.total_yoy','%'),('Xuất khẩu · so cùng kỳ','trade.q.export_yoy','%'),('Nhập khẩu · so cùng kỳ','trade.q.import_yoy','%'),('Xuất khẩu · so quý trước','trade.q.export_qoq','%'),('Nhập khẩu · so quý trước','trade.q.import_qoq','%'),('Cán cân tháng cuối kỳ','trade.month_balance_usd_bn','tỷ USD')])

OVERFLOW_JS="""() => Array.from(document.querySelectorAll('.page')).flatMap((page,index)=>{
 const content=page.querySelector('.page-content'),footer=page.querySelector('.page-footer'),box=page.getBoundingClientRect(),bad=[];
 for(const node of [content,...content.querySelectorAll('*')]){
  const r=node.getBoundingClientRect(),tag=node.tagName.toLowerCase();
  if(['svg','path','line','circle','rect','text'].includes(tag)||node.closest('svg'))continue;
  if(r.width&&r.height&&(r.bottom>footer.getBoundingClientRect().top-10||r.left<box.left+54||r.right>box.right-54||node.scrollWidth>node.clientWidth+2||node.scrollHeight>node.clientHeight+2))bad.push(tag+':'+node.className);
 }return bad.length?[{page:index+1,period:page.dataset.period,partial:page.dataset.page,items:bad.slice(0,12)}]:[];
})"""

def render_pdf(payload,destination,*,qa_directory=None,**options):
    from playwright.sync_api import sync_playwright,Error
    from pypdf import PdfReader
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    quality=inspect(payload)
    # Audit exists even when the gate aborts before rendering.
    destination.with_suffix('.quality_report.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2),encoding='utf-8')
    html=render_html(payload,**options)
    count=len(selected_pages(normalize(payload),options.get('pages'),options.get('hide_empty',False)))
    with sync_playwright() as pw:
        try:browser=pw.chromium.launch(headless=True)
        except Error:browser=pw.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page(viewport=dict(width=794,height=1123),device_scale_factor=1)
            page.route('**/*',lambda route:route.abort());page.set_content(html,wait_until='load');page.evaluate('() => document.fonts.ready')
            errors=page.evaluate(OVERFLOW_JS)
            if errors:
                logging.getLogger(__name__).error('Macro overflow %s',json.dumps(errors,ensure_ascii=False))
                raise ValueError('Tràn nội dung vĩ mô: '+json.dumps(errors,ensure_ascii=False))
            if qa_directory:
                qa=Path(qa_directory);qa.mkdir(parents=True,exist_ok=True)
                for i,node in enumerate(page.locator('.page').all(),1):node.screenshot(path=str(qa/f'page-{i:02}.png'))
            temporary=destination.with_suffix('.pdf.tmp')
            try:
                page.pdf(path=str(temporary),width='794px',height='1123px',print_background=True,prefer_css_page_size=True)
                if len(PdfReader(temporary).pages)!=count:raise ValueError('Số trang PDF không khớp partials')
                temporary.replace(destination)
            finally:
                if temporary.exists():temporary.unlink()
        finally:browser.close()
    destination.with_suffix('.json').write_text(json.dumps(normalize(payload),ensure_ascii=False,indent=2),encoding='utf-8')
    destination.with_suffix('.html').write_text(html,encoding='utf-8')
    return destination
