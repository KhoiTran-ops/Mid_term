"""Finite DNSE backfill: banks first, then every listed stock, with receipts."""
from datetime import datetime
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from stock_reports.core.config import Settings
from stock_reports.core.locking import ProcessLock
from stock_reports.data_sources.archive import ArchivedDNSEGateway,ResponseArchive
from stock_reports.data_sources.dnse.market import VIETNAM
from stock_reports.pipeline.market_refresh import refresh_market
from stock_reports.storage.market import MarketStore
from stock_reports.storage.industries import IndustryStore
from stock_reports.storage.inventory import write_inventory


def main():
    settings=Settings.from_root(ROOT)
    lock=ProcessLock(ROOT/'var/dnse-refresh.lock')
    if not lock.acquire():raise SystemExit('A DNSE refresh is already running')
    run_dir=settings.runs_directory/('dnse-full-'+datetime.now(VIETNAM).strftime('%Y%m%dT%H%M%S'))
    run_dir.mkdir(parents=True,exist_ok=True)
    state={'status':'running','pid':os.getpid(),'started_at':datetime.now(VIETNAM).isoformat(),
        'manifest':str(run_dir/'manifest.json'),'done':0}
    def persist():
        state['updated_at']=datetime.now(VIETNAM).isoformat()
        for path in (run_dir/'manifest.json',ROOT/'outputs/MARKET_REFRESH_PROGRESS.json'):
            tmp=path.with_suffix('.tmp')
            tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
            tmp.replace(path)
    gateway=None
    try:
        persist()
        store=MarketStore(settings.market_database);store.initialize()
        gateway=ArchivedDNSEGateway(settings.dnse_api_key,settings.dnse_api_secret,ResponseArchive(run_dir/'raw'))
        catalog=gateway.list_stock_instruments()
        banks={r['symbol'] for r in IndustryStore(settings.industries_database).list_companies()
            if str(r.get('industry_id'))=='12'}
        priority={s:i for i,s in enumerate(('VCB','ACB','BID','CTG','TCB','MBB','VPB','HDB','STB','FPT','HPG'))}
        catalog.sort(key=lambda item:(item.symbol not in priority,item.symbol not in banks,priority.get(item.symbol,99),item.symbol))
        state['total']=len(catalog)+1
        completed=set()
        def progress(symbol,done,total):
            completed.add(symbol)
            state.update(current_symbol=symbol,done=done,total=total)
            if done%25==0 or banks<=completed:
                if done%25==0 or not state.get('bank_reports_refreshed'):
                    state['inventory']=write_inventory(store,settings.outputs_directory)
            if banks<=completed and not state.get('bank_reports_refreshed'):
                try:
                    from stock_reports.pipeline.research_reports import GenerationRequest,generate_reports
                    state['bank_reports']=generate_reports(settings,GenerationRequest(kind='industry',industry_id='ngan-hang'))
                    state['bank_reports_refreshed']=True
                except Exception as error:
                    state.update(bank_reports_refreshed='failed',bank_report_error_type=type(error).__name__)
            persist()
            if done==1 or done%25==0:print(f'DNSE {done}/{total}: {symbol}',flush=True)
        state['result']=refresh_market(gateway,store,instruments=catalog,include_foreign=True,on_progress=progress)
        state['inventory']=write_inventory(store,settings.outputs_directory)
        state['status']='completed_with_issues' if state['result']['failures'] else 'completed'
        persist()
    except BaseException as error:
        state.update(status='failed',error_type=type(error).__name__);persist()
        raise
    finally:
        if gateway:gateway.close()
        lock.release()


if __name__=='__main__':main()
