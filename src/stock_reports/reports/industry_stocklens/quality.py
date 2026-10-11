"""Deterministic checks, no automatic ratings, forecasts or source corrections."""
from datetime import date,datetime
from pathlib import Path
import json
import math
import re
from jsonschema import Draft202012Validator,FormatChecker
from .data import normalize,get,source_valid,period_meta

ROOT=Path(__file__).parent

def inspect(payload):
    flags=[];missing=[]
    def flag(code,path,message,severity='error'):
        flags.append(dict(code=code,path=path,message=message,severity=severity))
    if not isinstance(payload,dict):return dict(status='needs_review',flags=[dict(code='schema',path='',message='JSON ngành phải là object',severity='error')],missing_fields=[])
    schema=json.loads((ROOT/'schema.json').read_text(encoding='utf-8'))
    for e in Draft202012Validator(schema,format_checker=FormatChecker()).iter_errors(payload):
        flag('schema','.'.join(str(x) for x in e.absolute_path),e.message)
    if flags:
        meta=payload.get('meta') if isinstance(payload.get('meta'),dict) else {}
        return dict(status='needs_review',flags=flags,missing_fields=[],industry=meta.get('industry_id'),period=meta.get('period_code'))
    d=normalize(payload)
    def reason(path):
        while path:
            if path in d['missing_reasons']:return d['missing_reasons'][path]
            path=path.rpartition('.')[0]
        return 'Nguồn chưa cung cấp số liệu được xác nhận cho đối tượng và kỳ này'
    try:cutoff=date.fromisoformat(d['meta']['report_date'])
    except (KeyError,ValueError,TypeError):cutoff=None
    try:period_meta(d['meta'].get('period_code',''))
    except (ValueError,KeyError):flag('period_code','meta.period_code','Mã kỳ báo cáo không hợp lệ')
    catalog={s.get('id'):s for s in d.get('meta',{}).get('sources',[]) if isinstance(s,dict)}
    def provenance(path):
        while path:
            if path in d['provenance']:return d['provenance'][path]
            path=path.rpartition('.')[0]
        return {}
    def walk(v,path=''):
        if isinstance(v,dict):
            for k,x in v.items():walk(x,f'{path}.{k}' if path else k)
        elif isinstance(v,list):
            for i,x in enumerate(v):walk(x,f'{path}.{i}')
        elif v is None:missing.append(dict(path=path,reason=reason(path)))
        elif isinstance(v,(int,float)) and not isinstance(v,bool):
            if not math.isfinite(v):flag('non_finite',path,'Giá trị không hữu hạn')
            if path.split('.')[0] not in ('meta','assertions','derived','provenance'):
                prov=provenance(path)
                if not prov.get('source_id') or prov['source_id'] not in catalog:flag('missing_source',path,'Số liệu không có nguồn trong danh mục', 'warning')
                unit=d['units'].get(path) or prov.get('unit')
                key=path.split('.')[-1]
                if unit and prov.get('expected_unit') and unit!=prov['expected_unit']:flag('unit_mismatch',path,'Đơn vị hiển thị khác đơn vị nguồn đã khai báo')
                implicit=key.endswith('_pct') or key in ('pct','cagr','cagr_revenue','cagr_volume','yoy_volume','gdp_share','revenue_yoy','net_income_yoy','cagr_forecast','utilization','self_sufficiency','target_upside','supply_cagr_hist','supply_cagr_fwd','demand_cagr_hist','demand_cagr_fwd') or key=='kg'
                if not unit and not implicit and key not in ('year','years','start_year','end_year','n_years'):flag('missing_unit',path,'Chưa có đơn vị cho số liệu','warning')
                if unit and (key in ('market_cap','total_assets','revenue','net_income','price','eps_ttm','target_price') or key=='value' and any(x in path.lower() for x in ('lnst','profit','income','revenue'))):
                    if not any(x in unit.upper() for x in ('VND','USD','EUR','ĐỒNG')):flag('unit_mismatch',path,'Chỉ tiêu tiền tệ bị gán đơn vị phi tiền tệ')
                if path.startswith('companies.table.rows.') and key in ('market_cap','total_assets','revenue','net_income') and unit and unit!='tỷ VND':flag('money_scale',path,'Bảng doanh nghiệp yêu cầu tỷ VND; không tự đổi tiền tệ/triệu-tỷ')
    walk(d)
    def dates(v,path=''):
        if isinstance(v,dict):
            for k,x in v.items():
                p=f'{path}.{k}' if path else k
                if k in ('as_of','date','published_at','report_date','period_end','start_date','end_date','registered_as_of') and x:
                    try:
                        token=str(x)[:10]
                        day=date.fromisoformat(token+'-01' if re.fullmatch(r'\d{4}-\d{2}',token) else token)
                        if cutoff and day>cutoff and '.regulations.' not in p:flag('future_date',p,'Ngày số liệu/nguồn muộn hơn ngày báo cáo')
                    except ValueError:flag('invalid_date',p,'Ngày không hợp lệ')
                dates(x,p)
        elif isinstance(v,list):
            for i,x in enumerate(v):dates(x,f'{path}.{i}')
    dates(d)
    share_paths=['global.value_chain.cost_structure','global.value_chain.output_structure','global.value_chain.input_mix','domestic.overview.output_structure','domestic.overview.export_structure','domestic.value_chain.cost_structure','domestic.value_chain.input_mix','domestic.value_chain.machinery_imports.origin_split']
    for prefix in ('global.segments','domestic.segments'):
        for i,row in enumerate(get(d,prefix,[])):
            share_paths.extend(f'{prefix}.{i}.{k}' for k in ('regional_split','demand_split','structure','market_share') if row.get(k))
            if row.get('export',{}).get('structure'):share_paths.append(f'{prefix}.{i}.export.structure')
    for i,p in enumerate(d['companies']['profiles']):
        if p.get('structure'):share_paths.append(f'companies.profiles.{i}.structure')
    for path in share_paths:
        rows=get(d,path,[])
        if not rows:continue
        vals=[r.get('pct') for r in rows]
        if any(v is None for v in vals):flag('share_missing',path,'Cơ cấu có thành phần thiếu; không vẽ thanh 100%','warning')
        elif any(v<0 or v>100 for v in vals) or abs(sum(vals)-100)>.5:flag('share_total',path,f'Tổng cơ cấu {sum(vals):.2f}% không trong 100% ± 0,5')
        for i,r in enumerate(rows):
            if r.get('derived') and not r.get('formula'):flag('derived_formula',f'{path}.{i}','Thành phần suy ra phải có công thức †')
    def scan(v,path=''):
        if isinstance(v,dict):
            if all(v.get(k) is not None for k in ('start_value','end_value','n_years','cagr')):
                if v['start_value']>0 and v['end_value']>0 and v['n_years']>0:
                    calculated=((v['end_value']/v['start_value'])**(1/v['n_years'])-1)*100
                    if abs(calculated-v['cagr'])>.3:flag('cagr_mismatch',path,f'CAGR công bố {v["cagr"]}% lệch CAGR tính lại {calculated:.2f}%')
                else:flag('cagr_domain',path,'Không thể tính CAGR với đầu/cuối/số năm không dương')
            if 'points' in v and v.get('unit'):
                for i,p in enumerate(v['points']):
                    if p.get('status') not in ('A','E','F'):flag('observation_status',f'{path}.points.{i}','Nhãn điểm cần phân biệt A/E/F')
                    if p.get('status')=='F' and not source_valid(p.get('source') or v.get('source')):flag('forecast_source',f'{path}.points.{i}','Dự phóng thiếu tổ chức và ngày nguồn')
                    if p.get('status') in ('A','E'):
                        label=str(p.get('label','')).rstrip('AE')
                        match=re.fullmatch(r'(?:9T)?(\d{4})',label)
                        if match and cutoff and int(match[1])>cutoff.year:flag('future_actual',f'{path}.points.{i}','Điểm thực tế/ước tính mang năm tương lai')
                if v.get('metric') in ('net_income','revenue','market_cap') and v.get('unit') not in ('tỷ VND','triệu USD','tỷ USD'):flag('unit_mismatch',path,'Chuỗi tiền tệ gán đơn vị sai')
            if 'years' in v and 'series' in v:
                for i,s in enumerate(v['series']):
                    if len(s.get('values',[]))!=len(v['years']):flag('series_length',f'{path}.series.{i}','Số giá trị không khớp số nhãn kỳ')
                    if any(str(y).endswith('F') for y in v['years']) and not source_valid(s.get('source') or v.get('source')):flag('forecast_source',f'{path}.series.{i}','Dự phóng giá thiếu nguồn và ngày')
            for k,x in v.items():scan(x,f'{path}.{k}' if path else k)
        elif isinstance(v,list):
            for i,x in enumerate(v):scan(x,f'{path}.{i}')
    scan(d)
    for path in ('global.overview.per_capita','global.supply_demand'):
        for i,row in enumerate(get(d,path,[])):
            forecast_keys=('cagr_forecast',) if 'per_capita' in path else ('supply_cagr_fwd','demand_cagr_fwd')
            if any(row.get(k) is not None for k in forecast_keys) and not source_valid(row.get('source')):flag('forecast_source',f'{path}.{i}','Dự phóng thiếu tổ chức/ngày nguồn')
    output=d['domestic']['outlook']['output_forecast']
    if any(output.get(k) is not None for k in ('to','cagr')) and not source_valid(output.get('source')):flag('forecast_source','domestic.outlook.output_forecast','Dự phóng sản lượng thiếu nguồn')
    for path,entry in d['derived'].items():
        if not isinstance(entry,dict) or not entry.get('formula'):flag('derived_formula',path,'Số suy ra phải ghi công thức và gắn †')
    for a in d['assertions']:
        value=get(d,a.get('metric_path',''))
        if a.get('value') is not None and value is not None and abs(value-a['value'])>a.get('tolerance',.3):flag('text_number_mismatch',a.get('text_path','assertions'),'Số trong diễn giải khác bảng/biểu đồ của cùng đối tượng')
    for i,s in enumerate(d['summary']['stances']):
        if not source_valid(s.get('source')):flag('stance_source',f'summary.stances.{i}','Ẩn quan điểm không có tổ chức/ngày nguồn','warning')
    table=d['companies']['table'];seen=set()
    exchange_catalog=d['meta'].get('exchange_catalog',{})
    for i,row in enumerate(table['rows']):
        p=f'companies.table.rows.{i}';ticker=row.get('ticker')
        if ticker in seen:flag('duplicate_ticker',p,'Mã bị lặp trong bảng ngành')
        seen.add(ticker)
        if exchange_catalog and exchange_catalog.get(ticker)!=row.get('exchange'):flag('ticker_exchange',p,'Mã/sàn không khớp danh mục sàn')
        if row.get('period') and row['period']!=table.get('period'):flag('period_mismatch',p,'Kỳ BCTC hàng không khớp nhãn kỳ bảng')
        for field in ('revenue','net_income'):
            prior=row.get(field+'_prior');current=row.get(field);pct=row.get(field+'_yoy')
            if prior is not None and current is not None and pct is not None:
                if prior<=0:flag('yoy_negative_base',p+'.'+field+'_yoy','Cùng kỳ không dương: cần N/A kèm chú thích, không dùng %YoY')
                elif abs((current/prior-1)*100-pct)>.3:flag('yoy_mismatch',p+'.'+field+'_yoy','%YoY lệch giá trị hiện tại/cùng kỳ')
        if row.get('market_cap') is not None and row.get('price_as_of') and row['price_as_of']!=row.get('market_cap_as_of',table.get('as_of')):flag('valuation_date',p,'Vốn hóa và giá không cùng ngày')
    for i,p in enumerate(d['companies']['profiles']):
        t=p.get('trading',{})
        if t.get('target_price') is not None and not source_valid(t.get('target_source')):flag('target_source',f'companies.profiles.{i}.trading.target_price','Ẩn giá mục tiêu không có tổ chức/ngày nguồn','warning')
        if t.get('price_as_of') and t.get('market_cap_as_of') and t['price_as_of']!=t['market_cap_as_of']:flag('valuation_date',f'companies.profiles.{i}.trading','Ngày vốn hóa/giá không khớp')
        if exchange_catalog and exchange_catalog.get(p.get('ticker'))!=p.get('exchange'):flag('ticker_exchange',f'companies.profiles.{i}','Hồ sơ mã/sàn không khớp danh mục')
        if t.get('price') is not None and t.get('target_price') is not None and t.get('target_upside') is not None and t['price']>0:
            actual=(t['target_price']/t['price']-1)*100
            if abs(actual-t['target_upside'])>.3:flag('target_upside_mismatch',f'companies.profiles.{i}.trading','Mức chênh giá mục tiêu của nguồn không khớp giá thị trường cùng hồ sơ; không tự sửa')
        if t.get('price') is not None and t.get('high_52w') is not None and t['price']>t['high_52w']:flag('quote_range',f'companies.profiles.{i}.trading','Giá hiện tại vượt cao 52 tuần trong hồ sơ; kiểm tra mốc cập nhật/điều chỉnh', 'warning')
    for group in ('global','domestic','companies'):
        if not get(payload,group):missing.append(dict(path=group,reason=reason(group)))
    attribution=d.get('meta',{}).get('attribution',{})
    if attribution.get('license_status','unknown')=='unknown':flag('license_unknown','meta.attribution','Chưa xác nhận bản quyền: chỉ xuất bản nháp có watermark','warning')
    return dict(status='needs_review' if any(f['severity']=='error' for f in flags) else 'passed_with_gaps' if flags or missing else 'passed',flags=flags,missing_fields=missing,industry=d.get('meta',{}).get('industry_id'),period=d.get('meta',{}).get('period_code'),checked_at=datetime.now().astimezone().isoformat())
