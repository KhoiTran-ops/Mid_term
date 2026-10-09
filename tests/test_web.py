from datetime import date
import sqlite3

from fastapi.testclient import TestClient

from stock_reports.core.config import Settings
from stock_reports.reports.models import ReportMetadata
from stock_reports.storage.reports import ReportCatalog
from stock_reports.web.app import create_app


def test_web_empty_state_and_filters_pdf_and_no_private_files(tmp_path):
    settings = Settings.from_root(tmp_path)
    client = TestClient(create_app(settings))
    assert 'Chưa có báo cáo' in client.get('/').text
    assert client.get('/api/reports').json()['total'] == 0
    pdf = tmp_path / 'test.pdf'
    pdf.write_bytes(b'%PDF-1.4\nfixture only\n%%EOF')
    catalog = ReportCatalog(settings.reports_database, settings.reports_directory)
    record = catalog.register(ReportMetadata(kind='stock',title='<script>alert(1)</script>',
        symbol='HPG',industry_id='steel',industry_name='Thép',as_of=date(2026,10,9)),pdf)
    catalog.register(ReportMetadata(kind='macro',title='Vĩ mô',as_of=date(2026,10,9)),pdf)
    assert client.get('/api/reports?symbol=HPG&industry_id=steel').json()['total'] == 1
    assert client.get('/?kind=macro').status_code == 200
    assert 'Vĩ mô' in client.get('/?kind=macro').text
    assert '<script>alert(1)</script>' not in client.get('/').text
    assert client.get('/api/reports?page=0').status_code == 422
    assert client.get('/api/reports?date_from=2026-10-10&date_to=2026-10-01').status_code == 422
    assert client.get(f'/api/reports/{record.id}/pdf').headers['content-type'] == 'application/pdf'
    assert client.get('/.env').status_code == 404
    assert client.get('/var/market_data.db').status_code == 404
    assert client.get('/api/reports/not-a-uuid/pdf').status_code == 404
    with sqlite3.connect(settings.reports_database) as db:
        db.execute('UPDATE reports SET pdf_filename=? WHERE id=?',('../../.env',record.id))
    assert client.get(f'/api/reports/{record.id}/pdf').status_code == 404
