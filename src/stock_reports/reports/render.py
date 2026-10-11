"""Distinct A4 research layouts for stock, industry and macro reports."""

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
from reportlab.platypus import (
    BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle, ActionFlowable,
)
from stock_reports.analysis.financials import FORMULA_VERSION


class ResearchChartDrawing(Drawing):
    def draw(self):
        super().draw()
        self.canv._research_chart_count = getattr(self.canv, '_research_chart_count', 0) + 1


class ChartPageGuard(ActionFlowable):
    def apply(self, doc):
        if getattr(doc.canv, '_research_chart_count', 0) >= 2:
            doc.handle_pageBreak()


INK = colors.HexColor('#203d36')
GRID = colors.HexColor('#d8dddb')
PALETTES = {
    'stock': (colors.HexColor('#08137f'), colors.HexColor('#1385c8'), colors.HexColor('#eef1f8')),
    'industry': (colors.HexColor('#26324a'), colors.HexColor('#d8892b'), colors.HexColor('#f3f0e9')),
    'macro': (colors.HexColor('#083b5c'), colors.HexColor('#00a6a6'), colors.HexColor('#eaf4f4')),
}


def register_fonts():
    root = Path(__file__).resolve().parents[1] / 'web/static/fonts'
    for suffix in ('Regular', 'Bold'):
        name = 'Research' + suffix
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(root / f'NotoSans-{suffix}.ttf')))
    pdfmetrics.registerFontFamily(
        'ResearchRegular', normal='ResearchRegular', bold='ResearchBold',
        italic='ResearchRegular', boldItalic='ResearchBold')


def line_chart(block, width=480, height=160, stroke=colors.HexColor('#1385c8')):
    drawing = ResearchChartDrawing(width, height)
    points = [value for value in block.values if value is not None]
    if not points:
        drawing.add(String(28, 75, 'Chưa đủ dữ liệu', fontName='ResearchRegular', fontSize=9))
        return drawing
    low, high = min(points), max(points)
    padding = (high - low) * .1 or max(abs(high) * .05, 1)
    low -= padding
    high += padding
    left, right, bottom, top = 48, width - 8, 30, height - 12
    for index in range(4):
        y = bottom + (top - bottom) * index / 3
        drawing.add(Line(left, y, right, y, strokeColor=colors.HexColor('#dfe5e2'), strokeWidth=.4))
        drawing.add(String(left - 5, y - 3, f'{low + (high-low)*index/3:.1f}',
                           textAnchor='end', fontName='ResearchRegular', fontSize=7, fillColor=INK))
    segments, segment = [], []
    for index, value in enumerate(block.values):
        if value is None:
            if segment:
                segments.append(segment)
            segment = []
            continue
        x = left + (right - left) * index / max(1, len(block.values) - 1)
        y = bottom + (top - bottom) * (value - low) / (high - low)
        segment.extend((x, y))
    if segment:
        segments.append(segment)
    for values in segments:
        if len(values) > 2:
            drawing.add(PolyLine(values, strokeColor=stroke, strokeWidth=1.7))
        else:
            drawing.add(Line(values[0] - 2, values[1], values[0] + 2, values[1], strokeColor=stroke))
    tick_count = 3 if width < 200 else 5
    indices = sorted({round(i * (len(block.labels) - 1) / (tick_count - 1))
                      for i in range(tick_count)}) if block.labels else []
    for index in indices:
        x = left + (right - left) * index / max(1, len(block.labels) - 1)
        drawing.add(String(x, bottom - 15, block.labels[index], textAnchor='middle',
                           fontName='ResearchRegular', fontSize=6.5, fillColor=INK))
    return drawing


