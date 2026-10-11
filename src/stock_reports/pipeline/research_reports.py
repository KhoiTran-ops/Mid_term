"""One report-generation service shared by CLI and web, reusing the existing publisher."""

from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal

from stock_reports.analysis.financials import FORMULA_VERSION, load_review, parse_period
from stock_reports.analysis.annuals import load_annual_review
from stock_reports.analysis.repository import ResearchRepository, VIETNAM
from stock_reports.analysis.research import build_document
from stock_reports.analysis.valuation import VALUATION_VERSION, load_scenarios
from stock_reports.core.locking import ProcessLock
from stock_reports.data_sources.archive import ArchivedCafeFTransport, ResponseArchive
from stock_reports.data_sources.cafef.client import CafeFClient
from stock_reports.data_sources.cafef.sync import sync_financial_history
from stock_reports.pipeline.publication import ReportPublisher
from stock_reports.reports.models import ReportKind
from stock_reports.reports.render import ResearchPdfRenderer
from stock_reports.storage.reports import ReportCatalog
from stock_reports.storage.market import MarketStore


class GenerationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind: Literal['stock','industry','macro','all']
    symbol: str | None = Field(default=None,pattern=r'^[A-Z0-9]{2,12}$')
    industry_id: str | None = Field(default=None,pattern=r'^[a-z0-9][a-z0-9-]{0,79}$')
    as_of: date = Field(default_factory=lambda: datetime.now(VIETNAM).date())
    period: str | None = Field(default=None,pattern=r'^\d{4}Q[1-4]$')
    peers: tuple[str, ...] = Field(default=(),max_length=5)
    horizon: Literal['short','medium','long'] | None = None
    macro_period: str | None = Field(default=None,pattern=r'^\d{4}(?:-9T|-Q[1-4]|-(?:0[1-9]|1[0-2]))?$')
    industry_period: str | None = Field(default=None,pattern=r'^\d{4}(?:-9T|-Q[1-4]|-(?:0[1-9]|1[0-2]))?$')

    @model_validator(mode='after')
    def scope(self):
        if self.as_of > datetime.now(VIETNAM).date():
            raise ValueError('Ngày chốt không được ở tương lai')
        if self.kind in ('stock','all') and not self.symbol:
            raise ValueError('Cần mã cổ phiếu')
        if self.kind=='industry' and not self.industry_id:
            raise ValueError('Cần chọn ngành')
        if any(not re.fullmatch(r'[A-Z0-9]{2,12}',p) for p in self.peers):
            raise ValueError('Mã so sánh không hợp lệ')
        return self


def document_fingerprint(document):
    def clean(value):
        if isinstance(value,dict):
            return {k:clean(v) for k,v in value.items() if k not in ('generated_at','retrieved_at') and
                not (k in ('template_version','template_sha256') and v is None) and
                not (k=='macro_stocklens_data' and v is None) and
                not (k=='industry_stocklens_data' and v is None) and
                not (k=='cover_blocks' and not v) and not (k=='chart_type' and v=='line')}
        if isinstance(value,list):return [clean(v) for v in value]
        return value
    payload=dict(document=clean(document.model_dump(mode='json')),report_format='research-a4-2.5',
        editorial_format='macro-reference-1.1' if document.editorial_markdown else None,formula_version=FORMULA_VERSION)
    if document.kind==ReportKind.STOCK:payload['valuation_version']=VALUATION_VERSION
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def report_analysis(settings,report_id,catalog=None):
    catalog=catalog or ReportCatalog(settings.reports_database,settings.reports_directory)
    record=catalog.get(report_id)
    if not record:return None
    path=settings.outputs_directory/'analysis'/f'{record.id}.json'
    if not path.is_file():return None
    payload=json.loads(path.read_text(encoding='utf-8'))
    return payload if payload.get('report_sha256')==record.sha256 else None


def generate_reports(settings,request: GenerationRequest, *, review_path=None,scenarios_path=None):
    lock=ProcessLock(settings.root/'var/report-generator.lock')
    if not lock.acquire():raise ValueError('Đang tạo báo cáo khác; chờ lượt hiện tại hoàn tất')
    try:
        return _generate(settings,request,review_path,scenarios_path)
    finally:
        lock.release()


