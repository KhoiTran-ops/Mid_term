import sqlite3

from openpyxl import Workbook

from stock_reports.pipeline.annual_financials import import_annual_workbook
from stock_reports.storage.market import MarketStore


def test_annual_workbook_import_is_separate_idempotent_and_flags_conflicts(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'A32-BRC'
    sheet.append(['Firm', 'Year', 'Doanh thu thuần', 'Doanh thu thuần (10)', 'Note '])
    sheet.append(['HPG', 2024, 100, 100, 'audited'])
    sheet.append(['HPG', 2024, 100, 101, 'audited'])
    path = tmp_path / 'annual.xlsx'
    workbook.save(path)
    store = MarketStore(tmp_path / 'market.db')
    store.initialize()

    first = import_annual_workbook(store.path, path, source_url='https://example.test/source')
    second = import_annual_workbook(store.path, path, source_url='https://example.test/source')

    assert first['saved_facts'] == 2
    assert first['conflict_facts'] == 1
    assert second['status'] == 'already_imported'
    with sqlite3.connect(store.path) as connection:
        assert connection.execute('SELECT COUNT(*) FROM annual_financial_facts').fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM financial_facts WHERE fiscal_quarter=0"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM data_anomalies WHERE dataset='annual_financial_facts'"
        ).fetchone()[0] == 1
