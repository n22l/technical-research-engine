"""Local-only browser interface. Start with python -B src/ui.py."""
import sys
sys.dont_write_bytecode = True
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from ui_service import Application, UIError
from verification_models import digest

ASSETS = Path(__file__).resolve().parent / 'ui_assets'


def create_server(port=8000, application=None):
    token = secrets.token_urlsafe(32)
    try:
        app = application or Application()
    except Exception:
        app = None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # No research text, filenames, URLs or credentials in access logs.

        def send(self, value, status=200, mime='application/json; charset=utf-8'):
            body = json.dumps(value, ensure_ascii=False).encode() if mime.startswith('application/json') else value.encode()
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def allowed(self, api=False):
            host = '127.0.0.1:' + str(self.server.server_port)
            if self.headers.get('Host') != host:
                return False
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                # A link from another site may open the app, but may not read
                # APIs, embed the page, load assets, or submit mutations.
                entry_navigation = (self.command == 'GET' and urlsplit(self.path).path == '/'
                                    and self.headers.get('Sec-Fetch-Mode') == 'navigate'
                                    and self.headers.get('Sec-Fetch-Dest') == 'document')
                if not entry_navigation:
                    return False
            if self.command == 'POST' and self.headers.get('Origin') != 'http://' + host:
                return False
            return not api or secrets.compare_digest(self.headers.get('X-UI-Token', ''), token)

        def do_GET(self):
            path = urlsplit(self.path).path
            if not self.allowed(path.startswith('/api/')):
                return self.send({'error': 'Local request rejected. Open http://127.0.0.1:' + str(self.server.server_port) + '/ directly and refresh the page. An older tab may have an expired session.'}, 403)
            if path == '/health':
                return self.send({'application': 'technical-research-engine', 'configured': app is not None,
                                  'storage_id': digest(str(app.base)) if app else None})
            assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
            if path in assets:
                file, mime = assets[path]
                return self.send((ASSETS / file).read_text(encoding='utf-8').replace('__UI_TOKEN__', token), mime=mime + '; charset=utf-8')
            try:
                if path == '/api/config':
                    return self.send(app.configuration() if app else {'configured': False})
                if app is None:
                    raise UIError('The engine needs an external private research directory. Set TECH_RESEARCH_DATA_DIR and restart.')
                parts = path.strip('/').split('/')
                if path == '/api/source-suggestions':
                    return self.send(app.source_suggestions())
                if path == '/api/history':
                    return self.send(app.history())
                if len(parts) == 3 and parts[:2] == ['api', 'run']:
                    return self.send(app.view(parts[2]))
                if len(parts) == 3 and parts[:2] == ['api', 'job']:
                    return self.send(app.job(parts[2]))
                if len(parts) == 4 and parts[:2] == ['api', 'export'] and parts[3] in ('json', 'markdown'):
                    return self.send(app.export(parts[2], parts[3]), mime='text/plain; charset=utf-8')
                return self.send({'error': 'Not found.'}, 404)
            except UIError as exc:
                self.send({'error': str(exc)}, 400)
            except OSError:
                self.send({'error': 'Unable to read private research. Check folder access and available storage.'}, 400)
            except Exception:
                self.send({'error': 'Unable to read private research state safely.'}, 400)

        def do_POST(self):
            if not self.allowed(True):
                return self.send({'error': 'Local request rejected. Refresh the page after an engine restart, then try again.'}, 403)
            try:
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise UIError('JSON request required.')
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 100000:
                    raise UIError('Request size is invalid.')
                values = json.loads(self.rfile.read(length))
                if not isinstance(values, dict):
                    raise UIError('Invalid request.')
                if app is None:
                    raise UIError('Configure TECH_RESEARCH_DATA_DIR and restart.')
                if self.path == '/api/source-suggestions':
                    return self.send(app.suggest_source(values), 201)
                if self.path == '/api/source-decisions':
                    return self.send(app.decide_source(values))
                if self.path == '/api/history-delete':
                    if type(values.get('deleted')) is not bool:
                        raise UIError('Choose delete or restore.')
                    return self.send(app.set_history_deleted(values.get('run_id', ''), values['deleted']))
                if self.path == '/api/research':
                    return self.send(app.start(values), 202)
                if self.path == '/api/review':
                    return self.send(app.save_review(values.get('run_id', ''), values))
                if self.path == '/api/verify':
                    return self.send(app.verify(values.get('run_id', ''), values.get('revision')))
                return self.send({'error': 'Not found.'}, 404)
            except UIError as exc:
                self.send({'error': str(exc)}, 400)
            except OSError:
                self.send({'error': 'Unable to save private research. Check folder write permissions and free disk space; restart with launch.py --data-dir PATH.'}, 400)
            except Exception:
                self.send({'error': 'Request failed. Check the fields and private configuration.'}, 400)

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server


if __name__ == '__main__':
    from startup import main
    raise SystemExit(main())
