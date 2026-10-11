"""Finite, resumable full-universe refresh with secret-free progress and backup."""
import argparse
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from stock_reports.core.config import Settings
from stock_reports.core.locking import ProcessLock
from stock_reports.data_sources.archive import ResponseArchive, ArchivedCafeFTransport
from stock_reports.data_sources.cafef.client import CafeFClient
from stock_reports.data_sources.cafef.sync import sync_financial_history, CafeFSynchronizer
from stock_reports.data_sources.dnse.market import VIETNAM
from stock_reports.pipeline.industries import update_industries
from stock_reports.pipeline.macro_data import update_macro
from stock_reports.storage.market import MarketStore
from stock_reports.storage.industries import IndustryStore
from stock_reports.storage.inventory import write_inventory


def write_json(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume',type=Path)
    parser.add_argument('--catalog-macro-current',action='store_true')
    parser.add_argument('--retry-symbols',nargs='+',default=[])
    args=parser.parse_args()
    if args.retry_symbols and not args.resume:parser.error('--retry-symbols requires --resume')
    settings=Settings.from_root(ROOT)
    run_lock=ProcessLock(ROOT/'var/full-data-refresh.lock')
    if not run_lock.acquire():raise SystemExit('A full refresh is already running')
    cafef_lock=ProcessLock(ROOT/'var/cafef-collector.lock')
    if not cafef_lock.acquire():
        run_lock.release();raise SystemExit('A CafeF collector is already running')
    started=datetime.now(VIETNAM)
    run_dir=(ROOT/args.resume).resolve() if args.resume else settings.runs_directory/('full-refresh-'+started.strftime('%Y%m%dT%H%M%S'))
    if not run_dir.is_relative_to(settings.runs_directory.resolve()):raise ValueError('Resume path must be inside var/runs')
    run_dir.mkdir(parents=True,exist_ok=True)
    manifest_path=run_dir/'manifest.json'
    previous=json.loads(manifest_path.read_text(encoding='utf-8')) if args.resume else {}
    state={**previous,'status':'running','pid':__import__('os').getpid(),
        'started_at':previous.get('started_at',started.isoformat()),'updated_at':started.isoformat(),
        'scope':'all listed companies; latest 8 published quarters; all 4 statement types; refetch existing data',
        'completed_symbols':previous.get('completed_symbols',[]),'results':previous.get('results',[])}
    retry={s.upper() for s in args.retry_symbols}
    if retry:
        state['completed_symbols']=[s for s in state['completed_symbols'] if s not in retry]
        state['bank_reports_refreshed']=False
    def persist(stage):
        state.update(stage=stage,updated_at=datetime.now(VIETNAM).isoformat())
        write_json(manifest_path,state)
        write_json(ROOT/'outputs/FULL_REFRESH_PROGRESS.json',{k:v for k,v in state.items() if k not in ('results','completed_symbols')}|{
            'completed':len(state['completed_symbols']),'manifest':str(manifest_path)})
    try:
        persist('backup')
        backup=run_dir/'market_data_before.sqlite3'
        if not backup.exists():
            with closing(sqlite3.connect(settings.market_database)) as source, closing(sqlite3.connect(backup)) as dest:
                source.backup(dest)
        state['backup']=str(backup)
        store=MarketStore(settings.market_database);store.initialize()
        state['before']=previous.get('before') or write_inventory(store,settings.outputs_directory)
        if not args.catalog_macro_current and not args.resume:
            persist('catalog')
            state['catalog']=update_industries(settings)
            persist('macro')
            state['macro']=update_macro(settings)
        companies=IndustryStore(settings.industries_database).list_companies()
        banking={r['symbol'] for r in companies if str(r.get('industry_id'))=='12'}
        all_symbols={s for s,_ in store.list_instruments()}
        priority=[s for s in ('ACB','VCB','BID','CTG','TCB','MBB','VPB','HDB','STB') if s in banking]
        ordered=list(dict.fromkeys([*priority,*sorted(banking),*sorted(all_symbols)]))
        state['total']=len(ordered);state['priority_banks']=len(banking)
        archive=ResponseArchive(run_dir/'raw')
        client=CafeFClient(transport=ArchivedCafeFTransport(archive,requests_per_second=1))
        done=set(state['completed_symbols'])
        for symbol in ordered:
            if symbol in done:continue
            state['current_symbol']=symbol;persist('financials')
            try:
                result=sync_financial_history(client,store,max_quarters=8,symbols=[symbol],incremental=False)
                record={'symbol':symbol,**asdict(result)}
                record['numeric_facts']=store.financial_numeric_fact_count_for(symbol)
            except Exception as error:
                record={'symbol':symbol,'error_type':type(error).__name__}
            state['results'].append(record)
            state['completed_symbols'].append(symbol);done.add(symbol)
            if len(done)%10==0 or (banking<=done and not state.get('bank_reports_refreshed')):
                state['latest_inventory']=write_inventory(store,settings.outputs_directory)
            print(f"CafeF {len(done)}/{len(ordered)} {symbol} saved={record.get('saved',0)} issues={record.get('rejected',1 if record.get('error_type') else 0)}",flush=True)
            if banking<=done and not state.get('bank_reports_refreshed'):
                persist('bank_report_generation')
                try:
                    from stock_reports.pipeline.research_reports import GenerationRequest,generate_reports
                    state['bank_report_results']=generate_reports(settings,GenerationRequest(kind='industry',industry_id='ngan-hang'))
                    state['bank_reports_refreshed']=True
                except Exception as error:
                    state['bank_report_error_type']=type(error).__name__
                    # Do not retry rendering on every subsequent symbol.
                    state['bank_reports_refreshed']='failed'
            persist('financials')
        persist('daily_prices')
        day=datetime.now(VIETNAM).date()
        while day.weekday()>=5:day-=timedelta(days=1)
        state['daily_prices']={'date':day.isoformat(),'results':[asdict(r) for r in CafeFSynchronizer(client=client,store=store).sync_daily(day)]}
        state['after']=write_inventory(store,settings.outputs_directory)
        state['status']='completed_with_issues' if any(r.get('rejected') or r.get('error_type') or not r.get('numeric_facts') for r in state['results']) else 'completed'
        state['completed_at']=datetime.now(VIETNAM).isoformat()
        persist('finished')
    except BaseException as error:
        state.update(status='interrupted' if isinstance(error,KeyboardInterrupt) else 'failed',error_type=type(error).__name__)
        persist(state.get('stage','unknown'))
        raise
    finally:
        cafef_lock.release();run_lock.release()


if __name__=='__main__':main()
