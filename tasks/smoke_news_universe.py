"""Read-only localhost smoke test and render QA for current report versions."""
import json
from pathlib import Path
import sys
import urllib.request
import pymupdf as fitz
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright, Error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from stock_reports.core.config import Settings
from stock_reports.storage.reports import ReportCatalog


def get(path):
    with urllib.request.urlopen('http://127.0.0.1:8000' + path, timeout=20) as response:
        return json.load(response)


def main():
    settings = Settings.from_root(ROOT)
    catalog = ReportCatalog(settings.reports_database, settings.reports_directory)
    statuses = dict(health=get('/api/health'), financial=get('/api/data-status'), reports=get('/api/report-refresh-status'))
    sources = get('/api/news/sources')['items']
    statuses['new_rss'] = [{k: s[k] for k in ('id', 'status', 'error', 'fetched_count')} for s in sources if s['id'].startswith(('cafef-', 'vneconomy-'))]
    latest = {}
    for ticker in ('AAA', 'FPT', 'HPG', 'VCB', 'ACB', 'ACG', 'SSI'):
        records = get('/api/reports?kind=stock&symbol=' + ticker + '&page_size=1')['items']
        if not records: continue
        record = records[0]; latest[ticker] = record['id']
        document = fitz.open(catalog.pdf_path(record['id']))
        assert len(document) == 10
        folder = ROOT / 'tmp/pdfs' / ('news-universe-' + ticker); folder.mkdir(parents=True, exist_ok=True)
        sheet = Image.new('RGB', (1280, 1455), '#dce2e8'); draw = ImageDraw.Draw(sheet)
        for i, page in enumerate(document):
            pix = page.get_pixmap(matrix=fitz.Matrix(1.333, 1.333), alpha=False)
            path = folder / f'page-{i+1:02}.png'; pix.save(path)
            im = Image.open(path); im.thumbnail((308,435)); x=(i%4)*320+6; y=(i//4)*485+28
            sheet.paste(im,(x,y));draw.text((x,y-18),f'{ticker} | {i+1}/10',fill='#0B1F33')
            assert 'mua/bán' in page.get_text()
        sheet.save(folder/'contact-sheet.png')
        print(f'{ticker}: 10 pages, footer checked, rendered', flush=True)
    with sync_playwright() as pw:
        try:browser=pw.chromium.launch(headless=True)
        except Error:browser=pw.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport=dict(width=1440,height=1000)); errors=[]
        page.on('pageerror',lambda error: errors.append(type(error).__name__))
        page.goto('http://127.0.0.1:8000/news?category=chungkhoan',wait_until='domcontentloaded')
        assert page.locator('#news-results').count()==1
        page.screenshot(path=str(ROOT/'tmp/pdfs/news-web.png'),full_page=True)
        page.goto('http://127.0.0.1:8000/reports/'+latest['FPT'],wait_until='domcontentloaded')
        page.wait_for_function("() => !document.querySelector('.company-news-status').textContent.includes('Đang tải')")
        assert page.locator('.company-news-items article').count()>0
        page.screenshot(path=str(ROOT/'tmp/pdfs/company-live-news-web.png'),full_page=True)
        assert not errors, errors
        browser.close()
    statuses['latest_reports']=latest
    (ROOT/'outputs/NEWS_UNIVERSE_SMOKE.json').write_text(json.dumps(statuses,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(statuses,ensure_ascii=False))


if __name__=='__main__':main()
