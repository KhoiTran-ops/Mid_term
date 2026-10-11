"""Dated release snapshots, separate from annual World Bank context.

NSO adapter deliberately scopes each metric to its paragraph and statistical period.
Missing/new formats fail closed per field; no fallback to design sample numbers.
Other providers can supply licensed JSON with field-level provenance through the
same nullable schema. No scraping of proprietary PMI history or Fiinpro login.
"""
from datetime import datetime,date,timedelta
import hashlib
import json
from pathlib import Path
import re
import time
import unicodedata
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from stock_reports.reports.macro_stocklens.data import normalize,period_meta,set_value,get
from stock_reports.reports.macro_stocklens.quality import inspect
from stock_reports.core.locking import ProcessLock

NUM=r'([\d.]+(?:,\d+)?)'

def vn_number(value):return float(value.replace('.','').replace(',','.'))

def parse_nso(html,release,retrieved_at):
    soup=BeautifulSoup(html,'html.parser')
    content=soup.select_one('.entry-content') or soup.select_one('article')
    if content is None:raise ValueError('NSO không có nội dung báo cáo; không lấy toàn bộ trang điều hướng')
    title=soup.find('h1');year=release['period'][:4]
    if title is None or '9 tháng' not in title.get_text(' ',strip=True).lower() or year not in title.get_text():raise ValueError('NSO sai tiêu đề / kỳ báo cáo')
    paragraphs=[unicodedata.normalize('NFC',re.sub(r'\s+',' ',p.get_text(' ',strip=True))) for p in content.find_all('p')]
    text='\n'.join(paragraphs)
    if len(text)<4000:raise ValueError('NSO nội dung quá ngắn')
    source=dict(id='nso-'+release['period'],name='Cục Thống kê',url=release['url'],source_published_at=release['published'],retrieved_at=retrieved_at,period_code=release['period'])
    d=normalize(dict(meta={**period_meta(release['period']),'report_date':release['published'],'sources':[source],'publisher_note':'Dữ liệu thống kê ước tính / sơ bộ theo thời điểm công bố; không dùng số minh họa của mẫu thiết kế.'}))
    def para(start):return next((p for p in paragraphs if re.search(start,p,re.I)), '')
    def pick(path,body,pattern,scale=1,sign=1):
        match=re.search(pattern,body,re.I)
        if match:
            set_value(d,path,vn_number(match[1])*scale*sign)
            d['provenance'][path]={**source,'source_id':source['id'],'raw_sha256':hashlib.sha256(html.encode()).hexdigest()}
        else:d['missing_reasons'][path]='Không tìm thấy đúng chỉ tiêu và kỳ trong công bố NSO đã lưu'
    growth=r'(?:ước\s*)?(?:tính\s*)?(?:tăng|đạt)\s+'+NUM
    p=para(r'GDP\)? chín tháng|GDP\)? 9 tháng')
    pick('gdp.ytd.yoy',p,r'GDP\)? (?:chín|9) tháng[^.]*?tăng\s+'+NUM)
    d['gdp']['ytd']['label']='9T/'+year;d['gdp']['q']['label']='Q3/'+year
    q=para(r'Tổng sản phẩm trong nước.*quý III/')
    pick('gdp.q.yoy',q,r'quý III/'+year+r'.*?tăng\s+'+NUM)
    for name,anchor in [('Nông, lâm nghiệp và thủy sản',r'nông, lâm nghiệp và thủy sản'),('Công nghiệp và xây dựng',r'công nghiệp và xây dựng'),('Dịch vụ',r'dịch vụ')]:
        m=re.search(anchor+r' tăng\s+'+NUM+r'%.*?đóng góp\s+'+NUM+r'%',p,re.I)
        if m:
            d['gdp']['sectors'].append(dict(name=name,yoy=vn_number(m[1]),contribution_pct=vn_number(m[2])))
    if d['gdp']['sectors']:d['provenance']['gdp.sectors']={**source,'source_id':source['id']}
    p=para(r'Chỉ số sản xuất công nghiệp \(IIP\).*quý') or para(r'(?:chín|9) tháng năm '+year+r'.*?IIP (?:ước )?tăng')
    pick('iip.q_yoy',p,r'quý.*?tăng\s+'+NUM+r'%')
    pick('iip.ytd_yoy',p,r'(?:chín|9) tháng năm '+year+r'.*?(?:IIP|chỉ số).*?tăng\s+'+NUM+r'%')
    pick('iip.manufacturing_yoy',p,r'chế biến, chế tạo tăng\s+'+NUM+r'%')
    d['missing_reasons']['iip.prev_ytd_yoy']='Phải đối chiếu IIP kỳ trước; 9,1% trong mẫu là chỉ số tiêu thụ, không phải IIP'
    p=para(r'Tính chung chín tháng.*doanh nghiệp đăng ký thành lập mới')
    pick('business.new_and_returned_k',p,r'(?:hơn\s*)'+NUM+r' nghìn doanh nghiệp đăng ký')
    pick('business.new_yoy',p,r'quay trở lại hoạt động, giảm\s+'+NUM,sign=-1)
    pick('business.exited_k',p,r'rút lui khỏi thị trường là\s+'+NUM)
    pick('business.exited_yoy',p,r'rút lui khỏi thị trường.*?giảm\s+'+NUM,sign=-1)
    p=para(r'Tổng mức bán lẻ')
    pick('retail.q.value_bn_vnd',p,r'quý III/'+year+r'.*?đạt\s+'+NUM+r' nghìn tỷ',scale=1000)
    pick('retail.q.qoq',p,r'quý III/'+year+r'.*?tăng\s+'+NUM+r'% so với quý trước')
    pick('retail.q.yoy',p,r'quý III/'+year+r'.*?quý trước và tăng\s+'+NUM)
    pick('retail.ytd.value_bn_vnd',p,r'(?:chín|9) tháng năm '+year+r'.*?đạt\s+'+NUM+r' nghìn tỷ',scale=1000)
    pick('retail.ytd.yoy',p,r'(?:chín|9) tháng năm '+year+r'.*?tăng\s+'+NUM+r'% so với cùng kỳ')
    p=para(r'Tính đến thời điểm.*tăng trưởng tín dụng')
    pick('monetary.credit_growth_ytd',p,r'tăng trưởng tín dụng.*?đạt\s+'+NUM)
    m=re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})',p)
    if m:d['monetary']['credit_as_of']=f'{m[3]}-{int(m[2]):02}-{int(m[1]):02}'
    d['missing_reasons']['monetary.fx_change_ytd']='Chưa có tỷ giá giao ngay NHNN cùng cơ sở so sánh; không thay bằng chỉ số giá USD của NSO'
    p=re.split(r'Vốn đầu tư trực tiếp nước ngoài thực hiện',para(r'Tổng vốn đầu tư nước ngoài đăng ký'),flags=re.I)[0]
    pick('fdi.registered_usd_bn',p,r'đạt\s+(?:gần\s+)?'+NUM+r' tỷ USD')
    pick('fdi.registered_yoy',p,r'tăng\s+'+NUM+r'%')
    if re.search(r'giảm\s+'+NUM+r'%',p):pick('fdi.registered_yoy',p,r'giảm\s+'+NUM+r'%',sign=-1)
    observed=re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})',p)
    if observed and 'fdi.registered_usd_bn' in d['provenance']:d['provenance']['fdi.registered_usd_bn']['observation_date']=f'{observed[3]}-{int(observed[2]):02}-{int(observed[1]):02}'
    p=para(r'Vốn đầu tư trực tiếp nước ngoài thực hiện')
    anchor=re.search(r'Vốn đầu tư trực tiếp nước ngoài thực hiện.*',p,re.I)
    p=anchor[0] if anchor else ''
    pick('fdi.disbursed_usd_bn',p,r'đạt\s+'+NUM+r' tỷ USD')
    pick('fdi.disbursed_yoy',p,r'tăng\s+'+NUM+r'%')
    for key,anchor in [('revenue','thu'),('expenditure','chi')]:
        p=para(r'Tổng '+anchor+r' ngân sách Nhà nước tháng')
        pick('budget.month.'+key,p,r'tháng.*?đạt\s+'+NUM+r' nghìn tỷ')
        pick('budget.ytd.'+key,p,r'(?:chín|9) tháng năm '+year+r'.*?đạt\s+'+NUM+r' nghìn tỷ')
        pick('budget.ytd.'+key+'_pct_plan',p,r'bằng\s+'+NUM+r'%')
        pick('budget.ytd.'+key+'_yoy',p,r'tăng\s+'+NUM+r'%')
    for key,anchor in [('export','xuất'),('import','nhập')]:
        p=para(r'Kim ngạch '+anchor+r' khẩu hàng hóa tháng')
        pick('trade.q.'+key+'_usd_bn',p,r'quý III/'+year+r'.*?đạt\s+'+NUM+r' tỷ USD')
        pick('trade.q.'+key+'_yoy',p,r'quý III/'+year+r'.*?tăng\s+'+NUM+r'% so với cùng kỳ')
        pick('trade.q.'+key+'_qoq',p,r'quý III/'+year+r'.*?cùng kỳ năm trước và tăng\s+'+NUM)
        pick('trade.ytd.'+key+'_usd_bn',p,r'(?:chín|9) tháng năm '+year+r'.*?đạt\s+'+NUM+r' tỷ USD')
        pick('trade.ytd.'+key+'_yoy',p,r'(?:chín|9) tháng năm '+year+r'.*?tăng\s+'+NUM+r'% so với cùng kỳ')
    p=para(r'(?:Tính chung|Trong) (?:chín|9) tháng.*tổng kim ngạch xuất,? nhập khẩu') or para(r'Tổng kim ngạch xuất,? nhập khẩu')
    pick('trade.ytd.total_usd_bn',p,r'(?:chín|9) tháng năm '+year+r'.*?đạt\s+'+NUM+r' tỷ USD')
    pick('trade.ytd.total_yoy',p,r'(?:chín|9) tháng năm '+year+r'.*?tăng\s+'+NUM+r'%')
    p=para(r'Theo số liệu sơ bộ, cán cân thương mại') or para(r'Cán cân thương mại.*tháng')
    pick('trade.month_balance_usd_bn',p,r'tháng.*?xuất siêu\s+'+NUM)
    pick('trade.ytd.balance_usd_bn',p,r'(?:chín|9) tháng năm '+year+r'.*?nhập siêu\s+'+NUM,sign=-1)
    pick('trade.domestic_balance_usd_bn',p,r'khu vực kinh tế trong nước nhập siêu\s+'+NUM,sign=-1)
    pick('trade.fdi_balance_usd_bn',p,r'khu vực có vốn đầu tư nước ngoài.*?xuất siêu\s+'+NUM)
    p=para(r'Về cơ cấu nhóm hàng nhập khẩu')
    for name,anchor in [('Tư liệu sản xuất','tư liệu sản xuất'),('Hàng tiêu dùng',r'(?:hàng tiêu dùng|vật phẩm tiêu dùng)')]:
        m=re.search(anchor+r'.*?chiếm\s+'+NUM+r'%',p,re.I)
        if m:d['trade']['import_structure'].append(dict(name=name,pct=vn_number(m[1])))
    if d['trade']['import_structure']:d['provenance']['trade.import_structure']={**source,'source_id':source['id']}
    p=para(r'Chỉ số giá tiêu dùng \(CPI\) tháng')
    pick('cpi.month_mom',p,r'tháng.*?tăng\s+'+NUM+r'% so với tháng trước')
    pick('cpi.month_yoy',p,r'và tăng\s+'+NUM+r'% so với cùng kỳ')
    pick('cpi.quarter_yoy',p,r'quý III/'+year+r' tăng\s+'+NUM)
    pick('cpi.ytd_avg_yoy',p,r'(?:chín|9) tháng năm (?:'+year+r'|nay),? CPI tăng\s+'+NUM)
    pick('cpi.core_ytd_yoy',p,r'lạm phát cơ bản tăng\s+'+NUM)
    return normalize(d)

