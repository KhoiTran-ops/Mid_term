"""Snapshot factual coverage; no imputation and no claim of full note verification."""
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from stock_reports.core.config import Settings
from stock_reports.storage.market import MarketStore
from stock_reports.storage.inventory import inventory
from stock_reports.data_sources.dnse.market import VIETNAM


def main():
    settings=Settings.from_root(ROOT);store=MarketStore(settings.market_database);store.initialize()
    summary,coverage=inventory(store)
    with sqlite3.connect(store.path,timeout=30) as db:
        rows=db.execute('SELECT symbol,statement_type,fiscal_year,COUNT(*),SUM(value_numeric IS NOT NULL) '
            'FROM annual_statement_facts WHERE fiscal_year BETWEEN 2021 AND 2025 GROUP BY symbol,statement_type,fiscal_year').fetchall()
    annual={}
    for symbol,statement,year,n,numeric in rows:
        if numeric:annual.setdefault((symbol,statement),set()).add(year)
    full=set(range(2021,2026));completed=0
    for item in coverage:
        symbol=item['symbol']
        groups={s:annual.get((symbol,s),set()) for s in ('BSheet','IncSta','CashFlow','CashFlowDirect')}
        complete=groups['BSheet'] & groups['IncSta'] & (groups['CashFlow']|groups['CashFlowDirect'])
        item['annual_complete_years']=sorted(complete)
        item['annual_missing_years']={s:sorted(full-v) for s,v in [('BSheet',groups['BSheet']),('IncSta',groups['IncSta']),('CashFlow',groups['CashFlow']|groups['CashFlowDirect'])]}
        completed+=complete==full
    summary['annual_complete_companies_2021_2025']=completed
    summary['coverage_definition']='Each statement has numeric rows; does not assert every component or note verified.'
    payload=dict(summary=summary,companies=coverage)
    output=settings.outputs_directory/'FINANCIAL_COVERAGE_AUDIT.json'
    output.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    note=f'''# Rà soát BCTC - {summary['checked_at']}

- Có số liệu BCTC quý: {summary['symbols_with_financial_numbers']} mã.
- Có số liệu cả ba bảng trong cửa sổ tám quý: {summary['symbols_with_eight_quarters_of_three_statements']} mã.
- Có cả ba bảng năm cho 2021-2025: {completed} mã.
- Thành phần BCTC quý: {summary['tables']['financial_facts']:,} dòng.
- Thành phần BCTC năm tải trực tiếp: {summary['tables']['annual_statement_facts']:,} dòng.
- Workbook lịch sử cũ giữ riêng: {summary['tables']['annual_financial_facts']:,} dòng.

Chỉ xác nhận hiện diện số liệu, không khẳng định mọi thành phần hay thuyết minh đã đủ.
Đợt tải toàn danh mục có thể vẫn đang chạy; xem FINANCIAL_COMPLETE_PROGRESS.json.
Danh sách từng mã và từng năm thiếu nằm trong FINANCIAL_COVERAGE_AUDIT.json.

## Đối chiếu VCB

Đã tải 40 tài liệu công bố gốc; đối chiếu các chỉ tiêu chính năm 2021-2025 và cửa sổ quý 2024Q3-2026Q2.
Đã nhập bảng dòng tiền trực tiếp gốc 2025Q1-Q3 (105 dòng; dấu gạch giữ null).
Tổng tài sản năm 2023 và LNST cổ đông ngân hàng 2025 dùng số gốc qua hồ sơ đối chiếu; dữ liệu CafeF lỗi vẫn giữ để truy vết.
Nợ phải trả 2026Q2 dùng bản gốc (chênh 5 triệu VND so với CafeF).
ROE/ROA 2024 dùng số đầu năm trình bày lại; các cột năm còn lại là bản năm đã công bố ban đầu.
NIM, CASA, CAR, nợ xấu, chi phí tín dụng có nguồn IR Q2/2026 và giữ khác biệt kỳ/phạm vi.

## Phần còn cần làm

1. Hoàn thành tải toàn danh mục và xử lý từng kỳ nguồn trống.
2. Đối chiếu thuyết minh và bản soát xét bán niên, không tự đánh dấu đã kiểm chứng toàn bộ.
3. Kiểm chứng cổ phiếu lưu hành, vốn thuộc cổ đông mẹ, EPS TTM và đơn vị giá.
4. Bổ sung cơ cấu cổ đông, công ty con, phân khúc và cổ tức từ công bố cùng kỳ.
5. Nhập giả định dự phóng/định giá có căn cứ; dữ liệu lịch sử không tự tạo giá mục tiêu.
'''
    (settings.outputs_directory/'FINANCIAL_REFRESH_REVIEW.md').write_text(note,encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
