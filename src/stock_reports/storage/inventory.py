"""Coverage checks and CSV exports for the next research project."""

import csv
from datetime import datetime
import json
from pathlib import Path
import sqlite3

from stock_reports.data_sources.dnse.market import VIETNAM


def local_time(timestamp):
    return datetime.fromtimestamp(timestamp, VIETNAM).isoformat() if timestamp else None


def inventory(store):
    with sqlite3.connect(store.path) as db:
        db.execute('BEGIN')
        counts = {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                  for table in ('instruments', 'ohlcv_bars', 'financial_facts',
                                'financial_periods', 'foreign_snapshots')}
        bars = db.execute('SELECT symbol,timeframe,COUNT(*),MIN(ts),MAX(ts) '
                          'FROM ohlcv_bars GROUP BY symbol,timeframe').fetchall()
        periods = db.execute('SELECT symbol,fiscal_year,fiscal_quarter FROM financial_periods').fetchall()
        financial = db.execute('''SELECT symbol,statement_type,fiscal_year,fiscal_quarter,
            COUNT(*),SUM(value_numeric IS NOT NULL) FROM financial_facts
            GROUP BY symbol,statement_type,fiscal_year,fiscal_quarter''').fetchall()
        instruments = db.execute('SELECT symbol,exchange,company_name FROM instruments ORDER BY symbol').fetchall()
        invalid_ohlc = db.execute('''SELECT COUNT(*) FROM ohlcv_bars
            WHERE low>high OR open<low OR open>high OR close<low OR close>high
               OR low<0 OR volume<0''').fetchone()[0]
        foreign_latest = db.execute('SELECT MAX(ts) FROM foreign_snapshots').fetchone()[0]
    by_bar = {(symbol, frame): (count, first, last) for symbol, frame, count, first, last in bars}
    by_period, by_statement = {}, {}
    for symbol, year, quarter in periods:
        by_period.setdefault(symbol, set()).add((year, quarter))
    for symbol, statement, year, quarter, rows, numbers in financial:
        if numbers:
            by_statement.setdefault((symbol, statement), set()).add((year, quarter))
    coverage = []
    for symbol, exchange, company in instruments:
        latest = sorted(by_period.get(symbol, set()), reverse=True)
        bs = by_statement.get((symbol, 'BSheet'), set())
        inc = by_statement.get((symbol, 'IncSta'), set())
        cf = by_statement.get((symbol, 'CashFlow'), set()) | by_statement.get((symbol, 'CashFlowDirect'), set())
        daily = by_bar.get((symbol, '1D'), (0, None, None))
        minute = by_bar.get((symbol, '1m'), (0, None, None))
        coverage.append(dict(symbol=symbol, exchange=exchange, company_name=company,
            daily_rows=daily[0], daily_latest=local_time(daily[2]),
            minute_rows=minute[0], minute_latest=local_time(minute[2]),
            reported_quarters=len(latest), latest_quarter=f'{latest[0][0]}Q{latest[0][1]}' if latest else None,
            balance_sheet_quarters=len(bs), income_statement_quarters=len(inc),
            cash_flow_quarters=len(cf), quarters_with_three_statements=len(bs & inc & cf),
            reported_window=','.join(f'{y}Q{q}' for y, q in latest),
            financial_status='available' if bs or inc or cf else 'missing'))
    latest_daily = max((last for _, frame, _, _, last in bars if frame == '1D'), default=None)
    latest_minute = max((last for _, frame, _, _, last in bars if frame == '1m'), default=None)
    summary = dict(checked_at=datetime.now(VIETNAM).isoformat(), tables=counts,
        latest_daily=local_time(latest_daily), latest_minute=local_time(latest_minute),
        latest_foreign_snapshot=local_time(foreign_latest / 1000) if foreign_latest else None,
        symbols_with_financial_numbers=sum(r['financial_status']=='available' for r in coverage),
        symbols_with_eight_reported_quarters=sum(r['reported_quarters']>=8 for r in coverage),
        symbols_with_eight_quarters_of_three_statements=sum(r['quarters_with_three_statements']>=8 for r in coverage),
        symbols_without_financial_numbers=sum(r['financial_status']=='missing' for r in coverage),
        ohlcv_rows_with_inconsistent_range=invalid_ohlc,
        notes=['Coverage means there are numeric facts, not that every financial line is complete.',
               'Eight quarters are the latest published periods per company, not a guarantee of a current quarter.',
               'Legacy financial values are preserved in original numeric form; UI unit labels are not conversion rules.',
               'Cash-flow period basis (quarter versus year-to-date) must be checked before financial analysis.',
               'Imported historical rows have original retrieval dates but no archived response attached.',
               'Use run manifests and raw receipts to distinguish newly fetched data from imported history.'])
    return summary, coverage


