"""Reproducible native-text extraction of audited FPT annual statement rows.

The page/code/column selectors below are document-specific evidence, NOT report
numbers. Ambiguous rows, missing units and failed identities abort the review.
"""
from datetime import datetime,UTC
import hashlib,json,re,sys
from pathlib import Path
import pymupdf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from stock_reports.analysis.annuals import AnnualReview

SPECS={
    2021:{'current_assets':(72,'100',54),'assets':(72,'270',663),'liabilities':(73,'300',56),
        'current_liabilities':(73,'310',57),'short_debt':(73,'320',56),'long_debt':(73,'338',57),
        'equity':(73,'400',661),'minority':(73,'429',662),'revenue':(74,'10',47),
        'gross_profit':(74,'20',47),'net_profit':(74,'60',47),'parent_profit':(74,'61',47),'cfo':(74,'20',664)},
    2023:{'current_assets':(143,'100',480),'assets':(145,'270',480),'liabilities':(146,'300',480),
        'current_liabilities':(146,'310',480),'short_debt':(146,'320',480),'long_debt':(146,'338',480),
        'equity':(147,'400',480),'minority':(147,'429',480),'revenue':(148,'10',480),
        'gross_profit':(148,'20',480),'net_profit':(149,'60',480),'parent_profit':(149,'61',480),'cfo':(150,'20',480)},
    2025:{'current_assets':(166,'100',279),'assets':(167,'270',279),'liabilities':(168,'300',279),
        'current_liabilities':(168,'310',280),'short_debt':(168,'320',280),'long_debt':(168,'338',280),
        'equity':(169,'400',279),'minority':(169,'429',280),'revenue':(170,'10',280),
        'gross_profit':(170,'20',280),'net_profit':(171,'60',280),'parent_profit':(171,'61',280),'cfo':(172,'20',279)}}


def row_numbers(page,code,x):
    words=page.get_text('words')
    anchors=[w for w in words if w[4]==code and abs(w[0]-x)<4]
    if len(anchors)!=1:raise ValueError(f'Ambiguous code {code} at {x}: {len(anchors)}')
    anchor=anchors[0];right=page.rect.width/2 if page.rect.width>1100 and x<100 else page.rect.width
    nums=sorted([w for w in words if anchor[0]<w[0]<right and abs(w[1]-anchor[1])<3
        and re.fullmatch(r'\(?\d{1,3}(?:\.\d{3}){2,}\)?',w[4])],key=lambda w:w[0])
    if len(nums)!=2:raise ValueError(f'Expected two annual columns code={code}; got {nums}')
    return [int(w[4].strip('()').replace('.',''))*(-1 if w[4].startswith('(') else 1) for w in nums]


def main():
    facts={};sources=[]
    for report_year,specs in SPECS.items():
        path=ROOT/f'var/issuer_disclosures/FPT/FPT_{report_year}_BCTN.pdf'
        side=path.with_suffix('.source.json')
        source=json.loads(side.read_text(encoding='utf-8')) if side.exists() else dict(source='FPT công bố gốc',
            url='https://fpt.com/api/media/20260408_fpt_bao_cao_thuong_nien_web_47ba292667.pdf',retrieved_at=datetime.now(UTC).isoformat())
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        with pymupdf.open(path) as pdf:
            extracted={}
            for key,(page,code,x) in specs.items():
                if not re.search(r'VN[ĐD]',pdf[page-1].get_text()):raise ValueError('VND unit missing')
                values=row_numbers(pdf[page-1],code,x);extracted[key]=values
                ref=dict(source_name='FPT BCTN kiểm toán',url=source['url'],retrieved_at=source['retrieved_at'],
                    locator=f'PDF trang {page}, mã {code}; SHA-256 {digest}; đơn vị VNĐ')
                if key=='minority':continue
                for j,year in enumerate((report_year,report_year-1)):
                    if year<2021:continue
                    facts[(year,key)]=dict(period=str(year),key=key,value_vnd=values[j],source=ref,reason='Trích đúng mã dòng và cột năm của BCTC hợp nhất kiểm toán, lớp văn bản gốc.')
            for j,year in enumerate((report_year,report_year-1)):
                if year<2021:continue
                a,l,e=(extracted[k][j] for k in ('assets','liabilities','equity'))
                if abs(a-l-e)>a*.005:raise ValueError('Audited balance identity failed')
                parent=extracted['equity'][j]-extracted['minority'][j]
                facts[(year,'parent_equity')]=dict(period=str(year),key='parent_equity',value_vnd=parent,
                    source=facts[(year,'equity')]['source'],reason='† Vốn mẹ = tổng vốn công bố (400) − lợi ích cổ đông không kiểm soát (429); không suy tổng vốn từ tài sản và nợ.')
        sources.append(ref)
    review=dict(symbol='FPT',years=list(range(2021,2026)),scope='consolidated',currency='VND',money_multiplier=1,
        sources=sources,notes_reviewed=False,review_note='Đối chiếu mã dòng và đơn vị VNĐ từ BCTN kiểm toán 2021, 2023, 2025. Năm 2022/2024 dùng cột so sánh cùng cơ sở; không xác nhận đã rà toàn bộ thuyết minh.',
        verified_facts=list(facts.values()),opening_balances=[])
    AnnualReview.model_validate(review)
    folder=ROOT/'var/annual_reviews';folder.mkdir(exist_ok=True)
    (folder/'FPT.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Verified annual facts:',len(facts))


if __name__=='__main__':main()