def fetch_snapshot(settings,release,force=False):
    directory=settings.root/'var/macro/releases'/release['period'];directory.mkdir(parents=True,exist_ok=True)
    index=directory/'latest.json';now=datetime.now().astimezone()
    if index.exists() and not force:
        old=json.loads(index.read_text(encoding='utf-8'))
        if now-datetime.fromisoformat(old['retrieved_at'])<timedelta(hours=12):return parse_nso((directory/old['file']).read_text(encoding='utf-8'),release,old['retrieved_at'])
    failure=None
    for attempt in range(3):
        try:
            response=httpx.get(release['url'],timeout=25,follow_redirects=True)
            response.raise_for_status()
            if urlparse(str(response.url)).hostname not in ('www.nso.gov.vn','nso.gov.vn','www.gso.gov.vn','gso.gov.vn'):raise ValueError('NSO chuyển hướng ra ngoài nguồn chính thức')
            stamp=now.isoformat();payload=parse_nso(response.text,release,stamp)
            filename=now.strftime('%Y%m%dT%H%M%S')+'-'+hashlib.sha256(response.content).hexdigest()[:12]+'.html'
            (directory/filename).write_text(response.text,encoding='utf-8')
            index.write_text(json.dumps(dict(url=str(response.url),retrieved_at=stamp,source_published_at=release['published'],file=filename),ensure_ascii=False,indent=2),encoding='utf-8')
            return payload
        except (httpx.HTTPError,ValueError) as error:
            failure=error
            if attempt<2:time.sleep(attempt+1)
    if index.exists():
        old=json.loads(index.read_text(encoding='utf-8'));payload=parse_nso((directory/old['file']).read_text(encoding='utf-8'),release,old['retrieved_at']);payload['source_differences']=[dict(source='NSO',reason='Nguồn tạm lỗi; sử dụng snapshot đã lưu',error=type(failure).__name__)];return payload
    raise ValueError(f'Không lấy được công bố {release["period"]}: {type(failure).__name__}')

