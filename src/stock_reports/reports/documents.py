from pathlib import Path
from typing import Protocol

from pydantic import Field, model_validator

from stock_reports.analysis.contracts import AnalysisSection, SectionKind
from stock_reports.reports.models import ReportKind, ReportMetadata


class ReportDocument(ReportMetadata):
    sections: tuple[AnalysisSection, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def require_sections(self):
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
