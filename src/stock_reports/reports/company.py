"""Company-specific PDF: conclusion first, Roman I-VIII, auditable valuation."""
from collections import OrderedDict
from html import escape
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing
from reportlab.platypus import BaseDocTemplate,Frame,PageTemplate,PageBreak,Paragraph,Spacer,Table,TableStyle,KeepTogether,ActionFlowable

from stock_reports.analysis.financials import FORMULA_VERSION
from stock_reports.analysis.valuation import VALUATION_VERSION

NAVY=colors.HexColor('#1B2F5B'); BLUE=colors.HexColor('#2482BD')
GRAY=colors.HexColor('#667085'); PALE=colors.HexColor('#F0F3F8')
AMBER=colors.HexColor('#8C692D'); GRID=colors.HexColor('#D9E0EC')
MARGIN=56.6929


class SectionStart(ActionFlowable):
    def apply(self,doc):
        if doc.frame._y-doc.frame._y1p<250:
            doc.handle_pageBreak()


def safe(value):
    return escape(str(value).replace('–','-').replace('—','-').replace('−','-')
                  .replace('≥','>=').replace('≤','<='))


def render_company(document,destination):
    from stock_reports.reports.render import register_fonts,line_chart
    register_fonts();destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    width,height=A4;available=width-2*MARGIN
    body=ParagraphStyle('company-body',fontName='ResearchRegular',fontSize=10,leading=14,
        textColor=NAVY,spaceAfter=8)
    small=ParagraphStyle('company-small',parent=body,fontSize=8.2,leading=11.2,textColor=GRAY,spaceAfter=6)
    heading=ParagraphStyle('company-heading',parent=body,fontName='ResearchBold',fontSize=16,leading=21,
        spaceBefore=4,spaceAfter=12,keepWithNext=True)
    sub=ParagraphStyle('company-sub',parent=body,fontName='ResearchBold',fontSize=10.6,leading=14.6,
        spaceBefore=5,spaceAfter=8,keepWithNext=True)
    cell=ParagraphStyle('company-cell',parent=body,fontSize=8.4,leading=11.3,spaceAfter=0)
    header=ParagraphStyle('company-table-head',parent=cell,fontName='ResearchBold',textColor=colors.white)
    source_style=ParagraphStyle('company-source',parent=small,fontSize=7.2,leading=9.8,spaceAfter=5)
    sources=OrderedDict()
    for part in document.sections:
        for item in (*part.findings,*part.blocks):
            for source in item.sources:sources.setdefault((str(source.url),source.source_name),[]).append(source)
    numbering={k:i+1 for i,k in enumerate(sources)}
    def cite(items):
        indices=sorted({numbering[(str(s.url),s.source_name)] for s in items})
        return ' ['+', '.join(str(i) for i in indices)+']' if indices else ''
    def para(value,style=body):return Paragraph(safe(value),style)
    def make_table(block,space=available,compact=False):
        count=len(block.headers)
        ratios={1:(1,),2:(.48,.52),3:(.35,.25,.40),4:(.25,.31,.26,.18),
                5:(.15,.34,.17,.17,.17),7:(.035,.13,.16,.16,.18,.165,.17)}.get(count)
        if block.title.startswith('Bảng 1:'):ratios=(.28,*([.12]*6))
        elif block.title.startswith('Bảng 2:'):ratios=(.25,.12,.12,.12,.12,.27)
        elif block.title.startswith('Bảng 3:'):ratios=(.36,*([.16]*4))
        elif block.title.startswith('BCTC:'):ratios=(.36,*([.64/(count-1)]*(count-1)))
        elif block.title.startswith('7.4.'):ratios=(.34,.18,.48)
        elif block.title.startswith('7.6.'):ratios=(.065,.145,.165,.16,.17,.145,.15)
        elif block.title.startswith('7.8.'):ratios=(.14,.38,.16,.16,.16)
        if ratios is None:ratios=(.32,*([.68/(count-1)]*(count-1)))
        # Normalise to exact available width, including peer tables with narrow STT.
        total=sum(ratios);columns=[space*r/total for r in ratios]
        rows=[]
        for index,row in enumerate((block.headers,*block.rows)):
            entries=[]
            for j,value in enumerate(row):
                style=header if index==0 else cell
                if index and re.fullmatch(r'[+\-]?[\d.,]+(?:%| lần)?',value):
                    text_width=stringWidth(value,cell.fontName,cell.fontSize)
                    font_size=min(cell.fontSize,cell.fontSize*(columns[j]-13)/max(1,text_width))
                    style=ParagraphStyle('numeric',parent=cell,alignment=2,fontSize=max(6.5,font_size))
                if index and 'Khuyến nghị' in row[0] and j==1:
                    style=ParagraphStyle('assessment',parent=cell,fontName='ResearchBold',
                        textColor=AMBER if document.assessment.startswith('Chưa') else NAVY)
                entries.append(para(value,style))
            rows.append(entries)
        table=Table(rows,colWidths=columns,repeatRows=1,hAlign='LEFT')
        padding=4 if compact else 6
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),
            ('LINEBELOW',(0,0),(-1,-1),.3,GRID),('LEFTPADDING',(0,0),(-1,-1),6),
            ('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),padding),
            ('BOTTOMPADDING',(0,0),(-1,-1),padding)]))
        return table
    def first_sentence(finding):
        text=finding.text;cut=text.find('. ')
        lead=text[:cut+1] if 0<cut<150 else text[:text.find(':')+1] if 0<text.find(':')<90 else ''
        return ('<b>'+safe(lead)+'</b>'+safe(text[len(lead):]) if lead else safe(text))+safe(cite(finding.sources))
    def finding_flow(finding,style=body):return Paragraph(first_sentence(finding),style)
    chart_count=[0]
    def chart_items(block,space=available):
        chart_count[0]+=1
        title=para(f'Biểu đồ {chart_count[0]}: '+block.title,sub)
        if block.chart_type=='pie':
            drawing=Drawing(space,180)
            pie=Pie();pie.x=(space-140)/2;pie.y=20;pie.width=pie.height=140
            pie.data=list(block.values);pie.labels=[str(i+1) for i in range(len(block.values))]
            pie.slices.fontName='ResearchRegular';pie.slices.fontSize=8
            palette=['#1B2F5B','#2482BD','#25876B','#7886AB','#60B3AE','#A1B7CF']
            for i in range(len(block.values)):
                pie.slices[i].fillColor=colors.HexColor(palette[i%len(palette)])
                pie.slices[i].strokeColor=colors.white
            drawing.add(pie)
            legend=para('; '.join(f'{i+1}. {label}: {value:g}%' for i,(label,value) in enumerate(zip(block.labels,block.values))),small)
            return [title,drawing,legend]
        return [title,line_chart(block,width=space,height=180,stroke=BLUE)]
    def add_block(block):
        if block.kind=='chart':
            items=chart_items(block)
        else:items=[para(block.title,sub),make_table(block)]
        if block.note or block.sources:
            items.append(para(('Nguồn:'+cite(block.sources)+'. ' if block.sources else '')+block.note,small))
        items.append(Spacer(1,5))
        if block.kind=='chart' or len(block.rows)<=12:story.append(KeepTogether(items))
        else:story.extend(items)
    def add_part(part,*,title=True):
        if title:story.append(para(part.title,heading))
        for finding in part.findings:story.append(finding_flow(finding))
        paired=[b for b in part.blocks if b.kind=='chart' and b.title.startswith('Cơ cấu doanh thu theo')]
        for item in part.blocks:
            if len(paired)==2 and item in paired:
                if item is paired[0]:
                    cells=[]
                    for b in paired:
                        entries=chart_items(b,available/2-12)
                        entries.append(para(b.note+cite(b.sources),small));cells.append(entries)
                    group=Table([cells],colWidths=[available/2]*2)
                    group.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),
                        ('RIGHTPADDING',(0,0),(-1,-1),12)]))
                    story.append(KeepTogether([group,Spacer(1,8)]))
            else:add_block(item)
    def decorate(canvas,doc):
        canvas.saveState();canvas.setFillColor(NAVY);canvas.setFont('ResearchBold',8.5)
        canvas.drawRightString(width-MARGIN,height-35,f'PHÂN TÍCH DOANH NGHIỆP | {document.symbol}')
        canvas.setStrokeColor(BLUE);canvas.setLineWidth(.7);canvas.line(MARGIN,height-44,width-MARGIN,height-44)
        canvas.setStrokeColor(GRID);canvas.line(MARGIN,42,width-MARGIN,42)
        canvas.setFillColor(GRAY);canvas.setFont('ResearchRegular',7.8)
        canvas.drawString(MARGIN,28,f'Chốt dữ liệu {document.as_of:%d/%m/%Y} | Thông tin có giới hạn kiểm chứng')
        canvas.drawRightString(width-MARGIN,28,f'{doc.page:02d}');canvas.restoreState()
    frame=Frame(MARGIN,55,available,height-116,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
    doc=BaseDocTemplate(str(destination),pagesize=A4,title=document.title,author='Nghiên cứu doanh nghiệp - nhận diện trung tính')
    doc.addPageTemplates([PageTemplate(id='company',frames=[frame],onPage=decorate)])
    by_kind={part.kind.value:part for part in document.sections}
    conclusion=by_kind['recommendation'];cover,trade=document.cover_blocks
    hero_title=Paragraph(safe(document.company_name or document.symbol),ParagraphStyle('hero-title',parent=heading,
        fontSize=18,leading=23,textColor=colors.white,spaceAfter=7))
    hero_caption=Paragraph(safe(f'{document.symbol} | {document.industry_name} | BÁO CÁO PHÂN TÍCH CỔ PHIẾU'),
        ParagraphStyle('hero-caption',parent=small,fontName='ResearchBold',textColor=colors.white,fontSize=8.2,leading=11))
    hero=Table([[[hero_title,hero_caption]]],colWidths=[available])
    hero.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),NAVY),('LEFTPADDING',(0,0),(-1,-1),16),
        ('RIGHTPADDING',(0,0),(-1,-1),16),('TOPPADDING',(0,0),(-1,-1),13),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
    story=[hero,Spacer(1,9),make_table(cover,compact=True),Spacer(1,8),para('LUẬN ĐIỂM VÀ ĐIỀU KIỆN ĐẦU TƯ',sub)]
    story.extend(finding_flow(f,small) for f in conclusion.findings[:3])
    left=[para(trade.title,sub),make_table(trade,space=available*.65-7,compact=True),
          para(trade.note+cite(trade.sources),source_style)]
    right=[para('RỦI RO ĐẦU TƯ',sub)]
    for risk in document.data_quality[:3]:right.append(para(risk,small))
    right.extend([para('PHẠM VI BÁO CÁO',sub),para('Kỳ BCTC: '+(document.financial_period or 'Chưa đủ dữ liệu'),small),
        para('Nguồn doanh thu/chi phí và tổng quan doanh nghiệp: mục I–III.',small),
        para('Giả định, phương pháp, độ nhạy và kiểm tra phát hành: mục VII.',small)])
    lower=Table([[left,right]],colWidths=[available*.65,available*.35])
    lower.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),
        ('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
    story.extend([lower,PageBreak()])
    for kind in ('company','industry','business','financial','prospects','risks','valuation','appendix'):
        if kind in ('valuation','appendix'):story.append(PageBreak())
        elif kind!='company':story.append(SectionStart())
        add_part(by_kind[kind])
        if kind=='industry':
            add_part(by_kind['macro'])
        if kind=='appendix':
            add_part(by_kind['technical'])
    story.append(para('Công thức và tài liệu nguồn',heading))
    story.append(para(f'Phiên bản {FORMULA_VERSION}; {VALUATION_VERSION}; {document.template_version}. '
        'ROE/ROA TTM = lợi nhuận bốn quý liên tiếp / bình quân vốn/tài sản đầu-cuối 12 tháng. '
        'P/B = giá / BVPS; P/E = giá / EPS. Ke = lãi suất phi rủi ro + beta × phần bù rủi ro. '
        'FCFF/FCFE chiết khấu từng năm và giá trị cuối kỳ; xem chi tiết tại mục VII. Thiếu dữ liệu không thay bằng 0.',small))
    for key,items in sources.items():
        first=items[0];locators=list(dict.fromkeys(s.locator for s in items if s.locator))
        detail='; '.join(locators[:2])
        if len(locators)>2:detail+='; định vị đầy đủ xem JSON snapshot.'
        value=f'[{numbering[key]}] {first.source_name}. Thu thập {first.retrieved_at.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")):%d/%m/%Y %H:%M}. {detail}'
        link=f' <link href="{escape(str(first.url),quote=True)}" color="#2482BD">Mở nguồn</link>' if first.url else ' Tài liệu cục bộ.'
        story.append(Paragraph(safe(value)+link,source_style))
    story.append(para('Miễn trừ trách nhiệm: báo cáo phục vụ thông tin và nghiên cứu, không phải lời chào mua/bán hoặc cam kết lợi nhuận. '
        'Các giả định do người soạn nhập không phải dữ kiện đã xảy ra; nhà đầu tư tự chịu trách nhiệm quyết định.',small))
    story.append(para('Người soạn: Chưa đủ dữ liệu. Người phê duyệt: Chưa đủ dữ liệu. '
        f'Ngày chốt: {document.as_of:%d/%m/%Y}.',small))
    doc.build(story);return destination
