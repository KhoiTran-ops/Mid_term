"""Archive issuer-published VCB financial PDFs, not a replacement for review."""
from datetime import datetime, UTC
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urljoin, urlparse

import requests
ROOT=Path(__file__).resolve().parents[1]
BASE='https://www.vietcombank.com.vn'


def main():
    folder=ROOT/'var/issuer_disclosures/VCB';folder.mkdir(parents=True,exist_ok=True)
    session=requests.Session()
    page=session.get(BASE+'/vi-VN/Nha-dau-tu',timeout=30);page.raise_for_status()
    endpoint=urljoin(BASE,html.unescape(re.search(r'data-search-endpoint="([^"]+)"',page.text).group(1)))
    entries=[]
    for offset in (0,100,200,300):
        response=session.get(endpoint,params={'p':100,'e':offset},timeout=30);response.raise_for_status()
        for row in response.json()['Results']:
            title=html.unescape(re.sub('<[^>]+>',' ',row['Html'])).strip()
            folded=title.casefold()
            if not any(str(y) in title or f'.{str(y)[2:]}' in title for y in range(2021,2027)):continue
            if not (('hợp nhất' in folded and ('bctc' in folded or 'báo cáo tài chính' in folded or re.search(r'Q[1-4]\.',title)))
                    or 'tỷ lệ an toàn vốn' in folded or 'trụ cột 3' in folded
                    or 'tài liệu nhà đầu tư' in folded):continue
            if 'tóm tắt' in folded:continue
            match=re.search(r'data-download-url="([^"]+)"',row['Html'])
            if not match:continue
            url=urljoin(BASE,html.unescape(match.group(1)))
            if urlparse(url).hostname!='www.vietcombank.com.vn' or '.pdf' not in url.lower():continue
            key=hashlib.sha256(url.encode()).hexdigest()[:20]
            path=folder/(key+'.pdf')
            if not path.exists():
                time.sleep(1)
                response=session.get(url,timeout=60);response.raise_for_status()
                if not response.content.startswith(b'%PDF'):
                    raise ValueError('Issuer document is not a PDF')
                path.write_bytes(response.content)
            entries.append(dict(title=title,url=url,path=str(path),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                retrieved_at=datetime.now(UTC).isoformat(),independently_reviewed=False))
        time.sleep(1)
    unique={r['url']:r for r in entries}
    target=folder/'manifest.json'
    target.write_text(json.dumps(list(unique.values()),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(downloaded=len(unique),manifest=str(target)),ensure_ascii=False))


if __name__=='__main__':main()
