"""Offline defaults; network collection only runs through the explicit data command."""

import argparse
from datetime import date
import json
from pathlib import Path
import subprocess
import sys

from stock_reports.core.config import Settings
from stock_reports.reports.models import ReportKind, ReportMetadata
from stock_reports.storage.reports import ReportCatalog


def main(argv=None, *, root: Path) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    settings = Settings.from_root(root)
    if argv and argv[0] == 'data':
        from stock_reports.pipeline.collection import main as collect
        collect(argv[1:], settings)
        return 0
    if argv and argv[0] == 'import-legacy':
        from stock_reports.pipeline.import_legacy import main as import_legacy
        import_legacy(argv[1:], settings)
        return 0
    parser = argparse.ArgumentParser(description='Hệ thống báo cáo đầu tư cổ phiếu')
    commands = parser.add_subparsers(dest='command')
    web = commands.add_parser('web', help='Mở thư viện báo cáo; không tự tải dữ liệu')
    web.add_argument('--port', type=int, default=8000)
    commands.add_parser('doctor', help='Kiểm tra cấu hình và các thành phần; không tải dữ liệu')
    commands.add_parser('test', help='Chạy kiểm thử trên dữ liệu tạm')
    reports = commands.add_parser('reports', help='Quản lý báo cáo PDF cục bộ')
    actions = reports.add_subparsers(dest='action', required=True)
    actions.add_parser('list')
    add = actions.add_parser('add', help='Đăng ký PDF đã có vào thư viện')
    add.add_argument('--pdf', type=Path, required=True)
    add.add_argument('--kind', type=ReportKind, choices=list(ReportKind), required=True)
    add.add_argument('--title', required=True)
    add.add_argument('--as-of', type=date.fromisoformat, required=True)
    add.add_argument('--symbol')
    add.add_argument('--company-name')
    add.add_argument('--industry-id')
    add.add_argument('--industry-name')
    commands.add_parser('data', help='Cập nhật, kiểm tra hoặc xuất dữ liệu; xem data --help')
    commands.add_parser('import-legacy', help='Nhập dữ liệu cũ; xem import-legacy --help')
    args = parser.parse_args(argv)
    if args.command in (None, 'web'):
        from stock_reports.web.app import create_app
        import uvicorn
        port = getattr(args, 'port', 8000)
        if not 1 <= port <= 65535:
            parser.error('Port must be in 1..65535')
        print(f'Thư viện báo cáo: http://127.0.0.1:{port}\nNhấn Ctrl+C để dừng web.', flush=True)
        uvicorn.run(create_app(settings), host='127.0.0.1', port=port)
    elif args.command == 'doctor':
        print(json.dumps(dict(project=str(settings.root),
            market_database=str(settings.market_database), market_data_exists=settings.market_database.is_file(),
            dnse_configured=settings.dnse_configured, downloads_started=False,
            available=['DNSE/CafeF collection', 'data inventory/CSV export', 'PDF catalog', 'web filters'],
            next=['company/news/macro/industry sources', 'financial normalization and ratios',
                  'analysis and valuation engines', 'PDF renderer and full report pipeline']),
            ensure_ascii=False, indent=2))
    elif args.command == 'test':
        return subprocess.call([sys.executable, '-m', 'pytest', str(settings.root / 'tests'), '-q',
            '--basetemp', str(settings.root / 'var/pytest-run')], cwd=settings.root)
    elif args.command == 'reports':
        catalog = ReportCatalog(settings.reports_database, settings.reports_directory)
        if args.action == 'list':
            print(catalog.list_reports().model_dump_json(indent=2))
        else:
            metadata = ReportMetadata(kind=args.kind, title=args.title, as_of=args.as_of,
                symbol=args.symbol.upper() if args.symbol else None, company_name=args.company_name,
                industry_id=args.industry_id, industry_name=args.industry_name)
            record = catalog.register(metadata, (settings.root / args.pdf).resolve())
            print(record.model_dump_json(indent=2))
    return 0
