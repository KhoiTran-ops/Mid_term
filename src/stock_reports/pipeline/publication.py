"""Compose a supplied PDF renderer and catalog without embedding analysis in the web."""

from pathlib import Path
from tempfile import TemporaryDirectory

from stock_reports.reports.documents import PdfRenderer, ReportDocument
from stock_reports.reports.models import ReportMetadata, StoredReport
from stock_reports.storage.reports import ReportCatalog


class ReportPublisher:
    def __init__(self, renderer: PdfRenderer, catalog: ReportCatalog):
        self.renderer = renderer
        self.catalog = catalog

    def publish(self, document: ReportDocument) -> StoredReport:
        with TemporaryDirectory(dir=self.catalog.directory) as temporary:
            destination = Path(temporary) / 'report.pdf'
            rendered = self.renderer.render(document, destination)
            if Path(rendered).resolve() != destination.resolve():
                raise ValueError('The renderer must return the requested destination')
            metadata = ReportMetadata.model_validate(document.model_dump(exclude={'sections'}))
            return self.catalog.register(metadata, destination)
