"""Ports to implement when selecting company, news, macro and industry sources."""

from datetime import datetime
from typing import Protocol

from stock_reports.domain.research import CompanyProfile, FinancialMetric, IndustryProfile, NewsArticle, Observation


class CompanySource(Protocol):
    def get_company(self, symbol: str) -> CompanyProfile: ...


class NewsSource(Protocol):
    def get_news(self, *, symbol: str | None, industry_id: str | None,
                 since: datetime, until: datetime) -> list[NewsArticle]: ...


class MacroSource(Protocol):
    def get_observations(self, *, since: datetime, until: datetime) -> list[Observation]: ...


class IndustrySource(Protocol):
    def get_industries(self) -> list[IndustryProfile]: ...


class FinancialMetricsSource(Protocol):
    def get_metrics(self, symbol: str, *, quarters: int = 8) -> list[FinancialMetric]: ...
