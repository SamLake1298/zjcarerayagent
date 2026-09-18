"""Local-only MVP server. Run with: python -m app.server"""
import argparse
import json
import mimetypes
import re
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from app.generator import validate_request, generate_section
from app.documents import export_docx

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))
JOBS, LOCK = {}, threading.RLock()
ACTIVE = threading.BoundedSemaphore(1)
BRANDS = list({p['brand'] for p in CATALOG['suppliers'] if p['brand']}) + [
    '华为', '用友', '思科', '纳龙', '中旗', '白象', '葆龄', '慧影', '问安', '飞雀', '非雀',
    '鸿鹄', '迈克', '瑞格', '明理', '江丰', '崇阳县', '昇腾', '鲲鹏', 'MindSpore', 'Cisco', 'Huawei']

def public_catalog():
    return {'chapter_title': CATALOG['chapter_title'], 'modules': [
        {'id': m['id'], 'title': m['title'], 'sections': [
            {k: s[k] for k in ('id', 'title', 'supplier_ids')} | {'headings': [b['title'] for b in s['blocks']]}
            for s in m['sections']]} for m in CATALOG['modules']],
        'suppliers': [{k: s[k] for k in ('id', 'label', 'file', 'kind')} for s in CATALOG['suppliers']]}

def run_job(job_id, request, key):
    try:
        selected = {s['id']: s['supplier'] for s in request['selections']}
        suppliers = {s['id']: s for s in CATALOG['suppliers']}
        result = {'id': job_id, 'mode': request['mode'], 'model': request['model'],
                  'project': request['project'], 'selections': request['selections'], 'sections': [],
                  'created_at': datetime.now().isoformat(timespec='seconds')}
        for module in CATALOG['modules']:
            for section in module['sections']:
                if section['id'] not in selected:
                    continue
                with LOCK:
                    JOBS[job_id]['current'] = section['id'] + ' ' + section['title']
                supplier = suppliers.get(selected[section['id']])
                generated = generate_section(section, supplier, request, key, BRANDS)
                result['sections'].append({'id': section['id'], 'title': section['title'],
                    'module_id': module['id'], 'module_title': module['title'], 'blocks': generated})
                checkpoint_dir = ROOT / 'outputs' / 'checkpoints'
                checkpoint_dir.mkdir(parents=True, exist_ok=True)
                checkpoint_path = checkpoint_dir / f'{job_id}-{len(result["sections"]):02d}.json'
                if checkpoint_path.exists():
                    raise ValueError('阶段结果文件冲突，已停止，未覆盖现有文件')
                with checkpoint_path.open('x', encoding='utf-8') as checkpoint:
                    json.dump(result, checkpoint, ensure_ascii=False, indent=2)
                with LOCK:
                    JOBS[job_id]['completed'] += 1
        output = ROOT / 'outputs'
        output.mkdir(exist_ok=True)
        json_path, docx_path = output / f'{job_id}.json', output / f'{job_id}.docx'
        if json_path.exists() or docx_path.exists():
            raise ValueError('输出文件冲突，已停止，未覆盖现有文件')
        document = export_docx(result)
        with docx_path.open('xb') as f:
            f.write(document)
        with json_path.open('x', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        with LOCK:
            JOBS[job_id].update(status='done', result=result, current='生成完成')
    except Exception as e:
        # Never return raw network data, request headers or API keys to the client/log.
        message = str(e) if isinstance(e, ValueError) else '生成失败，请检查材料配置或本地输出目录权限'
        with LOCK:
            completed = JOBS[job_id]['completed']
            if completed:
                message += f'。已完成的{completed}个子节已保存在本机outputs/checkpoints目录'
            JOBS[job_id].update(status='error', error=message)
    finally:
        key = None
        ACTIVE.release()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def local_request(self):
        host = self.headers.get('Host', '')
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        origin = self.headers.get('Origin')
        return host in allowed and (not origin or origin in {'http://' + h for h in allowed})

    def send(self, status, body, kind='application/json; charset=utf-8', filename=None):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.local_request():
            return self.send(403, {'error': '仅允许本机访问'})
        path = urlparse(self.path).path
        if path == '/api/catalog':
            return self.send(200, public_catalog())
        match = re.fullmatch(r'/api/jobs/([a-f0-9]{32})(/download)?', path)
        if match:
            with LOCK:
                job = dict(JOBS.get(match[1], {}))
            if not job:
                return self.send(404, {'error': '任务不存在，服务重启后请重新生成；已有文件保存在outputs目录'})
            if match[2]:
                if job['status'] != 'done':
                    return self.send(409, {'error': '文件尚未生成'})
                return self.send(200, (ROOT / 'outputs' / f'{match[1]}.docx').read_bytes(),
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document', f'chapter4-{match[1][:8]}.docx')
            return self.send(200, job)
        pages = {'/': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css'}
        if path in pages:
            file = ROOT / 'web' / pages[path]
            kind = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css'}[file.suffix]
            return self.send(200, file.read_bytes(), kind + '; charset=utf-8')
        self.send(404, {'error': '页面不存在'})

    def do_POST(self):
        if not self.local_request():
            return self.send(403, {'error': '仅允许本机访问'})
        if self.path != '/api/generate':
            return self.send(404, {'error': '接口不存在'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.send(415, {'error': '需要JSON请求'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 100_000:
                raise ValueError('请求大小不合法')
            body = json.loads(self.rfile.read(length))
            request, key = validate_request(body, CATALOG)
        except (ValueError, TypeError, AttributeError):
            return self.send(400, {'error': '请检查项目字段、章节和方案选择；DeepSeek模式必须提供有效格式的密钥及模型名'})
        if not ACTIVE.acquire(blocking=False):
            return self.send(409, {'error': '已有任务正在生成，请等待完成'})
        job_id = uuid.uuid4().hex
        with LOCK:
            JOBS[job_id] = {'id': job_id, 'status': 'running', 'completed': 0,
                            'total': len(request['selections']), 'current': '准备生成'}
        threading.Thread(target=run_job, args=(job_id, request, key), daemon=True).start()
        self.send(202, {'id': job_id})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Project proposal Agent: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
