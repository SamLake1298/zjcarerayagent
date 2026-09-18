from io import BytesIO
from pathlib import Path
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]

def export_docx(result):
    doc = Document(ROOT / 'data' / 'reference.docx')
    body = doc.element.body
    for node in list(body):
        if node.tag != qn('w:sectPr'):
            body.remove(node)
    # Remove content relationships left behind by the source chapter/body.
    # Otherwise a short export still contains all source images and custom XML.
    retained = {'styles', 'stylesWithEffects', 'numbering', 'settings', 'webSettings',
                'fontTable', 'theme', 'header', 'footer'}
    for rel_id, rel in list(doc.part.rels.items()):
        if rel.reltype.rsplit('/', 1)[-1] not in retained:
            doc.part.drop_rel(rel_id)
    doc.core_properties.author = ''
    doc.core_properties.last_modified_by = ''
    doc.core_properties.title = result['project']['name']
    doc.core_properties.subject = '第四章 项目建设内容与设计方案'
    doc.core_properties.comments = ''
    # Retain source page setup/styles. Use explicit original numbers in a chapter-only export.
    for section in doc.sections:
        for part in [section.header, section.footer]:
            for child in list(part._element):
                part._element.remove(child)
            for rel_id in list(part.part.rels):
                part.part.drop_rel(rel_id)
    for name in ['Normal', 'Title', 'Heading 1', 'Heading 2', 'Heading 3', 'Heading 4']:
        style = doc.styles[name]
        style.font.color.rgb = RGBColor(0, 0, 0)
        ppr = style.element.get_or_add_pPr()
        spacing = ppr.find(qn('w:spacing'))
        if spacing is not None:
            for attr in ('beforeLines', 'afterLines', 'beforeAutospacing', 'afterAutospacing'):
                spacing.attrib.pop(qn('w:' + attr), None)
        for tag in ['numPr', 'pBdr']:
            for node in list(ppr.findall(qn('w:' + tag))):
                ppr.remove(node)
        if name.startswith('Heading'):
            style.paragraph_format.keep_with_next = True
            style.paragraph_format.page_break_before = False
            style.paragraph_format.space_before = Pt(14 if name in ('Heading 1', 'Heading 2') else 10)
            style.paragraph_format.space_after = Pt(6)
    title = doc.add_paragraph(result['project']['name'], 'Title')
    title.paragraph_format.space_after = Pt(10)
    if result['mode'] == 'demo':
        doc.add_paragraph('演示文件：用于验证操作流程，正文为规则生成的占位示例，未调用大模型，未融合供应商方案。')
    doc.add_paragraph('第四章 项目建设内容与设计方案', 'Heading 1')
    last_module = None
    for section in result['sections']:
        if section['module_id'] != last_module:
            doc.add_paragraph(f"{section['module_id']} {section['module_title']}", 'Heading 2')
            last_module = section['module_id']
        doc.add_paragraph(f"{section['id']} {section['title']}", 'Heading 3')
        for index, block in enumerate(section['blocks']):
            if block['title']:
                doc.add_paragraph(f"{section['id']}.{index} {block['title']}", 'Heading 4')
            for text in block['paragraphs']:
                p = doc.add_paragraph(text, 'Normal')
                p.paragraph_format.first_line_indent = Pt(24)
                p.paragraph_format.line_spacing = 1.5
                p.paragraph_format.space_after = Pt(6)
                p.paragraph_format.widow_control = True
    footer = doc.sections[0].footer.paragraphs
    p = footer[0] if footer else doc.sections[0].footer.add_paragraph()
    p.alignment = 1
    field = OxmlElement('w:fldSimple')
    field.set(qn('w:instr'), 'PAGE')
    p._p.append(field)
    stream = BytesIO()
    for paragraph in doc.paragraphs:
        snap = OxmlElement('w:snapToGrid')
        snap.set(qn('w:val'), '0')
        paragraph._p.get_or_add_pPr().append(snap)
    doc.save(stream)
    return stream.getvalue()
