"""One report-generation service shared by CLI and web, reusing the existing publisher."""

from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal

from stock_reports.analysis.financials import load_review, parse_period
from stock_reports.analysis.repository import ResearchRepository, VIETNAM
from stock_reports.analysis.research import build_document
from stock_reports.analysis.valuation import load_scenarios
from stock_reports.core.locking import ProcessLock
from stock_reports.pipeline.publication import ReportPublisher
from stock_reports.reports.models import ReportKind
from stock_reports.reports.render import ResearchPdfRenderer
from stock_reports.storage.reports import ReportCatalog


class GenerationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind: Literal['stock','industry','macro','all']
    symbol: str | None = Field(default=None,pattern=r'^[A-Z0-9]{2,12}$')
    industry_id: str | None = Field(default=None,pattern=r'^[a-z0-9][a-z0-9-]{0,79}$')
    as_of: date = Field(default_factory=lambda: datetime.now(VIETNAM).date())
    period: str | None = Field(default=None,pattern=r'^\d{4}Q[1-4]$')
    peers: tuple[str, ...] = Field(default=(),max_length=5)

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
        if isinstance(value,dict):return {k:clean(v) for k,v in value.items() if k not in ('generated_at','retrieved_at')}
        if isinstance(value,list):return [clean(v) for v in value]
        return value
    payload=dict(document=clean(document.model_dump(mode='json')),report_format='research-a4-1.1')
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
        document=build_document(settings,kind=kind,as_of=request.as_of,symbol=request.symbol if kind==ReportKind.STOCK else None,
            industry_id=industry_id,period=parse_period(request.period) if request.period else None,peers=request.peers,
            review=review if kind==ReportKind.STOCK else None,scenarios=scenarios if kind==ReportKind.STOCK else None,repository=repo)
        fingerprint=document_fingerprint(document)
        cached=None
        for path in output.glob('*.json'):
            try:
                payload=json.loads(path.read_text(encoding='utf-8'))
                if payload.get('fingerprint')!=fingerprint:continue
                existing=catalog.get(path.stem)
                if existing and payload.get('report_sha256')==existing.sha256 and catalog.pdf_path(existing.id).is_file():
                    cached=existing;break
            except (ValueError,KeyError,FileNotFoundError):
                continue
        if cached:
            results.append(dict(report=cached.model_dump(mode='json'),reused=True))
            continue
        record=publisher.publish(document)
        tickers={document.symbol} if document.symbol else set()
        for part in document.sections:
            for block in part.blocks:
                if block.headers and block.headers[0]=='Mã':tickers.update(row[0] for row in block.rows)
        financial_inputs=[r for r in repo.financial_inputs() if r['symbol'] in tickers]
        from pypdf import PdfReader
        payload=dict(fingerprint=fingerprint,report_sha256=record.sha256,page_count=len(PdfReader(catalog.pdf_path(record.id)).pages),
            request=request.model_dump(mode='json'),document=document.model_dump(mode='json'),
            inputs=dict(financial_facts=financial_inputs,macro=repo.macro(),industry_snapshots=repo.snapshots(),
                prices={ticker:repo.bars(ticker) for ticker in sorted(tickers)},
                review=review.model_dump(mode='json') if review and kind==ReportKind.STOCK else None,
                scenarios=scenarios.model_dump(mode='json') if scenarios and kind==ReportKind.STOCK else None))
        temporary=output/f'{record.id}.json.tmp'
        temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(output/f'{record.id}.json')
        results.append(dict(report=record.model_dump(mode='json'),reused=False,page_count=payload['page_count']))
    return results
