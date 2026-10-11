"""Render exported PDFs, preserve full page PNGs and create labeled QA sheets."""
from pathlib import Path
import fitz
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
for ticker in ('FPT','HPG','VCB','ACB','ACG','SSI'):
    pdf=ROOT/'output/pdf'/f'{ticker}-stocklens-2026-10-11.pdf'
    folder=ROOT/'tmp/pdfs'/f'stocklens-final-{ticker}';folder.mkdir(parents=True,exist_ok=True)
    document=fitz.open(pdf)
    assert len(document)==10
    sheet=Image.new('RGB',(1280,1455),'#dce2e8');draw=ImageDraw.Draw(sheet)
    for i,page in enumerate(document):
        pix=page.get_pixmap(matrix=fitz.Matrix(1.333,1.333),alpha=False)
        path=folder/f'page-{i+1:02}.png';pix.save(path)
        im=Image.open(path);im.thumbnail((308,435))
        x=(i%4)*320+6;y=(i//4)*485+28
        sheet.paste(im,(x,y));draw.text((x,y-18),f'{ticker} | {i+1}/10',fill='#0B1F33')
        text=page.get_text()
        assert 'mua/bán' in text
    sheet.save(folder/'contact-sheet.png')
    print(f'{ticker}: 10 pages rendered and footer checked')
