"""Synthetic-only browser regression server; never reads production state."""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from ui import create_server
from ui_service import Application
from web_sources import SourcePolicy
from search_discovery import SearchResult


class FixtureProvider:
    name = 'local'

    def search(self, query, *, limit):
        return [SearchResult('Fixture', 'https://agency.example/record',
                             'SNIPPET_NOT_EVIDENCE', 'local', 1, '2026-01-01')]


def main():
    body = (b'<title>&lt;script&gt;inert()&lt;/script&gt;</title>'
            b'<meta name="date" content="2026-01-01">'
            b'<h2>Flight record</h2><p>Test booster reflight occurred.</p>')
    with tempfile.TemporaryDirectory(prefix='tre-ui-smoke-') as directory:
        policy = SourcePolicy({'agency.example': {'allowed': True, 'tier': 1,
                              'type': 'government', 'publisher': 'Synthetic Agency'}})
        app = Application(Path(directory), policy)
        with patch('ui_service.configured_provider', return_value=FixtureProvider()), \
             patch('verify.Fetcher.fetch', return_value=(body, 'text/html')):
            server = create_server(8001, app)
            print('SYNTHETIC TEST ONLY: http://127.0.0.1:8001', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()


if __name__ == '__main__':
    main()
