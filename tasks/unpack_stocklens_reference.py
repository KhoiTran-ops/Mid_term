"""Extract reference fonts/static pages as data; never execute bundled scripts."""
import argparse
import base64
import gzip
import json
from pathlib import Path
import re
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]


def island(text,name):
    return json.loads(re.search(r'<script type="__bundler/'+name+r'">(.*?)</script>',text,re.S)[1])


def unpack(path):
    root=path.read_text(encoding='utf-8');manifest=island(root,'manifest');order=island(root,'page_order')
    assets=ROOT/'src/stock_reports/reports/stocklens/assets/fonts';assets.mkdir(parents=True,exist_ok=True)
    qa=ROOT/'tmp/stocklens';qa.mkdir(parents=True,exist_ok=True)
    font_css=[]
    for i,key in enumerate(order):
        item=manifest[key];raw=base64.b64decode(item['data']);child=(gzip.decompress(raw) if item.get('compressed') else raw).decode()
        nested=island(child,'manifest');template=island(child,'template');soup=BeautifulSoup(template,'html.parser')
        for tag in soup(['script']):tag.decompose()
        for tag in soup(['x-dc','helmet']):tag.unwrap()
        for style in soup.find_all('style'):
            # Keep only embedded font faces; never fetch network fonts at render.
            css=style.get_text();faces=re.findall(r'@font-face\s*\{[^}]+\}',css)
            for face in faces:
                match=re.search(r'url\("([a-f0-9-]{36})"\)',face)
                if not match:continue
                asset=nested[match[1]]
                if asset['mime']!='font/woff2':raise ValueError('Unexpected font MIME')
                content=base64.b64decode(asset['data']);content=gzip.decompress(content) if asset.get('compressed') else content
                (assets/(match[1]+'.woff2')).write_bytes(content)
                if i==0:font_css.append(face.replace(match[1],'fonts/'+match[1]+'.woff2'))
                css=css.replace(match[1],'data:font/woff2;base64,'+base64.b64encode(content).decode())
            css=re.sub(r'@font-face\s*\{[^}]*https?[^}]*\}','',css)
            style.string=css
        text=str(soup).replace('{{accent}}','#1F5EFF')
        (qa/f'reference-{i+1:02}.html').write_text(text,encoding='utf-8')
    (assets.parent/'fonts.css').write_text('\n'.join(dict.fromkeys(font_css)),encoding='utf-8')
    print(json.dumps(dict(pages=len(order),fonts=len(list(assets.glob('*.woff2'))),reference=str(qa))))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('reference',type=Path);unpack(parser.parse_args().reference)
