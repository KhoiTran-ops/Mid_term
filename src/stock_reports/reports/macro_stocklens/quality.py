"""Data-only quality gate; missing data is not an invitation to invent values."""
from datetime import date,datetime
import json
import math
import re
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from .data import normalize,get,period_meta,FIELDS

ROOT=Path(__file__).parent

def validate_schema(payload):
    errors=sorted(Draft202012Validator(json.loads((ROOT/'schema.json').read_text(encoding='utf-8')),format_checker=FormatChecker()).iter_errors(payload),key=lambda e:str(e.path))
    if errors:raise ValueError('Macro JSON '+'.'.join(map(str,errors[0].path))+': '+errors[0].message)
    def finite(v):
        if isinstance(v,float) and not math.isfinite(v):raise ValueError('Macro JSON contains non-finite number')
        if isinstance(v,dict):
            for x in v.values():finite(x)
        elif isinstance(v,list):
            for x in v:finite(x)
    finite(payload)

def inspect(payload):
    validate_schema(payload);d=normalize(payload);flags=[];missing=[]
    def flag(code,path,message,severity='error'):flags.append(dict(code=code,path=path,message=message,severity=severity))
    def walk(v,path=''):
        if isinstance(v,dict):
            for k,x in v.items():walk(x,(path+'.'+k).strip('.'))
        elif isinstance(v,list):
            if not v:missing.append(dict(path=path,reason=d['missing_reasons'].get(path,'Nguồn chưa cung cấp chuỗi / nội dung cho kỳ này')))
            for i,x in enumerate(v):walk(x,f'{path}.{i}')
        elif v is None:
            missing.append(dict(path=path,reason=d['missing_reasons'].get(path,'Chưa có nguồn được xác nhận cho kỳ này')))
    for group in FIELDS:walk(d[group],group)
    source_ids={s.get('id') for s in d['meta']['sources'] if isinstance(s,dict)}
    def evidenced(path):
        while path:
            source=d['provenance'].get(path)
            if source and source.get('source_id') in source_ids:return True
            path=path.rpartition('.')[0]
        return False
    def check_evidence(value,path):
        if isinstance(value,dict):
            for k,v in value.items():check_evidence(v,path+'.'+k)
        elif isinstance(value,list):
            for i,v in enumerate(value):check_evidence(v,path+'.'+str(i))
        elif isinstance(value,(int,float)) and not path.endswith('.year') and path not in d['derived'] and not evidenced(path):
            group=path.split('.')[0]
            if not any(isinstance(s,dict) and group in s.get('groups',[]) for s in d['meta']['sources']):flag('unsourced_value',path,'Giá trị chưa có nguồn theo trường / nhóm')
    for group in FIELDS:check_evidence(d[group],group)
    derived_specs={
        'trade.ytd.balance_usd_bn':(['trade.ytd.export_usd_bn','trade.ytd.import_usd_bn'],lambda a,b:a-b),
        'trade.q.total_usd_bn':(['trade.q.export_usd_bn','trade.q.import_usd_bn'],lambda a,b:a+b),
        'budget.month.balance':(['budget.month.revenue','budget.month.expenditure'],lambda a,b:a-b),
        'budget.ytd.balance':(['budget.ytd.revenue','budget.ytd.expenditure'],lambda a,b:a-b),
        'business.exit_ratio_pct':(['business.exited_k','business.new_and_returned_k'],lambda a,b:a/b*100 if b>0 else None),
    }
    for path,metadata in d['derived'].items():
        if path not in derived_specs:flag('unsupported_derivation',path,'Chưa có công thức backend được kiểm tra cho trường này');continue
        paths,fn=derived_specs[path];values=[get(d,p) for p in paths]
        actual=get(d,path)
        expected_value=fn(*values) if all(v is not None for v in values) else None
        if expected_value is None or actual is None or abs(actual-expected_value)>.00001 or metadata.get('inputs')!=paths:flag('invalid_derivation',path,'Giá trị / đầu vào suy ra không khớp công thức backend')
    expected=period_meta(d['meta']['period_code'])
    for key in ('period_type','period_start','period_end'):
        if d['meta'].get(key,expected[key])!=expected[key]:flag('period_mismatch','meta.'+key,'Kỳ khai báo không khớp mã kỳ')
    cutoff=d['meta']['report_date']
    if expected['period_end']>cutoff:flag('period_after_report','meta.period_code','Kỳ thống kê kết thúc sau ngày báo cáo')
    year=expected['period_end'][:4];quarter=(int(expected['period_end'][5:7])-1)//3+1
    for path in ('gdp.q.label','gdp.ytd.label'):
        label=get(d,path)
        if label and year not in label:flag('period_mismatch',path,'Nhãn kỳ sai năm')
        if label and ('9T' in label or '9 tháng' in label) and expected['period_type']!='ytd9':flag('period_mismatch',path,'Nhãn 9 tháng không khớp loại kỳ')
    label=get(d,'gdp.q.label')
    if label and ('Q' in label or 'Quý' in label) and not any(q in label for q in (f'Q{quarter}',f'Quý {quarter}')):flag('period_mismatch','gdp.q.label','Quý không khớp kỳ báo cáo')
    for source in d['meta']['sources']:
        if isinstance(source,dict) and source.get('source_published_at','')[:10]>cutoff:flag('future_source','meta.sources','Nguồn được công bố sau ngày báo cáo')
        if isinstance(source,dict):
            try:date.fromisoformat(source['source_published_at'][:10]);datetime.fromisoformat(source['retrieved_at'])
            except (ValueError,KeyError):flag('invalid_source_date','meta.sources','Thiếu / sai định dạng ngày công bố hoặc thời điểm tải')
    for path,source in d['provenance'].items():
        if source.get('source_published_at','')[:10]>cutoff:flag('future_source',path,'Ngày công bố sau ngày chốt')
        if source.get('period_code',expected['period_code'])!=expected['period_code'] and not source.get('historical',False):flag('period_mismatch',path,'Trường dữ liệu thuộc kỳ khác')
        if source.get('observation_date') and source['observation_date']>expected['period_end']:flag('future_observation',path,'Ngày quan sát vượt kỳ thống kê')
    if d['monetary']['credit_as_of'] and d['monetary']['credit_as_of']>cutoff:flag('future_observation','monetary.credit_as_of','Ngày số liệu sau ngày chốt')
    elif d['monetary']['credit_as_of'] and d['monetary']['credit_as_of']>expected['period_end']:flag('period_mismatch','monetary.credit_as_of','Tín dụng chốt sau kỳ thống kê')
    monthly_paths=('cpi.monthly_series','retail.monthly_series','public_investment.monthly_series','pmi.series','monetary.series.credit','monetary.series.usd_vnd','monetary.series.interbank')
    for path in monthly_paths:
        for i,row in enumerate(get(d,path)):
            label=str(row.get('month',''))
            match=re.fullmatch(r'(\d{4})-(\d{1,2})',label)
            reverse=re.fullmatch(r'(\d{1,2})/(\d{4})',label)
            short=re.fullmatch(r'\d{1,2}',label)
            yy,mm=(int(match[1]),int(match[2])) if match else (int(reverse[2]),int(reverse[1])) if reverse else (int(year),int(label)) if short else (None,None)
            if yy is not None:
                if not 1<=mm<=12:flag('invalid_observation_date',f'{path}.{i}.month','Tháng ngoài 1–12')
                elif f'{yy}-{mm:02}'>expected['period_end'][:7]:flag('future_observation',f'{path}.{i}.month','Chuỗi chứa tháng sau kỳ thống kê')
    for group,unit in [('trade','tỷ USD'),('fdi','tỷ USD'),('budget','nghìn tỷ VND'),('public_investment','nghìn tỷ VND'),('retail','tỷ VND')]:
        for key,value in d['units'].items():
            if (key==group or key.startswith(group+'.') and not key.endswith(('yoy','qoq','pct','pct_plan'))) and value!=unit:flag('unit_mismatch','units.'+key,f'Đơn vị phải là {unit}; đang khai báo {value}')
    def identity(path,paths,fn,tolerance):
        values=[get(d,x) for x in paths];actual=get(d,path)
        if actual is not None and all(x is not None for x in values) and abs(actual-fn(*values))>tolerance+1e-9:flag('identity_mismatch',path,'Sai phép đối chiếu: '+', '.join(paths))
    identity('trade.ytd.balance_usd_bn',['trade.ytd.export_usd_bn','trade.ytd.import_usd_bn'],lambda x,y:x-y,.02)
    identity('trade.ytd.total_usd_bn',['trade.ytd.export_usd_bn','trade.ytd.import_usd_bn'],lambda x,y:x+y,.02)
    identity('trade.q.total_usd_bn',['trade.q.export_usd_bn','trade.q.import_usd_bn'],lambda x,y:x+y,.02)
    identity('trade.ytd.balance_usd_bn',['trade.domestic_balance_usd_bn','trade.fdi_balance_usd_bn'],lambda x,y:x+y,.02)
    for key in ('month','ytd'):identity(f'budget.{key}.balance',[f'budget.{key}.revenue',f'budget.{key}.expenditure'],lambda x,y:x-y,.02)
    for key in ('revenue','expenditure'):
        actual=get(d,'budget.ytd.'+key);pct=get(d,'budget.ytd.'+key+'_pct_plan');plan=get(d,'budget.plan.'+key)
        if all(v is not None for v in (actual,pct,plan)) and abs(actual-pct*plan/100)>abs(actual)*.01+1e-9:flag('budget_plan_mismatch','budget.ytd.'+key,'Số thực hiện không khớp % dự toán × dự toán, vượt 1%')
    contributions=[r.get('contribution_pct') for r in d['gdp']['sectors']]
    if sum(v for v in contributions if v is not None)>100.01:flag('gdp_contribution','gdp.sectors','Tổng đóng góp vượt 100%')
    # Optional competing observations are never silently averaged or selected.
    for item in d.get('comparisons',[]):
        a=item.get('primary');b=item.get('other')
        if a is None or b is None:continue
        delta=abs(a-b)
        if delta>.2+1e-9:flag('metric_source_conflict',item['path'],'Chênh lệch >0,2 điểm %; cần chọn nguồn gốc')
        elif delta>=.05-1e-9:flag('rounding_difference',item['path'],'Khác cách làm tròn; dùng giá trị nguồn gốc','warning')
    series=[('gdp.history','ytd_yoy'),('iip.history','ytd_yoy'),('cpi.history_ytd','yoy'),('retail.history','value_bn_vnd'),('trade.history_ytd','import_usd_bn'),('trade.history_ytd','export_usd_bn'),('fdi.history_ytd','registered'),('fdi.history_ytd','disbursed')]
    for path,metric in series:
        rows=get(d,path)
        years=[r.get('year') for r in rows]
        if years!=sorted(set(years)):flag('history_order',path,'Năm phải duy nhất và tăng dần')
        if any(y>int(year) for y in years):flag('future_observation',path,'Chuỗi lịch sử có năm sau kỳ thống kê')
        for i in range(1,len(rows)-1):
            a,x,b=(rows[j].get(metric) for j in (i-1,i,i+1))
            if all(v is not None for v in (a,x,b)) and a*b>0 and (x-a)*(x-b)>0 and max(abs(x-a)/abs(a),abs(x-b)/abs(b))>.4 and not rows[i].get('explanation'):
                flag('history_outlier',f'{path}.{i}.{metric}','Điểm nằm ngoài cả hai lân cận, lệch hơn 40% ít nhất một lân cận; cần giải thích','warning')
    return dict(period_code=expected['period_code'],status='blocked' if any(f['severity']=='error' for f in flags) else 'passed_with_gaps' if missing or flags else 'passed',flags=flags,missing=missing,derived=d['derived'],source_differences=d.get('source_differences',[]))
