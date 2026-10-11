"""One-off neutral redesign. No network calls or external data inputs."""
from pathlib import Path
from html import escape
import re
import pymupdf
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'C:\Users\ADMIN\Downloads\industry-ngan-hang-2026-10-09.pdf')
OUT = ROOT / 'output/pdf'
TMP = ROOT / 'tmp/pdfs/industry-redesign'
OUT.mkdir(parents=True, exist_ok=True)
TMP.mkdir(parents=True, exist_ok=True)
PDF = OUT / 'bao-cao-nganh-ngan-hang-2026-10-09-dan-trang.pdf'
for name, filename in [('Arial','arial.ttf'),('Arial-Bold','arialbd.ttf'),('Arial-Italic','ariali.ttf'),('Arial-BoldItalic','arialbi.ttf')]:
    pdfmetrics.registerFont(TTFont(name, str(Path('C:/Windows/Fonts') / filename)))
pdfmetrics.registerFontFamily('Arial', normal='Arial', bold='Arial-Bold', italic='Arial-Italic', boldItalic='Arial-BoldItalic')
NAVY = HexColor('#1B2F5B')
BLUE = HexColor('#2876AD')
GREEN = HexColor('#25876B')
RED = HexColor('#C54747')
GRAY = HexColor('#596578')
LIGHT = HexColor('#F2F5F8')
AMBER = HexColor('#8A6523')
W, H = A4
M = 56.6929  # 2 cm
CW = W - 2*M
STYLES = {
    'body': ParagraphStyle('body', fontName='Arial', fontSize=10.5, leading=15, textColor=NAVY, spaceAfter=8),
    'small': ParagraphStyle('small', fontName='Arial', fontSize=9, leading=12, textColor=GRAY),
    'title': ParagraphStyle('title', fontName='Arial-Bold', fontSize=18, leading=23, textColor=NAVY),
    'sub': ParagraphStyle('sub', fontName='Arial-Bold', fontSize=12, leading=16, textColor=NAVY),
    'cell': ParagraphStyle('cell', fontName='Arial', fontSize=10, leading=13, textColor=NAVY),
    'head': ParagraphStyle('head', fontName='Arial-Bold', fontSize=10, leading=13, textColor=white),
    'quote': ParagraphStyle('quote', fontName='Arial-Italic', fontSize=11, leading=17, textColor=NAVY),
}
doc = pymupdf.open(SOURCE)
urls = []
for link in doc[-1].get_links():
    url = link.get('uri')
    if url and url not in urls:
        urls.append(url)
assert len(urls) == 13
crop_specs = [(2,(62,595,558,744)), (3,(62,97,558,246)), (3,(62,309,558,458)), (3,(62,521,558,670))]
for i,(page,clip) in enumerate(crop_specs,1):
    doc[page].get_pixmap(matrix=pymupdf.Matrix(4,4), clip=pymupdf.Rect(clip), alpha=False).save(TMP/f'macro-{i}.png')

c = canvas.Canvas(str(PDF), pagesize=A4)
c.setTitle('Báo cáo ngành ngân hàng - Dữ liệu chốt 09/10/2026')
c.setAuthor('Bộ phận nghiên cứu - nhận diện trung tính')
audit = []
page = 0

def para(text, top, style='body', x=M, width=CW):
    p = Paragraph(text, STYLES[style])
    _, h = p.wrap(width, H)
    p.drawOn(c,x,H-top-h)
    audit.append((page,round(top,1),round(top+h,1),re.sub('<[^>]+>','',text)[:65]))
    if top+h > H-M:
        raise ValueError(f'Content overflow page {page}: {top+h:.1f}: {text[:70]}')
    return top+h

