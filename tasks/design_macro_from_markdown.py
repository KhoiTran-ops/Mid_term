"""Publish the dated macro reference and export a reviewable PDF and PNGs."""
from datetime import date
from pathlib import Path
import shutil
import sys
import json
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from stock_reports.core.config import Settings
from stock_reports.pipeline.research_reports import GenerationRequest,generate_reports
from stock_reports.storage.reports import ReportCatalog


def main():
    settings=Settings.from_root(ROOT)
    result=generate_reports(settings,GenerationRequest(kind='macro',as_of=date(2026,10,9)))[0]
    catalog=ReportCatalog(settings.reports_database,settings.reports_directory)
    source=catalog.pdf_path(result['report']['id'])
    output=ROOT/'output/pdf/bao-cao-vi-mo-viet-nam-10-2026-ban-markdown.pdf'
    output.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,output)
    # PNG previews are optional QA assets, not an extra production dependency.
    try:
        import pymupdf
    except ImportError:
        previews=False
    else:
        preview=ROOT/'tmp/pdfs/macro-markdown';preview.mkdir(parents=True,exist_ok=True)
        with pymupdf.open(output) as pdf:
            for index,page in enumerate(pdf):
                page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(preview/f'page-{index+1}.png')
        previews=True
    pages=PdfReader(output).pages
    print(json.dumps(dict(pdf=str(output),report_id=result['report']['id'],reused=result['reused'],
        pages=len(pages),previews=previews,page_text_lengths=[len(p.extract_text()) for p in pages]),ensure_ascii=False))


if __name__=='__main__':main()
