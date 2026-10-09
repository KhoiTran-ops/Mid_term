from datetime import date
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class ReportKind(StrEnum):
    STOCK = 'stock'
    INDUSTRY = 'industry'
    MACRO = 'macro'


class ReportMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    kind: ReportKind
    title: str = Field(min_length=1, max_length=240)
    as_of: date
    symbol: str | None = Field(default=None, pattern=r'^[A-Z0-9]{2,12}$')
    company_name: str | None = Field(default=None, max_length=240)
    industry_id: str | None = Field(default=None, pattern=r'^[a-z0-9][a-z0-9-]{0,79}$')
    industry_name: str | None = Field(default=None, max_length=160)

    @model_validator(mode='after')
    def check_scope(self):
        if self.kind == ReportKind.STOCK and (not self.symbol or not self.industry_id):
            raise ValueError('Stock reports require symbol and industry_id')
        if self.kind == ReportKind.INDUSTRY and (not self.industry_id or self.symbol):
            raise ValueError('Industry reports require industry_id and no stock symbol')
        if self.kind == ReportKind.MACRO and (self.symbol or self.industry_id):
            raise ValueError('Macro reports have no stock symbol or industry_id')
        return self


class StoredReport(ReportMetadata):
    id: str
    created_at: AwareDatetime
    sha256: str


class ReportPage(BaseModel):
    items: list[StoredReport]
    total: int
    page: int
    page_size: int