def table(rows, widths, top, numeric=(), pad=8):
    data = [[Paragraph(str(v), STYLES['head' if r == 0 else 'cell']) for v in row] for r,row in enumerate(rows)]
    t = Table(data,colWidths=widths,hAlign='LEFT')
    cmds=[('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
          ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
          ('TOPPADDING',(0,0),(-1,-1),pad),('BOTTOMPADDING',(0,0),(-1,-1),pad),
          ('LINEBELOW',(0,-1),(-1,-1),0.4,HexColor('#D7DEE8'))]
    for r in range(1,len(rows)):
        cmds.append(('BACKGROUND',(0,r),(-1,r),white if r%2 else LIGHT))
    # Paragraph alignment, rather than cell alignment, determines numeric placement.
    for col in numeric:
        for r in range(1,len(rows)):
            s=ParagraphStyle(f'num{r}-{col}',parent=STYLES['cell'],alignment=2)
            data[r][col]=Paragraph(str(rows[r][col]),s)
    t = Table(data,colWidths=widths,hAlign='LEFT')
    t.setStyle(TableStyle(cmds))
    _,h=t.wrap(CW,H)
    t.drawOn(c,M,H-top-h)
    audit.append((page,round(top,1),round(top+h,1),'TABLE'))
    if top+h>H-M: raise ValueError(f'Table overflow page {page}: {top+h}')
    return top+h

def box(title, text, top, color=BLUE, style='body'):
    p=Paragraph(text,STYLES[style]); _,ph=p.wrap(CW-28,H)
    h=ph+46
    c.setFillColor(LIGHT); c.roundRect(M,H-top-h,CW,h,5,fill=1,stroke=0)
    c.setFillColor(color); c.rect(M,H-top-h,3,h,fill=1,stroke=0)
    para(title,top+12,'sub',M+14,CW-28)
    para(text,top+34,style,M+14,CW-28)
    return top+h

def start(title=None):
    global page
    if page: c.showPage()
    page+=1
    c.setFillColor(NAVY); c.setFont('Arial-Bold',9)
    c.drawRightString(W-M,H-36,'BÁO CÁO NGÀNH NGÂN HÀNG')
    c.setStrokeColor(NAVY); c.setLineWidth(.5); c.line(M,H-44,W-M,H-44)
    c.setStrokeColor(HexColor('#CDD5E0')); c.line(M,M-8,W-M,M-8)
    c.setFont('Arial',8.5); c.setFillColor(GRAY)
    c.drawString(M,M-24,'Dữ liệu chốt 09/10/2026')
    c.drawRightString(W-M,M-24,f'{page:02d}')
    return para(title,65,'title')+16 if title else 65

def macro(i,title,top,unit,ref):
    top=para(f'Biểu đồ {i}: {title}',top,'sub')+7
    image_h=CW*149/496
    c.drawImage(str(TMP/f'macro-{i}.png'),M,H-top-image_h,width=CW,height=image_h)
    top+=image_h+5
    return para(f'Nguồn: World Bank WDI, tổng hợp từ đồ thị gốc [{ref}]. Đơn vị: {unit}.',top,'small')+12

# 1. Neutral cover with original geometric bands, no borrowed photography or logo.
start()
c.setFillColor(NAVY); c.rect(M,H-300,CW,230,fill=1,stroke=0)
c.setFillColor(BLUE); c.rect(M,H-300,12,230,fill=1,stroke=0)
c.setFillColor(GREEN); c.rect(M+12,H-300,7,230,fill=1,stroke=0)
cover=ParagraphStyle('cover',parent=STYLES['title'],fontSize=28,leading=36,textColor=white)
p=Paragraph('BÁO CÁO NGÀNH<br/>NGÂN HÀNG',cover);_,hh=p.wrap(CW-65,H);p.drawOn(c,M+34,H-108-hh)
c.setFont('Arial',11);c.setFillColor(white);c.drawString(M+34,H-224,'Tháng 10/2026 · Dữ liệu chốt 09/10/2026')
top=para('Biến động 1 năm âm;<br/>dữ liệu doanh nghiệp còn thiếu',325,'title')+19
top=box('BA THÔNG ĐIỆP CHÍNH',
    '“Danh mục ngân hàng của DNSE gồm 28 mã thuộc GICS cấp 2.” [1]<br/><br/>'
    '“Giá trị gốc 1y là -14,25; các kỳ 3y và 5y lần lượt là 51,94 và 60,22.” [2]<br/><br/>'
    '“Nhóm quan sát gồm ACB và VCB; biên lợi nhuận sau thuế chưa đủ dữ liệu.” [3, 4]',top,style='quote')+24
top=para('Chuyên viên phân tích: <b>[điền sau]</b><br/><br/>Người phê duyệt báo cáo: <b>[điền sau]</b>',top)
para('Nhận diện trung tính · Báo cáo thông tin và nghiên cứu',750,'small')

# 2. Highlights, with explicit non-recommendation only.
top=start('TIÊU ĐIỂM')
top=para('BỐI CẢNH VĨ MÔ',top,'sub')+10
top=para('<b>GDP năm 2025 tăng tốc so với năm 2024.</b> Tăng trưởng đạt 8,02%/năm, tăng 0,98 điểm phần trăm. Nội dung gốc gợi ý kiểm tra cầu nội địa và sản lượng ngành, chưa đủ để dự báo tăng trưởng doanh nghiệp năm 2026. [5]',top)+10
top=para('<b>Lạm phát năm 2025 thấp hơn năm 2024.</b> CPI đạt 3,31%/năm, giảm 0,31 điểm phần trăm. Cần kiểm tra khả năng chuyển chi phí vào giá bán và chi phí vốn từng ngành. [6]',top)+10
top=para('<b>Thương mại và FDI được ghi nhận theo tỷ lệ GDP.</b> Năm 2025, thương mại hàng hóa và dịch vụ đạt 190,34% GDP; FDI ròng vào đạt 4,27% GDP. [7, 8]',top)+20
top=para('NGÀNH NGÂN HÀNG',top,'sub')+10
top=para('<b>Danh mục ngành gồm 28 mã theo DNSE.</b> Nhóm ngân hàng thuộc GICS cấp 2, ID 12. Snapshot ngành có thời điểm nguồn 09/10/2026 lúc 08:00:05.098970 UTC. [1, 2]',top)+10
top=para('<b>Biến động kỳ 1y có giá trị gốc -14,25.</b> Các kỳ 3y và 5y có giá trị gốc dương, lần lượt 51,94 và 60,22. Bảng đủ tám kỳ được trình bày ở phần B. [2]',top)+10
top=para('<b>Nhóm doanh nghiệp quan sát gồm ACB và VCB.</b> Báo cáo giữ kỳ 2026Q2 và để thiếu biên lợi nhuận sau thuế. Các câu hỏi về NIM, chất lượng tín dụng và vốn an toàn được trình bày ở phần C. [3, 4]',top)+20
top=box('KHUYẾN NGHỊ ĐẦU TƯ VÀO NGÀNH',
    '<b>Ngắn / trung hạn:</b> <font color="#8A6523">Chưa đủ cơ sở khuyến nghị</font><br/><br/>'
    '<b>Dài hạn:</b> <font color="#8A6523">Chưa đủ cơ sở khuyến nghị</font>',top,AMBER)

# 3. Contents, fixed pagination validated after generation.
top=start('MỤC LỤC')
toc=[('A. TỔNG QUAN VĨ MÔ VÀ CHUỖI TÁC ĐỘNG',4),('    I. Bốn chỉ tiêu World Bank',4),('    II. Tin tức và các giả định truyền dẫn',5),
     ('B. DIỄN BIẾN VÀ PHÂN TÍCH NGÀNH NGÂN HÀNG',6),('    I. Danh mục 28 mã và biến động tám kỳ',6),('    II. Khung chuỗi giá trị',6),
     ('C. NHÓM DOANH NGHIỆP QUAN SÁT',7),('    I. ACB và VCB - kỳ 2026Q2',7),('    II. Các câu hỏi kiểm chứng',7),
     ('D. RỦI RO NGÀNH VÀ DỮ LIỆU CẦN BỔ SUNG',8),('    I. Rủi ro và Lưu ý dữ liệu',8),('    II. Năm nhóm dữ liệu cần bổ sung',8),
     ('E. PHỤ LỤC',9),('    I. Danh mục nguồn [1] - [13]',9),('    II. Phương pháp và miễn trừ trách nhiệm',9)]
for text,num in toc:
    c.setFont('Arial-Bold' if not text.startswith(' ') else 'Arial',10.5)
    c.setFillColor(NAVY);c.drawString(M,H-top-11,text)
    c.drawRightString(W-M,H-top-11,str(num))
    c.setStrokeColor(HexColor('#D9DFE7'));c.setDash(1,3);c.line(M,H-top-22,W-M,H-top-22);c.setDash()
    top+=33
top+=10
top=box('PHẠM VI ĐỌC BÁO CÁO',
    '<b>Số liệu, tin tức và nguồn được giữ từ bản đính kèm.</b> Các số trong ngoặc vuông dẫn tới danh mục nguồn ở trang 9. Khung “Lưu ý dữ liệu” ở trang 8 tập hợp các giới hạn chất lượng của bản gốc.',top)+16
para('<b>Khung phân tích không phải dự báo.</b> Các giả định truyền dẫn và câu hỏi kiểm chứng được tách khỏi phần quan sát số liệu; ô thiếu tiếp tục ghi “Chưa đủ dữ liệu”.',top)

# 4. First two macro charts.
top=start('A. Tổng quan vĩ mô và chuỗi tác động')
top=para('I. Bốn chỉ tiêu World Bank',top,'sub')+10
top=table([['Chỉ tiêu (2025)','Giá trị','Đơn vị','So với 2024'],
    ['GDP thực [5]','8,02','%/năm','+0,98 đpt'],['CPI [6]','3,31','%/năm','-0,31 đpt'],
    ['Thương mại [7]','190,34','% GDP','+16,45 đpt'],['FDI ròng vào [8]','4,27','% GDP','+0,04 đpt']],
    [190,75,88,CW-353],top,(1,3))+13
top=para('<b>GDP tăng tốc, CPI giảm so với năm 2024.</b> Diễn giải trong bản gốc gợi ý kiểm tra cầu nội địa, sản lượng, khả năng chuyển chi phí và chi phí vốn từng ngành. [5, 6]',top)+15
top=macro(1,'GDP thực năm 2025 tăng trưởng 8,02%/năm',top,'%/năm',5)
top=macro(2,'CPI năm 2025 đạt 3,31%/năm, thấp hơn 2024',top,'%/năm',6)

# 5. Remaining macro charts and original news items.
top=start('A. Vĩ mô và chuỗi tác động (tiếp)')
top=macro(3,'Thương mại năm 2025 đạt 190,34% GDP',top,'% GDP',7)
top=macro(4,'FDI ròng vào năm 2025 đạt 4,27% GDP',top,'% GDP',8)
top=para('II. Tin tức gần nhất',top,'sub')+8
news=[['Nguồn','Tiêu đề','Ngày đăng (UTC)','Liên quan ngành'],
 ['VnExpress [9]','Phó thủ tướng yêu cầu không để giá hàng hóa tăng bất hợp lý.','09/10/2026<br/>13:25:10','Chưa rõ'],
 ['VnEconomy [10]','Tăng tín dụng lãi suất ưu đãi cho doanh nghiệp nhỏ và vừa.','Chưa đủ dữ liệu','Chưa rõ'],
 ['CNBC [11]',"Nobel winner Krugman says France may have become 'too big to save'.",'09/10/2026<br/>11:33:48','Chưa rõ'],
 ['The Guardian [12]','Firmus pulls biggest ASX float since Telstra amid investor doubt about datacentre company.','09/10/2026<br/>04:37:55','Chưa rõ'],
 ['VietNamNet [13]','Bất chấp sóng gió thị trường, vàng vẫn được tin lấy lại mốc 160 triệu/lượng.','09/10/2026<br/>02:50:09','Chưa rõ']]
top=table(news,[78,220,97,CW-395],top,pad=5)+8
para('Nguồn: các bài [9] - [13], tổng hợp. Giữ tiêu đề gốc; mức liên quan để “Chưa rõ” do chưa có đánh giá trong đầu vào.',top,'small')

# 6. Sector chart and conceptual value chain.
top=start('B. Diễn biến và phân tích ngành ngân hàng')
top=para('I. Danh mục 28 mã và biến động tám kỳ',top,'sub')+10
top=para('<b>DNSE ghi nhận 28 mã ngân hàng trong danh mục GICS cấp 2.</b> Snapshot thống kê ngành mang thời điểm 09/10/2026 lúc 08:00:05.098970 UTC. [1, 2]',top)+13
top=para('Biểu đồ 5: Kỳ 1y âm, trong khi các kỳ 3y và 5y dương',top,'sub')+12
values=[.31,-.69,-3.50,-6.61,-2.67,-14.25,51.94,60.22]
periods=['1d','7d','1m','3m','6m','1y','3y','5y']
left=M+33; chart_top=top; chart_h=205; plot_w=CW-43
def yy(v): return H-chart_top-chart_h+(v+20)/90*chart_h
for tick in [-20,0,20,40,60]:
    c.setStrokeColor(HexColor('#DCE2E9'));c.setLineWidth(.5);c.line(left,yy(tick),left+plot_w,yy(tick))
    c.setFillColor(GRAY);c.setFont('Arial',8.5);c.drawRightString(left-7,yy(tick)-3,str(tick))
for j,(period,value) in enumerate(zip(periods,values)):
    x=left+(j+.5)*plot_w/8;zero=yy(0);end=yy(value)
    c.setFillColor(GREEN if value>=0 else RED);c.rect(x-14,min(zero,end),28,max(abs(end-zero),.6),fill=1,stroke=0)
    c.setFont('Arial-Bold',9);c.drawCentredString(x,end+(5 if value>=0 else -13),f'{value:.2f}'.replace('.',','))
    c.setFillColor(NAVY);c.setFont('Arial',9);c.drawCentredString(x,H-chart_top-chart_h-16,period)
top+=chart_h+27
top=para('Nguồn: DNSE thống kê ngành, tổng hợp [2]. Đơn vị: giá trị gốc do nguồn cung cấp.',top,'small')+20
top=para('II. Khung chuỗi giá trị',top,'sub')+12
top=table([['1. Nguồn vốn','2. Sử dụng vốn','3. Thu nhập','4. Kết quả'],
 ['Tiền gửi và vốn','Tín dụng / đầu tư','Thu nhập lãi, dịch vụ','Dự phòng và lợi nhuận']], [CW/4]*4,top)+18
top=box('GIẢ ĐỊNH TRUYỀN DẪN TRONG BẢN GỐC',
    '<b>Nếu lãi suất huy động tăng nhanh hơn lợi suất tài sản, biên lãi có thể thu hẹp.</b><br/><br/>'
    '<b>Nếu tăng trưởng kinh tế chậm lại, cầu tín dụng và khả năng trả nợ có thể suy yếu.</b>',top)+13
para('<b>Câu hỏi xuyên suốt:</b> Tăng tín dụng có đi cùng chất lượng tài sản và nguồn vốn ổn định?',top)

# 7. Company observation, no invented missing values.
top=start('C. Nhóm doanh nghiệp quan sát')
top=para('I. ACB và VCB - kỳ 2026Q2',top,'sub')+10
top=para('<b>Nhóm quan sát gồm hai ngân hàng ACB và VCB.</b> Bảng dưới giữ mô hình, kỳ và ô thiếu như bản gốc. [3, 4]',top)+15
top=table([['Mã','Mô hình','Kỳ','Biên LNST (%)'],['ACB [3]','Ngân hàng','2026Q2','Chưa đủ dữ liệu'],['VCB [4]','Ngân hàng','2026Q2','Chưa đủ dữ liệu']],
    [80,113,95,CW-288],top,(3,))+18
top=para('II. Các câu hỏi kiểm chứng',top,'sub')+14
top=box('1. BIÊN LÃI - NIM',
    '<b>Cần tài sản sinh lãi bình quân và thu nhập lãi đã chuẩn hóa 12 tháng.</b> Đây là câu hỏi kiểm chứng trong bản gốc; báo cáo không tự tính NIM khi thiếu các đầu vào này.',top)+17
top=box('2. CHẤT LƯỢNG TÍN DỤNG VÀ VỐN',
    '<b>Nợ xấu, nợ nhóm 2, dự phòng / bao phủ và CAR cần thuyết minh cùng định nghĩa quản lý.</b> Các chỉ tiêu cần được kiểm chứng trước khi dùng để so sánh doanh nghiệp.',top)+17
top=box('3. TĂNG TRƯỞNG VÀ NGUỒN VỐN',
    '<b>Tăng tín dụng có đi cùng chất lượng tài sản và nguồn vốn ổn định?</b> Giữ nguyên câu hỏi của bản gốc; không bổ sung kết luận cho ACB hoặc VCB khi chưa có dữ liệu.',top)+20
para('<b>Đối chiếu từng doanh nghiệp.</b> Biên lợi nhuận phụ thuộc mô hình và định nghĩa doanh thu. Phần giới hạn so sánh được tập hợp trong “Lưu ý dữ liệu” ở trang 8. [3, 4]',top)

# 8. Consolidated warnings and five explicitly requested missing inputs.
top=start('D. Rủi ro ngành và dữ liệu cần bổ sung')
top=para('I. Rủi ro và Lưu ý dữ liệu',top,'sub')+10
top=para('<b>Khung rủi ro gốc gồm chất lượng tín dụng, chênh lệch kỳ hạn, thanh khoản và vốn an toàn.</b> Đây là các nội dung cần kiểm chứng, không phải đánh giá tác động định lượng.',top)+12
warnings=(
 '<b>1. Đơn vị và phương pháp:</b> Biến động DNSE chưa kiểm chứng; giữ giá trị gốc, không ghép chuỗi OHLCV hoặc thay lợi suất chuẩn hóa, không dùng trực tiếp làm chỉ số định giá. [2]<br/><br/>'
 '<b>2. Mẫu so sánh:</b> Dưới 3 doanh nghiệp cùng kỳ đủ đầu vào; chưa đạt mẫu 3-5 để kết luận vị thế tương đối. Hai ngân hàng không đại diện toàn ngành; không lấy trung bình chéo mô hình hoặc biên lợi nhuận làm chuẩn ngành. [1, 3, 4]<br/><br/>'
 '<b>3. Phạm vi và đơn vị BCTC:</b> ACB và VCB chưa kiểm chứng scope/đơn vị. Biên LNST tiếp tục thiếu. [3, 4]<br/><br/>'
 '<b>4. Tần suất vĩ mô:</b> Các số World Bank là quan sát năm, không phải số tháng/quý hiện tại; không suy ra quyết định lãi suất hiện tại từ CPI năm. [5-8]<br/><br/>'
 '<b>5. Phân ngành:</b> Danh mục hiện tại, chưa có lịch sử thay đổi phân ngành. [1]<br/><br/>'
 '<b>6. Độ trễ và điều chỉnh:</b> Dữ liệu có thể trễ và được nguồn sửa. Ngày chốt lọc kỳ/thời điểm nguồn; không phải bộ backtest không có look-ahead.<br/><br/>'
 '<b>7. Tin tức:</b> Chưa xác minh quan hệ nhân quả hoặc tác động định lượng tới lợi nhuận; cần đọc tại nguồn để đánh giá. [9-13]<br/><br/>'
 '<b>8. Chuỗi hiện tại:</b> Chưa có lãi suất, tỷ giá và tín dụng tháng đã kiểm chứng; không sinh dự báo các biến này.')
top=box('LƯU Ý DỮ LIỆU',warnings,top,AMBER)+14
top=para('II. Năm nhóm dữ liệu cần bổ sung',top,'sub')+9
top=para('<b>Danh sách đầu vào cần bổ sung, không phải khuyến nghị:</b> (1) NIM và đầu vào tính NIM; (2) nợ xấu, nhóm 2 và bao phủ dự phòng; (3) CAR; (4) P/B ngành với đơn vị/phương pháp kiểm chứng; (5) thêm doanh nghiệp so sánh cùng kỳ, cùng định nghĩa, đạt mẫu 3-5.',top)

# 9. Source appendix. Original source URLs are retained as active links.
top=start('E. Phụ lục')
top=para('I. Danh mục nguồn',top,'sub')+9
descriptions=[
 ('DNSE GICS cấp 2','20:16','ID 12, Ngân hàng'),
 ('DNSE thống kê ngành','20:07','MQTT stats/sector/volatility, sector 12'),
 ('CafeF - ACB','21:03','IncSta 2026Q2, dòng 13: XIII. Lợi nhuận sau thuế'),
 ('CafeF - VCB','20:07','IncSta 2026Q2, dòng 13: XIII. Lợi nhuận sau thuế'),
 ('World Bank WDI','20:16','NY.GDP.MKTP.KD.ZG, Việt Nam, 2024; 2025'),
 ('World Bank WDI','20:16','FP.CPI.TOTL.ZG, Việt Nam, 2024; 2025'),
 ('World Bank WDI','20:16','NE.TRD.GNFS.ZS, Việt Nam, 2024; 2025'),
 ('World Bank WDI','20:16','BX.KLT.DINV.WD.GD.ZS, Việt Nam, 2024; 2025'),
 ('VnExpress · Kinh doanh','20:39',''),('VnEconomy · Kinh tế','20:16',''),
 ('CNBC · World economy','20:16',''),('The Guardian · Technology','20:16',''),('VietNamNet · Kinh doanh','20:16','')]
for i,((name,time,locator),url) in enumerate(zip(descriptions,urls),1):
    text=f'<b>[{i}] {name}.</b> Thu thập: 09/10/2026 {time}. '
    if locator: text+=escape(locator)+'. '
    text+=f'<link href="{escape(url,quote=True)}" color="#2876AD">Mở nguồn</link>'
    top=para(text,top,'cell')+7
top=para('Định vị còn lại của các chuỗi World Bank: xem JSON snapshot theo ghi chú bản gốc.',top,'small')+16
top=para('II. Phương pháp và miễn trừ trách nhiệm',top,'sub')+9
top=para('<b>Phiên bản phương pháp trong bản gốc: financials-1.0.</b> Bản gốc nêu công thức ở bảng chỉ tiêu / phần định giá và JSON snapshot cùng ID báo cáo để truy từng dòng, kỳ, nguồn; tài liệu đính kèm không cung cấp các công thức hay tệp JSON này. Bản dàn trang không tái tạo chúng. Thiếu dữ liệu được giữ thiếu, không thay bằng 0.',top)+12
box('MIỄN TRỪ TRÁCH NHIỆM',
    'Báo cáo phục vụ mục đích thông tin và nghiên cứu, không phải lời chào mua/bán hay cam kết lợi nhuận. Nhà đầu tư tự chịu trách nhiệm cho quyết định của mình.',top)
c.save()

# Reopen for objective structure checks and render every page for visual QA.
result=pymupdf.open(PDF)
assert len(result)==9
alltext='\n'.join(p.get_text() for p in result)
assert 'FPTS' not in alltext and 'FPT Securities' not in alltext
assert all(f'[{i}]' in alltext for i in range(1,14))
assert 'Chưa đủ cơ sở khuyến nghị' in alltext
assert not any(x in alltext for x in ['KHẢ QUAN','TRUNG LẬP','KÉM KHẢ QUAN'])
assert {l['uri'] for p in result for l in p.get_links() if l.get('uri')} == set(urls)
for p in result:
    p.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5),alpha=False).save(TMP/f'final-{p.number+1:02d}.png')
print(PDF)
print(f'PASS: {len(result)} pages; 13 source links; no brand / prohibited recommendation; layout bounds checked.')
for p in range(1,10):
    bottoms=[r[2] for r in audit if r[0]==p]
    print(f'Page {p}: bottom of body {max(bottoms):.1f} / {H-M:.1f} pt')