def _generate(settings,request,review_path,scenarios_path):
    if request.kind in ('stock', 'all'):
        ensure_financials(settings, (request.symbol, *request.peers))
        from stock_reports.data_sources.adjusted_prices import ensure_adjusted_history
        for symbol in dict.fromkeys((request.symbol,'VNINDEX')):
            if symbol:ensure_adjusted_history(settings,symbol,request.as_of)
        from stock_reports.analysis.market_fundamentals import load_market_snapshot
        known_market=load_market_snapshot(settings,request.symbol,request.as_of)
        if request.as_of==datetime.now(VIETNAM).date() and (known_market is None or
            datetime.fromisoformat(known_market['retrieved_at']).astimezone(VIETNAM).date()<request.as_of):
            from stock_reports.data_sources.cafef.fundamentals import refresh
            try:refresh(settings,[request.symbol])
            except (ValueError,RuntimeError,OSError):pass  # Financial data remains reportable if the provider is unavailable.
    repo=ResearchRepository(settings,request.as_of)
    if request.symbol:
        default_review=settings.root/'var/financial_reviews'/f'{request.symbol}.json'
        default_scenarios=settings.root/'config/valuation'/f'{request.symbol}.json'
        review_path=review_path or (default_review if default_review.exists() else None)
        scenarios_path=scenarios_path or (default_scenarios if default_scenarios.exists() else None)
    review,scenarios=load_review(review_path),load_scenarios(scenarios_path)
    catalog=ReportCatalog(settings.reports_database,settings.reports_directory)
    publisher=ReportPublisher(ResearchPdfRenderer(),catalog)
    output=settings.outputs_directory/'analysis'
    output.mkdir(parents=True,exist_ok=True)
    kinds=[ReportKind.STOCK,ReportKind.INDUSTRY,ReportKind.MACRO] if request.kind=='all' else [ReportKind(request.kind)]
    industry_id=repo.company(request.symbol)['industry']['slug'] if request.kind=='all' else request.industry_id
    results=[]
    for kind in kinds:
        industry_path=settings.root/'config/industry_stocklens.json'
        independent_industry=kind==ReportKind.INDUSTRY and industry_path.is_file() and json.loads(industry_path.read_text(encoding='utf-8')).get('enabled')
        macro_path=settings.root/'config/macro_stocklens.json'
        independent_macro=kind==ReportKind.MACRO and macro_path.is_file() and json.loads(macro_path.read_text(encoding='utf-8')).get('enabled')
        if independent_industry:
            from stock_reports.pipeline.industry_periods import load_period as load_industry_period
            from stock_reports.reports.industry_stocklens.document import build_document as build_industry_document
            document=build_industry_document(load_industry_period(settings,industry_id,request.industry_period,as_of=request.as_of))
        elif independent_macro:
            from stock_reports.pipeline.macro_periods import load_period
            from stock_reports.reports.macro_stocklens.document import build_document as build_macro_document
            document=build_macro_document(load_period(settings,request.macro_period,as_of=request.as_of))
        else:
            document=build_document(settings,kind=kind,as_of=request.as_of,symbol=request.symbol if kind==ReportKind.STOCK else None,
                industry_id=industry_id,period=parse_period(request.period) if request.period else None,peers=request.peers,
                review=review if kind==ReportKind.STOCK else None,scenarios=scenarios if kind==ReportKind.STOCK else None,repository=repo)
        if kind==ReportKind.STOCK:
            from stock_reports.reports.stocklens.data import build_payload,VERSION
            from stock_reports.reports.stocklens.render import validate,asset_fingerprint
            from stock_reports.analysis.profiles import detect_profile
            company=repo.company(request.symbol)
            data=repo.financials(request.symbol,period=parse_period(request.period) if request.period else None,review=review)
            stocklens=validate(build_payload(settings,repo,company,data,detect_profile(data,company['industry']['name']),document,horizon=request.horizon))
            document=document.model_copy(update=dict(stocklens_data=stocklens,template_version=VERSION,template_sha256=asset_fingerprint(),
                assessment='Dữ kiện và điều kiện theo dõi; không phải khuyến nghị mua/bán'))
        fingerprint=document_fingerprint(document)
        cached=catalog.find_by_generation_key(fingerprint)
        if cached is None:
            for path in output.glob('*.json'):
                try:
                    payload=json.loads(path.read_text(encoding='utf-8'))
                    if payload.get('fingerprint')!=fingerprint:continue
                    existing=catalog.get(path.stem)
                    if existing and payload.get('report_sha256')==existing.sha256 and catalog.pdf_path(existing.id).is_file():
                        cached=catalog.bind_generation_key(fingerprint,existing.id);break
                except (ValueError,KeyError,FileNotFoundError):
                    continue
        pdf_available=False
        if cached:
            try:
                pdf_available=catalog.pdf_path(cached.id).is_file()
            except FileNotFoundError:
                pass
            if pdf_available and report_analysis(settings,cached.id,catalog):
                results.append(dict(report=cached.model_dump(mode='json'),reused=True))
                continue
        if pdf_available:
            record,reused=cached,True
        else:
            record=publisher.publish(document,generation_key=fingerprint)
            reused=False
        tickers={document.symbol} if document.symbol else set()
        for part in document.sections:
            for block in part.blocks:
                if block.headers and block.headers[0]=='Mã':tickers.update(row[0] for row in block.rows)
        from pypdf import PdfReader
        if document.industry_stocklens_data is not None:
            from stock_reports.reports.industry_stocklens.quality import inspect
            inputs=dict(industry_period=document.industry_stocklens_data,quality_report=inspect(document.industry_stocklens_data),
                mode='Independent industry snapshot; no sample plastic data or stock scoring')
        elif document.macro_stocklens_data is not None:
            from stock_reports.reports.macro_stocklens.quality import inspect
            inputs=dict(macro_period= document.macro_stocklens_data,quality_report=inspect(document.macro_stocklens_data),
                mode='Independent period-specific macro snapshot; no annual WDI substitution')
        elif document.editorial_markdown:
            inputs=dict(reference_markdown=document.editorial_markdown,
                reference_name=document.editorial_source_name,reference_sha256=document.editorial_source_sha256,
                mode='user-provided dated snapshot; no live database values mixed into report',
                primary_sources_independently_verified=False)
        else:
            inputs=dict(financial_facts=[r for r in repo.financial_inputs() if r['symbol'] in tickers],
                macro=repo.macro(),macro_context=repo.macro_context(),industry_snapshots=repo.snapshots(),
                prices={ticker:repo.bars(ticker) for ticker in sorted(tickers)},
                review=review.model_dump(mode='json') if review and kind==ReportKind.STOCK else None,
                annual_review=(load_annual_review(settings,request.symbol).model_dump(mode='json')
                    if kind==ReportKind.STOCK and (settings.root/'var/annual_reviews'/f'{request.symbol}.json').exists() else None),
                scenarios=scenarios.model_dump(mode='json') if scenarios and kind==ReportKind.STOCK else None)
            if kind==ReportKind.STOCK:
                inputs['annual_financial_facts']=repo.annual(document.symbol)
                from stock_reports.analysis.market_fundamentals import load_market_snapshot
                inputs['market_fundamentals']=load_market_snapshot(settings,document.symbol,request.as_of)
        payload=dict(fingerprint=fingerprint,report_sha256=record.sha256,page_count=len(PdfReader(catalog.pdf_path(record.id)).pages),
            request=request.model_dump(mode='json'),document=document.model_dump(mode='json'),inputs=inputs)
        temporary=output/f'{record.id}.json.tmp'
        temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(output/f'{record.id}.json')
        if kind==ReportKind.STOCK and document.stocklens_data:
            from stock_reports.reports.stocklens.evidence import export_missing
            export_missing(document.stocklens_data,output/f'{record.id}.missing_report.json')
        results.append(dict(report=record.model_dump(mode='json'),reused=reused,page_count=payload['page_count']))
    return results