def load_period(settings,code=None,*,as_of=None,refresh=False,history=True):
    cfg=json.loads((settings.root/'config/macro_stocklens.json').read_text(encoding='utf-8'))
    cutoff=(as_of or datetime.now().date()).isoformat()
    if code is None:
        available=[r for r in cfg['releases'] if r['published']<=cutoff]
        if not available:raise ValueError('Chưa có kỳ vĩ mô công bố trước ngày chốt')
        code=max(available,key=lambda r:r['period'])['period']
    period_meta(code)
    releases={r['period']:r for r in cfg['releases']}
    if code not in releases:raise ValueError('Chưa cấu hình công bố chính thức kỳ '+code+'; nhập JSON kỳ tương ứng bằng --input')
    if releases[code]['published']>cutoff:raise ValueError('Kỳ vĩ mô chưa công bố tại ngày chốt')
    lock=ProcessLock(settings.root/'var/macro-periods.lock')
    if not lock.acquire():raise ValueError('Đang cập nhật kỳ vĩ mô; thử lại sau')
    try:
        d=fetch_snapshot(settings,releases[code],force=refresh)
        d['meta']['report_date']=cutoff
        historical=[];errors=[]
        if history:
            for r in sorted(cfg['releases'],key=lambda r:r['period']):
                if r['period']>=code or r['period'][4:]!=code[4:]:continue
                try:historical.append(fetch_snapshot(settings,r))
                except ValueError as e:errors.append(dict(period=r['period'],reason=str(e)))
        for old in historical+[d]:
            year=int(old['meta']['period_code'][:4])
            for target,fields in [('gdp.history',{'ytd_yoy':'gdp.ytd.yoy'}),('iip.history',{'ytd_yoy':'iip.ytd_yoy'}),('cpi.history_ytd',{'yoy':'cpi.ytd_avg_yoy'}),('retail.history',{'value_bn_vnd':'retail.ytd.value_bn_vnd','yoy':'retail.ytd.yoy'}),('trade.history_ytd',{'export_usd_bn':'trade.ytd.export_usd_bn','import_usd_bn':'trade.ytd.import_usd_bn'}),('fdi.history_ytd',{'registered':'fdi.registered_usd_bn','disbursed':'fdi.disbursed_usd_bn'})]:
                row=dict(year=year,**{name:get(old,path) for name,path in fields.items()})
                if target=='fdi.history_ytd':row['registered_as_of']=old['provenance'].get('fdi.registered_usd_bn',{}).get('observation_date')
                if any(v is not None for k,v in row.items() if k!='year'):
                    get(d,target).append(row)
                    src=old['meta']['sources'][0]
                    d['provenance'][target+'.'+str(len(get(d,target))-1)]={**src,'source_id':src['id'],'historical':year!=int(code[:4])}
            if old is not d:d['meta']['sources']+=old['meta']['sources']
        prev=next((x for x in historical if int(x['meta']['period_code'][:4])==int(code[:4])-1),None)
        if prev and prev['iip']['ytd_yoy'] is not None:
            d['iip']['prev_ytd_yoy']=prev['iip']['ytd_yoy'];d['provenance']['iip.prev_ytd_yoy']={**prev['meta']['sources'][0],'source_id':prev['meta']['sources'][0]['id'],'historical':True}
        for release in cfg.get('pmi_releases',[]):
            if release['period']!=code or release['published']>cutoff:continue
            try:
                values,source=fetch_pmi(settings,release,force=refresh)
                for path,value in values.items():
                    set_value(d,path,value);d['provenance'][path]={**source,'source_id':source['id']}
                d['meta']['sources'].append(source)
            except ValueError as e:errors.append(dict(source='S&P Global / Cimigo',reason=str(e)))
        for source_config in cfg.get('licensed_json_sources',[]):
            if source_config.get('period')!=code or source_config.get('published','')>cutoff:continue
            try:
                values,source,units=fetch_licensed_json(settings,source_config,force=refresh)
                for path,value in values.items():
                    set_value(d,path,value);d['provenance'][path]={**source,'source_id':source['id']}
                d['units'].update(units);d['meta']['sources'].append(source)
            except ValueError as e:errors.append(dict(source=source_config.get('name'),reason=str(e)))
        for group in ('budget.plan','public_investment','fdi.top_projects','fdi.top_countries'):
            if group not in d['missing_reasons']:d['missing_reasons'][group]='Chưa có công bố nguồn sơ cấp đúng kỳ / bộ dữ liệu được cấp phép cho nhóm này'
        d['source_differences']=d.get('source_differences',[])+errors
        if code=='2026-9T':
            d['source_differences'] += [dict(path='monetary.credit_growth_ytd',design_value=11.59,primary_value=d['monetary']['credit_growth_ytd'],reason='Mẫu dùng 30/9; NSO công bố ngày chốt 28/9. Không trộn ngày.'),dict(path='iip.prev_ytd_yoy',design_value=9.1,primary_value=d['iip']['prev_ytd_yoy'],reason='Đối chiếu riêng công bố IIP 9T/2025, không dùng đoạn chỉ số tiêu thụ trong công bố 2026.')]
        d=normalize(d);quality=inspect(d)
        cache=settings.root/'var/macro/periods';cache.mkdir(parents=True,exist_ok=True)
        temporary=cache/(code+'.json.tmp');temporary.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(cache/(code+'.json'))
        (cache/(code+'.quality_report.json')).write_text(json.dumps(quality,ensure_ascii=False,indent=2),encoding='utf-8')
        return d
    finally:lock.release()

