"""Archive HPG consolidated filings with immutable URL/content identifiers."""
from datetime import datetime, UTC
from hashlib import sha256
import json
from pathlib import Path
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import requests
import pymupdf

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / 'var/issuer_disclosures/HPG'
    folder.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    entries = {}
    for page in range(1, 10):
        url = 'https://www.hoaphat.com.vn/quan-he-co-dong/bao-cao-tai-chinh'
        response = session.get(url, params={'page': page}, timeout=40)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        for anchor in soup.select('a[href]'):
            title = anchor.get_text(' ', strip=True)
            href = urljoin(url, anchor['href'])
            if urlparse(href).hostname != 'file.hoaphat.com.vn' or '.pdf' not in href.lower():
                continue
            if not ('hợp nhất' in title.casefold() and any(str(y) in title for y in range(2021, 2027))):
                continue
            entries[href] = title
        time.sleep(1)
    url = 'https://www.hoaphat.com.vn/quan-he-co-dong/bao-cao-thuong-nien'
    response = session.get(url, timeout=40)
    response.raise_for_status()
    for anchor in BeautifulSoup(response.text, 'html.parser').select('a[href]'):
        title = anchor.get_text(' ', strip=True)
        href = urljoin(url, anchor['href'])
        if urlparse(href).hostname == 'file.hoaphat.com.vn' and '.pdf' in href.lower() and any(str(y) in title for y in range(2021, 2026)):
            entries[href] = title
    manifest = []
    for url, title in entries.items():
        key = sha256(url.encode()).hexdigest()[:20]
        candidates = list(folder.glob(key + '-*.pdf'))
        if candidates:
            path = candidates[0]
        else:
            response = session.get(url, timeout=90)
            response.raise_for_status()
            payload = response.content
            if not payload.startswith(b'%PDF'):
                raise ValueError('Not a PDF: ' + title)
            path = folder / (key + '-' + sha256(payload).hexdigest()[:16] + '.pdf')
            path.write_bytes(payload)
            time.sleep(1)
        with pymupdf.open(path) as pdf:
            # Extraction is an audit aid, not automatically verified financial input.
            text_path = path.with_suffix('.txt')
            text_path.write_text('\n'.join(f'\n=== PAGE {i+1} ===\n' + p.get_text() for i, p in enumerate(pdf)), encoding='utf-8')
            pages = len(pdf)
        manifest.append(dict(title=title, url=url, path=str(path), sha256=sha256(path.read_bytes()).hexdigest(),
                             pages=pages, retrieved_at=datetime.now(UTC).isoformat(), independently_reviewed=False))
        print(title, pages, path.name, flush=True)
    (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Archived', len(manifest), 'filings')


if __name__ == '__main__':
    main()
