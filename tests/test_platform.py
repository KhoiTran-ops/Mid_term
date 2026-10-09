from datetime import datetime, timezone
import sqlite3

import pytest

from stock_reports.core.config import Settings
from stock_reports.reports.models import ReportKind, ReportMetadata
from stock_reports.storage.reports import ReportCatalog


def metadata(kind='stock', symbol='HPG', industry_id='steel'):
    return ReportMetadata(kind=kind, title='Báo cáo phân tích', symbol=symbol,
        industry_id=industry_id, industry_name='Thép', as_of=datetime(2026,10,9,tzinfo=timezone.utc))


def test_settings_resolve_paths_against_project_not_working_directory(tmp_path, monkeypatch):
    root = tmp_path / 'moved project'
    root.mkdir()
    (root / '.env').write_text('DATABASE_PATH=var/market_data.db\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    config = Settings.from_root(root)
    assert config.market_database == root / 'var' / 'market_data.db'
    assert config.reports_directory == root / 'outputs' / 'reports'


def test_catalog_registers_pdf_and_filters_without_touching_original_file(tmp_path):
    catalog = ReportCatalog(tmp_path / 'reports.db', tmp_path / 'pdfs')
    file = tmp_path / 'input.pdf'
    file.write_bytes(b'%PDF-1.4\nfixture for catalog tests only\n%%EOF')
    stock = catalog.register(metadata(), file)
    catalog.register(metadata('industry', None), file)
    catalog.register(metadata('macro', None, None), file)
    assert file.exists()
    assert catalog.list_reports(kind=ReportKind.STOCK, symbol='hpg').total == 1
    assert catalog.list_reports(industry_id='steel').total == 2
    assert catalog.list_reports(page=2, page_size=2).total == 3
    assert len(catalog.list_reports(page=2, page_size=2).items) == 1
    assert catalog.pdf_path(stock.id).read_bytes() == file.read_bytes()


def test_catalog_rejects_non_pdf_and_unsafe_pdf_path(tmp_path):
    catalog = ReportCatalog(tmp_path / 'reports.db', tmp_path / 'pdfs')
    bad = tmp_path / 'bad.pdf'
    bad.write_text('not a PDF')
    with pytest.raises(ValueError):
        catalog.register(metadata(), bad)
    with pytest.raises(ValueError):
        catalog.pdf_path('../../.env')


def test_catalog_rolls_back_pdf_when_metadata_insert_fails(tmp_path):
    catalog = ReportCatalog(tmp_path / 'reports.db', tmp_path / 'pdfs')
    pdf = tmp_path / 'input.pdf'
    pdf.write_bytes(b'%PDF-1.4\nfixture only\n%%EOF')
    with sqlite3.connect(catalog.database) as db:
        db.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON reports BEGIN SELECT RAISE(ABORT, 'fixture failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        catalog.register(metadata(), pdf)
    assert not list(catalog.directory.iterdir())
    assert catalog.list_reports().total == 0
    assert pdf.exists()


@pytest.mark.parametrize('kwargs', [dict(kind='stock', symbol=None, industry_id='steel'),
    dict(kind='industry', symbol=None, industry_id=None),
    dict(kind='macro', symbol='HPG', industry_id=None)])
def test_report_scope_validation(kwargs):
    with pytest.raises(ValueError):
        metadata(**kwargs)
