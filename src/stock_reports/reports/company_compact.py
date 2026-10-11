"""Compact company PDF with explicit page groups and concise source references."""
from collections import OrderedDict
from html import escape
import math
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.graphics.shapes import Drawing, Line, PolyLine, Rect, String
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak, KeepTogether
from reportlab.platypus.tableofcontents import TableOfContents

from stock_reports.reports.company import NAVY, BLUE, PALE, GRAY, AMBER, GRID, MARGIN, safe

GREEN=colors.HexColor('#25876B');RED=colors.HexColor('#C84040')


def chart(block,width,height=170):
    drawing=Drawing(width,height)
    all_series=[('Giá / doanh thu',block.values),*block.series]
    values=[v for _,items in all_series for v in items if v is not None]
    if not values:return drawing
    low=min(0,min(values)) if block.chart_type=='bar' else min(values)
    high=max(0,max(values));span=high-low or 1
    step=10**math.floor(math.log10(span/4))
    step=next((v*step for v in (1,2,5,10) if v*step>=span/4),step*10)
    low=math.floor(low/step)*step;high=math.ceil(high/step)*step
    if high==low:high=low+step
    left,right,bottom,top=42,width-8,35,height-20
    y=lambda v:bottom+(top-bottom)*(v-low)/(high-low)
    for i in range(round((high-low)/step)+1):
        value=low+i*step;position=y(value)
        drawing.add(Line(left,position,right,position,strokeColor=GRID,strokeWidth=.4))
        label=f'{value:g}'.replace('.',',')
        drawing.add(String(left-5,position-3,label,textAnchor='end',fontName='ResearchRegular',fontSize=7,fillColor=GRAY))
    palette=[BLUE,GREEN,colors.HexColor('#B48A43'),colors.HexColor('#8C6CAE')]
    count=len(block.labels)
    if block.chart_type=='bar':
        slot=(right-left)/max(1,count);bar_width=slot*.65/len(all_series)
        for j,(_,items) in enumerate(all_series):
            for i,v in enumerate(items):
                if v is None:continue
                x=left+slot*i+slot*.175+bar_width*j
                color=RED if v<0 else palette[j] if len(all_series)>1 else GREEN
                drawing.add(Rect(x,min(y(v),y(0)),bar_width*.88,abs(y(v)-y(0)),fillColor=color,strokeColor=None))
                drawing.add(String(x+bar_width*.44,y(v)+4 if v>=0 else y(v)-9,f'{v:.1f}'.replace('.',','),
                    textAnchor='middle',fontName='ResearchRegular',fontSize=6.5,fillColor=GRAY))
        indices=range(count)
        x_at=lambda i:left+slot*(i+.5)
    else:
        x_at=lambda i:left+(right-left)*i/max(1,count-1)
        for j,(label,items) in enumerate(all_series):
            segments=[];segment=[]
            for i,v in enumerate(items):
                if v is None:
                    if segment:segments.append(segment);segment=[]
                else:segment.extend((x_at(i),y(v)))
            if segment:segments.append(segment)
            for points in segments:
                if len(points)>2:drawing.add(PolyLine(points,strokeColor=palette[j%len(palette)],strokeWidth=1.3))
            drawing.add(String(left+j*105,height-9,('Đóng cửa' if j==0 else label),fontName='ResearchRegular',fontSize=7,fillColor=palette[j%len(palette)]))
        indices=sorted({round(i*(count-1)/4) for i in range(5)})
    for i in indices:
        drawing.add(String(x_at(i),bottom-13,block.labels[i],textAnchor='middle',fontName='ResearchRegular',fontSize=6.5,fillColor=GRAY))
    if block.chart_type=='bar' and block.series:
        drawing.add(String(left,height-8,'Doanh thu',fontName='ResearchRegular',fontSize=7,fillColor=BLUE))
        drawing.add(String(left+95,height-8,'LNST',fontName='ResearchRegular',fontSize=7,fillColor=GREEN))
    return drawing


