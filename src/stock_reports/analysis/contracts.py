from enum import StrEnum
import math
from typing import Protocol

from pydantic import Field, model_validator

from stock_reports.domain.market import OHLCVBar
from stock_reports.domain.research import CompanyProfile, FinancialMetric, IndustryProfile, NewsArticle, Observation, ResearchModel, SourceReference


class SectionKind(StrEnum):
    MACRO = 'macro'
    INDUSTRY = 'industry'
    COMPANY = 'company'
    TECHNICAL = 'technical'
    FINANCIAL = 'financial'
    VALUATION = 'valuation'
    RECOMMENDATION = 'recommendation'
    RISKS = 'risks'


class Finding(ResearchModel):
    text: str = Field(min_length=1)
    is_assumption: bool = False
    sources: tuple[SourceReference, ...] = ()

    @model_validator(mode='after')
    def require_evidence(self):
        if not self.is_assumption and not self.sources:
            raise ValueError('A factual finding requires source evidence')
        return self


class ReportBlock(ResearchModel):
    kind: str = Field(pattern='^(table|chart)$')
    title: str
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    labels: tuple[str, ...] = ()
    values: tuple[float | None, ...] = ()
    note: str = ''
    sources: tuple[SourceReference, ...] = ()

    @model_validator(mode='after')
    def check_shape(self):
        if self.kind == 'table' and any(len(r) != len(self.headers) for r in self.rows):
            raise ValueError('Table columns must match headers')
        if self.kind == 'chart' and len(self.labels) != len(self.values):
            raise ValueError('Chart labels must match values')
        if any(v is not None and not math.isfinite(v) for v in self.values):
            raise ValueError('Chart values must be finite or missing')
        return self


class AnalysisSection(ResearchModel):
    kind: SectionKind
    title: str
    findings: tuple[Finding, ...] = Field(min_length=1)
    blocks: tuple[ReportBlock, ...] = ()


class AnalysisInputs(ResearchModel):
    company: CompanyProfile | None = None
    industry: IndustryProfile | None = None
    market: tuple[OHLCVBar, ...] = ()
    financials: tuple[FinancialMetric, ...] = ()
    news: tuple[NewsArticle, ...] = ()
    macro: tuple[Observation, ...] = ()
    industry_observations: tuple[Observation, ...] = ()


class AnalysisEngine(Protocol):
    """An engine calculates findings; report writers consume these verified outputs."""

    def analyze(self, inputs: AnalysisInputs) -> AnalysisSection: ...
