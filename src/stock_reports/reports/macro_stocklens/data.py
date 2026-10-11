"""Normalize nullable input and derive explicitly labelled accounting identities."""
from copy import deepcopy
from datetime import date
import re

DISCLAIMER = 'Chỉ mang tính tham khảo, không phải khuyến nghị đầu tư'
FIELDS = {
 'gdp': {'q':{'label':None,'yoy':None},'ytd':{'label':None,'yoy':None},'history':[],'sectors':[],'note':None},
 'iip':dict.fromkeys(('q_yoy','ytd_yoy','prev_ytd_yoy','manufacturing_yoy','note')) | {'history':[],'top_products':[]},
 'cpi':dict.fromkeys(('month_mom','month_yoy','quarter_yoy','ytd_avg_yoy','core_ytd_yoy','note')) | {'history_ytd':[],'monthly_series':[]},
 'retail':{'q':{'value_bn_vnd':None,'qoq':None,'yoy':None},'ytd':{'value_bn_vnd':None,'yoy':None},'history':[],'monthly_series':[],'note':None},
 'trade':{'q':dict.fromkeys(('total_usd_bn','total_yoy','export_usd_bn','import_usd_bn','export_yoy','import_yoy','export_qoq','import_qoq')),'ytd':dict.fromkeys(('total_usd_bn','total_yoy','export_usd_bn','export_yoy','import_usd_bn','import_yoy','balance_usd_bn')),'month_balance_usd_bn':None,'domestic_balance_usd_bn':None,'fdi_balance_usd_bn':None,'history_ytd':[],'quarterly_yoy':[],'import_structure':[],'note':None},
 'fdi':dict.fromkeys(('registered_usd_bn','registered_yoy','disbursed_usd_bn','disbursed_yoy','note')) | {'history_ytd':[],'top_countries':[],'top_projects':[]},
 'budget':{'month':dict.fromkeys(('revenue','expenditure','balance')),'ytd':dict.fromkeys(('revenue','revenue_pct_plan','revenue_yoy','expenditure','expenditure_pct_plan','expenditure_yoy','balance')),'plan':dict.fromkeys(('revenue','expenditure','deficit','borrowing')),'domestic_revenue_share_pct':None,'note':None},
 'public_investment':dict.fromkeys(('month_disbursed','ytd_disbursed','ytd_pct_plan','ytd_yoy','plan_total','note')) | {'monthly_series':[]},
 'monetary':dict.fromkeys(('credit_growth_ytd','credit_as_of','fx_change_ytd','note_credit','note_fx')) | {'series':{'credit':[],'usd_vnd':[],'interbank':[]}},
 'pmi':{'value':None,'previous':None,'series':[],'note':None},
 'business':dict.fromkeys(('new_and_returned_k','new_yoy','exited_k','exited_yoy','exit_ratio_pct','note')) | {'exit_ratio_history':[]},
 'conclusion':{'overall':[],'outlook':[],'opportunities':[],'risks':[],'disclaimer':DISCLAIMER},
}

def period_meta(code):
    if not re.fullmatch(r'\d{4}(?:-9T|-Q[1-4]|-(?:0[1-9]|1[0-2]))?',code):
        raise ValueError('Kỳ vĩ mô: YYYY-9T, YYYY-Q1..Q4, YYYY-MM hoặc YYYY')
    year=int(code[:4]);tail=code[5:]
    from calendar import monthrange
    if tail=='9T':kind,label,month='ytd9',f'9 tháng {year}',9
    elif tail.startswith('Q'):kind,label,month='quarter',f'Quý {tail[1]}/{year}',int(tail[1])*3
    elif tail:kind,label,month='month',f'Tháng {int(tail)}/{year}',int(tail)
    else:kind,label,month='year',f'Năm {year}',12
    start_month=month if kind=='month' else month-2 if kind=='quarter' else 1
    return dict(period_code=code,period_type=kind,period_label=label,period_start=f'{year}-{start_month:02}-01',period_end=f'{year}-{month:02}-{monthrange(year,month)[1]}')

def get(data,path):
    value=data
    for part in path.split('.'):
        if not isinstance(value,dict):return None
        value=value.get(part)
    return value

def set_value(data,path,value):
    parts=path.split('.');node=data
    for part in parts[:-1]:node=node.setdefault(part,{})
    node[parts[-1]]=value

def normalize(payload):
    data=deepcopy(payload)
    data.setdefault('meta',{}).setdefault('publisher_note',None)
    def merge(target,defaults):
        for k,v in defaults.items():
            if k not in target or target[k] is None and isinstance(v,(dict,list)):target[k]=deepcopy(v)
            elif isinstance(v,dict) and isinstance(target[k],dict):merge(target[k],v)
    merge(data,FIELDS)
    row_fields={
        'gdp.history':('ytd_yoy',),'gdp.sectors':('yoy','contribution_pct'),
        'iip.history':('ytd_yoy',),'iip.top_products':('yoy',),
        'cpi.history_ytd':('yoy',),'cpi.monthly_series':('yoy',),
        'retail.history':('value_bn_vnd','yoy'),'retail.monthly_series':('value_bn_vnd','yoy'),
        'trade.history_ytd':('export_usd_bn','import_usd_bn'),'trade.quarterly_yoy':('yoy',),'trade.import_structure':('pct',),
        'fdi.history_ytd':('registered','disbursed'),'fdi.top_countries':('usd_bn',),'fdi.top_projects':('province','country','usd_bn'),
        'public_investment.monthly_series':('value',),'monetary.series.credit':('value',),'monetary.series.usd_vnd':('value',),'monetary.series.interbank':('value',),
        'pmi.series':('value',),'business.exit_ratio_history':('pct',),
    }
    for path,keys in row_fields.items():
        for row in get(data,path):
            for key in keys:row.setdefault(key,None)
    for key in ('provenance','missing_reasons','derived','units'):data.setdefault(key,{})
    data['units']={'trade':'tỷ USD','fdi':'tỷ USD','budget':'nghìn tỷ VND','public_investment':'nghìn tỷ VND','retail':'tỷ VND',**data['units']}
    def derive(path,inputs,formula,fn):
        values=[get(data,k) for k in inputs]
        if get(data,path) is None and all(v is not None for v in values):
            result=fn(*values)
            if result is not None:
                set_value(data,path,round(result,6));data['derived'][path]=dict(formula=formula,inputs=inputs)
    derive('trade.ytd.balance_usd_bn',['trade.ytd.export_usd_bn','trade.ytd.import_usd_bn'],'XK − NK',lambda x,y:x-y)
    derive('trade.q.total_usd_bn',['trade.q.export_usd_bn','trade.q.import_usd_bn'],'XK quý + NK quý',lambda x,y:x+y)
    for key in ('month','ytd'):
        derive(f'budget.{key}.balance',[f'budget.{key}.revenue',f'budget.{key}.expenditure'],'Thu − Chi',lambda x,y:x-y)
    derive('business.exit_ratio_pct',['business.exited_k','business.new_and_returned_k'],'DN rút lui / (DN mới + quay lại) × 100',lambda x,y:x/y*100 if y>0 else None)
    return data