def _fetch_external(settings,source_config,adapter,force):
    """Shared immutable raw snapshots + twelve-hour cache + bounded retry."""
    url=source_config['url']
    if urlparse(url).scheme!='https':raise ValueError('Nguồn dữ liệu phải dùng HTTPS')
    name=hashlib.sha256((url+source_config['period']).encode()).hexdigest()[:20]
    directory=settings.root/'var/macro/external'/name;directory.mkdir(parents=True,exist_ok=True)
    index=directory/'latest.json';now=datetime.now().astimezone();old=None
    if index.exists():old=json.loads(index.read_text(encoding='utf-8'))
    if old and not force and now-datetime.fromisoformat(old['retrieved_at'])<timedelta(hours=12):return adapter((directory/old['file']).read_text(encoding='utf-8'),old['retrieved_at'])
    for attempt in range(3):
        try:
            response=httpx.get(url,timeout=20,follow_redirects=True);response.raise_for_status()
            if urlparse(str(response.url)).hostname!=urlparse(url).hostname:raise ValueError('Nguồn chuyển hướng ra ngoài host đã cấu hình')
            result=adapter(response.text,now.isoformat())
            filename=now.strftime('%Y%m%dT%H%M%S')+'-'+hashlib.sha256(response.content).hexdigest()[:12]+'.raw'
            (directory/filename).write_text(response.text,encoding='utf-8')
            index.write_text(json.dumps(dict(file=filename,url=str(response.url),retrieved_at=now.isoformat(),source_published_at=source_config['published']),ensure_ascii=False,indent=2),encoding='utf-8')
            return result
        except (httpx.HTTPError,ValueError) as error:
            if attempt<2:time.sleep(attempt+1)
    if old:return adapter((directory/old['file']).read_text(encoding='utf-8'),old['retrieved_at'])
    raise ValueError('Không tải / xác minh được nguồn đúng kỳ; không điền số mẫu')

