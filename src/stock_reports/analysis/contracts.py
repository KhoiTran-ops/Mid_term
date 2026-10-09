from enum import StrEnum
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


class AnalysisSection(ResearchModel):
    kind: SectionKind
    title: str
    findings: tuple[Finding, ...] = Field(min_length=1)


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
