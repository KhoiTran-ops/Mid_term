from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError
from pypdf import PdfReader

from stock_reports.domain.research import SourceReference
from stock_reports.reports.macro_reference import parse_reference,reference_document
from stock_reports.core.config import Settings
from stock_reports.pipeline.research_reports import GenerationRequest,generate_reports,report_analysis
from stock_reports.storage.reports import ReportCatalog

REFERENCE=Path(__file__).resolve().parents[1]/'config/report_content/macro-2026-10-09.md'


def test_reference_preserves_all_tables_periods_and_local_provenance():
    text=REFERENCE.read_text(encoding='utf-8-sig')
    _,preamble,parts=parse_reference(text)
    tables=[v for _,items in [('cover',preamble),*parts] for typ,v in items if typ=='table']
    assert len(tables)==7
    assert len(next(v for name,items in parts if name.startswith('C.') for typ,v in items if typ=='table'))==23
    doc=reference_document(REFERENCE,date(2026,10,9))
    assert len(doc.sections)==8
    assert doc.assessment=='Tổng quan dữ liệu, chưa đưa ra khuyến nghị'
    assert doc.editorial_markdown==text
    assert len(doc.editorial_source_sha256)==64
    assert all(s.url is None and s.locator for part in doc.sections for f in part.findings for s in f.sources)
    assert '9,01%' in doc.editorial_markdown and '8,02%' in doc.editorial_markdown


def test_local_source_without_locator_rejected():
    with pytest.raises(ValidationError,match='local source requires'):
        SourceReference(source_name='Tài liệu',url=None,retrieved_at='2026-10-10T05:00:00Z')


def test_reference_publication_uses_dated_snapshot_and_reuses_identical_pdf(tmp_path,monkeypatch):
    target=tmp_path/'config/report_content/macro-2026-10-09.md'
    target.parent.mkdir(parents=True)
    target.write_text(REFERENCE.read_text(encoding='utf-8-sig'),encoding='utf-8')
    settings=Settings.from_root(tmp_path)
    def forbidden(*a,**kw):pytest.fail('Must not mix live input values into approved reference')
    monkeypatch.setattr('stock_reports.analysis.repository.ResearchRepository.macro',forbidden)
    # The publishing service must avoid consulting unused live datasets for its input audit.
    first=generate_reports(settings,GenerationRequest(kind='macro',as_of=date(2026,10,9)))[0]
    second=generate_reports(settings,GenerationRequest(kind='macro',as_of=date(2026,10,9)))[0]
    assert second['reused'] and first['report']['id']==second['report']['id']
    payload=report_analysis(settings,first['report']['id'])
    assert payload['inputs']['reference_sha256']==payload['document']['editorial_source_sha256']
    assert not payload['inputs']['primary_sources_independently_verified']
    catalog=ReportCatalog(settings.reports_database,settings.reports_directory)
    pages=PdfReader(catalog.pdf_path(first['report']['id'])).pages
    text='\n'.join(p.extract_text() for p in pages)
    assert len(pages)==8
    assert all(len(p.extract_text())>600 for p in pages)
    for value in ('9,01%','8,02%','50,36','19,42','Chưa rõ','223,9'):
        assert value in text
    assert 'chưa kiểm chứng' in text.lower()
    assert 'None' not in text and ('không trộn' in text.lower() or 'không thay thế' in text.lower())
