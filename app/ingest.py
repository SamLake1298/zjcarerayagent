"""Import a read-only snapshot of the supplied chapter and supplier materials."""
import argparse
import hashlib
import json
from pathlib import Path
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parents[1]

def blocks(doc):
    for node in doc.element.body:
        if node.tag.endswith('}p'):
            p = Paragraph(node, doc)
            if p.text.strip():
                yield p.style.name, p.text.strip()
        elif node.tag.endswith('}tbl'):
            table = Table(node, doc)
            rows = [' | '.join(dict.fromkeys(c.text.strip() for c in r.cells)) for r in table.rows]
            yield 'Table', '\n'.join(rows)

def import_materials(template, supplier_dir, target):
    if target.exists():
        raise FileExistsError(f'为避免覆盖，目标必须是新文件：{target}')
    modules, module, section, block = [], None, None, None
    active = False
    for style, text in blocks(Document(template)):
        if style == 'Heading 1':
            if active:
                break
            active = text == '项目建设内容与设计方案'
            continue
        if not active:
            continue
        if style == 'Heading 2':
            module = {'id': f'4.{len(modules)+1}', 'title': text, 'intro': [], 'sections': []}
            modules.append(module)
            section = block = None
        elif style == 'Heading 3' and module:
            section = {'id': f"{module['id']}.{len(module['sections'])+1}", 'title': text, 'intro': [], 'blocks': []}
            module['sections'].append(section)
            block = None
        elif style == 'Heading 4' and section:
            block = {'title': text, 'text': []}
            section['blocks'].append(block)
        elif module:
            if block is not None:
                block['text'].append(text)
            elif section is not None:
                section['intro'].append(text)
            else:
                module['intro'].append(text)
    suppliers = []
    for file in sorted(supplier_dir.glob('*.docx')):
        name = file.stem
        if name.startswith('13.'):
            label, brand, kind = '崇阳县参考方案（供应商未明确）', '', 'reference'
        else:
            label = name.split('-', 1)[0].split('.', 1)[-1]
            brand, kind = label, 'supplier'
        suppliers.append({'id': hashlib.sha256(file.name.encode()).hexdigest()[:12],
                          'label': label, 'brand': brand, 'kind': kind,
                          'file': file.name, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
                          'text': '\n\n'.join(t for _, t in blocks(Document(file)))})
    # Candidate mappings are editable business configuration, not exclusivity rules.
    mapping = {
        '4.1': ['卫医通', '用友'], '4.2': ['华为-医疗', '卫医通', '用友'],
        '4.3': ['华为-远程', '思科'],
        '4.4.1': ['慧影', '非雀', '武汉鸿鹄'], '4.4.2': ['中旗', '纳龙'],
        '4.4.3': ['迈克'], '4.4.4': ['明理', '江丰'], '4.4.5': ['白象'],
        '4.4.6': ['13.', '先进院'], '4.4.7': ['中移'], '4.4.8': ['华为-远程', '思科'],
        '4.5': ['华为-远程', '思科'], '4.6': ['问安', '先进院'], '4.7': ['问安', '先进院'],
        '4.8': ['先进院'], '4.9': ['问安'], '4.10.1': ['问安'], '4.10.2': ['葆龄'],
        '4.10.3': ['问安'], '4.10.4': ['瑞格'], '4.10.5': ['葆龄'], '4.10.6': ['问安', '葆龄'],
        '4.11': ['问安'], '4.12': ['卫医通', '用友', '华为-远程', '思科']}
    for m in modules:
        for s in m['sections']:
            hints = mapping.get(s['id'], mapping.get(m['id'], []))
            s['supplier_ids'] = [p['id'] for p in suppliers if any(h in p['file'] for h in hints)]
    data = {'version': 1, 'chapter_title': '项目建设内容与设计方案',
            'template_file': template.name, 'template_sha256': hashlib.sha256(template.read_bytes()).hexdigest(),
            'modules': modules, 'suppliers': suppliers}
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--template', type=Path, required=True)
    parser.add_argument('--suppliers', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'data' / 'catalog.json')
    args = parser.parse_args()
    data = import_materials(args.template, args.suppliers, args.output)
    print(f"Imported {len(data['modules'])} modules, {len(data['suppliers'])} solutions.")
