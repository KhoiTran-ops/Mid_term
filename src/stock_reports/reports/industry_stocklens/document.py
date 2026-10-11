"""Catalog wrapper consumes only the industry JSON, not legacy macro/stock sections."""
from datetime import date
from stock_reports.analysis.contracts import AnalysisSection,Finding,SectionKind
from stock_reports.domain.research import SourceReference
from stock_reports.reports.documents import ReportDocument
from stock_reports.reports.models import ReportKind
from . import VERSION
from .quality import inspect
from .render import page_plan,asset_fingerprint

def build_document(payload):
    meta=payload['meta'];quality=inspect(payload)
    sources=tuple(SourceReference(source_name=s['name'],url=s['url'],retrieved_at=s['retrieved_at']) for s in meta['sources'] if s['url'].startswith('https://'))
    sections=[AnalysisSection(kind=SectionKind.RISKS if p['key']=='13_views_risks' else SectionKind.INDUSTRY,title=p['title'],findings=(Finding(text='Hồ sơ dữ liệu ngành · '+meta['period_label'],sources=sources,is_assumption=not sources),)) for p in page_plan(payload)]
    return ReportDocument(kind=ReportKind.INDUSTRY,title='StockLens · '+meta['industry_name']+' · '+meta['period_label'],as_of=date.fromisoformat(meta['report_date']),industry_id=meta['industry_id'],industry_name=meta['industry_name'],sections=tuple(sections),industry_stocklens_data=payload,template_version=VERSION,template_sha256=asset_fingerprint(),assessment='Chỉ mang tính tham khảo, không phải khuyến nghị đầu tư',data_quality=tuple(f['message'] for f in quality['flags']))
