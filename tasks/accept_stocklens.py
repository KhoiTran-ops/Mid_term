"""Emit the full requested acceptance table, including unresolved/basis differences."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from stock_reports.reports.stocklens.render import validate
from stock_reports.reports.stocklens.evidence import export_missing

TARGETS={
    'price.close':57900,'price.change_3m':-11.7,'price.change_6m':-17.5,'price.change_12m':-30.7,
    'technical.ma50':64108,'technical.ma200':70867,'technical.rsi14':23.7,'technical.macd_hist':-737.5,
    'technical.turnover_ma20':353.3e9,'technical.volume_vs_ma20':1.99,
    'scores.fa_raw':75.9,'scores.fa':70.7,'scores.fa_coverage':80,'scores.ta':5,'scores.unified':18.1,
    'financials.ratios.roe.3':28.3,'financials.ratios.roa.3':14,'financials.ratios.debt_to_equity':.48,
    'financials.ratios.current_ratio':1.4,'financials.ratios.ocf_to_ni.3':.90,
    'valuation.eps_ttm':5303,'valuation.pe_ttm':10.92,'valuation.pb':2.74,
    'valuation.peer_median_pe':10.82,'valuation.peer_count':23,'valuation.peer_snapshot_date':'2026-10-02',
    'annual_report.total_matches':1141,'annual_report.distinct_keywords':7,'annual_report.density_per_10000':97.38}


def get(data,path):
    for token in path.split('.'):
        data=data[int(token)] if isinstance(data,list) else data.get(token)
        if data is None:return None
    return data


def acceptance(data):
    validate(data);rows=[]
    for path,target in TARGETS.items():
        actual=get(data,path);reason=None
        if actual is None:
            status='unavailable';reason=data['methodology']['missing_reason'].get(path,'Thiếu đầu vào gốc.')
        else:
            match=actual==target if isinstance(target,str) else abs(actual-target)<=abs(target)*.02
            status='pass' if match else 'fail'
            if not match and path.startswith('technical.'):
                reference={'technical.turnover_ma20':'technical.reference_turnover_ma20','technical.volume_vs_ma20':'technical.reference_volume_vs_ma20'}.get(path)
                comparable=get(data,reference) if reference else None
                if comparable is not None and abs(comparable-target)<=abs(target)*.02:
                    status='different_basis';reason=f'X10 chưa điều chỉnh KL thưởng: {comparable}; hiện hành điều chỉnh ×1,1 theo yêu cầu mục 1.'
        rows.append(dict(field=path,expected=target,actual=actual,status=status,reason=reason))
    return dict(ticker=data['meta']['ticker'],price_date=data['meta']['price_date'],tolerance=.02,
        all_targets_met=all(r['status']=='pass' for r in rows),counts={s:sum(r['status']==s for r in rows) for s in ('pass','different_basis','unavailable','fail')},rows=rows)


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,default=ROOT/'output/pdf/FPT-stocklens-2026-10-11.json');p.add_argument('--out',type=Path,default=ROOT/'output/pdf/FPT-acceptance.json');args=p.parse_args()
    data=json.loads(args.input.read_text(encoding='utf-8'));result=acceptance(data)
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    export_missing(data,args.out.parent/'missing_report.json')
    print(json.dumps(result['counts']));print('All requested targets met:',result['all_targets_met'])
    if result['counts']['fail']:raise SystemExit(1)


if __name__=='__main__':main()