def fetch_pmi(settings,release,*,force=False):
    def adapter(html,retrieved):
        soup=BeautifulSoup(html,'html.parser');text=re.sub(r'\s+',' ',soup.get_text(' ',strip=True))
        if f'Vietnam PMI {release["month"]} {release["year"]}' not in text:raise ValueError('Cimigo đã chuyển kỳ; không dùng headline kỳ mới cho kỳ cũ')
        match=re.search(r'Index.*?\(PMI.*?(?:dropped|rose|increased|fell|registered).*?(\d+\.\d+).*?'+release['month']+r'.*?(?:reading of|from) (\d+\.\d+)',text)
        if not match:raise ValueError('Không tìm thấy headline PMI và kỳ trước')
        source=dict(id='pmi-'+release['period'],name='S&P Global · Cimigo',url=release['url'],source_published_at=release['published'],retrieved_at=retrieved,period_code=release['period'])
        return {'pmi.value':float(match[1]),'pmi.previous':float(match[2])},source
    return _fetch_external(settings,release,adapter,force)

def fetch_licensed_json(settings,config,*,force=False):
    """MPI/MOF/NHNN/Fiinpro bridge for an explicitly authorized JSON feed.

    Contract: {period_code, fields: {dotted_path: value}, units: {...}}.
    Configure only endpoints whose use the publisher has authorized. No keys in URL.
    """
    if config.get('authorized') is not True:raise ValueError('Nguồn JSON chưa được xác nhận quyền sử dụng')
    if urlparse(config['url']).query:raise ValueError('Không cấu hình credential / query trong URL nguồn')
    def adapter(raw,retrieved):
        payload=json.loads(raw)
        if payload.get('period_code')!=config['period']:raise ValueError('Nguồn JSON sai kỳ')
        values=payload.get('fields',{})
        if not isinstance(values,dict) or any(p.split('.')[0] not in ('gdp','iip','cpi','retail','trade','fdi','budget','public_investment','monetary','pmi','business') for p in values):raise ValueError('Nguồn JSON có trường ngoài phạm vi thống kê')
        source=dict(id=config['id'],name=config['name'],url=config['url'],source_published_at=config['published'],retrieved_at=retrieved,period_code=config['period'])
        return values,source,payload.get('units',{})
    return _fetch_external(settings,config,adapter,force)
