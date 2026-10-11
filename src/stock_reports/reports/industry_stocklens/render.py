"""Industry-only template, deterministic pagination and fail-closed overflow QA."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from jinja2 import Environment,FileSystemLoader,StrictUndefined,select_autoescape
from .data import normalize,get,has_data,source_valid
from .quality import inspect
from .charts import number,columns,stacked,horizontal

ROOT=Path(__file__).parent
PAGES=('01_summary','02_global_overview','03_global_value_chain','04_global_supply','05_global_segments','06_domestic_overview','07_domestic_competition','08_domestic_regulations','09_domestic_segment','10_domestic_segment','11_domestic_segment','12_outlook','13_views_risks','14_companies','15_profiles','16_profiles')
TITLES=('Tóm tắt ngành','Thế giới: tổng quan','Thế giới: chuỗi giá trị','Thế giới: cung - cầu và chính sách','Thế giới: các mảng chủ lực','Việt Nam: tổng quan','Việt Nam: cạnh tranh và chuỗi giá trị','Việt Nam: pháp lý','Việt Nam: mảng sản phẩm 1','Việt Nam: mảng sản phẩm 2','Việt Nam: mảng sản phẩm 3','Triển vọng và dự phóng','Quan điểm của nguồn và rủi ro','Doanh nghiệp niêm yết','Hồ sơ doanh nghiệp nổi bật','Hồ sơ doanh nghiệp nổi bật')
PATHS=dict(zip(PAGES,('summary','global.overview','global.value_chain','global.supply_demand','global.segments','domestic.overview','domestic.competition','domestic.regulations','domestic.segments','domestic.segments','domestic.segments','domestic.outlook','domestic.risks','companies.table','companies.profiles','companies.profiles')))
COLUMN_LABELS={'group':'Mảng','ticker':'Mã','exchange':'Sàn','market_cap':'Vốn hóa','total_assets':'Tổng TS','revenue':'DT','revenue_yoy':'%YoY DT','net_income':'LNST','net_income_yoy':'%YoY LN','note':'Ghi chú'}
NUMERIC_COLUMNS=tuple(k for k in COLUMN_LABELS if k not in ('group','ticker','exchange','note'))
TRADING_FIELDS=(('price','Giá hiện tại','VND/cp'),('high_52w','Cao 52 tuần','VND/cp'),('low_52w','Thấp 52 tuần','VND/cp'),('avg_volume_10d','KLGD BQ 10 ngày','cp'),('eps_ttm','EPS trailing','VND/cp'),('pe_ttm','P/E trailing','lần'))

def indexed(rows):return [{**r,'_index':i} for i,r in enumerate(rows)]
def chunk(rows,n):return [rows[i:i+n] for i in range(0,len(rows),n)] or [[]]

def page_plan(payload,order=None,hide_empty=True):
    d=normalize(payload);plans=[]
    def add(key,**kwargs):
        first=not any(p['key']==key for p in plans)
        title=TITLES[PAGES.index(key)]
        kicker='TÓM TẮT NGÀNH' if key=='01_summary' else 'A · THẾ GIỚI' if key.startswith(('02','03','04','05')) else 'B · VIỆT NAM' if key[:2] in ('06','07','08','09','10','11') else 'C · TRIỂN VỌNG VÀ RỦI RO' if key[:2] in ('12','13') else 'D · DOANH NGHIỆP TRONG NGÀNH'
        plans.append(dict(key=key,path=PATHS[key],title=title,kicker=kicker,first=first,**kwargs))
    s=d['summary'];lists=[chunk(indexed(s['kpis']),4),chunk(s['stances'],5),chunk(s['global_highlights'],3),chunk(s['domestic_highlights'],3)]
    for i in range(max(map(len,lists))):add('01_summary',**{k:rows[i] if i<len(rows) else [] for k,rows in zip(('kpis','stances','global_highlights','domestic_highlights'),lists)})
    o=d['global']['overview'];chunks=[chunk(o['phases'],7),chunk(o['per_capita'],8),chunk(o['notes'],4)]
    if not hide_empty or has_data(o):
        for i in range(max(map(len,chunks))):add('02_global_overview',**{k:r[i] if i<len(r) else [] for k,r in zip(('phases','per_capita','notes'),chunks)})
    v=d['global']['value_chain'];price=v['price_forecast']
    if not hide_empty or has_data(v):
        # Wide tables are split by both rows and year columns, never clipped.
        year_chunks=chunk(list(enumerate(price['years'])),9)
        for ys in year_chunks:
            for ss in chunk(price['series'],5):
                f={**price,'years':[y for _,y in ys],'series':[{**r,'values':[r['values'][i] if i<len(r['values']) else None for i,_ in ys]} for r in ss]}
                add('03_global_value_chain',price_forecast=f)
    supply=chunk(indexed(d['global']['supply_demand']),5);policies=chunk(d['global']['policy_trends'],2)
    if not hide_empty or d['global']['supply_demand'] or d['global']['policy_trends']:
        for i in range(max(len(supply),len(policies))):
            rows=supply[i] if i<len(supply) else []
            add('04_global_supply',supply=rows,policies=policies[i] if i<len(policies) else [],utilization=[dict(label=r['material'],value=r.get('utilization')) for r in rows])
    segments=indexed(d['global']['segments']);traits=chunk(d['global']['segment_traits'],6)
    if not hide_empty or segments or d['global']['segment_traits']:
        batches=chunk(segments,2) if sum(bool(r.get('regional_split') or r.get('demand_split')) for r in segments)<=1 else chunk(segments,1)
        for i in range(max(len(batches),len(traits))):add('05_global_segments',segments=batches[i] if i<len(batches) else [],traits=traits[i] if i<len(traits) else [])
    o=d['domestic']['overview']
    if not hide_empty or has_data(o):
        for rows in chunk(o['per_capita'],8):add('06_domestic_overview',per_capita=rows)
    if not hide_empty or has_data(d['domestic']['competition']) or has_data(d['domestic']['value_chain']):
        comps=chunk(d['domestic']['competition'],5);mach=chunk(d['domestic']['value_chain']['machinery_imports']['cagr_periods'],4)
        for i in range(max(len(comps),len(mach))):add('07_domestic_competition',competition=comps[i] if i<len(comps) else [],machinery=mach[i] if i<len(mach) else [])
    regs=indexed(d['domestic']['regulations'])
    if not hide_empty or regs or d['domestic']['authorities']:
        # Split legal tables without losing paragraphs or rows.
        expanded=[]
        for r in regs:
            tables=r.get('tables',[])
            if not tables:expanded.append(r);continue
            for t in tables:
                for rows in chunk(t['rows'],12):expanded.append({**r,'tables':[{**t,'rows':rows}]})
        batches=[];batch=[];weight=0
        for r in expanded:
            w=2+sum(len(t['rows']) for t in r.get('tables',[]))
            if batch and weight+w>15:batches.append(batch);batch=[];weight=0
            batch.append(r);weight+=w
        if batch:batches.append(batch)
        for i,rs in enumerate(batches or [[]]):add('08_domestic_regulations',regulations=rs,authorities=d['domestic']['authorities'] if i==0 else [])
    for i,r in enumerate(indexed(d['domestic']['segments'])):
        key=PAGES[8+min(i,2)]
        x=r.get('export',{});sets=[chunk(r.get('notes',[])+x.get('notes',[]),4),chunk(r.get('customers',[]),4),chunk(r.get('growth_series',[])+x.get('series',[]),1),chunk(r.get('headwinds',[]),3),chunk(r.get('tailwinds',[]),3)]
        for j in range(max(map(len,sets))):
            add(key,segment=r,notes=sets[0][j] if j<len(sets[0]) else [],customers=sets[1][j] if j<len(sets[1]) else [],series=sets[2][j] if j<len(sets[2]) else [],headwinds=sets[3][j] if j<len(sets[3]) else [],tailwinds=sets[4][j] if j<len(sets[4]) else [],export_structure=x.get('structure',[]) if j==0 else [])
            plans[-1]['title']=r['name']+(' · tiếp' if j else '')
            plans[-1]['scope_paths']=[f'domestic.segments.{i}']
    o=d['domestic']['outlook'];sets=[chunk(o['segment_table'],5),chunk(o['series'],2),chunk(o['macro_drivers'],3)]
    if not hide_empty or has_data(o):
        for i in range(max(map(len,sets))):add('12_outlook',**{k:r[i] if i<len(r) else [] for k,r in zip(('segments','series','drivers'),sets)})
    errors=[f for f in inspect(payload)['flags'] if f['severity']=='error'];sets=[chunk(s['stances'],5),chunk(d['domestic']['risks'],3),chunk(errors,5),chunk(d['meta']['sources'],12)]
    for i in range(max(map(len,sets))):add('13_views_risks',**{k:r[i] if i<len(r) else [] for k,r in zip(('stances','risks','flags','sources'),sets)})
    if not s['stances'] and not d['domestic']['risks']:
        for p in plans:
            if p['key']=='13_views_risks':p['title']='Nguồn dữ liệu và phạm vi sử dụng'
    table=d['companies']['table']
    if not hide_empty or table['rows']:
        batches=[];batch=[];height=0
        for row in indexed(table['rows']):
            # Conservative estimate includes wrapped group names and missing reasons.
            # The final browser gate measures every row before committing a PDF.
            lines=max(1,(len(row.get('group') or '')+13)//14)
            for field in NUMERIC_COLUMNS:
                if field in table['columns'] and row.get(field) is None:
                    if field.endswith('_yoy') and row.get(field.replace('_yoy','_prior')) is not None and row[field.replace('_yoy','_prior')]<=0:continue
                    path=f'companies.table.rows.{row["_index"]}.{field}';reason=d['missing_reasons'].get(path) or d['missing_reasons'].get(path.rpartition('.')[0]) or 'Nguồn chưa cung cấp dữ liệu được xác nhận cho kỳ này'
                    lines=max(lines,2+(len(reason)+12)//13)
            weight=max(28,lines*9+15)
            if batch and (len(batch)==19 or height+weight>650):batches.append(batch);batch=[];height=0
            batch.append(row);height+=weight
        if batch:batches.append(batch)
        for rows in batches or [[]]:add('14_companies',rows=rows,columns=table['columns'],scope_paths=[f'companies.table.rows.{r["_index"]}' for r in rows])
    profiles=indexed(d['companies']['profiles']);batches=[];current=[]
    for profile in profiles:
        large=bool(profile.get('tables') or profile.get('structure') or len(profile.get('business_points',[]))>4 or len(profile.get('series',[]))>1)
        if large:
            if current:batches.append(current);current=[]
            batches.append([profile])
        else:
            current.append(profile)
            if len(current)==2:batches.append(current);current=[]
    if current:batches.append(current)
    if not hide_empty and not batches:batches=[[]]
    for i,ps in enumerate(batches):add('15_profiles' if i==0 else '16_profiles',profiles=ps,scope_paths=[f'companies.profiles.{r["_index"]}' for r in ps])
    if order is not None:
        if not order or len(order)!=len(set(order)) or any(x not in PAGES for x in order):raise ValueError('Thứ tự trang ngành không hợp lệ')
        plans=[p for key in order for p in plans if p['key']==key]
    if not plans:raise ValueError('Không có trang ngành để xuất')
    return plans

def asset_fingerprint():
    digest=hashlib.sha256()
    for p in sorted(p for p in ROOT.rglob('*') if p.is_file() and p.suffix in ('.py','.html','.css','.json')):
        digest.update(str(p.relative_to(ROOT)).encode());digest.update(p.read_bytes())
    assets=ROOT.parent/'stocklens/assets'
    digest.update((assets/'fonts.css').read_bytes())
    for p in sorted((assets/'fonts').glob('*.woff2')):digest.update(p.read_bytes())
    return digest.hexdigest()

def styles(accent):
    if not re.fullmatch(r'#[0-9A-Fa-f]{6}',accent):raise ValueError('Accent must be a hex color')
    import base64
    assets=ROOT.parent/'stocklens/assets'
    def embed(m):
        p=(assets/m[1]).resolve()
        if not p.is_relative_to((assets/'fonts').resolve()):raise ValueError('Invalid font path')
        return 'url("data:font/woff2;base64,'+base64.b64encode(p.read_bytes()).decode()+'")'
    fonts=re.sub(r'url\("([^"]+)"\)',embed,(assets/'fonts.css').read_text(encoding='utf-8'))
    return fonts+'\n'+(ROOT/'tokens.css').read_text(encoding='utf-8')+'\n'+(ROOT/'components.css').read_text(encoding='utf-8')+'\n:root{--accent:'+accent+'}.three{grid-template-columns:repeat(3,minmax(0,1fr))}'

def source_label(source):
    if not source_valid(source):return 'Chưa có nguồn xác nhận'
    return (source.get('organization') or source.get('name'))+' · '+(source.get('date') or source.get('published_at'))[:10]

def render_html(payload,*,accent='#1F5EFF',pages=None,hide_empty=True,draft=False,exported_at=None):
    quality=inspect(payload)
    if any(f['code'] in ('schema','non_finite') for f in quality['flags']):raise ValueError('JSON ngành không hợp lệ: '+json.dumps(quality['flags'],ensure_ascii=False)[:2000])
    d=normalize(payload);plan=page_plan(payload,pages,hide_empty)
    sources_by_id={s['id']:s for s in d['meta']['sources']}
    def ancestor(mapping,path):
        while path:
            if path in mapping:return mapping[path]
            path=path.rpartition('.')[0]
        return None
    def reason(path):return ancestor(d['missing_reasons'],path) or 'Nguồn chưa cung cấp dữ liệu được xác nhận cho kỳ này'
    def unit(path):
        return d['units'].get(path) or (ancestor(d['provenance'],path) or {}).get('unit') or ''
    def source_text(path,explicit=None):
        if isinstance(explicit,dict) and source_valid(explicit.get('source')):return source_label(explicit['source'])
        prov=ancestor(d['provenance'],path) or {};s=sources_by_id.get(prov.get('source_id'))
        if s:return '['+s['id']+'] '+s['name']
        refs={v['source_id'] for k,v in d['provenance'].items() if k.startswith(path+'.')}
        names=['['+sid+'] '+sources_by_id[sid]['name'] for sid in sorted(refs) if sid in sources_by_id]
        return '; '.join(names) or 'Chưa có nguồn xác nhận'
    def source(path,units='',explicit=None):
        from markupsafe import Markup,escape
        return Markup('<div class="source">Nguồn: ')+escape(source_text(path,explicit))+escape(' · Đơn vị: '+units if units else '')+Markup('</div>')
    def footer(p):
        prefixes=p.get('scope_paths') or [p['path']]
        if p['key']=='04_global_supply':prefixes.append('global.policy_trends')
        if p['key']=='07_domestic_competition':prefixes.append('domestic.value_chain')
        refs={entry['source_id'] for path,entry in d['provenance'].items() if any(path==x or path.startswith(x+'.') for x in prefixes)}
        names=['['+sid+'] '+sources_by_id[sid]['name'] for sid in sorted(refs) if sid in sources_by_id]
        return '; '.join(names) or 'Xem nguồn tại từng khối / danh mục nguồn'
    def review(p):
        if p.get('flags'):return True
        prefixes=p.get('scope_paths') or [p['path']]
        if p['key']=='04_global_supply':prefixes.append('global.policy_trends')
        if p['key']=='07_domestic_competition':prefixes.append('domestic.value_chain')
        return any(f['severity']=='error' and (f['path'].startswith('meta') or any(f['path']==x or f['path'].startswith(x+'.') for x in prefixes)) for f in quality['flags'])
    env=Environment(loader=FileSystemLoader(ROOT),undefined=StrictUndefined,autoescape=select_autoescape(('html',)))
    env.filters['num']=number
    def tone(v,polarity):return 'neutral' if v is None or v==0 or polarity=='neutral' else 'good' if (v>0)==(polarity=='higher_good') else 'bad'
    tz=ZoneInfo('Asia/Ho_Chi_Minh');stamp=(exported_at or datetime.now(tz)).astimezone(tz).strftime('%d/%m/%Y %H:%M %z')
    return env.get_template('base.html').render(d=d,quality=quality,pages=plan,styles=styles(accent),exported_at=stamp,draft=draft,unknown_license=d['meta']['attribution']['license_status']=='unknown',reason=reason,units=unit,source=source,source_label=source_label,footer_sources=footer,review=review,derived=lambda p:p in d['derived'],tone=tone,text=lambda x:x['text'] if isinstance(x,dict) else x,columns=columns,stacked=stacked,horizontal=horizontal,sourced_stances=lambda rows:[r for r in rows if source_valid(r.get('source'))],valid_source=source_valid,rating_tone=lambda r:'good' if r=='KHẢ QUAN' else 'bad' if r=='KÉM KHẢ QUAN' else '',column_labels=COLUMN_LABELS,numeric_columns=NUMERIC_COLUMNS,trading_fields=TRADING_FIELDS)

OVERFLOW_JS="""() => Array.from(document.querySelectorAll('.page')).flatMap((page,index)=>{
 const content=page.querySelector('.page-content'),footer=page.querySelector('.page-footer'),box=page.getBoundingClientRect(),bad=[];
 for(const node of [page.querySelector('.page-header'),footer,content,...content.querySelectorAll('*')]){
 const r=node.getBoundingClientRect(),tag=node.tagName.toLowerCase();if(node.closest('svg'))continue;
 if(r.width&&r.height&&(r.left<box.left+54||r.right>box.right-54||node.scrollWidth>node.clientWidth+2||node.scrollHeight>node.clientHeight+2||(node.closest('.page-content')&&r.bottom>footer.getBoundingClientRect().top-10)))bad.push({tag,class:node.className,text:node.textContent.slice(0,90),bottom:r.bottom-box.top});
 }return bad.length?[{page:index+1,industry:page.dataset.industry,period:page.dataset.period,partial:page.dataset.page,items:bad.slice(0,15)}]:[];
})"""

def render_pdf(payload,destination,*,qa_directory=None,**options):
    from playwright.sync_api import sync_playwright,Error
    from pypdf import PdfReader
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    quality=inspect(payload)
    def save_audit():destination.with_suffix('.quality_report.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2),encoding='utf-8')
    save_audit();html=render_html(payload,**options)
    plan=page_plan(payload,options.get('pages'),options.get('hide_empty',True))
    quality['pages']=[dict(number=i+1,partial=p['key'],title=p['title']) for i,p in enumerate(plan)]
    with sync_playwright() as pw:
        try:browser=pw.chromium.launch(headless=True)
        except Error:browser=pw.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page(viewport={'width':794,'height':1123},device_scale_factor=1)
            page.route('**/*',lambda route:route.abort());page.set_content(html,wait_until='load');page.evaluate('() => document.fonts.ready')
            overflow=page.evaluate(OVERFLOW_JS)
            if overflow:
                logging.getLogger(__name__).error('Industry overflow %s',json.dumps(overflow,ensure_ascii=False))
                quality['overflow']=overflow;quality['status']='needs_review';save_audit()
                raise ValueError('Tràn nội dung ngành (không cắt âm thầm): '+json.dumps(overflow,ensure_ascii=False))
            if qa_directory:
                qa=Path(qa_directory);qa.mkdir(parents=True,exist_ok=True)
                for i,node in enumerate(page.locator('.page').all(),1):node.screenshot(path=str(qa/f'page-{i:02}.png'))
            temporary=destination.with_suffix('.pdf.tmp')
            try:
                page.pdf(path=str(temporary),width='794px',height='1123px',print_background=True,prefer_css_page_size=True)
                if len(PdfReader(temporary).pages)!=len(plan):raise ValueError('Số trang PDF không khớp partials')
                temporary.replace(destination)
            finally:
                if temporary.exists():temporary.unlink()
        finally:browser.close()
    quality['overflow']=[];save_audit()
    destination.with_suffix('.json').write_text(json.dumps(normalize(payload),ensure_ascii=False,indent=2),encoding='utf-8')
    destination.with_suffix('.html').write_text(html,encoding='utf-8')
    return destination
