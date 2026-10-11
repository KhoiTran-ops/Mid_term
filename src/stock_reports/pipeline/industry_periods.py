"""Industry snapshot adapter: never substitutes plastic examples or FA/TA scores."""
from datetime import date,datetime,UTC
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from stock_reports.analysis.repository import ResearchRepository,VIETNAM
from stock_reports.analysis.annuals import load_annual_review,annual_value
from stock_reports.analysis.market_fundamentals import load_market_snapshot,provider_metrics,market_quote
from stock_reports.reports.industry_stocklens.data import normalize,period_meta

def _write_snapshot(settings,source_name,url,payload,retrieved_at):
    """Content-addressed raw source, independent from mutable working drafts."""
    raw=json.dumps(payload,sort_keys=True,ensure_ascii=False).encode('utf-8');digest=hashlib.sha256(raw).hexdigest()
    root=settings.root/'var/industry/raw'/source_name;root.mkdir(parents=True,exist_ok=True)
    path=root/(digest+'.json')
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Snapshot nguồn đã thay đổi nội dung, không ghi đè')
    if not path.exists():path.write_bytes(raw)
    metadata=root/(digest+'.source.json')
    if not metadata.exists():metadata.write_text(json.dumps(dict(url=url,retrieved_at=retrieved_at,sha256=digest),ensure_ascii=False,indent=2),encoding='utf-8')
    return digest

def fetch_json_source(settings,config):
    """Each provider uses an explicit authorized JSON bridge, not invented API access."""
    if config.get('license_status') not in ('own','licensed'):raise ValueError('Nguồn ngành chưa xác nhận quyền sử dụng')
    import requests
    url=config['url']
    if not url.startswith('https://'):raise ValueError('Nguồn ngành cần URL HTTPS')
    response=requests.get(url,timeout=20);response.raise_for_status();payload=response.json()
    if not isinstance(payload,dict):raise ValueError('Nguồn phải trả JSON ngành dạng object')
    _write_snapshot(settings,config['id'],url,payload,datetime.now(UTC).isoformat())
    return payload

def load_period(settings,industry_id,period=None,*,as_of=None,refresh=False,allow_example=False):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}',industry_id):raise ValueError('Mã ngành không hợp lệ')
    as_of=as_of or datetime.now(VIETNAM).date();period=period or as_of.strftime('%Y-%m');label,end=period_meta(period)
    if date(int(period[:4]),1,1)>as_of:raise ValueError('Kỳ ngành không được ở tương lai')
    suffix=period[5:]
    if suffix.isdigit() and date(int(period[:4]),int(suffix),1)>as_of:raise ValueError('Tháng báo cáo ngành không được ở tương lai')
    if suffix.startswith('Q') and date(int(period[:4]),(int(suffix[1])-1)*3+1,1)>as_of:raise ValueError('Quý báo cáo ngành không được ở tương lai')
    paths=[settings.root/'config/industry/periods'/industry_id/(period+'.json')]
    for path in paths:
        if path.is_file():
            d=json.loads(path.read_text(encoding='utf-8'))
            if d['meta']['industry_id']!=industry_id or d['meta']['period_code']!=period:raise ValueError('Snapshot JSON không khớp ngành/kỳ')
            if d['meta'].get('example') and not allow_example:raise ValueError('JSON ngành này là minh họa, không được dùng cho báo cáo dữ liệu thật')
            if date.fromisoformat(d['meta']['report_date'])>as_of:raise ValueError('Ngày snapshot muộn hơn ngày chốt')
            return d
    config_path=settings.root/'config/industry_stocklens.json'
    config=json.loads(config_path.read_text(encoding='utf-8')) if config_path.is_file() else {}
    selected=next((s for s in config.get('json_sources',[]) if s['industry_id']==industry_id and s['period']==period),None)
    if selected:
        d=fetch_json_source(settings,selected)
        if d['meta']['industry_id']!=industry_id or d['meta']['period_code']!=period:raise ValueError('Feed trả sai ngành/kỳ')
        return d
    d=build_from_repository(settings,industry_id,period,as_of)
    draft=settings.root/'var/industry/periods'/industry_id/(period+'.json');draft.parent.mkdir(parents=True,exist_ok=True)
    draft.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
    return d

