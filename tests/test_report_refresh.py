from dataclasses import replace
import json
import sqlite3

from stock_reports.core.config import Settings
from stock_reports.pipeline.report_refresh import ReportRefreshRunner


def test_report_refresh_debounces_preserves_horizon_and_continues_errors(tmp_path, monkeypatch):
    settings = Settings.from_root(tmp_path)
    config = tmp_path / 'config'; config.mkdir()
    (config / 'report_refresh.json').write_text(json.dumps({'enabled': True, 'minimum_interval_seconds': 300}))
    settings.reports_database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.reports_database) as db:
        db.execute('CREATE TABLE reports(id TEXT, symbol TEXT, kind TEXT, created_at TEXT)')
        db.executemany('INSERT INTO reports VALUES (?,?,?,?)', [('a','ACB','stock','2026-10-11'),('f','FPT','stock','2026-10-11')])
    archive = settings.outputs_directory / 'analysis'; archive.mkdir(parents=True)
    (archive / 'f.json').write_text(json.dumps({'request': {'horizon': 'long'}}))
    runner = ReportRefreshRunner(settings)
    monkeypatch.setattr(runner, 'signature', lambda *args: 'v1')
    clock = [1000]; monkeypatch.setattr('stock_reports.pipeline.report_refresh.time.monotonic', lambda: clock[0])
    calls = []
    def generate(settings, request):
        calls.append(request)
        if request.symbol == 'ACB': raise ValueError('private detail')
        return [{'report': {'id': 'new'}, 'reused': False}]
    monkeypatch.setattr('stock_reports.pipeline.report_refresh.generate_reports', generate)
    result = runner.run_once()
    assert result == [{'symbol':'ACB','error_type':'ValueError'}, {'symbol':'FPT','report_id':'new','reused':False}]
    assert calls[1].horizon == 'long'
    assert runner.run_once() == []
    clock[0] += 301; runner.run_once()
    assert len(calls) == 3  # unchanged successful report is not regenerated
    assert 'private detail' not in (settings.outputs_directory / 'REPORT_REFRESH_STATUS.json').read_text()
