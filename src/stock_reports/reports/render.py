"""A4 research layout inspired by the supplied SSI example, with embedded Vietnamese fonts."""

from collections import OrderedDict
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing, Line, PolyLine, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, NextPageTemplate, PageTemplate, Paragraph, Spacer, Table, TableStyle


NAVY=colors.HexColor('#11116b')
TEAL=colors.HexColor('#18866f')
GRAY=colors.HexColor('#eeeeef')
INK=colors.HexColor('#203d36')


def register_fonts():
    root=Path(__file__).resolve().parents[1]/'web/static/fonts'
    for suffix in ['Regular','Bold']:
        name='Research'+suffix
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name,str(root/f'NotoSans-{suffix}.ttf')))
    pdfmetrics.registerFontFamily('ResearchRegular',normal='ResearchRegular',bold='ResearchBold',italic='ResearchRegular',boldItalic='ResearchBold')


def line_chart(block,width=480,height=160):
    drawing=Drawing(width,height)
    points=[v for v in block.values if v is not None]
    if not points:
        drawing.add(String(28,75,'Chưa đủ dữ liệu',fontName='ResearchRegular',fontSize=9))
        return drawing
    low,high=min(points),max(points)
    padding=(high-low)*.1 or max(abs(high)*.05,1)
    low-=padding;high+=padding
    left,right,bottom,top=48,width-8,30,height-12
    for i in range(4):
        y=bottom+(top-bottom)*i/3
        drawing.add(Line(left,y,right,y,strokeColor=colors.HexColor('#dfe5e2'),strokeWidth=.4))
        drawing.add(String(left-5,y-3,f'{low+(high-low)*i/3:.1f}',textAnchor='end',fontName='ResearchRegular',fontSize=7,fillColor=INK))
    segments=[];segment=[]
    for i,value in enumerate(block.values):
        if value is None:
            if segment:segments.append(segment)
            segment=[]
        else:
            x=left+(right-left)*i/max(1,len(block.values)-1)
            y=bottom+(top-bottom)*(value-low)/(high-low)
            segment.extend([x,y])
    if segment:segments.append(segment)
    for segment in segments:
        if len(segment)>2:drawing.add(PolyLine(segment,strokeColor=TEAL,strokeWidth=1.6))
        else:drawing.add(Line(segment[0]-2,segment[1],segment[0]+2,segment[1],strokeColor=TEAL))
    tick_count=3 if width<200 else 5
    indices=sorted({round(i*(len(block.labels)-1)/(tick_count-1)) for i in range(tick_count)}) if block.labels else []
    for i in indices:
        x=left+(right-left)*i/max(1,len(block.labels)-1)
        drawing.add(String(x,bottom-15,block.labels[i],textAnchor='middle',fontName='ResearchRegular',fontSize=6.5,fillColor=INK))
    return drawing