class ResearchPdfRenderer:
    def render(self, document, destination):
        if document.industry_stocklens_data is not None:
            from stock_reports.reports.industry_stocklens.render import render_pdf
            return render_pdf(document.industry_stocklens_data,destination)
        if document.macro_stocklens_data is not None:
            from stock_reports.reports.macro_stocklens.render import render_pdf
            return render_pdf(document.macro_stocklens_data,destination)
        if document.stocklens_data is not None:
            from stock_reports.reports.stocklens.render import render_pdf
            return render_pdf(document.stocklens_data,destination,accent=document.stocklens_data['meta'].get('accent','#1F5EFF'))
        if document.editorial_markdown:
            from stock_reports.reports.macro_reference import render_reference
            return render_reference(document,destination)
        if document.kind.value=='stock' and document.template_version:
            if document.template_version.startswith('company-compact-'):
                from stock_reports.reports.company_compact import render_compact_company
                return render_compact_company(document,destination)
            from stock_reports.reports.company import render_company
            return render_company(document,destination)
        register_fonts()
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        kind = document.kind.value
        primary, accent, tint = PALETTES[kind]
        width, height = A4

        sources = OrderedDict()
        for section in document.sections:
            for entry in (*section.findings, *section.blocks):
                for source in entry.sources:
                    sources.setdefault((str(source.url), source.source_name), []).append(source)
        numbering = {key: index + 1 for index, key in enumerate(sources)}

        body = ParagraphStyle('body', fontName='ResearchRegular', fontSize=9.2,
                              leading=13.7, spaceAfter=8, textColor=INK, splitLongWords=True)
        heading = ParagraphStyle('heading', parent=body, fontName='ResearchBold', fontSize=15,
                                 leading=20, textColor=primary, spaceBefore=15,
                                 spaceAfter=10, keepWithNext=True)
        sub = ParagraphStyle('sub', parent=body, fontName='ResearchBold', fontSize=10.5,
                             leading=15, textColor=primary, spaceBefore=7, keepWithNext=True)
        small = ParagraphStyle('small', parent=body, fontSize=7.3, leading=10,
                               spaceAfter=7, textColor=colors.HexColor('#586c66'))
        source_style = ParagraphStyle('source', parent=small, fontSize=6.2, leading=7.8,
                                      spaceAfter=3)
        cell = ParagraphStyle('cell', parent=body, fontSize=7.1, leading=10, spaceAfter=0)
        header_cell = ParagraphStyle('headercell', parent=cell, fontName='ResearchBold', textColor=colors.white)
        sidebar = ParagraphStyle('sidebar', parent=body, fontSize=8.2, leading=12)
        kicker = ParagraphStyle('kicker', parent=small, fontName='ResearchBold', fontSize=8.2,
                                leading=11, textColor=accent, spaceAfter=6)

        def cite(refs):
            ids = sorted({numbering[(str(source.url), source.source_name)] for source in refs})
            return ' [' + ', '.join(map(str, ids)) + ']' if ids else ''

        def make_table(block, available, limit=None):
            rows = [[Paragraph(escape(value), header_cell) for value in block.headers]]
            body_rows = block.rows[:limit] if limit else block.rows
            rows.extend([Paragraph(escape(value), cell) for value in row] for row in body_rows)
            count = len(block.headers)
            columns = ([available * .34] + [available * .66 / (count - 1)] * (count - 1)) if count > 1 else [available]
            table = Table(rows, colWidths=columns, repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), primary),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, tint]),
                ('LINEBELOW', (0, 0), (-1, -1), .3, GRID),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            return table

        def decorate(canvas, doc):
            canvas._research_chart_count = 0
            canvas.saveState()
            canvas.setTitle(document.title)
            canvas.setAuthor('Equity Research - hệ thống phân tích dữ liệu')
            canvas.setStrokeColor(primary)
            canvas.setLineWidth(.7)
            canvas.line(40, height - 57, width - 40, height - 57)
            names = {'stock': 'Báo cáo phân tích cổ phiếu',
                     'industry': 'Báo cáo phân tích ngành',
                     'macro': 'Báo cáo tổng quan vĩ mô'}
            canvas.setFont('ResearchBold', 11)
            canvas.setFillColor(primary)
            canvas.drawString(40, height - 40, names[kind])
            canvas.setFont('ResearchBold', 9)
            canvas.drawRightString(width - 40, height - 40, 'EQUITY RESEARCH')
            canvas.setStrokeColor(GRID)
            canvas.line(40, 38, width - 40, 38)
            canvas.setFont('ResearchRegular', 7)
            canvas.setFillColor(INK)
            canvas.drawString(40, 24, f'Chốt dữ liệu: {document.as_of:%d/%m/%Y}')
            canvas.drawCentredString(width / 2, 24, 'Phân tích tự động có truy nguồn')
            canvas.drawRightString(width - 40, 24, f'Trang {doc.page}')

            if doc.page == 1 and kind == 'stock':
                canvas.setFillColor(tint)
                canvas.rect(40, 54, 148, height - 128, fill=1, stroke=0)
                y = height - 92
                values = [
                    document.company_name or 'Doanh nghiệp', document.symbol or '',
                    document.industry_name or 'Chưa phân loại ngành',
                    'Kỳ tài chính: ' + (document.financial_period or 'Theo nguồn'),
                    'Đánh giá: ' + document.assessment,
                    'Tạo lúc: ' + document.generated_at.astimezone(
                        ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M'),
                ]
                for index, text in enumerate(values):
                    style = ParagraphStyle(
                        'side' + str(index), parent=sidebar,
                        fontName='ResearchBold' if index in (0, 1) else 'ResearchRegular',
                        textColor=primary if index in (0, 1) else INK)
                    paragraph = Paragraph(escape(text), style)
                    _, paragraph_height = paragraph.wrap(124, 600)
                    paragraph.drawOn(canvas, 52, y - paragraph_height)
                    y -= paragraph_height + 13
                note = Paragraph(
                    'BCTC chính thức và thuyết minh là tài liệu nguồn để đối chiếu. '
                    'Khuyến nghị chỉ xuất hiện khi đủ điều kiện kiểm chứng.', small)
                _, note_height = note.wrap(124, 300)
                note.drawOn(canvas, 52, y - note_height)
                y -= note_height + 16
                chart = next((block for section in document.sections for block in section.blocks
                              if block.kind == 'chart' and block.values), None)
                if chart and y > 220:
                    chart_title = Paragraph(escape(chart.title), small)
                    _, title_height = chart_title.wrap(124, 100)
                    chart_title.drawOn(canvas, 52, y - title_height)
                    renderPDF.draw(line_chart(chart, width=124, height=105, stroke=accent),
                                   canvas, 52, y - title_height - 110)
            elif doc.page == 1:
                hero_height = 118 if kind == 'industry' else 132
                canvas.setFillColor(primary)
                canvas.roundRect(40, height - 72 - hero_height, width - 80,
                                 hero_height, 8, fill=1, stroke=0)
                canvas.setFillColor(accent)
                canvas.rect(40, height - 72 - hero_height, 8, hero_height, fill=1, stroke=0)
                canvas.setFont('ResearchBold', 8)
                canvas.drawString(62, height - 96,
                                  'SECTOR INTELLIGENCE' if kind == 'industry' else 'MACRO DASHBOARD')
                canvas.setFillColor(colors.white)
                canvas.setFont('ResearchBold', 18)
                hero = (document.industry_name or 'Phân tích ngành') if kind == 'industry' \
                    else 'Kinh tế Việt Nam & thị trường vốn'
                canvas.drawString(62, height - 122, hero[:54])
                canvas.setFont('ResearchRegular', 9)
                canvas.drawString(62, height - 145,
                                  'Ngày chốt dữ liệu ' + document.as_of.strftime('%d/%m/%Y'))
            canvas.restoreState()

        if kind == 'stock':
            first = Frame(202, 54, width - 242, height - 126,
                          leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        else:
            first = Frame(40, 54, width - 80, height - 270,
                          leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        later = Frame(40, 54, width - 80, height - 126,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        doc = BaseDocTemplate(str(destination), pagesize=A4, title=document.title, allowSplitting=True)
        doc.addPageTemplates([
            PageTemplate(id='cover', frames=[first], onPage=decorate),
            PageTemplate(id='body', frames=[later], onPage=decorate),
        ])

        story = [NextPageTemplate('body')]
        if kind == 'stock':
            story.extend([
                Paragraph(escape(document.title), heading),
                Paragraph('Đánh giá: ' + escape(document.assessment), sub),
                Paragraph('Ngày chốt: ' + document.as_of.strftime('%d/%m/%Y') +
                          ' | Kỳ tài chính: ' + escape(document.financial_period or 'Theo từng nguồn'), small),
            ])
        else:
            story.extend([
                Paragraph('TÓM TẮT ĐIỀU HÀNH' if kind == 'industry' else 'CHỈ BÁO & KỊCH BẢN', kicker),
                Paragraph(escape(document.title), heading),
                Paragraph('Đánh giá: ' + escape(document.assessment), sub),
            ])

        cover_findings = list(document.sections[0].findings[:2])
        if kind == 'stock':
            financial = next((section for section in document.sections
                              if section.kind.value == 'financial'), document.sections[0])
            cover_findings.extend([finding for finding in financial.findings
                                   if not finding.is_assumption][:2])
        for finding in cover_findings:
            story.append(Paragraph(escape(finding.text) + escape(cite(finding.sources)), body))

        if kind == 'industry':
            preview = next((block for section in document.sections for block in section.blocks
                            if block.kind == 'table' and block.rows), None)
            if preview:
                story.extend([Paragraph(escape(preview.title), sub),
                              make_table(preview, width - 80, limit=5)])
        elif kind == 'macro':
            charts = [block for section in document.sections for block in section.blocks
                      if block.kind == 'chart' and block.values][:2]
            if charts:
                cells = [[Paragraph(escape(chart.title), small),
                          line_chart(chart, width=225, height=112, stroke=accent)] for chart in charts]
                story.append(Table([cells], colWidths=[(width - 90) / len(cells)] * len(cells), hAlign='LEFT'))

        story.append(Paragraph('Phạm vi và chất lượng dữ liệu', sub))
        for note in document.data_quality[:2]:
            story.append(Paragraph(escape(note), small))
        story.append(PageBreak())

        roman = ('I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII')
        for index, section in enumerate(document.sections):
            story.append(Paragraph(f'{roman[index]}. ' + escape(section.title), heading))
            for finding in section.findings:
                prefix = 'Khung phân tích / giả định: ' if finding.is_assumption else ''
                story.append(Paragraph(escape(prefix + finding.text) + escape(cite(finding.sources)), body))
            chart_count = sum(block.kind == 'chart' for block in section.blocks)
            chart_group_started = False
            for block in section.blocks:
                if block.kind == 'chart':
                    if kind != 'stock' and chart_count > 2 and not chart_group_started:
                        story.append(PageBreak())
                        chart_group_started = True
                    story.append(ChartPageGuard())
                story.append(Paragraph(escape(block.title), sub))
                if block.kind == 'chart':
                    story.append(line_chart(block, width=later._width, stroke=accent))
                elif block.headers:
                    story.append(make_table(block, later._width))
                story.append(Paragraph(escape(block.note) + escape(cite(block.sources)), small))
                story.append(Spacer(1, 5))

        story.append(PageBreak())
        story.append(Paragraph('Phụ lục: công thức, chất lượng và tài liệu nguồn', heading))
        story.append(Paragraph(
            f'Các công thức hiển thị tại bảng chỉ tiêu và phần định giá. Phiên bản {FORMULA_VERSION}. '
            'Thiếu dữ liệu được giữ thiếu, không thay bằng 0. JSON snapshot lưu cùng ID báo cáo '
            'để truy từng dòng, kỳ và nguồn.', body))
        # Detailed row-level warnings remain in the JSON snapshot and in their
        # analytical sections.  Keep the appendix concise so a lone citation or
        # disclaimer never creates an almost-empty trailing page.
        for note in tuple(dict.fromkeys(document.data_quality))[:8]:
            story.append(Paragraph(escape(note), small))
        for key, refs in sources.items():
            unique = list(dict.fromkeys(source.locator for source in refs if source.locator))
            first_ref = refs[0]
            detail = '; '.join(unique[:2])
            if len(unique) > 2:
                detail += '; các định vị còn lại xem JSON snapshot.'
            text = (f'[{numbering[key]}] {first_ref.source_name}. Thu thập: '
                    f'{first_ref.retrieved_at.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")):%d/%m/%Y %H:%M}. '
                    f'{detail}')
            link = (f' <link href="{escape(key[0], quote=True)}" color="{accent.hexval()}">Mở nguồn ↗</link>'
                if first_ref.url else ' Tài liệu đính kèm; chưa có URL nguồn gốc.')
            story.append(Paragraph(escape(text)+link, source_style))
        story.append(Paragraph(
            'Miễn trừ trách nhiệm: Báo cáo phục vụ mục đích thông tin và nghiên cứu, không phải '
            'lời chào mua/bán hay cam kết lợi nhuận. Nhà đầu tư tự chịu trách nhiệm cho quyết định của mình.',
            source_style))
        doc.build(story)
        return destination
