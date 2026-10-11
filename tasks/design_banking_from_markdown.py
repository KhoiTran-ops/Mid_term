"""Render only the user-supplied Markdown; no data fetching or recalculation."""
from pathlib import Path
import re
from html import escape
import pymupdf
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('C:/Users/ADMIN/Downloads/Báo cáo ngành Ngân hàng – 10 2026.md')
TEXT=SOURCE.read_text(encoding='utf-8-sig')
OUT=ROOT/'output/pdf'
TMP=ROOT/'tmp/pdfs/banking-markdown'
OUT.mkdir(parents=True,exist_ok=True)
TMP.mkdir(parents=True,exist_ok=True)
PDF=OUT/'bao-cao-nganh-ngan-hang-10-2026-ban-markdown.pdf'
NAVY=HexColor('#1B2F5B'); BLUE=HexColor('#2876AD'); GREEN=HexColor('#25876B')
RED=HexColor('#C54747'); GRAY=HexColor('#596578'); LIGHT=HexColor('#F2F5F8'); AMBER=HexColor('#8A6523')
W,H=A4; M=56.6929; CW=W-2*M
for name,file in [('Arial','arial.ttf'),('Arial-Bold','arialbd.ttf'),('Arial-Italic','ariali.ttf'),('Arial-BoldItalic','arialbi.ttf')]:
    pdfmetrics.registerFont(TTFont(name,str(Path('C:/Windows/Fonts')/file)))
pdfmetrics.registerFontFamily('Arial',normal='Arial',bold='Arial-Bold',italic='Arial-Italic',boldItalic='Arial-BoldItalic')
styles={
 'body':ParagraphStyle('body',fontName='Arial',fontSize=10.5,leading=15,textColor=NAVY),
 'small':ParagraphStyle('small',fontName='Arial',fontSize=9,leading=12,textColor=GRAY),
 'title':ParagraphStyle('title',fontName='Arial-Bold',fontSize=18,leading=23,textColor=NAVY),
 'sub':ParagraphStyle('sub',fontName='Arial-Bold',fontSize=12,leading=16,textColor=NAVY),
 'cell':ParagraphStyle('cell',fontName='Arial',fontSize=10,leading=13,textColor=NAVY),
 'head':ParagraphStyle('head',fontName='Arial-Bold',fontSize=10,leading=13,textColor=white),
 'quote':ParagraphStyle('quote',fontName='Arial-Italic',fontSize=11,leading=17,textColor=NAVY),
}
def markup(s):
    s=escape(s.strip().replace('–','-').replace('−','-').replace('—','-'))
    return re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',s)

tables=[]; current=[]
for line in TEXT.splitlines()+['']:
    if line.startswith('|'):
        row=[x.strip() for x in line.strip('|').split('|')]
        if not all(re.fullmatch(r':?-+:?',x) for x in row): current.append(row)
    elif current:
        tables.append(current);current=[]
assert len(tables)==8
sections={}
for part in TEXT.split('\n## ')[1:]:
    name,_,body=part.partition('\n')
    sections[name.split('.')[0].strip()]=body
highlights=[line[2:] for line in sections['TIÊU ĐIỂM'].splitlines() if line.startswith('- ')]
notes=sections['C'].split('**Nhận xét:**')[1]
company_notes=[line[2:] for line in notes.splitlines() if line.startswith('- ')]
risks=[]
for line in sections['D'].splitlines():
    if re.match(r'^\d+\. ',line): risks.append(re.sub(r'^\d+\. ','',line))
assert len(highlights)==5 and len(company_notes)==5 and len(risks)==5

c=canvas.Canvas(str(PDF),pagesize=A4)
c.setTitle('Báo cáo ngành ngân hàng - Tháng 10/2026')
c.setAuthor('Bộ phận nghiên cứu - nhận diện trung tính')
page=0; bounds=[]
def p(text,top,style='body',x=M,width=CW):
    obj=Paragraph(text,styles[style]);_,h=obj.wrap(width,H)
    if top+h>H-M: raise ValueError(f'Overflow page {page}: {top+h:.1f} {text[:50]}')
    obj.drawOn(c,x,H-top-h); bounds.append((page,top+h));return top+h
