from datetime import date, datetime
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from stock_reports.core.config import Settings
from stock_reports.reports.models import ReportKind, ReportPage, StoredReport
from stock_reports.storage.reports import ReportCatalog
from stock_reports.pipeline.news_runtime import configured_news, NewsRunner
from stock_reports.pipeline.report_refresh import ReportRefreshRunner
from stock_reports.web.news import news_router
from stock_reports.web.generation import ReportJobs, generation_router
from stock_reports.pipeline.research_reports import report_analysis
from stock_reports.analysis.repository import ResearchRepository, VIETNAM
from stock_reports.storage.market import MarketStore
from starlette.middleware.trustedhost import TrustedHostMiddleware


LABELS = {'stock': 'Cổ phiếu', 'industry': 'Ngành', 'macro': 'Vĩ mô'}


def create_app(settings: Settings) -> FastAPI:
    assets = Path(__file__).resolve().parent
    catalog = ReportCatalog(settings.reports_database, settings.reports_directory)
    templates = Jinja2Templates(directory=assets / 'templates')
    templates.env.filters['local_time'] = lambda value: datetime.fromisoformat(value).astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M')
    news_store, collector = configured_news(settings)
    runner = NewsRunner(settings, collector)
    jobs = ReportJobs(settings)
    report_runner=ReportRefreshRunner(settings)

    @asynccontextmanager
    async def lifespan(app):
        if settings.news_auto_update:
            runner.start()
        report_runner.start()
        yield
        await asyncio.to_thread(runner.stop)
        await asyncio.to_thread(jobs.stop)
        await asyncio.to_thread(report_runner.stop)

    app = FastAPI(title='Thư viện báo cáo đầu tư', version='0.2.0', docs_url=None, redoc_url=None, lifespan=lifespan)
    app.include_router(news_router(news_store, templates))
    app.include_router(generation_router(settings, catalog, templates, jobs))
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost','127.0.0.1','testserver'])
    app.mount('/static', StaticFiles(directory=assets / 'static'), name='static')

    @app.middleware('http')
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; object-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, error):
        return JSONResponse(status_code=error.status_code,
            content={'error': {'code': 'NOT_FOUND' if error.status_code == 404 else 'INVALID_REQUEST',
                               'message': str(error.detail)}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return JSONResponse(status_code=422,
            content={'error': {'code': 'INVALID_REQUEST', 'message': 'Bộ lọc không hợp lệ.'}})

    @app.get('/api/health')
    def health():
        return {'status': 'ok'}

    @app.get('/api/data-status')
    def data_status():
        path=settings.outputs_directory/'FINANCIAL_COMPLETE_PROGRESS.json'
        try:
            payload=json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {'status':'not_started'}
        allowed=('status','stage','completed','total','current_symbol','updated_at',
                 'annual_complete_companies','quarterly_complete_latest_eight','max_quarters')
        result={k:payload[k] for k in allowed if k in payload}
        # Do not keep advertising a crashed collector as running indefinitely.
        if result.get('status')=='running' and result.get('updated_at'):
            from datetime import datetime,UTC
            try:
                if (datetime.now(UTC)-datetime.fromisoformat(result['updated_at'])).total_seconds()>600:
                    result['status']='stale'
            except (ValueError,TypeError):result['status']='stale'
        return result

    @app.get('/api/report-refresh-status')
    def report_refresh_status():
        path=settings.outputs_directory/'REPORT_REFRESH_STATUS.json'
        try:return json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError):return dict(enabled=False,status='not_started')

    @app.get('/favicon.ico', include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    @app.get('/api/reports', response_model=ReportPage)
    def reports(kind: ReportKind | None = None,
                symbol: str | None = Query(None, max_length=12),
                industry_id: str | None = Query(None, max_length=80),
                query: str | None = Query(None, max_length=240),
                date_from: date | None = None, date_to: date | None = None,
                page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
        try:
            return catalog.list_reports(kind=kind, symbol=symbol, industry_id=industry_id,
                query=query, date_from=date_from, date_to=date_to, page=page, page_size=page_size)
        except ValueError as error:
            raise HTTPException(422, 'Khoảng ngày không hợp lệ.') from error

    @app.get('/api/reports/{report_id}', response_model=StoredReport)
    def report_detail(report_id: str):
        try:
            record = catalog.get(report_id)
        except ValueError:
            record = None
        if record is None:
            raise HTTPException(404, 'Không tìm thấy báo cáo.')
        return record

    @app.get('/api/reports/{report_id}/pdf')
    def report_pdf(report_id: str, download: bool = False):
        try:
            record = catalog.get(report_id)
            path = catalog.pdf_path(report_id)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, 'Không tìm thấy tệp báo cáo.')
        filename = f'{record.kind}-{record.symbol or record.industry_id or "macro"}-{record.as_of}.pdf'
        return FileResponse(path, media_type='application/pdf', filename=filename,
                            content_disposition_type='attachment' if download else 'inline')

    @app.get('/api/reports/{report_id}/stocklens-data')
    def stocklens_data(report_id:str):
        try:payload=report_analysis(settings,report_id,catalog)
        except (ValueError,FileNotFoundError):payload=None
        data=payload['document'].get('stocklens_data') if payload else None
        if not data:raise HTTPException(404,'Báo cáo không có JSON StockLens.')
        return Response(json.dumps(data,ensure_ascii=False,indent=2),media_type='application/json',
            headers={'Content-Disposition':f'attachment; filename="{data["meta"]["ticker"]}-stocklens.json"'})

    @app.get('/api/reports/{report_id}/industry-data')
    def industry_data(report_id:str):
        try:payload=report_analysis(settings,report_id,catalog)
        except (ValueError,FileNotFoundError):payload=None
        data=payload['document'].get('industry_stocklens_data') if payload else None
        if not data:raise HTTPException(404,'Báo cáo không có JSON ngành StockLens.')
        return Response(json.dumps(data,ensure_ascii=False,indent=2),media_type='application/json',
            headers={'Content-Disposition':f'attachment; filename="industry-{data["meta"]["industry_id"]}-{data["meta"]["period_code"]}.json"'})

    @app.get('/api/reports/{report_id}/industry-quality')
    def industry_quality(report_id:str):
        try:payload=report_analysis(settings,report_id,catalog)
        except (ValueError,FileNotFoundError):payload=None
        data=payload['document'].get('industry_stocklens_data') if payload else None
        if not data:raise HTTPException(404,'Báo cáo không có dữ liệu ngành StockLens.')
        from stock_reports.reports.industry_stocklens.quality import inspect
        return Response(json.dumps(inspect(data),ensure_ascii=False,indent=2),media_type='application/json',
            headers={'Content-Disposition':'attachment; filename="quality_report.json"'})

    @app.get('/api/reports/{report_id}/macro-data')
    def macro_data(report_id:str):
        try:payload=report_analysis(settings,report_id,catalog)
        except (ValueError,FileNotFoundError):payload=None
        data=payload['document'].get('macro_stocklens_data') if payload else None
        if not data:raise HTTPException(404,'Báo cáo không có JSON vĩ mô StockLens.')
        return Response(json.dumps(data,ensure_ascii=False,indent=2),media_type='application/json',
            headers={'Content-Disposition':f'attachment; filename="macro-{data["meta"]["period_code"]}.json"'})

    @app.get('/api/reports/{report_id}/macro-quality')
    def macro_quality(report_id:str):
        try:payload=report_analysis(settings,report_id,catalog)
        except (ValueError,FileNotFoundError):payload=None
        data=payload['document'].get('macro_stocklens_data') if payload else None
        if not data:raise HTTPException(404,'Báo cáo không có dữ liệu vĩ mô StockLens.')
        from stock_reports.reports.macro_stocklens.quality import inspect
        return Response(json.dumps(inspect(data),ensure_ascii=False,indent=2),media_type='application/json',
            headers={'Content-Disposition':'attachment; filename="quality_report.json"'})

    @app.get('/api/reports/{report_id}/missing-report')
    def missing_data_report(report_id:str):
        try:payload=report_analysis(settings,report_id,catalog)
        except (ValueError,FileNotFoundError):payload=None
        data=payload['document'].get('stocklens_data') if payload else None
        if not data:raise HTTPException(404,'Báo cáo không có dữ liệu StockLens.')
        from stock_reports.reports.stocklens.evidence import missing_report
        return Response(json.dumps(missing_report(data),ensure_ascii=False,indent=2),media_type='application/json',
            headers={'Content-Disposition':'attachment; filename="missing_report.json"'})

    @app.get('/')
    def library(request: Request, kind: str = Query('', max_length=20),
                symbol: str = Query('', max_length=12), industry_id: str = Query('', max_length=80),
                query: str = Query('', max_length=240), date_from: str = Query('', max_length=10),
                date_to: str = Query('', max_length=10), page: int = Query(1, ge=1)):
        filters = dict(kind=kind, symbol=symbol.upper(), industry_id=industry_id,
                       query=query, date_from=date_from, date_to=date_to)
        error = None
        try:
            result = catalog.list_reports(kind=ReportKind(kind) if kind else None,
                symbol=symbol or None, industry_id=industry_id or None, query=query or None,
                date_from=date.fromisoformat(date_from) if date_from else None,
                date_to=date.fromisoformat(date_to) if date_to else None, page=page)
        except ValueError:
            error = 'Vui lòng kiểm tra loại báo cáo và khoảng ngày đã chọn.'
            result = ReportPage(items=[], total=0, page=1, page_size=20)
        total_pages = max(1, (result.total + result.page_size - 1) // result.page_size)
        repo = ResearchRepository(settings, datetime.now(VIETNAM).date())
        details = {}
        for record in result.items:
            payload = report_analysis(settings, record.id, catalog)
            details[record.id] = dict(pages=payload['page_count'] if payload else None,
                assessment=payload['document']['assessment'] if payload else '')
        counts = {key:catalog.list_reports(kind=ReportKind(key),page_size=1).total for key in LABELS}
        companies = repo.companies()
        industries = repo.industries()
        market_store = MarketStore(settings.market_database)
        market_store.initialize()
        financial_symbols = market_store.financial_symbols()
        coverage = dict(companies=len(companies), industries=len(industries),
                        macro_observations=len(repo.macro()),
                        financial_companies=len(financial_symbols))
        return templates.TemplateResponse(request=request, name='library.html',
            context=dict(result=result, filters=filters, options=catalog.filter_options(),
                latest_news=news_store.list_news(page_size=3)['items'],
                labels=LABELS, error=error, total_pages=total_pages, active='reports',
                details=details, counts=counts, coverage=coverage,
                industry_options=industries, companies=companies,
                financial_symbols=financial_symbols,
                previous_url=str(request.url.include_query_params(page=page-1)) if page>1 else None,
                next_url=str(request.url.include_query_params(page=page+1)) if page<total_pages else None),
            status_code=422 if error else 200)

    return app
