#!/usr/bin/env python3
"""
Convert markdown benchmark report to professional PDF.

Uses reportlab for PDF generation with embedded images.
"""

import os
import re
from datetime import datetime
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
    PageBreak, KeepTogether
)


def parse_markdown(md_path: Path) -> dict:
    """Parse markdown into structured sections."""
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    sections = {
        'title': '',
        'metadata': [],
        'content': [],
    }
    
    lines = content.split('\n')
    current_section = None
    current_text = []
    in_table = False
    table_rows = []
    
    for line in lines:
        # Title
        if line.startswith('# '):
            sections['title'] = line[2:].strip()
            continue
        
        # Metadata
        if line.startswith('**Generated:**') or line.startswith('**Platform:**') or \
           line.startswith('**CPU:**') or line.startswith('**Power Monitoring:**') or \
           line.startswith('**Total Measurements:**') or line.startswith('**Algorithms Tested:**') or \
           line.startswith('**Operation Types:**'):
            sections['metadata'].append(line)
            continue
        
        # Section headers
        if line.startswith('## '):
            if current_text:
                sections['content'].append(('text', '\n'.join(current_text)))
                current_text = []
            if table_rows:
                sections['content'].append(('table', table_rows))
                table_rows = []
                in_table = False
            sections['content'].append(('h2', line[3:].strip()))
            continue
        
        if line.startswith('### '):
            if current_text:
                sections['content'].append(('text', '\n'.join(current_text)))
                current_text = []
            if table_rows:
                sections['content'].append(('table', table_rows))
                table_rows = []
                in_table = False
            sections['content'].append(('h3', line[4:].strip()))
            continue
        
        # Images
        img_match = re.match(r'!\[(.*?)\]\((.*?)\)', line)
        if img_match:
            if current_text:
                sections['content'].append(('text', '\n'.join(current_text)))
                current_text = []
            sections['content'].append(('image', img_match.group(2)))
            continue
        
        # Tables
        if '|' in line and line.strip().startswith('|'):
            if '---' in line:
                continue  # Skip separator
            row = [cell.strip() for cell in line.split('|')[1:-1]]
            if row:
                if not in_table:
                    in_table = True
                table_rows.append(row)
            continue
        elif in_table and table_rows:
            sections['content'].append(('table', table_rows))
            table_rows = []
            in_table = False
        
        # Bullet points
        if line.strip().startswith('- '):
            if current_text:
                sections['content'].append(('text', '\n'.join(current_text)))
                current_text = []
            sections['content'].append(('bullet', line.strip()[2:]))
            continue
        
        # Regular text
        if line.strip():
            current_text.append(line)
        elif current_text:
            sections['content'].append(('text', '\n'.join(current_text)))
            current_text = []
    
    if current_text:
        sections['content'].append(('text', '\n'.join(current_text)))
    if table_rows:
        sections['content'].append(('table', table_rows))
    
    return sections


def create_pdf(md_path: Path, output_path: Path, image_dir: Path):
    """Create PDF from parsed markdown."""
    
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
    )
    
    # Styles
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='ReportTitle',
        parent=styles['Heading1'],
        fontSize=20,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1a1a2e'),
    ))
    styles.add(ParagraphStyle(
        name='ReportH2',
        parent=styles['Heading2'],
        fontSize=16,
        spaceBefore=20,
        spaceAfter=10,
        textColor=colors.HexColor('#16213e'),
    ))
    styles.add(ParagraphStyle(
        name='ReportH3',
        parent=styles['Heading3'],
        fontSize=13,
        spaceBefore=15,
        spaceAfter=8,
        textColor=colors.HexColor('#0f3460'),
    ))
    styles.add(ParagraphStyle(
        name='ReportBody',
        parent=styles['Normal'],
        fontSize=10,
        spaceBefore=6,
        spaceAfter=6,
        alignment=TA_JUSTIFY,
        leading=14,
    ))
    styles.add(ParagraphStyle(
        name='ReportBullet',
        parent=styles['Normal'],
        fontSize=10,
        leftIndent=20,
        spaceBefore=3,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name='ReportMeta',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.gray,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name='ReportCaption',
        parent=styles['Italic'],
        fontSize=9,
        spaceBefore=5,
        spaceAfter=15,
        textColor=colors.HexColor('#555555'),
        alignment=TA_JUSTIFY,
    ))
    
    story = []
    
    # Parse markdown
    sections = parse_markdown(md_path)
    
    # Title
    story.append(Paragraph(sections['title'], styles['ReportTitle']))
    story.append(Spacer(1, 20))
    
    # Metadata
    for meta in sections['metadata']:
        clean_meta = re.sub(r'\*\*(.*?)\*\*', r'\1', meta)
        story.append(Paragraph(clean_meta, styles['ReportMeta']))
    story.append(Spacer(1, 30))
    
    # Content
    for item_type, item_content in sections['content']:
        if item_type == 'h2':
            story.append(PageBreak())
            story.append(Paragraph(item_content, styles['ReportH2']))
        
        elif item_type == 'h3':
            story.append(Paragraph(item_content, styles['ReportH3']))
        
        elif item_type == 'text':
            # Clean markdown formatting
            clean_text = item_content
            clean_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', clean_text)
            clean_text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', clean_text)
            clean_text = re.sub(r'`(.*?)`', r'<font name="Courier">\1</font>', clean_text)
            story.append(Paragraph(clean_text, styles['ReportBody']))
        
        elif item_type == 'bullet':
            clean_bullet = item_content
            clean_bullet = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', clean_bullet)
            story.append(Paragraph(f"• {clean_bullet}", styles['ReportBullet']))
        
        elif item_type == 'image':
            img_path = image_dir / item_content
            if img_path.exists():
                # Calculate image size to fit page width
                img = Image(str(img_path), width=16*cm, height=10*cm)
                img.hAlign = 'CENTER'
                story.append(Spacer(1, 10))
                story.append(img)
                story.append(Spacer(1, 5))
        
        elif item_type == 'table':
            if item_content:
                # Create table
                table = Table(item_content, repeatRows=1)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('TOPPADDING', (0, 0), (-1, 0), 8),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                    ('TOPPADDING', (0, 1), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                ]))
                story.append(Spacer(1, 10))
                story.append(table)
                story.append(Spacer(1, 10))
    
    # Footer
    story.append(Spacer(1, 30))
    story.append(Paragraph(
        f"Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        styles['ReportMeta']
    ))
    
    # Build PDF
    doc.build(story)
    print(f"PDF saved to: {output_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Convert markdown report to PDF")
    parser.add_argument("-i", "--input", type=str, default="power_analysis/BENCHMARK_REPORT.md")
    parser.add_argument("-o", "--output", type=str, default="power_analysis/BENCHMARK_REPORT.pdf")
    args = parser.parse_args()
    
    md_path = Path(args.input)
    output_path = Path(args.output)
    image_dir = md_path.parent
    
    if not md_path.exists():
        print(f"Error: Markdown file not found: {md_path}")
        return
    
    create_pdf(md_path, output_path, image_dir)


if __name__ == "__main__":
    main()
