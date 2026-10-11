"""Render primary filing pages for manual visual verification (no OCR import)."""
import json
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT/'var/issuer_disclosures/HPG/manifest.json').read_text(encoding='utf-8'))
    requests = {
        'Báo cáo tài chính hợp nhất năm 2021 sau kiểm toán': range(1, 12),
        'Báo cáo tài chính hợp nhất năm 2022': range(4, 12),
        'Báo cáo tài chính hợp nhất năm 2023 sau kiểm toán': range(4, 12),
        'Báo cáo tài chính hợp nhất năm 2024': range(4, 12),
        'BCTC hợp nhất năm 2025 sau kiểm toán': range(1, 12),
        'Báo cáo tài chính hợp nhất soát xét 6 tháng 2026': range(1, 13),
        'Báo cáo thường niên năm 2025': (8, 11, 12, 28, 30, 38, 41, 43, 44, 58, 59, 60),
    }
    for r in manifest:
        pages = requests.get(r['title'])
        if pages is None and ('2024' in r['title'] or '2025' in r['title']) and 30<=r['pages']<=37:
            pages = (2, 3, 4, 5, 6, 7)
        if pages is None:
            continue
        folder = ROOT/'tmp/pdfs/hpg-primary'/Path(r['path']).stem[:20]
        folder.mkdir(parents=True, exist_ok=True)
        with pymupdf.open(r['path']) as pdf:
            for page in pages:
                pdf[page-1].get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(folder/f'page-{page}.png')
        print(r['title'], folder.name)


if __name__ == '__main__':
    main()