def ensure_financials(settings, symbols, *, max_quarters=8):
    """Refresh the requested symbols and require usable quarterly statements."""
    selected = tuple(dict.fromkeys(symbol.upper() for symbol in symbols if symbol))
    if not selected:
        return None
    store = MarketStore(settings.market_database)
    store.initialize()
    universe = {symbol for symbol, _exchange in store.list_instruments()}
    unknown = [symbol for symbol in selected if symbol not in universe]
    if unknown:
        raise ValueError('Không tìm thấy mã trong danh mục doanh nghiệp: ' + ', '.join(unknown))
    started = datetime.now(VIETNAM)
    archive = ResponseArchive(settings.runs_directory /
                              ('report-financials-' + started.strftime('%Y%m%dT%H%M%S%f')) /
                              'raw')
    collector_lock = ProcessLock(settings.root/'var/cafef-collector.lock')
    if not collector_lock.acquire():
        missing = [symbol for symbol in selected if store.financial_numeric_fact_count_for(symbol)==0]
        if missing:
            raise ValueError('Đang tải lại BCTC toàn thị trường; chưa có dữ liệu cho '
                + ', '.join(missing) + '. Vui lòng tạo báo cáo sau khi lượt tải mã này hoàn tất.')
        # Use committed source data while the full refresh is running; never start
        # another collector and exceed CafeF's shared request budget.
        return None
    try:
        client = CafeFClient(transport=ArchivedCafeFTransport(
            archive, requests_per_second=1))
        result = sync_financial_history(client, store, max_quarters=max_quarters,
                                        symbols=selected, incremental=True)
    finally:
        collector_lock.release()
    missing = [symbol for symbol in selected if store.financial_numeric_fact_count_for(symbol) == 0]
    if missing:
        detail = ', '.join(missing)
        raise ValueError(
            f'Không tải được BCTC quý cho {detail} từ CafeF. '
            'Mã có thể chưa công bố BCTC hoặc nguồn đang tạm gián đoạn; vui lòng thử lại sau.')
    return result
