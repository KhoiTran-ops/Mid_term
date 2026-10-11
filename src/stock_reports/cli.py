"""Unified web, report catalog and data collectors."""

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
    industry_render=commands.add_parser('render-industry',help='Xuất StockLens ngành độc lập từ JSON / snapshot dữ liệu ngành')
    industry_render.add_argument('--industry',required=True)
    industry_render.add_argument('--period',required=True)
    industry_render.add_argument('--out',type=Path,required=True)
    industry_render.add_argument('--input',type=Path)
    industry_render.add_argument('--draft',action='store_true')
    industry_render.add_argument('--keep-empty-pages',action='store_true')
    industry_render.add_argument('--pages',nargs='+')
    industry_render.add_argument('--accent',default='#1F5EFF')
    industry_render.add_argument('--qa-dir',type=Path)
    macro_render=commands.add_parser('render-macro',help='Xuất StockLens vĩ mô độc lập từ công bố chính thức / JSON')
    macro_render.add_argument('--period',required=True)
    macro_render.add_argument('--out',type=Path,required=True)
    macro_render.add_argument('--input',type=Path)
    macro_render.add_argument('--draft',action='store_true')
    macro_render.add_argument('--hide-empty-pages',action='store_true')
    macro_render.add_argument('--refresh',action='store_true')
    macro_render.add_argument('--pages',nargs='+')
    macro_render.add_argument('--accent',default='#1F5EFF')
    macro_render.add_argument('--qa-dir',type=Path)
    render = commands.add_parser('render',help='Xuất StockLens 10 trang từ dữ liệu thật hoặc JSON đã kiểm tra')
    render.add_argument('--ticker',required=True)
    render.add_argument('--out',type=Path,required=True)
    render.add_argument('--input',type=Path)
    render.add_argument('--as-of',type=date.fromisoformat)
    render.add_argument('--horizon',choices=['short','medium','long'])
    web = commands.add_parser('web', help='Mở thư viện báo cáo và tin tức; tự cập nhật tin theo cấu hình')
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
    generate = actions.add_parser('generate', help='Tạo PDF cổ phiếu/ngành/vĩ mô từ dữ liệu đã lưu')
    generate.add_argument('--kind', choices=['stock','industry','macro','all'], default='all')
    generate.add_argument('--symbol')
    generate.add_argument('--industry-id')
    generate.add_argument('--as-of', type=date.fromisoformat)
    generate.add_argument('--period')
    generate.add_argument('--macro-period')
    generate.add_argument('--industry-period')
    generate.add_argument('--peers', nargs='+', default=[])
    generate.add_argument('--review', type=Path)
    generate.add_argument('--scenarios', type=Path)
    generate.add_argument('--horizon',choices=['short','medium','long'])
    macro = commands.add_parser('macro', help='Cập nhật dữ liệu vĩ mô năm từ World Bank')
    macro.add_argument('action', choices=['update','status'])
    commands.add_parser('data', help='Cập nhật, kiểm tra hoặc xuất dữ liệu; xem data --help')
    commands.add_parser('import-legacy', help='Nhập dữ liệu cũ; xem import-legacy --help')
    news = commands.add_parser('news', help='Thu thập tin RSS/Atom/listing và xem trạng thái nguồn')
    news.add_argument('action', choices=['update', 'watch', 'status'])
    news.add_argument('--force', action='store_true', help='Bỏ qua lịch đến hạn, vẫn áp dụng khóa một collector')
    industries = commands.add_parser('industries', help='Thu thập phân ngành và thống kê ngành công khai DNSE')
    industries.add_argument('action', choices=['update', 'watch', 'status'])
    industries.add_argument('--interval', type=int, default=60, help='Khoảng cập nhật snapshot, giây; tối thiểu 60')
    industries.add_argument('--catalog-only', action='store_true',
                            help='Chỉ tải doanh nghiệp/GICS công khai; bỏ qua snapshot MQTT')
    args = parser.parse_args(argv)
    if args.command in (None, 'web'):
        from stock_reports.web.app import create_app
        import uvicorn
        port = getattr(args, 'port', 8000)
        if not 1 <= port <= 65535:
            parser.error('Port must be in 1..65535')
        print(f'Thư viện báo cáo: http://127.0.0.1:{port}\nNhấn Ctrl+C để dừng web.', flush=True)
        uvicorn.run(create_app(settings), host='127.0.0.1', port=port)
    elif args.command == 'render-industry':
        from stock_reports.pipeline.industry_periods import load_period
        from stock_reports.reports.industry_stocklens.render import render_pdf
        payload=json.loads(args.input.read_text(encoding='utf-8')) if args.input else load_period(settings,args.industry,args.period,allow_example=True)
        if payload['meta']['industry_id']!=args.industry or payload['meta']['period_code']!=args.period:parser.error('JSON không khớp --industry / --period')
        render_pdf(payload,args.out,draft=args.draft or payload['meta'].get('example',False),hide_empty=not args.keep_empty_pages,pages=args.pages,accent=args.accent,qa_directory=args.qa_dir)
        import shutil
        audit=args.out.with_suffix('.quality_report.json');generic=args.out.parent/'quality_report.json'
        if audit.resolve()!=generic.resolve():shutil.copy2(audit,generic)
        print(f'StockLens Industry: {args.out}; JSON, HTML và quality_report cùng tên. '+('BẢN MINH HỌA, không dùng cho báo cáo thật.' if payload['meta'].get('example') else ''))
    elif args.command == 'render-macro':
        from stock_reports.pipeline.macro_periods import load_period
        from stock_reports.reports.macro_stocklens.render import render_pdf
        from stock_reports.reports.macro_stocklens.data import period_meta
        period_meta(args.period)
        payload=json.loads(args.input.read_text(encoding='utf-8')) if args.input else load_period(settings,args.period,refresh=args.refresh)
        if payload['meta']['period_code']!=args.period:parser.error('Mã kỳ JSON khác --period')
        render_pdf(payload,args.out,draft=args.draft,hide_empty=args.hide_empty_pages,pages=args.pages,accent=args.accent,qa_directory=args.qa_dir)
        import shutil
        audit=args.out.with_suffix('.quality_report.json')
        generic_audit=args.out.parent/'quality_report.json'
        if audit.resolve()!=generic_audit.resolve():shutil.copy2(audit,generic_audit)
        print(f'StockLens Macro: {args.out}; JSON, HTML và quality_report cùng tên.')
    elif args.command == 'render':
        from stock_reports.reports.stocklens.render import render_pdf,render_html,validate
        if args.input:
            payload=validate(json.loads(args.input.read_text(encoding='utf-8')))
            if payload['meta']['ticker']!=args.ticker.upper():parser.error('Mã JSON khác --ticker')
            if args.horizon and payload['meta']['horizon']!=args.horizon:parser.error('Đổi khung thời gian ở backend JSON, không chỉ đổi nhãn PDF')
            render_pdf(payload,args.out,accent=payload['meta'].get('accent','#1F5EFF'))
        else:
            from stock_reports.pipeline.research_reports import generate_reports,GenerationRequest,report_analysis
            import shutil
            params=dict(kind='stock',symbol=args.ticker.upper(),horizon=args.horizon)
            if args.as_of:params['as_of']=args.as_of
            result=generate_reports(settings,GenerationRequest(**params))[0]
            payload=report_analysis(settings,result['report']['id'])['document']['stocklens_data']
            args.out.parent.mkdir(parents=True,exist_ok=True)
            source=ReportCatalog(settings.reports_database,settings.reports_directory).pdf_path(result['report']['id'])
            if source.resolve()!=args.out.resolve():shutil.copy2(source,args.out)
        args.out.with_suffix('.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        args.out.with_suffix('.html').write_text(render_html(payload,accent=payload['meta'].get('accent','#1F5EFF')),encoding='utf-8')
        from stock_reports.reports.stocklens.evidence import export_missing
        export_missing(payload,args.out.with_suffix('.missing_report.json'))
        export_missing(payload,args.out.parent/'missing_report.json')
        print(f'StockLens: {args.out} (10 trang); JSON và HTML cùng tên.')
    elif args.command == 'industries':
        from stock_reports.pipeline.industries import update_industries
        from stock_reports.storage.industries import IndustryStore
        from stock_reports.core.locking import ProcessLock
        import time
        if args.interval < 60:
            parser.error('Industry interval must be at least 60 seconds')
        if args.action == 'status':
            print(json.dumps(IndustryStore(settings.industries_database).summary(), ensure_ascii=False, indent=2))
        else:
            lock = ProcessLock(settings.root / 'var/industry-collector.lock')
            if not lock.acquire():
                parser.error('An industry collector is already running')
            try:
                if args.action == 'update':
                    print(json.dumps(update_industries(
                        settings, collect_snapshot=not args.catalog_only
                    ), ensure_ascii=False, indent=2))
                else:
                    next_catalog_refresh = 0
                    while True:
                        try:
                            refresh_catalog = time.monotonic() >= next_catalog_refresh
                            result = update_industries(settings, refresh_catalog=refresh_catalog,
                                                       collect_snapshot=not args.catalog_only)
                            if refresh_catalog:
                                next_catalog_refresh = time.monotonic() + 86400
                            print(json.dumps(result, ensure_ascii=False), flush=True)
                        except Exception as error:
                            print(f'Industry collection failed ({type(error).__name__}); will retry.', flush=True)
                        time.sleep(args.interval)
            except KeyboardInterrupt:
                pass
            finally:
                lock.release()
    elif args.command == 'news':
        from stock_reports.pipeline.news_runtime import configured_news, NewsRunner
        from stock_reports.core.locking import ProcessLock
        store, collector = configured_news(settings)
        if args.action == 'status':
            print(json.dumps(dict(total=store.list_news()['total'], sources=[dict(id=s['id'],
                name=s['config']['name'], status=s['status'], error=s['error'],
                last_success=s['last_success'], next_run=s['next_run']) for s in store.sources()]), ensure_ascii=False, indent=2))
        elif not collector:
            parser.error('Missing config/news_sources.json')
        elif args.action == 'update':
            lock = ProcessLock(settings.root / 'var/news-collector.lock')
            if not lock.acquire():
                parser.error('A news collector is already running; check news status')
            try:
                result = collector.run(force=args.force)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 2 if result['failed'] else 0
            finally:
                lock.release()
        else:
            runner = NewsRunner(settings, collector)
            if not runner.start():
                parser.error('A news collector is already running')
            print('Thu thập tin theo lịch nguồn. Nhấn Ctrl+C để dừng.', flush=True)
            try:
                while runner.thread.is_alive():
                    runner.thread.join(timeout=1)
            except KeyboardInterrupt:
                pass
            finally:
                runner.stop()
    elif args.command == 'doctor':
        print(json.dumps(dict(project=str(settings.root),
            market_database=str(settings.market_database), market_data_exists=settings.market_database.is_file(),
            dnse_configured=settings.dnse_configured, downloads_started=False,
            dnse_public_catalog='available_without_credentials',
            dnse_authenticated_market='configured' if settings.dnse_configured else 'missing_DNSE_API_SECRET_or_key',
            available=['DNSE/CafeF collection', 'DNSE industry snapshots and classification', 'data inventory/CSV export', 'PDF catalog', 'web filters', 'news collection and filters'],
            next=['verify original financial statement units/scope/notes', 'current monthly macro inputs',
                  'DNSE industry unit verification and advanced valuation models'],
            research=['stock/industry/macro PDF generation', 'World Bank annual macro observations',
                      'model-specific financial formulas and gated PB/PE scenarios', 'Stitch library and PDF preview']),
            ensure_ascii=False, indent=2))
    elif args.command == 'test':
        (settings.root / 'var').mkdir(parents=True, exist_ok=True)
        return subprocess.call([sys.executable, '-m', 'pytest', str(settings.root / 'tests'), '-q',
            '--basetemp', str(settings.root / 'var/pytest-run')], cwd=settings.root)
    elif args.command == 'macro':
        if args.action=='update':
            from stock_reports.pipeline.macro_data import update_macro
            print(json.dumps(update_macro(settings),ensure_ascii=False,indent=2))
        else:
            path=settings.root/'var/macro/worldbank.json'
            print(path.read_text(encoding='utf-8') if path.exists() else '{"status":"missing"}')
    elif args.command == 'reports':
        catalog = ReportCatalog(settings.reports_database, settings.reports_directory)
        if args.action == 'list':
            print(catalog.list_reports().model_dump_json(indent=2))
        elif args.action == 'generate':
            from stock_reports.pipeline.research_reports import GenerationRequest, generate_reports
            params=dict(kind=args.kind,symbol=args.symbol.upper() if args.symbol else None,industry_id=args.industry_id,
                period=args.period.upper() if args.period else None,peers=[s.upper() for s in args.peers],horizon=args.horizon,macro_period=args.macro_period,industry_period=args.industry_period)
            if args.as_of:params['as_of']=args.as_of
            request=GenerationRequest.model_validate(params)
            print(json.dumps(generate_reports(settings,request,review_path=args.review,scenarios_path=args.scenarios),ensure_ascii=False,indent=2))
        else:
            metadata = ReportMetadata(kind=args.kind, title=args.title, as_of=args.as_of,
                symbol=args.symbol.upper() if args.symbol else None, company_name=args.company_name,
                industry_id=args.industry_id, industry_name=args.industry_name)
            record = catalog.register(metadata, (settings.root / args.pdf).resolve())
            print(record.model_dump_json(indent=2))
    return 0
