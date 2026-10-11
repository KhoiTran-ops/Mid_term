"""Finite follow-up for a specific download run: audit and refresh existing stock reports."""
import argparse
from datetime import date, datetime
import json
from pathlib import Path
import sqlite3
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from stock_reports.core.config import Settings
from stock_reports.core.locking import ProcessLock
from stock_reports.core.files import atomic_json
from stock_reports.data_sources.dnse.market import VIETNAM
from audit_financial_coverage import main as audit
from audit_company_components import main as audit_components


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True,type=Path)
    parser.add_argument('--audit-only',action='store_true',help='Audit after completion; running web refreshes watched reports')
    args=parser.parse_args()
    run=(ROOT/args.run).resolve()
    if not run.is_relative_to(ROOT/'var/runs'):raise ValueError('Run outside workspace archive')
    lock=ProcessLock(ROOT/'var/financial-finalizer.lock')
    if not lock.acquire():raise SystemExit('A finalizer already watches this workspace')
    settings=Settings.from_root(ROOT)
    progress=settings.outputs_directory/'REPORT_REFRESH_PROGRESS.json'
    def save(payload):
        payload['updated_at']=datetime.now(VIETNAM).isoformat()
        atomic_json(progress,payload)
    try:
        while True:
            try:state=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
            except (OSError,ValueError):time.sleep(15);continue
            status=state.get('status')
            if status in ('completed','completed_with_gaps'):break
            if status in ('failed','interrupted'):save(dict(status='download_failed',message='See financial run manifest; no automatic claim of completeness'));return
            save(dict(status='waiting_for_download',run=run.name))
            time.sleep(15)
        audit()
        audit_components()
        if args.audit_only:
            save(dict(status='audits_completed',download_status=status,
                report_updates='Running web updates watched reports using current-day snapshots'))
            return
        from stock_reports.pipeline.research_reports import GenerationRequest,generate_reports
        with sqlite3.connect(settings.reports_database) as db:
            scopes=db.execute("SELECT symbol,MAX(as_of) FROM reports WHERE kind='stock' AND symbol IS NOT NULL GROUP BY symbol").fetchall()
        results=[]
        for symbol,day in scopes:
            save(dict(status='regenerating',current_symbol=symbol,completed=len(results),total=len(scopes)))
            try:
                reports=generate_reports(settings,GenerationRequest(kind='stock',symbol=symbol,as_of=date.fromisoformat(day)))
                results.append(dict(symbol=symbol,reports=[dict(report_id=r['report']['id'],reused=r['reused']) for r in reports]))
            except Exception as error:
                results.append(dict(symbol=symbol,error_type=type(error).__name__))
        save(dict(status='completed_with_errors' if any('error_type' in r for r in results) else 'completed',
            download_status=status,results=results,completed=len(results),total=len(scopes)))
    finally:lock.release()


if __name__=='__main__':main()