class ResearchPdfRenderer:
    def render(self, document,destination):
        register_fonts()
        destination=Path(destination)
        destination.parent.mkdir(parents=True,exist_ok=True)
        sources=OrderedDict()
        for part in document.sections:
            for entry in [*part.findings,*part.blocks]:
                for source in entry.sources:
                    key=(str(source.url),source.source_name)
                    sources.setdefault(key,[]).append(source)
        numbering={key:i+1 for i,key in enumerate(sources)}
        body=ParagraphStyle('body',fontName='ResearchRegular',fontSize=9.3,leading=14,spaceAfter=8,textColor=INK,splitLongWords=True)
        heading=ParagraphStyle('heading',parent=body,fontName='ResearchBold',fontSize=15,leading=20,textColor=NAVY,spaceBefore=15,spaceAfter=10,keepWithNext=True)
        sub=ParagraphStyle('sub',parent=body,fontName='ResearchBold',fontSize=10.5,leading=15,textColor=NAVY,spaceBefore=7,keepWithNext=True)
        small=ParagraphStyle('small',parent=body,fontSize=7.3,leading=10,spaceAfter=7,textColor=colors.HexColor('#586c66'))
        cell=ParagraphStyle('cell',parent=body,fontSize=7.1,leading=10,spaceAfter=0)
        header_cell=ParagraphStyle('headercell',parent=cell,fontName='ResearchBold',textColor=colors.white)
        sidebar=ParagraphStyle('sidebar',parent=body,fontSize=8.3,leading=12)

        def cite(refs):
            ids=sorted({numbering[(str(s.url),s.source_name)] for s in refs})
            return ' ['+', '.join(map(str,ids))+']' if ids else ''

        width,height=A4
        def decorate(canvas,doc):
            canvas.saveState()
            canvas.setTitle(document.title)
            canvas.setAuthor('Equity Research - hệ thống phân tích dữ liệu')
            canvas.setStrokeColor(NAVY);canvas.setLineWidth(.7)
            canvas.line(40,height-57,width-40,height-57)
            canvas.setFont('ResearchBold',11);canvas.setFillColor(NAVY)
            names={'stock':'Báo cáo phân tích cổ phiếu','industry':'Báo cáo phân tích ngành','macro':'Báo cáo tổng quan vĩ mô'}
            canvas.drawString(40,height-40,names[document.kind.value])
            canvas.setFont('ResearchBold',9);canvas.drawRightString(width-40,height-40,'EQUITY RESEARCH')
            canvas.setStrokeColor(colors.HexColor('#c6cdca'));canvas.line(40,38,width-40,38)
            canvas.setFont('ResearchRegular',7);canvas.setFillColor(INK)
            canvas.drawString(40,24,f'Chốt dữ liệu: {document.as_of:%d/%m/%Y}')
            canvas.drawCentredString(width/2,24,'Phân tích tự động có truy nguồn')
            canvas.drawRightString(width-40,24,f'Trang {doc.page}')
            if doc.page==1:
                canvas.setFillColor(GRAY);canvas.rect(40,54,148,height-128,fill=1,stroke=0)
                y=height-92
                values=[document.company_name or document.industry_name or 'Kinh tế Việt Nam',
                    document.symbol or document.kind.value.upper(),document.industry_name or 'Tổng quan liên ngành',
                    'Kỳ tài chính: '+(document.financial_period or 'Theo năm/kỳ nguồn'),
                    'Đánh giá: '+document.assessment,
                    'Tạo lúc: '+document.generated_at.astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M')]
                for i,text in enumerate(values):
                    style=ParagraphStyle('side'+str(i),parent=sidebar,fontName='ResearchBold' if i in (0,1) else 'ResearchRegular',textColor=NAVY if i in (0,1) else INK)
                    p=Paragraph(escape(text),style);_,h=p.wrap(124,600);p.drawOn(canvas,52,y-h);y-=h+13
                p=Paragraph('Báo cáo phân tích do chương trình tạo. BCTC chính thức và thuyết minh là tài liệu nguồn riêng để đối chiếu.',small)
                _,h=p.wrap(124,300);p.drawOn(canvas,52,y-h);y-=h+16
                chart=next((b for s in document.sections for b in s.blocks if b.kind=='chart' and b.values),None)
                if chart and y>220:
                    p=Paragraph(escape(chart.title),small);_,h=p.wrap(124,100);p.drawOn(canvas,52,y-h)
                    renderPDF.draw(line_chart(chart,width=124,height=105),canvas,52,y-h-110)
            canvas.restoreState()

        first=Frame(202,54,width-242,height-126,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
        later=Frame(40,54,width-80,height-126,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
        doc=BaseDocTemplate(str(destination),pagesize=A4,title=document.title,allowSplitting=True)
        doc.addPageTemplates([PageTemplate(id='cover',frames=[first],onPage=decorate),PageTemplate(id='body',frames=[later],onPage=decorate)])
        story=[NextPageTemplate('body'),Paragraph(escape(document.title),heading),
            Paragraph('Đánh giá: '+escape(document.assessment),sub),
            Paragraph('Ngày chốt: '+document.as_of.strftime('%d/%m/%Y')+' | Kỳ tài chính: '+escape(document.financial_period or 'Theo từng nguồn'),small)]
        from reportlab.platypus import PageBreak
        cover_findings=list(document.sections[0].findings[:2])
        if document.kind.value=='stock':
            financial=next((s for s in document.sections if s.kind.value=='financial'),document.sections[0])
            cover_findings.extend([f for f in financial.findings if not f.is_assumption][:2])
        for item in cover_findings:
            story.append(Paragraph(escape(item.text)+escape(cite(item.sources)),body))
        story.append(Paragraph('Phạm vi và chất lượng dữ liệu',sub))
        for note in document.data_quality[:2]:story.append(Paragraph(escape(note),small))
        story.append(PageBreak())
        for index,part in enumerate(document.sections):
            story.append(Paragraph(f'{index+1}. '+escape(part.title),heading))
            for item in part.findings:
                prefix='Khung phân tích / giả định: ' if item.is_assumption else ''
                story.append(Paragraph(escape(prefix+item.text)+escape(cite(item.sources)),body))
            for block in part.blocks:
                story.append(Paragraph(escape(block.title),sub))
                if block.kind=='chart':
                    # A cover with long macro charts continues to full-width pages naturally.
                    story.append(line_chart(block,width=later._width))
                elif block.headers:
                    rows=[[Paragraph(escape(v),header_cell) for v in block.headers]]
                    rows.extend([Paragraph(escape(v),cell) for v in row] for row in block.rows)
                    available=later._width
                    count=len(block.headers)
                    columns=([available*.34]+[available*.66/(count-1)]*(count-1)) if count>1 else [available]
                    table=Table(rows,colWidths=columns,repeatRows=1,hAlign='LEFT')
                    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
                        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f2f4f2')]),
                        ('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#d8dddb')),
                        ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
                        ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
                    story.append(table)
                story.append(Paragraph(escape(block.note)+escape(cite(block.sources)),small))
                story.append(Spacer(1,5))
        story.append(Paragraph('Phụ lục: công thức, chất lượng và tài liệu nguồn',heading))
        story.append(Paragraph('Các công thức hiển thị tại bảng chỉ tiêu và phần định giá. Phiên bản financials-1.0. Thiếu dữ liệu được giữ thiếu; không thay bằng 0. JSON snapshot lưu cùng ID báo cáo để truy từng dòng, kỳ và nguồn.',body))
        for note in document.data_quality:
            story.append(Paragraph(escape(note),small))
        for key,refs in sources.items():
            unique=list(dict.fromkeys(s.locator for s in refs if s.locator))
            first_ref=refs[0]
            detail='; '.join(unique[:2])
            if len(unique)>2:detail+='; các định vị còn lại xem JSON snapshot.'
            text=f"[{numbering[key]}] {first_ref.source_name}. Thu thập: {first_ref.retrieved_at.astimezone(ZoneInfo('Asia/Ho_Chi_Minh')):%d/%m/%Y %H:%M}. {detail}"
            story.append(Paragraph(escape(text)+f'<br/><link href="{escape(key[0],quote=True)}" color="#18866f">'+escape(key[0])+'</link>',small))
        doc.build(story)
        return destination