def section(text,top): return p(text,top,'sub')+10
def panel(title,text,top,color=BLUE,style='body'):
    obj=Paragraph(text,styles[style]);_,h=obj.wrap(CW-28,H); h+=46
    c.setFillColor(LIGHT);c.roundRect(M,H-top-h,CW,h,4,fill=1,stroke=0)
    c.setFillColor(color);c.rect(M,H-top-h,3,h,fill=1,stroke=0)
    p(title,top+12,'sub',M+14,CW-28);p(text,top+34,style,M+14,CW-28)
    return top+h
def grid(rows,widths,top,numeric=(),pad=7,highlight=None):
    values=[]
    for i,row in enumerate(rows):
        out=[]
        for j,value in enumerate(row):
            value=value or 'Chưa đủ dữ liệu'
            sty=styles['head' if i==0 else 'cell']
            if i and j in numeric:
                sty=ParagraphStyle(f'right-{page}-{i}-{j}',parent=sty,alignment=2)
            out.append(Paragraph(markup(value),sty))
        values.append(out)
    t=Table(values,colWidths=widths)
    commands=[('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
        ('TOPPADDING',(0,0),(-1,-1),pad),('BOTTOMPADDING',(0,0),(-1,-1),pad)]
    for i in range(1,len(rows)):
        commands.append(('BACKGROUND',(0,i),(-1,i),LIGHT if i%2==0 else white))
        if highlight and highlight in row[0]:
            commands.append(('BACKGROUND',(0,i),(-1,i),HexColor('#E4EDF5')))
    t.setStyle(TableStyle(commands));_,h=t.wrap(CW,H)
    if top+h>H-M:raise ValueError(f'Table overflow page {page}: {top+h:.1f}')
    t.drawOn(c,M,H-top-h);bounds.append((page,top+h));return top+h
def start(title):
    global page
    if page:c.showPage()
    page+=1
    c.setFillColor(NAVY);c.setFont('Arial-Bold',9)
    c.drawRightString(W-M,H-36,'BÁO CÁO NGÀNH NGÂN HÀNG')
    c.setStrokeColor(NAVY);c.setLineWidth(.5);c.line(M,H-44,W-M,H-44)
    c.setStrokeColor(HexColor('#CDD5E0'));c.line(M,M-8,W-M,M-8)
    c.setFont('Arial',8.5);c.setFillColor(GRAY)
    c.drawString(M,M-24,'Dữ liệu chốt 09/10/2026');c.drawRightString(W-M,M-24,f'{page:02d}')
    return p(title,65,'title')+17
def source(text,top):return p('Nguồn: '+text,top,'small')+14

# 1. Cover: original shapes, no borrowed branding or photographs.
start('')
c.setFillColor(NAVY);c.rect(M,H-300,CW,230,fill=1,stroke=0)
c.setFillColor(BLUE);c.rect(M,H-300,12,230,fill=1,stroke=0)
c.setFillColor(GREEN);c.rect(M+12,H-300,7,230,fill=1,stroke=0)
coverstyle=ParagraphStyle('cover',parent=styles['title'],fontSize=28,leading=36,textColor=white)
obj=Paragraph('BÁO CÁO NGÀNH<br/>NGÂN HÀNG',coverstyle);_,h=obj.wrap(CW-65,H);obj.drawOn(c,M+34,H-108-h)
c.setFillColor(white);c.setFont('Arial',11);c.drawString(M+34,H-224,'Tháng 10/2026 · Dữ liệu chốt 09/10/2026')
top=p('Điều chỉnh sau chu kỳ tăng dài hạn;<br/>dữ liệu doanh nghiệp cần kiểm chứng',324,'title')+17
top=panel('BA THÔNG ĐIỆP CHÍNH',
    '“Ngành ngân hàng có giá trị gốc DNSE -14,25 trong 1 năm, nhưng vẫn +51,94 sau 3 năm và +60,22 sau 5 năm.” [1]<br/><br/>'
    '“Quý 2/2026, thu nhập lãi thuần và lợi nhuận sau thuế của ACB, VCB cho thấy diễn biến khác nhau.” [2]<br/><br/>'
    '“Tiền gửi tăng chậm hơn tài sản ở cả hai ngân hàng; đơn vị và cơ sở báo cáo còn cần kiểm chứng.” [2]',top,style='quote')+20
top=p('Chuyên viên phân tích: <b>[điền sau]</b><br/><br/>Người phê duyệt: <b>[điền sau]</b>',top)+20
p('<font color="#8A6523"><b>Chưa đủ cơ sở khuyến nghị</b></font><br/>Chỉ mang tính thông tin, không phải tư vấn đầu tư.',top)

# 2. All five original highlights retained.
top=start('TIÊU ĐIỂM')
for i,text in enumerate(highlights):
    top=p(markup(text),top)+15
top=panel('KHUYẾN NGHỊ ĐẦU TƯ VÀO NGÀNH',
 '<b>Ngắn / trung hạn:</b> <font color="#8A6523">Chưa đủ cơ sở khuyến nghị</font><br/><br/>'
 '<b>Dài hạn:</b> <font color="#8A6523">Chưa đủ cơ sở khuyến nghị</font>',top,AMBER)+18
overview=[['Phạm vi','Thông tin theo bản nội dung']]+tables[0][1:]
overview=[row for row in overview if 'Đánh giá ngành' not in row[0]]
grid(overview,[250,CW-250],top,pad=6)

# 3. Page map and reading rules.
top=start('MỤC LỤC')
toc=[('A. TỔNG QUAN VĨ MÔ',4),('   I. Chỉ tiêu World Bank và giả định truyền dẫn',4),('   II. Tin tức gần nhất',4),
 ('B. DIỄN BIẾN NGÀNH NGÂN HÀNG',5),('   I. Tám kỳ biến động DNSE',5),('   II. So sánh GICS và chuỗi giá trị',5),
 ('C. DOANH NGHIỆP QUAN SÁT: ACB VÀ VCB',6),('   I. Số liệu quý 2/2026 và nhận xét',6),('   II. Chỉ báo tính sơ bộ',7),
 ('D. RỦI RO VÀ DỮ LIỆU CÒN THIẾU',8),('   I. Các rủi ro cần theo dõi',8),('   II. Dữ liệu bổ sung và điều kiện xem xét lại',8),
 ('E. PHỤ LỤC',9),('   I. Lưu ý dữ liệu và câu hỏi kiểm chứng',9),('   II. Nguồn, công thức và miễn trừ trách nhiệm',10)]
for text,num in toc:
    c.setFillColor(NAVY);c.setFont('Arial' if text.startswith(' ') else 'Arial-Bold',10.5)
    c.drawString(M,H-top-11,text);c.drawRightString(W-M,H-top-11,str(num))
    c.setStrokeColor(HexColor('#D9DFE7'));c.setDash(1,3);c.line(M,H-top-23,W-M,H-top-23);c.setDash();top+=32
top+=14
top=panel('CÁCH ĐỌC BẢN DÀN TRANG',
 '<b>Số liệu gốc và chỉ báo tính sơ bộ được tách riêng.</b> Bảng tài chính ở trang 6; các chỉ báo do người soạn tính ở trang 7. Khung “Lưu ý dữ liệu” ở trang 9 tập hợp các giới hạn của đầu vào.',top)+17
p('<b>Không bổ sung dữ liệu bên ngoài.</b> Bản này sử dụng nội dung Markdown được cung cấp; số nguồn [1]-[9] dẫn tới danh mục nhà cung cấp ở trang 10. Ô trống được ghi “Chưa đủ dữ liệu”.',top)

# 4. Macro snapshot and all original news classifications.
top=start('A. Tổng quan vĩ mô')
top=section('I. Chỉ tiêu World Bank năm 2025',top)
top=p('Bảng 1: GDP tăng tốc, CPI thấp hơn năm 2024',top,'sub')+8
top=grid(tables[1],[150,75,111,CW-336],top,numeric=(1,2),pad=6)+6
top=source('World Bank WDI, tổng hợp theo bản nội dung [3]. Đơn vị theo từng chỉ tiêu.',top)
top=panel('CHUỖI TÁC ĐỘNG - KHUNG GIẢ ĐỊNH, KHÔNG PHẢI DỰ BÁO',
 '<b>Nếu lãi suất huy động tăng nhanh hơn lợi suất tài sản, biên lãi có thể thu hẹp.</b><br/><br/>'
 '<b>Nếu tăng trưởng kinh tế chậm lại, cầu tín dụng và khả năng trả nợ có thể suy yếu.</b>',top)+15
top=section('II. Tin tức gần nhất',top)
news=[row[:] for row in tables[2]]
for row in news[1:]:
    if row[2]=='Chưa rõ':row[2]='Chưa đủ dữ liệu'
top=grid(news,[78,225,83,CW-386],top,pad=5)+7
source('VnExpress, VnEconomy, VietNamNet, CNBC, The Guardian [4-8]. Phân loại giữ theo bản nội dung; cần đọc tại nguồn để đánh giá tác động.',top)

# 5. Exact raw sector values; no percent sign added.
top=start('B. Diễn biến ngành ngân hàng')
top=section('I. Tám kỳ biến động theo DNSE',top)
top=p('<b>Danh mục GICS cấp 2 gồm 28 mã ngân hàng.</b> Trong 22 nhóm GICS, ngân hàng đứng thứ 13 về mức biến động 1 tháng và thứ 5 về 1 phiên. [1]',top)+12
top=p('Biểu đồ 1: Kỳ 1 năm âm, các kỳ 3 năm và 5 năm dương',top,'sub')+10
values=[float(s.replace(',','.')) for s in tables[3][1][1:]]
periods=['1d','7d','1m','3m','6m','1y','3y','5y']
chart_h=170; left=M+30; plot_w=CW-40
def yy(v):return H-top-chart_h+(v+20)/90*chart_h
for tick in [-20,0,20,40,60]:
    c.setStrokeColor(HexColor('#DCE2E9'));c.setLineWidth(.5);c.line(left,yy(tick),left+plot_w,yy(tick))
    c.setFillColor(GRAY);c.setFont('Arial',8.5);c.drawRightString(left-7,yy(tick)-3,str(tick))
for j,(label,value) in enumerate(zip(periods,values)):
    x=left+(j+.5)*plot_w/8;zero=yy(0);end=yy(value)
    c.setFillColor(GREEN if value>=0 else RED);c.rect(x-14,min(zero,end),28,max(abs(end-zero),.6),fill=1,stroke=0)
    c.setFont('Arial-Bold',9);c.drawCentredString(x,end+(5 if value>=0 else -13),f'{value:.2f}'.replace('.',','))
    c.setFillColor(NAVY);c.setFont('Arial',9);c.drawCentredString(x,H-top-chart_h-16,label)
top+=chart_h+27
top=source('DNSE, tổng hợp [1]. Đơn vị: giá trị gốc, chưa kiểm chứng.',top)
top=section('II. So sánh GICS và chuỗi giá trị',top)
top=p('Bảng 2: Ngân hàng so với các nhóm GICS khác',top,'sub')+8
top=grid(tables[4],[145,66,66,CW-277],top,numeric=(1,2),pad=5,highlight='Ngân hàng')+7
top=source('DNSE, theo bản nội dung [1]. Đơn vị: giá trị gốc.',top)
panel('KHUNG CHUỖI GIÁ TRỊ',
 '<b>Tiền gửi và vốn → tín dụng / đầu tư → thu nhập lãi và dịch vụ → dự phòng và lợi nhuận.</b>',top)

# 6. Full financial table and original company observations.
top=start('C. Doanh nghiệp quan sát: ACB và VCB')
top=section('I. Số liệu quý 2/2026 và nhận xét',top)
top=p('Bảng 3: Số liệu tài chính và giao dịch của hai ngân hàng',top,'sub')+8
top=grid(tables[5],[291,95,CW-386],top,numeric=(1,2),pad=6)+7
top=source('CafeF (BCTC), DNSE (giá đóng cửa) [1, 2]. Tài chính: tỷ đồng theo bản nội dung; giá chưa xác minh đơn vị. Khối lượng: cổ phiếu, chưa định vị nguồn riêng trong Markdown. Lưu ý đầy đủ tại trang 9.',top)
for text in company_notes[:2]:
    top=panel('ACB - ĐIỂM CẦN KIỂM CHỨNG' if text.startswith('**ACB') else 'VCB - ĐIỂM CẦN KIỂM CHỨNG',markup(text),top)+14

# 7. Every provisional indicator and formula from the Markdown is preserved.
top=start('C. Doanh nghiệp quan sát (tiếp)')
top=section('II. Chỉ báo tính sơ bộ',top)
top=p('<b>Các chỉ báo dưới đây do người soạn tính từ số liệu nguồn, chưa được nguồn xác nhận.</b> Giữ nguyên giá trị và ký hiệu xấp xỉ, không tính lại hoặc bổ sung chỉ tiêu.',top)+12
top=p('Bảng 4: Chỉ báo tăng trưởng, cơ cấu và sinh lời',top,'sub')+8
indicators=[row[:] for row in tables[6]]
for row in indicators[1:7]:
    if not row[1]:row[1]='Xem công thức tăng trưởng (trang 10)'
top=grid(indicators,[201,155,62,CW-418],top,numeric=(2,3),pad=5)+7
top=source('Chỉ báo sơ bộ trong bản nội dung, dựa trên số liệu CafeF [2]. Các tỷ lệ này chưa được nguồn kiểm chứng.',top)
top=p(markup(company_notes[2]),top)+12
p(markup(company_notes[4]),top)

# 8. All original risk factors and gaps, not new recommendations.
top=start('D. Rủi ro và dữ liệu còn thiếu')
top=section('I. Các rủi ro cần theo dõi',top)
for i,text in enumerate(risks):
    top=p(f'<b>{i+1}.</b> '+markup(text),top)+12
top=section('II. Dữ liệu bổ sung và điều kiện xem xét lại',top)
top=p('Bảng 5: Các đầu vào còn thiếu hoặc chưa kiểm chứng',top,'sub')+8
top=grid(tables[7],[280,CW-280],top,pad=6)+17
reassessment=sections['D'].split('**Điều kiện xem xét lại đánh giá ngành:**')[1].strip()
panel('ĐIỀU KIỆN XEM XÉT LẠI ĐÁNH GIÁ NGÀNH',markup(reassessment),top,AMBER)

# 9. Quality caveats consolidated; company news retained exactly from supplied text.
top=start('E. Phụ lục')
top=section('I. Lưu ý dữ liệu và câu hỏi kiểm chứng',top)
warnings=(
 '<b>1. Đơn vị tài chính:</b> Tỷ đồng theo nguồn, giá trị gốc chia 10^9, chưa xác nhận là VND. Hợp nhất/riêng và quý/lũy kế chưa kiểm chứng với BCTC gốc. [2]<br/><br/>'
 '<b>2. Chỉ báo sơ bộ:</b> Các tỷ lệ do người soạn tính, chưa được nguồn xác nhận. Thu nhập lãi thuần quy năm / tài sản bình quân không phải NIM. [2]<br/><br/>'
 '<b>3. Mẫu so sánh:</b> Chỉ có 2/28 mã, không đại diện toàn ngành; không lấy trung bình làm chuẩn. Chưa đủ nhóm 3-5 ngân hàng có đầu vào phù hợp. [1, 2]<br/><br/>'
 '<b>4. DNSE:</b> Biến động ngành giữ giá trị gốc; đơn vị và phương pháp chưa kiểm chứng. Danh mục phân ngành hiện tại, chưa có lịch sử thay đổi. Giá đóng cửa chưa xác minh đơn vị. [1]<br/><br/>'
 '<b>5. Vĩ mô:</b> World Bank là số năm 2025, không phải tháng/quý hiện tại. Chưa có chuỗi lãi suất, tỷ giá, tín dụng tháng đã kiểm chứng; không sinh dự báo từ các biến này. [3]<br/><br/>'
 '<b>6. Độ trễ và tin tức:</b> Dữ liệu có thể được nguồn điều chỉnh; chưa xác minh quan hệ nhân quả hoặc tác động định lượng của tin tức.<br/><br/>'
 '<b>7. Dòng tiền:</b> Ô ACB Q4/2025 có nhãn “trước những thay đổi về tài sản và vốn lưu động”; không coi là dòng tiền hoạt động kinh doanh đầy đủ. [2]')
top=panel('LƯU Ý DỮ LIỆU',warnings,top,AMBER)+17
top=section('1. Câu hỏi kiểm chứng của ngành',top)
for text in ['<b>NIM:</b> Cần tài sản sinh lãi bình quân và thu nhập lãi đã chuẩn hóa 12 tháng.',
 '<b>Chất lượng tài sản:</b> Nợ xấu, nhóm 2, dự phòng / bao phủ và CAR cần thuyết minh cùng định nghĩa quản lý.',
 '<b>Tăng tín dụng có đi cùng chất lượng tài sản và nguồn vốn ổn định không?</b>']:
    top=p(text,top)+9
top=section('2. Tin về ACB',top)
p(markup(company_notes[3]),top)

# 10. Provenance stays limited to source names actually present in the Markdown.
top=start('E. Phụ lục (tiếp)')
top=section('II. Nguồn, công thức và miễn trừ trách nhiệm',top)
top=panel('PHẠM VI NGUỒN CỦA BẢN DÀN TRANG',
 '<b>Nội dung và số liệu được lấy từ bản Markdown do người dùng cung cấp.</b> Danh mục dưới ghi nhà cung cấp được nêu trong tài liệu, không phải xác nhận độc lập. Markdown không kèm URL bài viết, URL dữ liệu hoặc BCTC gốc; bản dàn trang không tự tạo liên kết hay bổ sung số liệu.',top)+17
source_rows=[['Nguồn','Phạm vi theo bản nội dung'],
 ['[1] DNSE','Phân ngành GICS cấp 2, thống kê ngành, giá đóng cửa. Khối lượng có trong bảng nội dung, chưa định vị nguồn riêng.'],
 ['[2] CafeF','BCTC các kỳ; thu thập 09/10/2026. Chỉ báo tính sơ bộ do người soạn tính.'],
 ['[3] World Bank WDI','NY.GDP.MKTP.KD.ZG; FP.CPI.TOTL.ZG; NE.TRD.GNFS.ZS; BX.KLT.DINV.WD.GD.ZS.'],
 ['[4] VnExpress','Tin giá hàng hóa; 09/10/2026.'],['[5] VnEconomy','Tin tín dụng ưu đãi doanh nghiệp nhỏ và vừa; ngày đăng chưa đủ dữ liệu.'],
 ['[6] VietNamNet','Tin vàng 09/10/2026; tin ACB / BVBank bảo hiểm 04/09/2026.'],
 ['[7] CNBC','Tin Krugman / Pháp; 09/10/2026.'],['[8] The Guardian','Tin Firmus / ASX; 09/10/2026.'],
 ['[9] Vietcap','Tin ACB ngày 23/10/2025; nội dung được giữ tại trang 9.']]
top=grid(source_rows,[130,CW-130],top,pad=5)+16
top=section('1. Công thức trong bản nội dung',top)
formulas=sections['E'].split('**Công thức:**')[1].split('\n\n')[0].strip()
top=p(markup(formulas),top)+15
disclaimer=sections['E'].split('*Miễn trừ trách nhiệm:')[1].rstrip().rstrip('*').strip()
panel('2. MIỄN TRỪ TRÁCH NHIỆM',markup(disclaimer),top,AMBER)
c.save()

result=pymupdf.open(PDF)
assert len(result)==10
alltext='\n'.join(p.get_text() for p in result)
assert 'FPTS' not in alltext and not any(s in alltext for s in ['KHẢ QUAN','TRUNG LẬP','KÉM KHẢ QUAN'])
for i in range(1,10):assert f'[{i}]' in alltext
for token in ['1.067.845','2.657.441','7.785','19.142','4.292','14.551','16,8%','18,0%','28.160','500 tỷ','67,0%','59,5%','33,5%','20,15','56,70','11.569.900','3.049.500']:
    assert token in alltext,token
assert 'không phải NIM' in alltext
assert 'Chưa đủ cơ sở khuyến nghị' in alltext
assert all('Dữ liệu chốt 09/10/2026' in p.get_text() for p in result)
for p in result:
    p.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5),alpha=False).save(TMP/f'page-{p.number+1:02d}.png')
print(PDF)
print('PASS: 10 pages, all 7 data tables consumed, all 5 company notes, 9 named sources, key values and warnings retained.')
for i in range(1,11):print(f'Page {i}: body ends {max(b for a,b in bounds if a==i):.1f} / {H-M:.1f} pt')
