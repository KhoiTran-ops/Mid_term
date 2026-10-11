"""Dated, user-provided macro snapshots: preserve content and label provenance."""
from datetime import datetime, UTC
from hashlib import sha256
from html import escape
from pathlib import Path
import re

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import BaseDocTemplate,Frame,PageTemplate,PageBreak,Paragraph,Spacer,Table,TableStyle

from stock_reports.analysis.contracts import AnalysisSection,Finding,ReportBlock,SectionKind
from stock_reports.domain.research import SourceReference
from stock_reports.reports.documents import ReportDocument

NAVY=colors.HexColor('#083B5C'); TEAL=colors.HexColor('#168E91')
GREEN=colors.HexColor('#25876B'); RED=colors.HexColor('#C54747')
GRAY=colors.HexColor('#586778'); PALE=colors.HexColor('#EFF5F7')
AMBER=colors.HexColor('#936D28')
MARGIN=56.6929


def plain(text):
    return re.sub(r'\*\*([^*]+)\*\*|\*([^*]+)\*',lambda m:m[1] or m[2],text).strip()


def markup(text):
    text=escape(text.replace('–','-').replace('—','-').replace('−','-'))
    text=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',text)
    return re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)',r'<i>\1</i>',text)


def parse_blocks(body):
    """Parse tables and paragraphs, treating Markdown as data, never instructions."""
    blocks=[]; lines=body.splitlines(); i=0
    while i<len(lines):
        line=lines[i].strip()
        if not line:i+=1;continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                row=[v.strip() for v in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?',v) for v in row):rows.append(row)
                i+=1
            if rows and any(len(r)!=len(rows[0]) for r in rows):
                raise ValueError('Reference table has inconsistent columns')
            blocks.append(('table',rows));continue
        blocks.append(('text',line));i+=1
    return blocks


def parse_reference(text):
    title=plain(next(line[2:] for line in text.splitlines() if line.startswith('# ')))
    parts=re.split(r'^## ',text,flags=re.M)
    sections=[]
    for part in parts[1:]:
        name,_,body=part.partition('\n')
        sections.append((name.strip(),parse_blocks(body)))
    if not sections:raise ValueError('Reference requires Markdown sections')
    return title,parse_blocks(parts[0].split('\n',1)[1]),sections


def reference_document(path,as_of):
    text=Path(path).read_text(encoding='utf-8-sig')
    title,_,parts=parse_reference(text)
    stamp=datetime.fromtimestamp(Path(path).stat().st_mtime,UTC)
    sections=[]
    for name,items in parts:
        kind=SectionKind.INDUSTRY if name.startswith('C.') else SectionKind.RISKS if name.startswith(('E.','F.')) else SectionKind.MACRO
        ref=SourceReference(source_name='Bản tổng hợp vĩ mô do người dùng cung cấp',url=None,
            retrieved_at=stamp,locator=f'{Path(path).name}, mục {name}; nguồn thứ hai chưa kiểm chứng độc lập')
        findings=[Finding(text=plain(value),sources=(ref,)) for typ,value in items if typ=='text']
        tables=[ReportBlock(kind='table',title=f'Bảng trong mục {name}',headers=tuple(map(plain,value[0])),
            rows=tuple(tuple(map(plain,r)) for r in value[1:]),sources=(ref,)) for typ,value in items if typ=='table']
        sections.append(AnalysisSection(kind=kind,title=name,findings=tuple(findings or [Finding(
            text='Số liệu theo bảng của tài liệu tổng hợp được cung cấp.',sources=(ref,))]),blocks=tuple(tables)))
    return ReportDocument(kind='macro',title=title,as_of=as_of,
        assessment='Tổng quan dữ liệu, chưa đưa ra khuyến nghị',sections=tuple(sections),
        data_quality=('Bản nội dung cố định theo ngày chốt trong Markdown, không trộn dữ liệu mới tải vào.',
            'Agriseco là nguồn thứ hai được dẫn lại; chưa có PDF/URL gốc để kiểm chứng độc lập.',
            'World Bank là số năm; không so sánh trực tiếp số năm với số 9 tháng.',
            'Giá trị ngành DNSE giữ đơn vị gốc, chưa kiểm chứng đơn vị/phương pháp.'),
        editorial_markdown=text,editorial_source_name=Path(path).name,
        editorial_source_sha256=sha256(text.encode('utf-8')).hexdigest())


def sector_chart(rows,width):
    data=[(plain(row[0]),float(row[2].replace(',','.'))) for row in rows[1:]]
    row_height=18
    height=row_height*len(data)+38; drawing=Drawing(width,height)
    label_width=155; left=label_width; right=width-28
    low=min(0,min(v for _,v in data))-1; high=max(0,max(v for _,v in data))+1
    x=lambda v:left+(v-low)/(high-low)*(right-left)
    zero=x(0)
    drawing.add(Line(zero,22,zero,height-10,strokeColor=GRAY,strokeWidth=.5))
    for i,(label,value) in enumerate(data):
        y=height-25-i*row_height
        drawing.add(String(0,y, label,fontName='ResearchRegular',fontSize=8.6,fillColor=NAVY))
        drawing.add(Rect(min(zero,x(value)),y-2,abs(x(value)-zero),10,
            fillColor=GREEN if value>=0 else RED,strokeColor=None))
        drawing.add(String(x(value)+(5 if value>=0 else -5),y,
            f'{value:+.2f}'.replace('.',','),textAnchor='start' if value>=0 else 'end',
            fontName='ResearchBold',fontSize=8,fillColor=NAVY))
    drawing.add(String(0,4,'Đơn vị: giá trị gốc DNSE, chưa kiểm chứng; không gắn ký hiệu %.',
        fontName='ResearchRegular',fontSize=8,fillColor=GRAY))
    return drawing


def render_reference(document,destination):
    from stock_reports.reports.render import register_fonts
    register_fonts()
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    title,preamble,sections=parse_reference(document.editorial_markdown)
    width,height=A4; available=width-2*MARGIN
    body=ParagraphStyle('macro-body',fontName='ResearchRegular',fontSize=10.2,leading=14.4,
        textColor=NAVY,spaceAfter=9)
    small=ParagraphStyle('macro-small',parent=body,fontSize=8.4,leading=11.8,textColor=GRAY)
    heading=ParagraphStyle('macro-heading',parent=body,fontName='ResearchBold',fontSize=16,leading=21,
        spaceAfter=14,keepWithNext=True)
    sub=ParagraphStyle('macro-sub',parent=body,fontName='ResearchBold',fontSize=10.6,leading=15,
        spaceBefore=4,spaceAfter=9,keepWithNext=True)
    cell=ParagraphStyle('macro-cell',parent=body,fontSize=8.8,leading=11.8,spaceAfter=0)
    head=ParagraphStyle('macro-head',parent=cell,fontName='ResearchBold',textColor=colors.white)
    def para(value,style=body):return Paragraph(markup(value),style)
    def table(rows,section=''):
        count=len(rows[0]);ratios={2:(.42,.58),3:(.48,.26,.26),4:(.22,.17,.23,.38)}[count]
        if section.startswith('B.'):ratios=(.16,.20,.32,.32)
        if section.startswith('D.'):ratios=(.17,.48,.17,.18)
        data=[];last_group=''
        for i,row in enumerate(rows):
            out=[]
            for j,value in enumerate(row):
                if section.startswith('B.') and i and j==0:
                    if value:last_group=value
                    else:value=last_group
                value=value or 'Chưa đủ dữ liệu'
                style=head if i==0 else cell
                if i and re.fullmatch(r'[+\-]?[\d.,]+(?:%|%/năm| điểm phần trăm|% GDP)?',plain(value)):
                    style=ParagraphStyle(f'number-{i}-{j}',parent=cell,alignment=2)
                out.append(para(value,style))
            data.append(out)
        item=Table(data,colWidths=[available*r for r in ratios],repeatRows=1,hAlign='LEFT')
        item.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),('LINEBELOW',(0,0),(-1,-1),.35,colors.HexColor('#D5E2E8')),
            ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
            ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
        return item
    def add_items(items,name):
        for typ,value in items:
            if typ=='table':
                if name.startswith('B.') and len(value)>13:
                    rows=[list(row) for row in value]
                    last_group=''
                    for row in rows[1:]:
                        if row[0]:last_group=row[0]
                        else:row[0]=last_group
                    story.extend([table(rows[:9],name),PageBreak(),
                        para('B. SỐ LIỆU BỔ SUNG (tiếp)',heading),
                        table([rows[0],*rows[9:]],name),Spacer(1,11)])
                else:story.extend([table(value,name),Spacer(1,11)])
            else:
                is_title=value.startswith('**') and value.endswith('**')
                story.append(para(value,sub if is_title else body))
    def decorate(canvas,doc):
        canvas.saveState();canvas.setFillColor(NAVY);canvas.setFont('ResearchBold',8.5)
        canvas.drawRightString(width-MARGIN,height-35,'VĨ MÔ VIỆT NAM | THỊ TRƯỜNG VỐN')
        canvas.setStrokeColor(TEAL);canvas.setLineWidth(.7);canvas.line(MARGIN,height-44,width-MARGIN,height-44)
        canvas.setStrokeColor(colors.HexColor('#CBD9E1'));canvas.line(MARGIN,42,width-MARGIN,42)
        canvas.setFont('ResearchRegular',8);canvas.setFillColor(GRAY)
        canvas.drawString(MARGIN,28,f'Dữ liệu chốt {document.as_of:%d/%m/%Y} · Thông tin, không phải tư vấn đầu tư')
        canvas.drawRightString(width-MARGIN,28,f'{doc.page:02d}');canvas.restoreState()
    frame=Frame(MARGIN,55,available,height-116,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
    doc=BaseDocTemplate(str(destination),pagesize=A4,title=title,author='Bộ phận nghiên cứu - nhận diện trung tính')
    doc.addPageTemplates([PageTemplate(id='macro',frames=[frame],onPage=decorate)])
    story=[]
    hero=Drawing(available,105)
    hero.add(Rect(0,0,available,105,fillColor=NAVY,strokeColor=None))
    hero.add(Rect(0,0,7,105,fillColor=TEAL,strokeColor=None))
    for i,line in enumerate(('TỔNG QUAN VĨ MÔ VIỆT NAM','VÀ THỊ TRƯỜNG VỐN')):
        hero.add(String(22,70-i*26,line,fontName='ResearchBold',fontSize=19,fillColor=colors.white))
    hero.add(String(22,15,f'THÁNG {document.as_of:%m/%Y} | DỮ LIỆU CHỐT {document.as_of:%d/%m/%Y}',
        fontName='ResearchRegular',fontSize=9,fillColor=colors.white))
    story.extend([hero,Spacer(1,13)])
    # Highlights lead the dashboard. Every original item and every table is retained.
    for typ,value in preamble:
        if typ=='text':story.append(para(value,small))
    highlights=next(items for name,items in sections if name=='TIÊU ĐIỂM')
    story.append(para('TIÊU ĐIỂM',heading));add_items(highlights,'TIÊU ĐIỂM')
    for typ,value in preamble:
        if typ=='table':story.extend([table(value),Spacer(1,8)])
    story.append(PageBreak())
    for name,items in sections:
        if name=='TIÊU ĐIỂM':continue
        # News and transmission/risks share a continuous spread; gaps/sources share a page.
        if name.startswith(('A.','B.','C.','D.','F.')) and not name.startswith('A.'):
            story.append(PageBreak())
        story.append(para(name,heading))
        if name.startswith('C.'):
            table_item=next(v for typ,v in items if typ=='table')
            # Keep the full 22-row table; use original values again, without any new return calculation.
            before=[];after=[];passed=False
            for item in items:
                if item[0]=='table':passed=True;before.append(item)
                elif passed:after.append(item)
                else:before.append(item)
            add_items(before,name)
            story.append(PageBreak());story.append(para('C. THỊ TRƯỜNG (tiếp)',heading))
            story.append(para('Biểu đồ 1: Chín nhóm tăng, mười ba nhóm giảm trong một tháng',sub))
            story.extend([sector_chart(table_item,available),Spacer(1,10),
                para('Nguồn: DNSE, dẫn lại từ bản tổng hợp người dùng cung cấp. Giá trị gốc; đơn vị và phương pháp chưa kiểm chứng.',small)])
            add_items(after,name)
        else:add_items(items,name)
        if name.startswith('G.'):
            story.append(para('LƯU Ý TRUY NGUỒN',sub))
            story.append(para('Các số liệu và tin tức trong PDF này được dẫn lại từ bản Markdown người dùng cung cấp. '
                'Chưa có PDF/URL gốc của bản tin Agriseco ngày 06/10/2026 hay từng bài tin để kiểm chứng độc lập. '
                'Không thay thế các nguồn này bằng đường dẫn suy đoán.',small))
            story.append(para('Phạm vi bản nội dung: giữ nguyên đánh giá thiếu nến và dữ liệu tháng tại thời điểm bản tổng hợp; '
                'không dùng nhận định này để kết luận kho DNSE hiện tại vẫn thiếu dữ liệu.',small))
    doc.build(story)
    return destination
