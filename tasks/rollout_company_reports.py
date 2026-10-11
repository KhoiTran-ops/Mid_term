"""Verify the default layout over the catalog and refresh existing company reports."""
import argparse
from datetime import date, datetime, UTC
import json
from pathlib import Path
import shutil
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from stock_reports.analysis.financials import load_review
from stock_reports.analysis.repository import ResearchRepository
from stock_reports.analysis.research import build_document
from stock_reports.core.config import Settings
from stock_reports.pipeline.research_reports import GenerationRequest, generate_reports
from stock_reports.storage.reports import ReportCatalog


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--as-of',type=date.fromisoformat,required=True);parser.add_argument('--audit-only',action='store_true');parser.add_argument('--skip-audit',action='store_true');args=parser.parse_args()
    settings=Settings.from_root(ROOT);repo=ResearchRepository(settings,args.as_of)
    with sqlite3.connect(settings.market_database) as db:
        numeric={r[0] for r in db.execute('SELECT DISTINCT symbol FROM financial_facts WHERE value_numeric IS NOT NULL')}
    checks=[]
    for company in ([] if args.skip_audit else repo.companies()):
        ticker=company['symbol']
        if ticker not in numeric:
            checks.append(dict(symbol=ticker,status='no_numeric_financials'));continue
        try:
            path=settings.root/'var/financial_reviews'/f'{ticker}.json'
            doc=build_document(settings,kind='stock',as_of=args.as_of,symbol=ticker,
                review=load_review(path) if path.is_file() else None,repository=repo)
            checks.append(dict(symbol=ticker,status='ready',template=doc.template_version,
                financial_period=doc.financial_period,
                valuation_rows=sum(len(b.rows) for s in doc.sections if s.kind.value=='valuation' for b in s.blocks if 'định giá' in b.title.lower())))
        except Exception as error:checks.append(dict(symbol=ticker,status='error',error_type=type(error).__name__,message=str(error)[:250]))
    ready=[r for r in checks if r['status']=='ready']
    audit=dict(as_of=args.as_of.isoformat(),updated_at=datetime.now(UTC).isoformat(),
        default_layout='compact for every company unless explicitly configured otherwise',
        catalog_total=len(checks),ready=len(ready),missing_financials=sum(r['status']=='no_numeric_financials' for r in checks),
        errors=[r for r in checks if r['status']=='error'],checks=checks)
    settings.outputs_directory.mkdir(exist_ok=True)
    if not args.skip_audit:
        (settings.outputs_directory/'COMPANY_LAYOUT_ROLLOUT_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    results=[]
    if not args.audit_only:
        with sqlite3.connect(settings.reports_database) as db:
            symbols=[r[0] for r in db.execute("SELECT DISTINCT symbol FROM reports WHERE kind='stock' AND symbol IS NOT NULL ORDER BY symbol")]
        catalog=ReportCatalog(settings.reports_database,settings.reports_directory)
        for ticker in symbols:
            try:
                result=generate_reports(settings,GenerationRequest(kind='stock',symbol=ticker,as_of=args.as_of))[0]
                dest=ROOT/'output/pdf'/f'{ticker.lower()}-bao-cao-doanh-nghiep-{args.as_of}.pdf'
                dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(catalog.pdf_path(result['report']['id']),dest)
                results.append(dict(symbol=ticker,report_id=result['report']['id'],reused=result['reused']))
            except Exception as error:results.append(dict(symbol=ticker,error_type=type(error).__name__,message=str(error)[:250]))
        (settings.outputs_directory/'COMPANY_REPORT_ROLLOUT_RESULTS.json').write_text(json.dumps(dict(as_of=str(args.as_of),results=results),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(catalog=audit['catalog_total'],ready=audit['ready'],missing=audit['missing_financials'],errors=audit['errors'],reports=results),ensure_ascii=False))


if __name__=='__main__':main()