def write_inventory(store, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    summary, coverage = inventory(store)
    (output / 'data_inventory.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    with (output / 'coverage.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(coverage[0]) if coverage else ['symbol'])
        writer.writeheader()
        writer.writerows(coverage)
    text = f'''# Tình trạng dữ liệu

Kiểm tra: {summary['checked_at']}

- Danh mục: {summary['tables']['instruments']:,} mã.
- OHLCV DNSE: {summary['tables']['ohlcv_bars']:,} bản ghi.
- Nến ngày mới nhất: {summary['latest_daily']}.
- Nến phút mới nhất: {summary['latest_minute']}.
- Số liệu tài chính CafeF: {summary['tables']['financial_facts']:,} dòng.
- Mã có số liệu tài chính: {summary['symbols_with_financial_numbers']:,}.
- Mã có 8 kỳ báo cáo: {summary['symbols_with_eight_reported_quarters']:,}.
- Mã có số liệu ở cả 3 báo cáo trong 8 quý: {summary['symbols_with_eight_quarters_of_three_statements']:,}.
- Mã chưa có số liệu tài chính: {summary['symbols_without_financial_numbers']:,}.
- OHLCV có giá ngoài khoảng thấp/cao: {summary['ohlcv_rows_with_inconsistent_range']:,}; giữ nguyên dữ liệu nguồn để kiểm tra.

Xem `coverage.csv` để kiểm tra từng mã. “Có 3 báo cáo” chỉ xác nhận mỗi báo cáo
có số liệu; không khẳng định mọi chỉ tiêu đều đầy đủ. Tối đa 8 quý mới nhất
đã công bố của từng doanh nghiệp; có thể thiếu hoặc cũ với mã ngừng giao dịch.

Số liệu cũ nhập từ dự án nguồn giữ ngày tải gốc. Các phản hồi tải mới được lưu
tại `var/runs/*/raw`, kết quả cập nhật tại `var/runs/*/manifest.json`.
Đơn vị giá, đơn vị từng chỉ tiêu tài chính, EPS và tính lũy kế của lưu chuyển
tiền tệ cần được kiểm chứng trước khi định giá. Không tự nhân số liệu CafeF
theo nhãn “tỷ đồng” trên giao diện: giá trị HTML gốc có thể đã ở đơn vị đồng.
'''
    (output / 'DATA_STATUS.md').write_text(text, encoding='utf-8')
    return summary


def export_data(store, output: Path, symbols=None):
    output.mkdir(parents=True, exist_ok=True)
    tables = ('instruments', 'ohlcv_bars', 'financial_periods', 'financial_facts', 'foreign_snapshots')
    result = {}
    with sqlite3.connect(store.path) as db:
        for table in tables:
            query = f'SELECT * FROM {table}'
            if symbols:
                query += ' WHERE symbol IN (' + ','.join('?' for _ in symbols) + ')'
            cursor = db.execute(query, [s.upper() for s in symbols] if symbols else [])
            path = output / f'{table}.csv'
            with path.open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow([c[0] for c in cursor.description])
                writer.writerows(cursor)
            result[table] = str(path)
    return result
