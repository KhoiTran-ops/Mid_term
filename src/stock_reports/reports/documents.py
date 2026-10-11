from pathlib import Path
from datetime import datetime, UTC
from typing import Protocol

from pydantic import AwareDatetime, Field, model_validator

from stock_reports.analysis.contracts import AnalysisSection, ReportBlock, SectionKind
from stock_reports.reports.models import ReportKind, ReportMetadata


class ReportDocument(ReportMetadata):
    sections: tuple[AnalysisSection, ...] = Field(min_length=1)
    generated_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    financial_period: str | None = None
    assessment: str = 'Chưa đủ cơ sở khuyến nghị'
    data_quality: tuple[str, ...] = ()
    editorial_markdown: str | None = None
    editorial_source_name: str | None = None
    editorial_source_sha256: str | None = None
    template_version: str | None = None
    template_sha256: str | None = None
    cover_blocks: tuple[ReportBlock, ...] = ()
    stocklens_data: dict | None = None
    macro_stocklens_data: dict | None = None
    industry_stocklens_data: dict | None = None

    @model_validator(mode='after')
    def require_sections(self):
        if self.stocklens_data is not None and self.kind!=ReportKind.STOCK:
            raise ValueError('StockLens input requires a stock report')
        if self.macro_stocklens_data is not None and self.kind!=ReportKind.MACRO:
            raise ValueError('Macro StockLens input requires a macro report')
        if self.industry_stocklens_data is not None and self.kind!=ReportKind.INDUSTRY:
            raise ValueError('Industry StockLens input requires an industry report')
        if self.editorial_markdown and (self.kind != ReportKind.MACRO or not self.editorial_source_sha256):
            raise ValueError('Editorial Markdown requires a sourced macro report')
        present = {section.kind for section in self.sections}
        required = {
            ReportKind.STOCK: {SectionKind.MACRO, SectionKind.INDUSTRY, SectionKind.COMPANY,
                SectionKind.TECHNICAL, SectionKind.FINANCIAL, SectionKind.VALUATION,
                SectionKind.RECOMMENDATION, SectionKind.RISKS},
            ReportKind.INDUSTRY: {SectionKind.INDUSTRY, SectionKind.RISKS},
            ReportKind.MACRO: {SectionKind.MACRO, SectionKind.RISKS},
        }[self.kind]
        if not required <= present:
            raise ValueError('Missing report sections: ' + ', '.join(sorted(required - present)))
        return self


class PdfRenderer(Protocol):
    def render(self, document: ReportDocument, destination: Path) -> Path: ...
