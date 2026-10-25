"""Render the editable technical report to an assessed, paginated PDF.

ReportLab and project-local numerical figures are the only authoring inputs.
The report has nine main-content pages followed by one references page.
"""
from __future__ import annotations

from html import escape
from pathlib import Path
import re

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                               TableStyle, Image, PageBreak, KeepTogether)
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
NAVY=colors.HexColor('#18364A')
TEAL=colors.HexColor('#087F8C')
INK=colors.HexColor('#233746')
RULE=colors.HexColor('#D2DFE6')
LIGHT=colors.HexColor('#F0F5F7')
styles={
    'title':ParagraphStyle('title',fontName='Helvetica-Bold',fontSize=22,leading=25,textColor=NAVY,spaceAfter=11),
    'subtitle':ParagraphStyle('subtitle',fontName='Helvetica',fontSize=9,leading=12,textColor=colors.HexColor('#536977'),spaceAfter=13),
    'h2':ParagraphStyle('h2',fontName='Helvetica-Bold',fontSize=15,leading=18,textColor=NAVY,spaceAfter=9,keepWithNext=True),
    'body':ParagraphStyle('body',fontName='Helvetica',fontSize=10.1,leading=13.3,textColor=INK,spaceAfter=8,allowWidows=0,allowOrphans=0),
    'cell':ParagraphStyle('cell',fontName='Helvetica',fontSize=8.5,leading=11.2,textColor=INK),
    'head':ParagraphStyle('head',fontName='Helvetica-Bold',fontSize=8.5,leading=11.2,textColor=colors.white),
    'formula':ParagraphStyle('formula',fontName='Courier',fontSize=8.35,leading=11.4,textColor=NAVY,backColor=LIGHT,borderPadding=7,spaceBefore=3,spaceAfter=13),
    'caption':ParagraphStyle('caption',fontName='Helvetica',fontSize=8.7,leading=11.5,textColor=colors.HexColor('#506875'),spaceAfter=10),
}

def markup(value:str)->str:
    """Convert the limited editable-report Markdown to safe PDF text markup."""
    value=escape(value)
    value=re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)',lambda m:'<link href="'+m[2]+'" color="#087F8C">'+m[1]+'</link>',value)
    value=re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',value)
    value=re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)',r'<i>\1</i>',value)
    value=re.sub(r'`([^`]+)`',r'<font name="Courier">\1</font>',value)
    return value

def paragraph(text,style='body'):
    return Paragraph(markup(text),styles[style])

def table(lines,width):
    rows=[[c.strip() for c in line.strip('| ').split('|')] for line in lines]
    rows=[row for row in rows if not all(re.fullmatch(r'[-: ]+',cell) for cell in row)]
    first=rows[0][0]
    if len(rows[0])==5:ratios=[.30,.18,.18,.17,.17]
    elif first=='Primary input':ratios=[.28,.28,.44]
    elif first.startswith('Original numerical'):ratios=[.46,.54]
    elif first=='Check':ratios=[.43,.22,.20,.15]
    else:ratios=[1/len(rows[0])]*len(rows[0])
    data=[[paragraph(c,'head' if i==0 else 'cell') for c in row] for i,row in enumerate(rows)]
    result=Table(data,colWidths=[x*width for x in ratios],hAlign='LEFT',spaceBefore=4,spaceAfter=12)
    result.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),
                               ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,LIGHT]),
                               ('VALIGN',(0,0),(-1,-1),'TOP'),
                               ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
                               ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
                               ('LINEBELOW',(0,0),(-1,-1),.3,RULE)]))
    return result

def page_footer(canvas,doc):
    """Use stable page numbers, with references explicitly outside main count."""
    canvas.saveState()
    width,height=A4
    canvas.setStrokeColor(RULE);canvas.line(43,34,width-43,34)
    canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#617582'))
    canvas.drawString(43,23,'MMA3001  |  Dataset 2: sensor reconstruction')
    label=f'{doc.page} / 9 main pages' if doc.page<=9 else 'References (excluded from main page count)'
    canvas.drawRightString(width-43,23,label)
    canvas.restoreState()

def main()->None:
    """Build and check the exact main-content and references page allocation."""
    source=ROOT/'reports/MMA3001_Dataset2_technical_report.md'
    target=source.with_suffix('.pdf')
    document=SimpleDocTemplate(str(target),pagesize=A4,leftMargin=43,rightMargin=43,topMargin=37,bottomMargin=46,
                               title='Retrospective CO2 gap reconstruction: audited Dataset 2',
                               author='Lachlan Elliott; substantial AI assistance disclosed in report')
    pages=source.read_text().split('<!-- PAGE BREAK -->')
    if len(pages)!=10:raise ValueError('Expected nine main pages and one references page')
    story=[]
    for page_index,content in enumerate(pages):
        if page_index:story.append(PageBreak())
        lines=content.strip().splitlines();i=0
        while i<len(lines):
            line=lines[i].strip()
            if not line:i+=1;continue
            if line.startswith('# '):story.append(paragraph(line[2:],'title'));i+=1;continue
            if line.startswith('## '):story.append(paragraph(line[3:],'h2'));i+=1;continue
            if line.startswith('MMA3001 Numerical'):story.append(paragraph(line,'subtitle'));i+=1;continue
            if line.startswith('|'):
                group=[]
                while i<len(lines) and lines[i].strip().startswith('|'):group.append(lines[i].strip());i+=1
                story.append(table(group,document.width));continue
            match=re.match(r'!\[(.*?)\]\((.*?)\)',line)
            if match:
                path=(source.parent/match[2]).resolve()
                with PILImage.open(path) as image:width,height=image.size
                display_width=document.width
                display_height=display_width*height/width
                if display_height>223:
                    display_width*=223/display_height;display_height=223
                visual=Image(str(path),width=display_width,height=display_height)
                visual.hAlign='CENTER'
                story.append(KeepTogether([visual,Spacer(1,5),paragraph(match[1],'caption')]))
                i+=1;continue
            if line.startswith('`') and line.endswith('`'):
                story.append(paragraph(line[1:-1],'formula'));i+=1;continue
            group=[line];i+=1
            while i<len(lines) and lines[i].strip() and not lines[i].lstrip().startswith(('#','|','![')):
                group.append(lines[i].strip());i+=1
            story.append(paragraph(' '.join(group)))
    document.build(story,onFirstPage=page_footer,onLaterPages=page_footer)
    reader=PdfReader(target)
    if len(reader.pages)!=10:
        raise RuntimeError(f'Report layout overflow: expected10pages, got{len(reader.pages)}. Review before delivery.')
    expected=[f'{i}.' for i in range(1,10)]
    for i,prefix in enumerate(expected):
        if prefix not in (reader.pages[i].extract_text() or ''):
            raise RuntimeError(f'Missing expected main-content section on page{i+1}')
    print(f'{target}: 9 main-content pages plus1references page')

if __name__=='__main__':
    main()