def render_compact_company(document,destination):
    from stock_reports.reports.render import register_fonts
    register_fonts();destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    width,height=A4;available=width-2*MARGIN
    body=ParagraphStyle('compact-body',fontName='ResearchRegular',fontSize=10,leading=14,textColor=NAVY,spaceAfter=7)
    small=ParagraphStyle('compact-small',parent=body,fontSize=8.1,leading=10.7,textColor=GRAY,spaceAfter=5)
    heading=ParagraphStyle('compact-heading',parent=body,fontName='ResearchBold',fontSize=14,leading=18,spaceBefore=6,spaceAfter=8,keepWithNext=True)
    sub=ParagraphStyle('compact-sub',parent=heading,fontSize=10.1,leading=13,spaceBefore=4,spaceAfter=5)
    cell=ParagraphStyle('compact-cell',parent=body,fontSize=8,leading=10.4,spaceAfter=0)
    source_style=ParagraphStyle('compact-source',parent=small,fontSize=7.2,leading=9.2,spaceAfter=6)
    sources=OrderedDict()
    for part in document.sections:
        for item in (*part.findings,*part.blocks):
            for source in item.sources:sources.setdefault(str(source.url) or source.source_name,[]).append(source)
    numbering={k:i+1 for i,k in enumerate(sources)}
    def cite(refs):
        nums=sorted({numbering[str(s.url) or s.source_name] for s in refs})
        return ' ['+', '.join(map(str,nums))+']' if nums else ''
    def p(value,style=body):
        # One short missing-value symbol; explanation is supplied once.
        value=str(value).replace('Chưa đủ dữ liệu','-')
        return Paragraph(safe(value),style)
    table_counter=[0];chart_counter=[0]
    def make_table(block):
        n=len(block.headers)
        ratios=(.28,*([.72/(n-1)]*(n-1))) if n>1 else (1,)
        if n==2:ratios=(.42,.58)
        if n==3:ratios=(.32,.47,.21) if 'Kỳ' in block.headers else (.32,.19,.49)
        if n>=8:ratios=(.15,*([.85/(n-1)]*(n-1)))
        table_widths=[available*r for r in ratios]
        rows=[]
        for i,row in enumerate((block.headers,*block.rows)):
            cells=[]
            for j,value in enumerate(row):
                numeric=bool(i and re.fullmatch(r'[+\-]?[\d.,]+(?:%| lần| VND/cp| VND| tỷ VND| cp)?',value))
                style=ParagraphStyle('entry',parent=cell,fontSize=7.3 if n>=7 else 8,leading=10.4,
                    fontName='ResearchBold' if not i else 'ResearchRegular',textColor=colors.white if not i else NAVY,
                    alignment=2 if numeric else 0)
                if numeric and (block.title.startswith('Diễn biến') or 'Biến động' in row[0]):
                    style.textColor=RED if value.startswith('-') else GREEN
                if i and value.startswith('Chưa đủ cơ sở'):style.textColor=AMBER
                cells.append(p(value,style))
            rows.append(cells)
        table=Table(rows,colWidths=table_widths,repeatRows=1,hAlign='LEFT')
        commands=[('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),('LINEBELOW',(0,0),(-1,-1),.3,GRID),
            ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),
            ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]
        if 'QUÝ' in block.headers[-1] or re.fullmatch(r'\d{4}Q[1-4]',block.headers[-1]) and n==7:
            commands.append(('LINEBEFORE',(-1,0),(-1,-1),.4,NAVY,1,None,None,2,2))
        table.setStyle(TableStyle(commands));return table
    story=[]
    def add_block(block):
        if block.kind=='chart':
            chart_counter[0]+=1;title=f'Biểu đồ {chart_counter[0]}: '+block.title
            items=[p(title,sub),chart(block,available)]
        else:
            table_counter[0]+=1;title=f'Bảng {table_counter[0]}: '+block.title
            items=[p(title,sub),make_table(block)]
        if block.sources or block.note:items.append(p('Nguồn:'+cite(block.sources)+('. '+block.note if block.kind=='chart' and block.note else ''),small))
        items.append(Spacer(1,4))
        story.append(KeepTogether(items))
    def add_part(part,blocks=None):
        title=p(part.title,heading)
        if part.kind.value not in ('business','macro','prospects','risks'):title._toc_title=part.title
        story.append(title)
        for finding in part.findings:
            text=finding.text;cut=text.find('. ');lead=text[:cut+1] if 0<cut<160 else ''
            content=('<b>'+safe(lead)+'</b>'+safe(text[len(lead):]) if lead else safe(text))+safe(cite(finding.sources))
            story.append(Paragraph(content,body))
        for b in part.blocks if blocks is None else blocks:add_block(b)
    by={s.kind.value:s for s in document.sections}
    hero=Table([[p(document.company_name or document.symbol,ParagraphStyle('compact-hero',parent=heading,fontSize=18,leading=23,textColor=colors.white)),
        p(document.symbol,ParagraphStyle('ticker',parent=heading,fontSize=23,textColor=colors.white))]],colWidths=[available*.82,available*.18])
    hero.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),NAVY),('LEFTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
    story.extend([hero,Spacer(1,8),p('BÁO CÁO DOANH NGHIỆP | '+document.financial_period,sub)])
    for b in document.cover_blocks:add_block(b)
    story.append(p('TÓM TẮT KẾT QUẢ',heading))
    for f in by['recommendation'].findings:story.append(p(f.text+cite(f.sources),body))
    why=by['valuation'].blocks[0] if by['valuation'].blocks else None
    if document.assessment.startswith('Chưa'):
        story.append(p('VÌ SAO CHƯA KHUYẾN NGHỊ',sub))
        story.append(p('Chưa khuyến nghị không có nghĩa là chưa có dữ liệu. Các chỉ tiêu tính được và chỉ tiêu do nguồn tổng hợp vẫn hiển thị tại mục VII; giá mục tiêu cần giả định và kiểm tra riêng.',small))
    warning=Paragraph('<b>LƯU Ý DỮ LIỆU</b><br/>'+'<br/>'.join(safe(w) for w in document.data_quality),small)
    warning_table=Table([[warning]],colWidths=[available])
    warning_table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#FFF5DE')),('BOX',(0,0),(-1,-1),.5,AMBER),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    story.extend([warning_table,PageBreak()])
    story.append(p('MỤC LỤC NGẮN',sub))
    toc=TableOfContents();toc.levelStyles=[ParagraphStyle('compact-toc',parent=small,fontSize=8,leading=10,spaceBefore=1,spaceAfter=1)]
    toc.tableStyle=TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),
        ('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)])
    story.extend([toc,Spacer(1,8)])
    add_part(by['company']);add_part(by['business']);story.append(PageBreak())
    add_part(by['industry']);add_part(by['macro']);story.append(PageBreak())
    add_part(by['financial']);story.append(PageBreak())
    add_part(by['appendix'],[b for b in by['appendix'].blocks if b.kind=='table']);story.append(PageBreak())
    story.append(p('KẾT QUẢ QUÝ VÀ DIỄN BIẾN GIÁ',heading))
    for b in by['appendix'].blocks:
        if b.kind=='chart':add_block(b)
    add_part(by['technical']);story.append(PageBreak())
    add_part(by['prospects']);add_part(by['risks']);add_part(by['valuation']);story.append(PageBreak())
    source_title=p('NGUỒN VÀ PHƯƠNG PHÁP',heading);source_title._toc_title='Nguồn và phương pháp';story.append(source_title)
    story.append(p('Bảng tài chính chia giá trị cho 10^9, biểu đồ kết quả chia 10^12. Khi chưa có hồ sơ đối chiếu, đây là giá trị nguồn, không xác nhận đơn vị/phạm vi. Cột QUÝ không phải số năm; KQKD chỉ coi là quý riêng nếu hồ sơ xác nhận. ROE/ROA năm = LNST năm / bình quân đầu-cuối năm; TTM = LNST bốn quý / bình quân đầu-cuối 12 tháng. Dấu gạch không phải số 0. CFO giữ cơ sở nguồn; không trừ các bản khác lần điều chỉnh. Không dùng tài sản = nợ + vốn để điền số thiếu. Chỉ tiêu CafeF là dữ kiện tổng hợp, không phải giả định dự phóng hay khuyến nghị. Đơn vị và kỳ của nguồn giá độc lập không được tự áp sang chuỗi giá nhà cung cấp khác.',small))
    citations=[]
    for key,items in sources.items():
        first=items[0];details=list(dict.fromkeys(s.locator.split('; SHA-256')[0] for s in items if s.locator))
        detail='; '.join(details[:1]);detail=re.sub(r';?\s*SHA-256.*','',detail)
        if detail.startswith('var/'):detail='Kỳ và dòng số liệu lưu trong hồ sơ đối chiếu.'
        # The filing's period is essential even when a row locator is generic.
        filename=str(first.url).split('/')[-1]
        years=re.findall(r'20\d{2}',filename)
        if first.source_name=='Hòa Phát BCTC gốc' and years:
            quarter=re.search(r'quy-([1-4]|i{1,3}|iv)(?:-|\.)',filename)
            period_label=('quý '+quarter[1].upper()+'/' if quarter else 'năm / bán niên ')+years[-1]
            detail=period_label+'. '+detail
        if first.source_name=='Hòa Phát BCTN 2025':detail='Năm 2025; trang 12, 28, 41, 43, 58, 59 (hoạt động và kế hoạch tách riêng).'
        value=f'[{numbering[key]}] {first.source_name}. '+detail
        link=f' <link href="{escape(str(first.url),quote=True)}" color="#2482BD">Nguồn gốc</link>' if first.url else ''
        citations.append(Paragraph(safe(value)+link,source_style))
    for offset in range(0,len(citations),24):
        group=citations[offset:offset+24];middle=(len(group)+1)//2
        cols=Table([[group[:middle],group[middle:]]],colWidths=[available/2]*2)
        cols.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),12)]))
        story.append(cols)
    story.append(p('Miễn trừ trách nhiệm: tài liệu phục vụ thông tin và nghiên cứu, không phải lời chào mua/bán hay cam kết lợi nhuận. Kế hoạch của doanh nghiệp không phải dự báo độc lập. Người đọc tự chịu trách nhiệm cho quyết định đầu tư.',small))
    story.append(p('Chuyên viên: [điền sau] | Người phê duyệt: [điền sau]',small))
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont('ResearchBold',8);canvas.setFillColor(NAVY)
        canvas.drawRightString(width-MARGIN,height-35,'BÁO CÁO DOANH NGHIỆP | '+document.symbol)
        canvas.setStrokeColor(BLUE);canvas.line(MARGIN,height-44,width-MARGIN,height-44)
        canvas.setStrokeColor(GRID);canvas.line(MARGIN,42,width-MARGIN,42)
        canvas.setFont('ResearchRegular',7.5);canvas.setFillColor(GRAY)
        canvas.drawString(MARGIN,28,f'Chốt dữ liệu: {document.as_of:%d/%m/%Y}')
        canvas.drawRightString(width-MARGIN,28,f'Trang {doc.page}');canvas.restoreState()
    class CompactDocTemplate(SimpleDocTemplate):
        def afterFlowable(self,flowable):
            if hasattr(flowable,'_toc_title'):
                self.notify('TOCEntry',(0,flowable._toc_title,self.page))
    pdf=CompactDocTemplate(str(destination),pagesize=A4,leftMargin=MARGIN,rightMargin=MARGIN,topMargin=58,bottomMargin=55,title=document.title)
    pdf.multiBuild(story,onFirstPage=footer,onLaterPages=footer)
    return destination
