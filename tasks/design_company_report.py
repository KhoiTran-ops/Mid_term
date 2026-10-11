"""Publish a company report using the shared web/CLI generator and export a PDF."""
import argparse
from datetime import date
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from pypdf import PdfReader
from stock_reports.core.config import Settings
from stock_reports.pipeline.research_reports import GenerationRequest,generate_reports
from stock_reports.storage.reports import ReportCatalog


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--symbol',default='VCB')
    parser.add_argument('--as-of',type=date.fromisoformat,default=date(2026,10,9))
    args=parser.parse_args();settings=Settings.from_root(ROOT)
    result=generate_reports(settings,GenerationRequest(kind='stock',symbol=args.symbol.upper(),as_of=args.as_of))[0]
    catalog=ReportCatalog(settings.reports_database,settings.reports_directory)
    output=ROOT/'output/pdf'/f'{args.symbol.lower()}-bao-cao-doanh-nghiep-{args.as_of.isoformat()}.pdf'
    output.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(catalog.pdf_path(result['report']['id']),output)
    try:import pymupdf
    except ImportError:previews=False
    else:
        preview=ROOT/'tmp/pdfs'/f'company-{args.symbol.lower()}'
        preview.mkdir(parents=True,exist_ok=True)
        with pymupdf.open(output) as pdf:
            for i,page in enumerate(pdf):page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(preview/f'page-{i+1}.png')
        previews=True
    pages=PdfReader(output).pages
    print(json.dumps(dict(pdf=str(output),report_id=result['report']['id'],reused=result['reused'],pages=len(pages),
        previews=previews,page_text_lengths=[len(p.extract_text()) for p in pages]),ensure_ascii=False))


if __name__=='__main__':main()
