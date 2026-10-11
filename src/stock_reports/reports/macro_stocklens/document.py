"""Catalog wrapper using only macro JSON; no stock/annual analysis context."""
from datetime import date
from stock_reports.analysis.contracts import AnalysisSection,Finding,SectionKind
from stock_reports.domain.research import SourceReference
from stock_reports.reports.documents import ReportDocument
from stock_reports.reports.models import ReportKind
from . import VERSION
from .quality import inspect
from .render import PAGES,TITLES,asset_fingerprint

def build_document(payload):
    quality=inspect(payload)
    sources=tuple(SourceReference(source_name=s['name'],url=s['url'],retrieved_at=s['retrieved_at']) for s in payload['meta']['sources'] if isinstance(s,dict))
    sections=tuple(AnalysisSection(kind=SectionKind.RISKS if page=='08_conclusion' else SectionKind.MACRO,title=TITLES[page],findings=(Finding(text='Hồ sơ dữ liệu '+payload['meta']['period_label'],sources=sources,is_assumption=not sources),)) for page in PAGES)
    return ReportDocument(kind=ReportKind.MACRO,title='StockLens · Vĩ mô Việt Nam · '+payload['meta']['period_label'],as_of=date.fromisoformat(payload['meta']['report_date']),sections=sections,macro_stocklens_data=payload,template_version=VERSION,template_sha256=asset_fingerprint(),assessment='Chỉ mang tính tham khảo, không phải khuyến nghị đầu tư',data_quality=tuple(f['message'] for f in quality['flags']))
