"""Judge boundary and finite provider allowance exercise real HTTP and persistent SQLite."""
from contextlib import contextmanager
import importlib
import json
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
from fastapi.testclient import TestClient


def configuration(tmp_path):
    return {'judge_access': {'origin': 'https://judge.example', 'token': 'fictional-invitation-' * 3,
                            'expires_at': '2099-01-01T00:00:00Z'},
            'provider_budget': {'ledger': str(tmp_path/'allowance.sqlite3'), 'max_requests': 2,
                'max_output_tokens': 10000, 'max_request_bytes': 20000,
                'models': ['nvidia/test'], 'expires_at': '2099-01-01T00:00:00Z'}}


def test_judge_gate_does_not_issue_workspace_access_before_invitation(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    create_app = importlib.import_module('backend.app').create_app
    config = configuration(tmp_path)
    with TestClient(create_app(tmp_path/'workspace', config), base_url='https://judge.example') as client:
        response = client.get('/')
        assert 'fictional documents only' in response.text and not client.cookies
        assert client.get('/api/snapshot').status_code == 401
        assert client.get('/assets/private.js').status_code == 401
        assert client.post('/judge/session', data={'token': config['judge_access']['token']}).status_code == 403
        assert client.post('/judge/session', data={'token': 'wrong'}, headers={'Origin':'https://judge.example'}).status_code == 403
        response = client.post('/judge/session', data={'token':config['judge_access']['token']},
                               headers={'Origin':'https://judge.example'}, follow_redirects=False)
        assert response.status_code == 303
        cookie = response.headers['set-cookie']
        assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=strict' in cookie
        assert client.get('/api/snapshot').status_code == 401
        client.get('/')
        assert client.get('/api/snapshot').status_code == 200
        assert client.get('/api/gmail/start').status_code == 404
        assert client.get('/api/snapshot', headers={'Origin':'https://attacker.example'}).status_code == 403
        assert client.get('/api/snapshot', headers={'Host':'attacker.example'}).status_code == 403
        assert client.post('/api/proposals/demo').status_code == 200
    # The session is revoked on server restart; the same invitation can start another session.
    with TestClient(create_app(tmp_path/'workspace', config), base_url='https://judge.example') as restarted:
        assert restarted.get('/api/snapshot').status_code == 401
    config['judge_access']['expires_at'] = '2000-01-01T00:00:00Z'
    with TestClient(create_app(tmp_path/'workspace', config), base_url='https://judge.example') as expired:
        assert expired.get('/').status_code == 403


def test_attempt_budget_counts_retries_and_survives_reconstruction(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    models = importlib.import_module('backend.models')
    received = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            payload = b'{"ok":true}'
            self.send_response(429 if len(received) == 1 else 200)
            self.send_header('Retry-After','0')
            self.send_header('Content-Length',str(len(payload)))
            self.end_headers(); self.wfile.write(payload)
        def log_message(self, *args): pass
    server = HTTPServer(('127.0.0.1',0),Handler)
    worker = threading.Thread(target=server.serve_forever,daemon=True); worker.start()
    monkeypatch.setattr(models,'ENDPOINT',f'http://127.0.0.1:{server.server_port}')
    monkeypatch.setenv('NEBIUS_API_KEY','fictional-http-contract-key')
    config = configuration(tmp_path)
    try:
        provider = models.Nebius(config)
        with pytest.raises(ValueError, match='Model is outside'):
            provider.request('/chat/completions', {'model':'nvidia/other','max_tokens':10})
        result, _ = provider.request('/chat/completions', {'model':'nvidia/test','max_tokens':10})
        assert result['ok'] and len(received) == 2
        with pytest.raises(ValueError, match='exhausted'):
            models.Nebius(configuration(tmp_path)).request('/chat/completions', {'model':'nvidia/test','max_tokens':10})
        assert len(received) == 2
    finally:
        server.shutdown(); worker.join(timeout=5); server.server_close()
