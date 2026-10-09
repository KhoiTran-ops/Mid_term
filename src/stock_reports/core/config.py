"""Load configuration only at startup; resolve paths from the project root."""

from dataclasses import dataclass, field
import os
from pathlib import Path

from dotenv import dotenv_values


@dataclass(frozen=True)
class Settings:
    root: Path
    market_database: Path
    reports_database: Path
    reports_directory: Path
    outputs_directory: Path
    runs_directory: Path
    dnse_api_key: str | None = field(default=None, repr=False)
    dnse_api_secret: str | None = field(default=None, repr=False)

    @classmethod
    def from_root(cls, root: Path) -> 'Settings':
        root = Path(root).resolve()
        values = {**dotenv_values(root / '.env'), **os.environ}

        def path(key: str, default: str) -> Path:
            return (root / (values.get(key) or default)).resolve()

        return cls(root=root, market_database=path('DATABASE_PATH', 'var/market_data.db'),
            reports_database=path('REPORTS_DATABASE_PATH', 'var/reports.db'),
            reports_directory=path('REPORTS_DIRECTORY', 'outputs/reports'),
            outputs_directory=root / 'outputs', runs_directory=root / 'var/runs',
            dnse_api_key=values.get('DNSE_API_KEY'), dnse_api_secret=values.get('DNSE_API_SECRET'))

    @property
    def dnse_configured(self) -> bool:
        return bool(self.dnse_api_key and self.dnse_api_secret)
