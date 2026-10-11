"""Normalize structure only. Business calculations belong in the data adapter."""
from copy import deepcopy
from datetime import date
import re

DEFAULTS = {
 'summary': {'hero': {'title':None,'subtitle':None,'metric_label':None,'metric_value':None,'metric_note':None},'kpis':[],'stances':[],'global_highlights':[],'domestic_highlights':[],'thesis':None},
 'global': {'overview':{'phases':[],'size':{'value':None,'unit':None,'year':None},'per_capita':[],'notes':[]},'value_chain':{'cost_structure':[],'output_structure':[],'input_mix':[],'price_forecast':{'unit':None,'years':[],'series':[]},'commodity_price':{'name':None,'forecast':None,'note':None}},'supply_demand':[],'policy_trends':[],'segments':[],'segment_traits':[]},
 'domestic': {'overview':{'revenue':None,'gdp_share':None,'volume':None,'cagr_revenue':None,'cagr_volume':None,'yoy_volume':None,'output_structure':[],'export_structure':[],'market_split':{'domestic_pct':None,'export_pct':None,'import_value':None},'per_capita':[]},'competition':[],'value_chain':{'cost_structure':[],'input_mix':[],'domestic_supply':{'capacity':None,'self_sufficiency':None,'new_capacity_note':None},'machinery_imports':{'cagr_periods':[],'origin_split':[]}},'regulations':[],'authorities':[],'segments':[],'outlook':{'output_forecast':{'from':None,'to':None,'cagr':None},'segment_table':[],'series':[],'macro_drivers':[]},'risks':[]},
 'companies': {'table':{'as_of':None,'period':None,'columns':['group','ticker','exchange','market_cap','total_assets','revenue','revenue_yoy','net_income','net_income_yoy'],'rows':[],'footnotes':[]},'profiles':[]},
 'disclaimer':{'text':None,'holdings_disclosure':None},'units':{},'provenance':{},'missing_reasons':{},'derived':{},'assertions':[],
}

def get(d,path,default=None):
    for part in path.split('.'):
        try:d=d[int(part)] if isinstance(d,list) else d[part]
        except (KeyError,IndexError,TypeError,ValueError):return default
    return d

def normalize(payload):
    def merge(base,extra):
        result=deepcopy(base)
        for k,v in extra.items():
            result[k]=merge(result[k],v) if isinstance(result.get(k),dict) and isinstance(v,dict) else deepcopy(v)
        return result
    return merge(DEFAULTS,payload)

def period_meta(code):
    m=re.fullmatch(r'(\d{4})(?:-(9T|Q[1-4]|0[1-9]|1[0-2]))?',code)
    if not m:raise ValueError('Kỳ ngành phải là YYYY-MM, YYYY-Qn, YYYY-9T hoặc YYYY')
    year=int(m[1]);suffix=m[2]
    if suffix=='9T':return f'9T/{year}',date(year,9,30)
    if suffix and suffix.startswith('Q'):
        import calendar
        month=int(suffix[1])*3
        return f'Quý {suffix[1]}/{year}',date(year,month,calendar.monthrange(year,month)[1])
    if suffix:
        import calendar
        month=int(suffix)
        return f'{month:02}/{year}',date(year,month,calendar.monthrange(year,month)[1])
    return str(year),date(year,12,31)

def source_valid(source):
    return isinstance(source,dict) and bool(source.get('organization') or source.get('name')) and bool(source.get('date') or source.get('published_at'))

def has_data(value):
    if isinstance(value,dict):
        return any(has_data(v) for k,v in value.items() if k not in ('source','source_id','unit','as_of','period','period_code','name','label','title','polarity','columns','footnotes'))
    if isinstance(value,list):return any(has_data(v) for v in value)
    return value is not None and value!=''
