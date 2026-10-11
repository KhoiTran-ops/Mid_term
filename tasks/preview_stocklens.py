"""Build source-backed samples and fail closed on pagination overflow."""
import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from stock_reports.core.config import Settings
from stock_reports.analysis.repository import ResearchRepository
from stock_reports.analysis.financials import load_review
from stock_reports.analysis.profiles import detect_profile
from stock_reports.analysis.research import build_document
from stock_reports.reports.models import ReportKind
from stock_reports.reports.stocklens.data import build_payload
from stock_reports.reports.stocklens.render import render_pdf,render_html,validate

def main():
    p=argparse.ArgumentParser();p.add_argument('tickers',nargs='+');p.add_argument('--as-of',type=date.fromisoformat,default=date(2026,10,11));args=p.parse_args()
    settings=Settings.from_root(ROOT);repo=ResearchRepository(settings,args.as_of)
    for ticker in args.tickers:
        path=ROOT/'var/financial_reviews'/f'{ticker}.json';review=load_review(path if path.exists() else None)
        company=repo.company(ticker);data=repo.financials(ticker,review=review)
        doc=build_document(settings,kind=ReportKind.STOCK,as_of=args.as_of,symbol=ticker,repository=repo,review=review)
        payload=validate(build_payload(settings,repo,company,data,detect_profile(data,company['industry']['name']),doc))
        folder=ROOT/'outputs/stocklens';folder.mkdir(parents=True,exist_ok=True)
        (folder/f'{ticker}.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        (folder/f'{ticker}.html').write_text(render_html(payload,accent=payload['meta']['accent']),encoding='utf-8')
        dest=ROOT/'output/pdf'/f'{ticker}-stocklens-{args.as_of}.pdf'
        render_pdf(payload,dest,accent=payload['meta']['accent'],qa_directory=ROOT/'tmp/pdfs'/f'stocklens-{ticker}')
        print(f'{ticker}: {dest}',flush=True)

if __name__=='__main__':main()
