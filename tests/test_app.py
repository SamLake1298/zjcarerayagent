import io
import json
import unittest
import zipfile
import tempfile
from pathlib import Path
from unittest.mock import patch
from docx import Document
from app.generator import validate_request, generate_section, parse_output, completion, outline
from app.documents import export_docx

CATALOG = json.loads((Path(__file__).resolve().parents[1] / 'data/catalog.json').read_text(encoding='utf-8'))
SECTION = CATALOG['modules'][3]['sections'][1]

class GenerationTests(unittest.TestCase):
    def payload(self, **extra):
        return {'mode': 'demo', 'project': {'name': '测试县强基工程'},
                'selections': [{'id': SECTION['id'], 'supplier': SECTION['supplier_ids'][0]}], **extra}

    def test_real_materials_structure(self):
        self.assertEqual(len(CATALOG['modules']), 12)
        self.assertEqual(sum(len(m['sections']) for m in CATALOG['modules']), 50)
        self.assertEqual(len(CATALOG['suppliers']), 20)
        reference = next(p for p in CATALOG['suppliers'] if p['file'].startswith('13.'))
        self.assertEqual(reference['kind'], 'reference')
        self.assertEqual(reference['brand'], '')

    def test_invalid_selection_and_supplier(self):
        for selections in [[], [{'id': '../secret'}], [{'id': SECTION['id'], 'supplier': 'unknown'}],
                           [{'id': SECTION['id']}, {'id': SECTION['id']}]]:
            with self.assertRaises(ValueError):
                validate_request(self.payload(selections=selections), CATALOG)

    def test_real_mode_requires_key_and_secret_not_persisted(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(ValueError):
                validate_request(self.payload(mode='deepseek'), CATALOG)
        request, key = validate_request(self.payload(mode='deepseek', api_key='test-secret'), CATALOG)
        self.assertEqual(key, 'test-secret')
        self.assertNotIn('test-secret', json.dumps(request))

    def test_actual_material_in_model_prompt(self):
        request, key = validate_request(self.payload(mode='deepseek', api_key='test-secret'), CATALOG)
        supplier = next(s for s in CATALOG['suppliers'] if s['id'] == SECTION['supplier_ids'][0])
        def fake(messages, token, model):
            self.assertEqual(token, 'test-secret')
            body = json.loads(messages[1]['content'])
            self.assertEqual(body['supplier_reference'], supplier['text'])
            self.assertEqual(body['section']['id'], SECTION['id'])
            self.assertIn('不可信参考资料', messages[0]['content'])
            return json.dumps({'blocks': [{'title': b['title'], 'paragraphs': ['拟完善县乡村心电协同诊断体系。']} for b in outline(SECTION)]})
        blocks = generate_section(SECTION, supplier, request, key, ['纳龙'], transport=fake)
        self.assertEqual([b['title'] for b in blocks], [b['title'] for b in outline(SECTION)])

    def test_wrong_headings_and_brand_rejected(self):
        valid = {'blocks': [{'title': b['title'], 'paragraphs': ['拟建设心电网络。']} for b in outline(SECTION)]}
        valid['blocks'][0]['paragraphs'] = ['采用纳龙品牌的产品。']
        with self.assertRaisesRegex(ValueError, '品牌'):
            parse_output(json.dumps(valid), SECTION, ['纳龙'])
        valid['blocks'][0] = {'title': '擅自改写标题', 'paragraphs': ['正文']}
        with self.assertRaisesRegex(ValueError, '结构'):
            parse_output(json.dumps(valid), SECTION, [])

    def test_demo_no_model_and_docx_preserves_heading_structure(self):
        request, key = validate_request(self.payload(), CATALOG)
        def forbidden(*args):
            self.fail('演示模式不应调用API')
        blocks = generate_section(SECTION, None, request, key, [], transport=forbidden)
        result = {'project': request['project'], 'mode': 'demo', 'sections': [{
            'id': SECTION['id'], 'title': SECTION['title'], 'module_id': '4.4',
            'module_title': CATALOG['modules'][3]['title'], 'blocks': blocks}]}
        binary = export_docx(result)
        doc = Document(io.BytesIO(binary))
        with zipfile.ZipFile(io.BytesIO(binary)) as package:
            self.assertFalse(any(n.startswith(('word/media/', 'customXml/')) for n in package.namelist()))
        texts = [p.text for p in doc.paragraphs]
        self.assertIn('第四章 项目建设内容与设计方案', texts)
        self.assertIn('4.4.2 心电诊断中心', texts)
        self.assertTrue(any('演示文件' in t for t in texts))
        self.assertFalse(any('项目建设与运营管理' in t for t in texts))
        self.assertEqual(sum(p.style.name == 'Heading 4' for p in doc.paragraphs), len(SECTION['blocks']))
        self.assertAlmostEqual(doc.sections[0].page_width.cm, 21, places=2)

    def test_http_client_protocol_and_error(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self, _): return b'{"choices":[{"finish_reason":"stop","message":{"content":"{}"}}]}'
        with patch('urllib.request.urlopen', return_value=Response()) as call:
            self.assertEqual(completion([{'role': 'user', 'content': 'json'}], 'test-secret', 'deepseek-flash'), '{}')
            req = call.call_args.args[0]
            self.assertEqual(req.full_url, 'https://api.deepseek.com/chat/completions')
            self.assertEqual(req.get_header('Authorization'), 'Bearer test-secret')

    def test_harmless_format_variants_normalized(self):
        blocks = [{'title': b['title'], 'paragraphs': '第一段。\n\n第二段。'} for b in outline(SECTION)]
        blocks[1]['title'] = '4.4.2.1  标准化建设 '
        result = parse_output(json.dumps({'blocks': blocks}), SECTION, [])
        self.assertEqual(result[1]['title'], '标准化建设')
        self.assertEqual(result[0]['paragraphs'], ['第一段。', '第二段。'])

    def test_format_failure_retries_once_with_skeleton(self):
        request, key = validate_request(self.payload(mode='deepseek', api_key='test-secret'), CATALOG)
        calls = []
        def fake(messages, *_):
            calls.append(len(messages))
            if len(calls) == 1:
                return '{"blocks": []}'
            self.assertIn('JSON骨架', messages[-1]['content'])
            return json.dumps({'blocks': [{'title': b['title'], 'paragraphs': ['拟完善服务体系。']} for b in outline(SECTION)]})
        result = generate_section(SECTION, None, request, key, [], transport=fake)
        self.assertEqual(calls, [2, 3])
        self.assertEqual(len(result), len(outline(SECTION)))

    def test_repeated_failure_has_specific_reason_and_bound(self):
        request, key = validate_request(self.payload(mode='deepseek', api_key='test-secret'), CATALOG)
        calls = []
        def fake(*_):
            calls.append(1)
            return '{"blocks": []}'
        with self.assertRaisesRegex(ValueError, '实际返回0个.*自动修正一次'):
            generate_section(SECTION, None, request, key, [], transport=fake)
        self.assertEqual(len(calls), 2)

    def test_later_failure_preserves_completed_section_without_key(self):
        from app import server
        request, key = validate_request(self.payload(selections=[{'id': '4.4.2'}, {'id': '4.4.4'}]), CATALOG)
        job_id = 'checkpoint-test'
        server.JOBS[job_id] = {'completed': 0, 'total': 2, 'status': 'running'}
        calls = []
        def fake(section, *args):
            calls.append(section['id'])
            if len(calls) == 2:
                raise ValueError('模拟第二节结构失败')
            return [{'title': '', 'paragraphs': ['已完成的正文。']}]
        with tempfile.TemporaryDirectory() as directory:
            server.ACTIVE.acquire()
            with patch.object(server, 'ROOT', Path(directory)), patch.object(server, 'generate_section', side_effect=fake):
                server.run_job(job_id, request, 'secret-must-not-be-saved')
            files = list((Path(directory) / 'outputs/checkpoints').glob('*.json'))
            self.assertEqual(len(files), 1)
            raw = files[0].read_text(encoding='utf-8')
            self.assertNotIn('secret-must-not-be-saved', raw)
            self.assertEqual(len(json.loads(raw)['sections']), 1)
            self.assertEqual(server.JOBS[job_id]['status'], 'error')
            self.assertIn('已完成的1个子节已保存', server.JOBS[job_id]['error'])
        del server.JOBS[job_id]

if __name__ == '__main__':
    unittest.main()
