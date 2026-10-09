from datetime import date, datetime, timezone

import pytest

from stock_reports.analysis.contracts import AnalysisSection, Finding
from stock_reports.domain.research import SourceReference
from stock_reports.pipeline.publication import ReportPublisher
from stock_reports.reports.documents import ReportDocument
from stock_reports.storage.reports import ReportCatalog


def finding():
    source = SourceReference(source_name='Nguồn thử nghiệm',url='https://example.org/data',
        retrieved_at=datetime(2026,10,9,tzinfo=timezone.utc))
    return Finding(text='Dữ kiện kiểm thử', sources=(source,))


def test_findings_require_evidence_unless_explicitly_assumptions():
    with pytest.raises(ValueError):
        Finding(text='Kết luận không có nguồn')
    assert Finding(text='Giả định mô hình',is_assumption=True).is_assumption


def test_stock_document_requires_macro_industry_and_valuation_sections():
    with pytest.raises(ValueError):
        ReportDocument(kind='stock',title='HPG',symbol='HPG',industry_id='steel',as_of=date(2026,10,9),
            sections=(AnalysisSection(kind='technical',title='Kỹ thuật',findings=(finding(),)),))


def test_publication_uses_supplied_renderer_and_registers_only_finished_pdf(tmp_path):
    document = ReportDocument(kind='macro',title='Báo cáo thử nghiệm',as_of=date(2026,10,9),sections=tuple(
        AnalysisSection(kind=kind,title=kind,findings=(finding(),)) for kind in ('macro','risks')))

    class Renderer:
        def render(self, document, destination):
            destination.write_bytes(b'%PDF-1.4\nfixture for publisher tests\n%%EOF')
            return destination

    catalog = ReportCatalog(tmp_path / 'reports.db', tmp_path / 'pdf')
    record = ReportPublisher(Renderer(),catalog).publish(document)
    assert catalog.pdf_path(record.id).exists()
    assert len(list(catalog.directory.iterdir())) == 1


def test_failed_renderer_does_not_publish_partial_report(tmp_path):
    document = ReportDocument(kind='macro', title='Test', as_of=date(2026,10,9), sections=tuple(
        AnalysisSection(kind=kind, title=kind, findings=(finding(),)) for kind in ('macro', 'risks')))

    class FailingRenderer:
        def render(self, document, destination):
            destination.write_bytes(b'%PDF-1.4\npartial output')
            raise RuntimeError('Rendering failed')

    catalog = ReportCatalog(tmp_path / 'reports.db', tmp_path / 'pdf')
    with pytest.raises(RuntimeError, match='Rendering failed'):
        ReportPublisher(FailingRenderer(), catalog).publish(document)
    assert catalog.list_reports().total == 0
    assert not list(catalog.directory.iterdir())
