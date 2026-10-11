"""Resumable annual 2021-2025 + expanded quarterly financial refresh.

One shared CafeF lock, one request/second, raw receipts, atomic progress and a
SQLite backup. Completeness refers to source observations, never imputation.
"""
import argparse
from contextlib import closing
from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from stock_reports.core.config import Settings
from stock_reports.core.locking import ProcessLock
from stock_reports.data_sources.archive import ResponseArchive, ArchivedCafeFTransport
from stock_reports.data_sources.cafef.annual import sync_annual_financials
from stock_reports.data_sources.cafef.client import CafeFClient
from stock_reports.data_sources.cafef.sync import sync_financial_history
from stock_reports.data_sources.dnse.market import VIETNAM
from stock_reports.storage.market import MarketStore
from stock_reports.core.files import atomic_json


def write_json(path, payload):
    atomic_json(path,payload)


def coverage(store, symbol):
    from stock_reports.analysis.financials import ALIASES, load_financials
    data=load_financials(store.path,symbol)
    with closing(sqlite3.connect(store.path,timeout=30)) as db:
        annual=db.execute('SELECT statement_type,fiscal_year,COUNT(*),SUM(value_numeric IS NOT NULL) '
            'FROM annual_statement_facts WHERE symbol=? AND fiscal_year BETWEEN 2021 AND 2025 '
            'GROUP BY statement_type,fiscal_year',(symbol,)).fetchall()
        quarterly=db.execute('SELECT statement_type,fiscal_year,fiscal_quarter,COUNT(*),'
            'SUM(value_numeric IS NOT NULL) FROM financial_facts WHERE symbol=? '
            'GROUP BY statement_type,fiscal_year,fiscal_quarter',(symbol,)).fetchall()
    bs={y for s,y,n,v in annual if s=='BSheet' and v}
    inc={y for s,y,n,v in annual if s=='IncSta' and v}
    cf={y for s,y,n,v in annual if s in ('CashFlow','CashFlowDirect') and v}
    by={s:{(y,q) for st,y,q,n,v in quarterly if st==s and v} for s in
        ('BSheet','IncSta','CashFlow','CashFlowDirect')}
    complete=by['BSheet'] & by['IncSta'] & (by['CashFlow'] | by['CashFlowDirect'])
    latest=data.periods[0] if data.periods else None
    common=('assets','equity','liabilities','revenue','net_profit','parent_profit','pretax_profit','cfo')
    return dict(symbol=symbol,annual_complete_years=sorted(bs&inc&cf),
        annual_missing_years={s:sorted(set(range(2021,2026))-v) for s,v in
            [('BSheet',bs),('IncSta',inc),('CashFlow',cf)]},
        annual_rows=[dict(statement=s,year=y,rows=n,numeric_rows=v) for s,y,n,v in annual],
        latest_reported_quarters=[f'{y}Q{q}' for y,q in data.periods],
        quarters_with_three_statements=[f'{y}Q{q}' for y,q in sorted(complete,reverse=True)],
        latest_mapped_fields={k:str(data.value(k,latest)) if latest and data.value(k,latest) is not None
                              else None for k in common},
        verified_review_present=data.review is not None,
        warnings=data.warnings,
        not_a_guarantee_of_all_components=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume',type=Path)
    parser.add_argument('--symbols',nargs='+')
    parser.add_argument('--max-quarters',type=int,default=24)
    parser.add_argument('--retry-failed',action='store_true')
    parser.add_argument('--retry-symbols',nargs='+',default=[])
    parser.add_argument('--priority-symbols',nargs='+',default=[])
    args=parser.parse_args()
    settings=Settings.from_root(ROOT)
    locks=[ProcessLock(ROOT/'var/full-data-refresh.lock'),ProcessLock(ROOT/'var/cafef-collector.lock')]
    for index,lock in enumerate(locks):
        if not lock.acquire():
            for held in locks[:index]:held.release()
            raise SystemExit('A financial collector is already running; no duplicate job started.')
    started=datetime.now(VIETNAM)
    run=(ROOT/args.resume).resolve() if args.resume else settings.runs_directory/(
        'financial-complete-'+started.strftime('%Y%m%dT%H%M%S'))
    if not run.is_relative_to(settings.runs_directory.resolve()):
        raise ValueError('Resume must be inside var/runs')
    run.mkdir(parents=True,exist_ok=True)
    state=json.loads((run/'manifest.json').read_text(encoding='utf-8')) if args.resume else {
        'started_at':started.isoformat(),'completed_symbols':[],'results':[]}
    # Retry earlier runs whose 2021 own-year route failed, using the corrected
    # overlapping annual window. Keep their prior receipts and results.
    repaired={r['symbol'] for r in state['results'] if any(
        i.get('anchor_year')==2021 and i.get('status_code')==404
        for i in r.get('annual',{}).get('issues',[])) and r['symbol'] not in state.get('annual_window_repaired',[])}
    if repaired:
        state.setdefault('prior_results',[]).extend(r for r in state['results'] if r['symbol'] in repaired)
        state['results']=[r for r in state['results'] if r['symbol'] not in repaired]
        state['completed_symbols']=[s for s in state['completed_symbols'] if s not in repaired]
        state.setdefault('annual_window_repaired',[]).extend(sorted(repaired))
    if args.retry_failed or args.retry_symbols:
        failed={r['symbol'] for r in state['results'] if args.retry_failed and r.get('error_type')}
        failed.update(s.upper() for s in args.retry_symbols)
        state['results']=[r for r in state['results'] if r['symbol'] not in failed]
        state['completed_symbols']=[s for s in state['completed_symbols'] if s not in failed]
    store=MarketStore(settings.market_database)
    selected=state.get('symbols') or (list(dict.fromkeys(s.upper() for s in args.symbols)) if args.symbols else
        list(dict.fromkeys(['VCB','ACB','HPG','FPT','SSI','BID','CTG','TCB','MBB','VPB','HDB','STB',
                           *[s for s,_ in store.list_instruments()]])))
    unknown=set(selected)-{s for s,_ in store.list_instruments()}
    if unknown:raise ValueError('Unknown symbols: '+','.join(sorted(unknown)))
    selected=list(dict.fromkeys([*[s.upper() for s in args.priority_symbols if s.upper() in selected],*selected]))
    state.update(status='running',pid=os.getpid(),symbols=selected,total=len(selected),
        scope='annual 2021-2025; up to 24 latest published quarters; expanded component rows; original nulls preserved',
        max_quarters=state.get('max_quarters',args.max_quarters))
    def persist(stage):
        state.update(stage=stage,updated_at=datetime.now(VIETNAM).isoformat())
        write_json(run/'manifest.json',state)
        write_json(settings.outputs_directory/'FINANCIAL_COMPLETE_PROGRESS.json',{
            k:v for k,v in state.items() if k not in ('results','prior_results','symbols','completed_symbols')} | {
            'completed':len(state['completed_symbols']),'manifest':str(run/'manifest.json')})
        write_json(settings.outputs_directory/'FULL_REFRESH_PROGRESS.json',{
            k:v for k,v in state.items() if k not in ('results','prior_results','symbols','completed_symbols')} | {
            'completed':len(state['completed_symbols']),'manifest':str(run/'manifest.json')})
    try:
        persist('backup')
        backup=run/'market_data_before.sqlite3'
        if not backup.exists():
            with closing(sqlite3.connect(settings.market_database,timeout=30)) as source, closing(sqlite3.connect(backup)) as dest:
                source.backup(dest)
        state['backup']=str(backup)
        store.initialize()
        client=CafeFClient(transport=ArchivedCafeFTransport(ResponseArchive(run/'raw'),requests_per_second=1))
        done=set(state['completed_symbols'])
        for symbol in selected:
            if symbol in done:continue
            state['current_symbol']=symbol;persist('annual')
            result={'symbol':symbol}
            try:
                result['annual']=sync_annual_financials(client,store,symbol,incremental=True)
                persist('quarterly')
                result['quarterly']=asdict(sync_financial_history(client,store,symbols=[symbol],
                    max_quarters=state['max_quarters'],incremental=True))
                result['coverage']=coverage(store,symbol)
                write_json(run/'coverage'/f'{symbol}.json',result['coverage'])
            except Exception as error:
                result['error_type']=type(error).__name__
                # An unavailable issuer must not terminate the remaining universe.
                # Never persist provider exception strings that could contain credentials.
            state['results'].append(result)
            state['completed_symbols'].append(symbol);done.add(symbol)
            state['annual_complete_companies']=sum(len(r.get('coverage',{}).get('annual_complete_years',[]))==5
                for r in state['results'])
            state['quarterly_complete_latest_eight']=sum(set(r.get('coverage',{}).get('latest_reported_quarters',[])) <=
                set(r.get('coverage',{}).get('quarters_with_three_statements',[])) and
                len(r.get('coverage',{}).get('latest_reported_quarters',[]))==8 for r in state['results'])
            print(f"Financial {len(done)}/{len(selected)} {symbol} annual={result.get('annual',{}).get('saved',0)} "
                  f"quarterly={result.get('quarterly',{}).get('saved',0)}",flush=True)
            persist('financials')
        from stock_reports.storage.inventory import write_inventory
        state['inventory']=write_inventory(store,settings.outputs_directory)
        state['status']='completed_with_gaps' if any(r.get('error_type') or
            len(r.get('coverage',{}).get('annual_complete_years',[]))<5 or
            not set(r.get('coverage',{}).get('latest_reported_quarters',[])) <=
                set(r.get('coverage',{}).get('quarters_with_three_statements',[])) for r in state['results']) else 'completed'
        state['completed_at']=datetime.now(VIETNAM).isoformat();persist('finished')
    except BaseException as error:
        state.update(status='interrupted' if isinstance(error,KeyboardInterrupt) else 'failed',
                     error_type=type(error).__name__)
        persist(state.get('stage','unknown'));raise
    finally:
        for lock in locks:lock.release()


if __name__=='__main__':main()
