"""Persist the analyst's visually checked issuer disclosures, with immutable PDF hashes.

Numbers here are transcription evidence, never requested acceptance constants.
Income quarter conversion is explicit; half-year cash flow remains YTD.
"""
from datetime import datetime,UTC
from decimal import Decimal
import hashlib,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from stock_reports.core.config import Settings
from stock_reports.analysis.financials import load_financials,FinancialReview,ALIASES
from stock_reports.analysis.annuals import load_annual_review,annual_value
from stock_reports.analysis.repository import ResearchRepository


def main():
    settings=Settings.from_root(ROOT);repo=ResearchRepository(settings,datetime(2026,10,11).date())
    raw=load_financials(settings.market_database,'FPT');facts=[]
    def ref(file,page,label):
        path=ROOT/'var/issuer_disclosures/FPT'/file
        if file=='FPT_2026H1_reviewed.pdf':url='https://fpt.com/api/media/20260821_FPT_BCTC_hop_nhat_ban_nien_da_soat_xet_nam_2026_3b1ebb3536.pdf'
        else:url=json.loads(path.with_suffix('.source.json').read_text(encoding='utf-8'))['url']
        return dict(source_name='FPT công bố gốc',url=url,retrieved_at=datetime.now(UTC).isoformat(),
            locator=f'PDF trang {page}; {label}; VND; SHA-256 {hashlib.sha256(path.read_bytes()).hexdigest()}')
    h1={
        'assets':(73563105859500,9,'mã 280'), 'liabilities':(32567425051243,10,'mã 300'),
        'equity':(40995680808257,11,'mã 400; gồm cổ đông không kiểm soát'),
        'parent_equity':(39851463524930,11,'† mã 400 trừ mã 429 (1.144.217.283.327); không suy tổng vốn từ tài sản − nợ'),
        'current_assets':(45603129033273,8,'mã 100'),'current_liabilities':(29194331060043,10,'mã 310'),
        'short_debt':(16368916886521,10,'mã 321'),'long_debt':(2080610610531,10,'mã 339'),
        'cfo':(-1145666005788,13,'mã 20; lũy kế 6 tháng, không phải quý 2 riêng')}
    for key,(value,page,label) in h1.items():facts.append(dict(period='2026Q2',key=key,value_vnd=value,source=ref('FPT_2026H1_reviewed.pdf',page,label),reason='Đã đọc trực quan trang gốc và đối chiếu OCR; ưu tiên bản soát xét bán niên. '+label))
    for key,value in [('assets',68586094785217),('equity',40122036570361),('liabilities',28464058214856)]:
        facts.append(dict(period='2026Q1',key=key,value_vnd=value,source=ref('FPT_2026Q1.pdf',4 if key=='assets' else 5 if key=='liabilities' else 6,'mã 280 tổng tài sản' if key=='assets' else 'Bảng tình hình tài chính'),reason='Đối chiếu trực quan công bố quý 1, đúng dòng tổng; không dùng dòng tài sản dài hạn khác của CafeF.'))
    # Revised H1 minus published Q1, NOT raw Q2 plus revised H1.
    for key,total in [('revenue',26268500667974),('gross_profit',8524634170902),('net_profit',5047128933102),('parent_profit',5054958601533)]:
        q1=raw.value(key,(2026,1))
        if q1 is None:raise ValueError('Missing published Q1 comparator')
        facts.append(dict(period='2026Q2',key=key,value_vnd=str(Decimal(total)-q1),source=ref('FPT_2026H1_reviewed.pdf',12,'† H1/2026 soát xét − Q1/2026 công bố'),reason='† Quý 2 riêng = H1/2026 soát xét − Q1/2026 cùng cơ sở hợp nhất; thay giá trị quý 2 chưa soát xét.'))
    annual=load_annual_review(settings,'FPT')
    for key in ('assets','liabilities','equity','parent_equity','current_assets','current_liabilities','short_debt','long_debt','cfo'):
        value,match=annual_value(repo.annual('FPT'),key,2025,annual)
        if value is not None and match:
            facts.append(dict(period='2025Q4',key=key,value_vnd=str(value),source=match[0]['verified_source'],
                reason='Số dư cuối năm hoặc cash flow lũy kế năm kiểm toán 2025 thay bản quý 4 chưa kiểm toán; không dùng số năm làm thu nhập quý.'))
    facts.append(dict(period='2025Q2',key='cfo',value_vnd=1683573278329,
        source=ref('FPT_2026H1_reviewed.pdf',13,'mã 20, cột so sánh H1/2025; YTD'),
        reason='Đọc trực quan cột so sánh H1/2025 công bố trên BCTC soát xét 2026; giữ số lũy kế, không trừ các bản sửa đổi khác cơ sở.'))
    facts.append(dict(period='2025Q1',key='cfo',value_vnd=-2506903722401,
        source=ref('FPT_2026Q1.pdf',9,'mã 20, cột so sánh Q1/2025; YTD'),
        reason='Đối chiếu trực quan cột so sánh quý 1/2025 của BCTC quý 1/2026; quý 1 bằng YTD.'))
    for key in ('revenue','gross_profit','net_profit','parent_profit'):
        total,match=annual_value(repo.annual('FPT'),key,2025,annual)
        q=[raw.value(key,(2025,n)) for n in (1,2,3)]
        if total is None or any(v is None for v in q):raise ValueError('Missing annual/Q1-Q3 reconciliation')
        facts.append(dict(period='2025Q4',key=key,value_vnd=str(total-sum(q)),source=match[0]['verified_source'],reason='† Quý 4 riêng = năm 2025 kiểm toán − Q1 − Q2 − Q3 theo công bố; không giữ quý 4 chưa kiểm toán khi cả năm đã điều chỉnh.'))
    share_source=ref('FPT_2026_share_update.pdf',2,'1.885.727.648 cổ phần; thời điểm thay đổi vốn 30/09/2026')
    review=dict(symbol='FPT',periods=[f'{y}Q{q}' for y,q in raw.periods],scope='consolidated',currency='VND',money_multiplier=1,
        income_basis='quarter',cash_flow_basis='ytd',cash_flow_quarters_comparable=False,
        source=ref('FPT_2026H1_reviewed.pdf',12,'BCTC hợp nhất bán niên soát xét'),
        verification_sources=[share_source,ref('FPT_2026Q1.pdf',7,'Báo cáo kết quả kinh doanh quý riêng')],
        review_note='Đơn vị VND. CafeF thu nhập quý riêng, lưu chuyển tiền tệ lũy kế. Q2/2026 soát xét trừ Q1 công bố; Q4/2025 năm kiểm toán trừ ba quý công bố. Không tự trừ dòng tiền khác bản sửa đổi; không xác nhận đã rà toàn bộ thuyết minh.',
        verified_facts=facts,shares_outstanding=1885727648,parent_equity_vnd=39851463524930,
        period_disclosures={'2026Q2':'Từ 01/01/2026 FPT Telecom chuyển từ hợp nhất toàn bộ sang phương pháp vốn chủ sở hữu. Không tính YoY doanh thu/LNST hợp nhất thô; sử dụng LNST mẹ. H1 soát xét: doanh thu 26.268,5; LNST mẹ 5.055,0; OCF −1.145,7 tỷ VND.'})
    FinancialReview.model_validate(review)
    folder=ROOT/'var/financial_reviews';folder.mkdir(exist_ok=True)
    (folder/'FPT.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Verified quarterly facts:',len(facts))


if __name__=='__main__':main()
