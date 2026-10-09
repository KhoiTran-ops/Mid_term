"""Archive successful provider responses without logging authentication data."""

from datetime import datetime, UTC
import hashlib
import json
from pathlib import Path

from data.cafef.client import RateLimitedTransport
from data.dnse_market import DNSEGateway


class ResponseArchive:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def save(self, provider: str, request: str, payload: bytes, suffix: str):
        folder = self.root / provider
        folder.mkdir(exist_ok=True)
        name = hashlib.sha256(request.encode()).hexdigest()[:24] + suffix
        path = folder / name
        path.write_bytes(payload)
        receipt = dict(provider=provider, request=request,
                       fetched_at=datetime.now(UTC).isoformat(),
                       path=str(path), sha256=hashlib.sha256(payload).hexdigest())
        with (self.root / 'receipts.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(receipt, ensure_ascii=False) + '\n')


class ArchivedCafeFTransport(RateLimitedTransport):
    def __init__(self, archive: ResponseArchive, **kwargs):
        super().__init__(**kwargs)
        self.archive = archive

    def get(self, url: str) -> bytes:
        raw = super().get(url)
        self.archive.save('cafef', url, raw,
                          '.html' if 'BaoCaoTaiChinh' in url else '.json')
        return raw


class ArchivedDNSEGateway(DNSEGateway):
    def __init__(self, key: str, secret: str, archive: ResponseArchive, **kwargs):
        super().__init__(key, secret, **kwargs)
        self.archive = archive

    def _get(self, path: str, params: dict[str, object]) -> dict[str, object]:
        payload = super()._get(path, params)
        self.archive.save('dnse', path + '?' + json.dumps(params, sort_keys=True),
                          json.dumps(payload, ensure_ascii=False).encode('utf-8'), '.json')
        return payload
