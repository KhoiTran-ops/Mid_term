"""Normalized inputs for future research; never assume a source's unit or period basis."""

from decimal import Decimal
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, HttpUrl


class Quality(StrEnum):
    RAW = 'raw'
    VERIFIED = 'verified'
    MISSING = 'missing'


class ResearchModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')


class SourceReference(ResearchModel):
    source_name: str
    url: HttpUrl
    retrieved_at: AwareDatetime
    published_at: AwareDatetime | None = None


class Observation(ResearchModel):
    metric: str
    value: Decimal | str | None
    unit: str
    period: str
    quality: Quality
    source: SourceReference


class FinancialMetric(Observation):
    symbol: str
    period_basis: str  # point_in_time, quarter, year_to_date or annual; verified by the source adapter.


class CompanyProfile(ResearchModel):
    symbol: str
    name: str
    exchange: str
    industry_id: str | None
    source: SourceReference


class NewsArticle(ResearchModel):
    title: str
    url: HttpUrl
    published_at: AwareDatetime
    symbols: tuple[str, ...]
    industry_ids: tuple[str, ...]
    source: SourceReference


class IndustryProfile(ResearchModel):
    id: str
    name: str
    classification: str
    symbols: tuple[str, ...]
    source: SourceReference