def build_from_repository(settings,industry_id,period,as_of):
    repo=ResearchRepository(settings,as_of);industry=repo.industry(industry_id)
    label,end=period_meta(period);cutoff=min(as_of,end);year=cutoff.year-1
    rows=repo.companies(industry['sector_id']);now=datetime.now(UTC).isoformat()
    d=normalize({'meta':dict(industry_id=industry['slug'],industry_name=industry['name'],period_code=period,period_label=label,report_date=as_of.isoformat(),language='vi',sources=[],attribution=dict(publisher='StockLens',report_title='Dữ liệu ngành '+industry['name'],published_at=as_of.isoformat(),license_status='own'),exchange_catalog={r['symbol']:r['exchange'].upper().replace('HSX','HOSE') for r in rows},data_note='Phạm vi: doanh nghiệp thuộc GICS cấp 2 của DNSE, không phải tổng quy mô kinh tế của ngành. Chỉ trình bày BCTC đã có hồ sơ đơn vị; không lấy FA/TA hoặc tự sinh quan điểm. Bảng năm và giá thị trường có ngày riêng.')})
    d['summary']['hero'].update(title=industry['name'].upper(),subtitle='Phạm vi GICS cấp 2 · '+label,metric_label='Doanh nghiệp trong danh mục',metric_value=len(rows),metric_note='Số mã trong danh mục DNSE; không đại diện độ phủ BCTC')
    d['units']['summary.hero.metric_value']='doanh nghiệp'
    cat_source=dict(id='dnse-catalog',name='DNSE GICS / danh mục',url=industry['source_url'],retrieved_at=industry['retrieved_at'])
    d['meta']['sources'].append(cat_source);d['provenance']['summary.hero.metric_value']={'source_id':cat_source['id'],'unit':'doanh nghiệp'}
    _write_snapshot(settings,'dnse',industry['source_url'],dict(industry=industry,companies=rows),industry['retrieved_at'])
    snapshot=next((r for r in repo.snapshots() if r['sector_id']==industry['sector_id']),None)
    if snapshot:
        raw=json.loads(snapshot['raw_json']);raw_values=dict(zip(raw.get('priceVolatilityKey',[]),raw.get('priceVolatilityValue',[])))
        sid='dnse-index';url='https://banggia.dnse.com.vn/v2/nganh/danh-muc-nganh/'+industry['slug']
        d['meta']['sources'].append(dict(id=sid,name='DNSE biến động chỉ số nhóm',url=url,retrieved_at=snapshot['retrieved_at']))
        d['provenance']['summary.kpis']={'source_id':sid,'unit':'%'}
        for key in ('1d','1m','1y','5y'):
            v=raw_values.get(key)
            d['summary']['kpis'].append(dict(label='Hiệu suất chỉ số nhóm · '+key,value=float(v) if v is not None else None,unit='%',polarity='higher_good'))
        _write_snapshot(settings,'dnse-index',url,raw,snapshot['retrieved_at'])
    d['companies']['table'].update(as_of=as_of.isoformat(),period=str(year),footnotes=[f'BCTC năm {year}; không đổi nhãn thành tháng/quý. LNST hợp nhất, không đồng nhất LNST cổ đông công ty mẹ.','Vốn hóa/giá có ngày xác nhận riêng. Không có ảnh chụp đúng ngày thì để trống; không gán vốn hóa hiện tại cho ngày quá khứ.','%YoY † = (năm hiện tại / cùng kỳ - 1) × 100; cùng kỳ không dương hiển thị N/A.'])
    for company in rows:
        symbol=company['symbol'];exchange=company['exchange'].upper().replace('HSX','HOSE');i=len(d['companies']['table']['rows']);path=f'companies.table.rows.{i}'
        row=dict(group=industry['name'],ticker=symbol,exchange=exchange,name=company.get('company_name') or company.get('name') or symbol,period=str(year),market_cap=None,total_assets=None,revenue=None,revenue_yoy=None,net_income=None,net_income_yoy=None)
        try:review=load_annual_review(settings,symbol);raw=repo.annual(symbol)
        except (ValueError,OSError):review=None;raw=[]
        if review and year in review.years:
            sid='bctc-'+symbol
            sources=[s for s in review.sources if not s.published_at or s.published_at.astimezone(VIETNAM).date()<=as_of]
            if not sources:review=None
            else:
                src=next((s for s in sources if str(year) in s.source_name or str(year) in str(s.url)),sources[-1])
                d['meta']['sources'].append(dict(id=sid,name=f'{symbol} · BCTC {year}',url=str(src.url),retrieved_at=src.retrieved_at.isoformat()))
                d['provenance'][path]={'source_id':sid,'unit':'tỷ VND','period':str(year)}
                _write_snapshot(settings,'financials',str(src.url),dict(symbol=symbol,rows=raw,review=review.model_dump(mode='json')),now)
                for key,target in [('assets','total_assets'),('revenue','revenue'),('net_profit','net_income')]:
                    value,matches=annual_value(raw,key,year,review)
                    row[target]=float(value*review.money_multiplier/Decimal(1_000_000_000)) if value is not None else None
                    d['units'][path+'.'+target]='tỷ VND'
                    if matches:
                        evidence=matches[0].get('verified_source') or dict(url=matches[0]['source_url'],retrieved_at=matches[0]['imported_at'])
                        field_sid=next((s['id'] for s in d['meta']['sources'] if s['url']==evidence['url']),sid+'-'+target)
                        if not any(s['id']==field_sid for s in d['meta']['sources']):d['meta']['sources'].append(dict(id=field_sid,name=f'{symbol} · {year} · {target}',url=evidence['url'],retrieved_at=evidence['retrieved_at']))
                        d['provenance'][path+'.'+target]={'source_id':field_sid,'unit':'tỷ VND','period':str(year)}
                    if target in ('revenue','net_income'):
                        prior,prior_matches=annual_value(raw,key,year-1,review) if year-1 in review.years else (None,[])
                        prior_bn=float(prior*review.money_multiplier/Decimal(1_000_000_000)) if prior is not None else None
                        row[target+'_prior']=prior_bn
                        row[target+'_yoy']=(row[target]/prior_bn-1)*100 if row[target] is not None and prior_bn is not None and prior_bn>0 else None
                        d['units'][path+'.'+target+'_yoy']='%'
                        d['units'][path+'.'+target+'_prior']='tỷ VND'
                        if prior_matches:
                            evidence=prior_matches[0].get('verified_source') or dict(url=prior_matches[0]['source_url'],retrieved_at=prior_matches[0]['imported_at'])
                            prior_sid=next((s['id'] for s in d['meta']['sources'] if s['url']==evidence['url']),sid+'-'+target+'-prior')
                            if not any(s['id']==prior_sid for s in d['meta']['sources']):d['meta']['sources'].append(dict(id=prior_sid,name=f'{symbol} · BCTC {year-1}',url=evidence['url'],retrieved_at=evidence['retrieved_at']))
                            d['provenance'][path+'.'+target+'_prior']={'source_id':prior_sid,'unit':'tỷ VND','period':str(year-1)}
                        if row[target+'_yoy'] is not None:d['derived'][path+'.'+target+'_yoy']={'formula':'(Hiện tại / cùng kỳ - 1) × 100','inputs':[path+'.'+target,path+'.'+target+'_prior']}
        if not review:d['missing_reasons'][path]='Chưa đối chiếu đơn vị BCTC'
        d['missing_reasons'][path+'.market_cap']='Chưa có vốn hóa đúng ngày'
        snapshot=load_market_snapshot(settings,symbol,as_of)
        quote=market_quote(snapshot,repo.cutoff)
        if snapshot and quote:
            trading_day=quote['timestamp'].astimezone(VIETNAM).date().isoformat()
            # Undated provider market cap must have been captured on quote day.
            retrieved_day=datetime.fromisoformat(snapshot['retrieved_at']).astimezone(VIETNAM).date().isoformat()
            metrics={m['label']:m for m in provider_metrics(snapshot)}
            cap=metrics.get('Vốn hóa theo nguồn')
            sid='market-'+symbol;src=quote['source']
            d['meta']['sources'].append(dict(id=sid,name=symbol+' · CafeF thị trường',url=str(src.url),retrieved_at=snapshot['retrieved_at']))
            if cap and trading_day==retrieved_day:
                row.update(market_cap=float(cap['value']),market_cap_as_of=trading_day,price_as_of=trading_day)
                d['provenance'][path+'.market_cap']={'source_id':sid,'unit':'tỷ VND'}
            if review:
                ppath=f'companies.profiles.{len(d["companies"]["profiles"])}'
                eps=metrics.get('EPS cơ bản theo nguồn');pe=metrics.get('P/E theo nguồn')
                profile=dict(name=company.get('company_name') or company.get('name') or symbol,ticker=symbol,exchange=exchange,trading=dict(as_of=trading_day,price=float(quote['value_vnd']),high_52w=None,low_52w=None,avg_volume_10d=None,eps_ttm=float(eps['value']) if eps else None,pe_ttm=float(pe['value']) if pe else None,target_price=None,target_upside=None),business_points=[],series=[])
                d['companies']['profiles'].append(profile);d['provenance'][ppath+'.trading']={'source_id':sid}
                for key in ('price','high_52w','low_52w','eps_ttm','target_price'):d['units'][ppath+'.trading.'+key]='VND/cp'
                d['units'][ppath+'.trading.avg_volume_10d']='cp';d['units'][ppath+'.trading.pe_ttm']='lần'
        d['companies']['table']['rows'].append(row)
    for group in ('global','domestic'):
        d['missing_reasons'][group]='Chưa có bộ thống kê chuyên ngành/chuỗi quốc tế được cấp quyền cho ngành và kỳ này; không thay bằng mẫu nhựa hoặc báo cáo vĩ mô'
    d['disclaimer']['text']='Dữ liệu danh mục, chỉ số nhóm và doanh nghiệp niêm yết không đại diện toàn bộ hoạt động kinh tế của ngành. Không tự tạo nhận định, xếp hạng hay giá mục tiêu. Các trang chưa có dữ liệu được ẩn và ghi trong quality_report.'
    used_sources={p['source_id'] for p in d['provenance'].values()}
    d['meta']['sources']=[s for s in d['meta']['sources'] if s['id'] in used_sources]
    return d
