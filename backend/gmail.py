"""Read-only OAuth and selected Gmail messages. Tokens stay on this computer."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import os
import secrets
import time
from urllib.parse import urlencode
import httpx
from .schemas import Message

SCOPES = 'https://www.googleapis.com/auth/gmail.readonly'


class TextHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag in ('p', 'br', 'div', 'li') and not self.hidden:
            self.text.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


def body_text(payload):
    plain, html = [], []
    def walk(part):
        data = part.get('body', {}).get('data')
        if data:
            text = base64.urlsafe_b64decode(data + '=' * (-len(data) % 4)).decode('utf-8', errors='replace')
            if part.get('mimeType') == 'text/plain':
                plain.append(text)
            elif part.get('mimeType') == 'text/html':
                parser = TextHTML()
                parser.feed(text)
                html.append(''.join(parser.text))
        for child in part.get('parts', []):
            walk(child)
    walk(payload)
    return '\n'.join(plain or html).strip()


class Gmail:
    def __init__(self, directory, config):
        self.path, self.config = directory / 'gmail-tokens.json', config
        self.pending = {}

    def status(self):
        return {'configured': bool(self.config.get('gmail_client_id') and os.environ.get('GOOGLE_CLIENT_SECRET')),
                'connected': self.path.exists(), 'scope': 'Gmail read-only',
                'storage': 'Local token file protected by filesystem permissions; not encrypted at rest'}

    def start(self):
        if not self.status()['configured']:
            raise ValueError('Set gmail_client_id in config.yaml and GOOGLE_CLIENT_SECRET in the server environment')
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        self.pending = {state: (verifier, time.time() + 600)}
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
            'client_id': self.config['gmail_client_id'], 'redirect_uri': self.config['gmail_redirect_uri'],
            'response_type': 'code', 'scope': SCOPES, 'state': state,
            'access_type': 'offline', 'prompt': 'consent', 'code_challenge': challenge,
            'code_challenge_method': 'S256',
        })

    def exchange(self, values):
        with httpx.Client(timeout=30) as client:
            response = client.post('https://oauth2.googleapis.com/token', data={
                'client_id': self.config['gmail_client_id'],
                'client_secret': os.environ.get('GOOGLE_CLIENT_SECRET', ''), **values,
            })
        if response.status_code >= 400:
            raise ValueError('Google could not authorize this connection. Reconnect Gmail.')
        return response.json()

    def save(self, tokens):
        tokens['expires_at'] = time.time() + tokens.get('expires_in', 3600) - 60
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, 'w') as handle:
            json.dump(tokens, handle)

    def callback(self, code, state):
        pending = self.pending.pop(state, None)
        if not pending or pending[1] < time.time():
            raise ValueError('OAuth state expired or did not match; reconnect Gmail')
        tokens = self.exchange({'grant_type': 'authorization_code', 'code': code,
                                'redirect_uri': self.config['gmail_redirect_uri'], 'code_verifier': pending[0]})
        if SCOPES not in tokens.get('scope', '').split():
            raise ValueError('Gmail read permission was not granted')
        self.save(tokens)

    def access(self):
        if not self.path.exists():
            raise ValueError('Connect Gmail first')
        tokens = json.loads(self.path.read_text())
        if tokens['expires_at'] < time.time():
            if not tokens.get('refresh_token'):
                raise ValueError('Gmail connection expired. Reconnect it.')
            refreshed = self.exchange({'grant_type': 'refresh_token', 'refresh_token': tokens['refresh_token']})
            tokens.update(refreshed)
            self.save(tokens)
        return tokens['access_token']

    def get(self, path, params=None):
        with httpx.Client(timeout=30) as client:
            response = client.get('https://gmail.googleapis.com/gmail/v1/users/me/' + path,
                                  headers={'Authorization': 'Bearer ' + self.access()}, params=params)
        if response.status_code >= 400:
            raise ValueError(f'Gmail returned HTTP {response.status_code}; reconnect or retry after quota resets')
        return response.json()

    def search(self, query, page_token=None):
        result = self.get('messages', {'q': query, 'maxResults': 15, **({'pageToken': page_token} if page_token else {})})
        summaries = []
        for entry in result.get('messages', []):
            item = self.get('messages/' + entry['id'], {'format': 'metadata', 'metadataHeaders': ['Subject', 'From']})
            headers = {h['name'].lower(): h['value'] for h in item['payload'].get('headers', [])}
            summaries.append({'id': item['id'], 'subject': headers.get('subject', '(no subject)'), 'sender': headers.get('from', '')})
        return {'messages': summaries, 'next_page_token': result.get('nextPageToken')}

    def selected(self, ids):
        profile = self.get('profile')
        account = hashlib.sha256(profile['emailAddress'].encode()).hexdigest()[:16]
        messages = []
        for message_id in ids:
            if not message_id.isalnum():
                raise ValueError('Invalid Gmail message ID')
            item = self.get('messages/' + message_id, {'format': 'full'})
            payload = item['payload']
            headers = {h['name'].lower(): h['value'] for h in payload.get('headers', [])}
            body = body_text(payload)
            if not body:
                raise ValueError('A selected message has no supported text body')
            messages.append(Message(id=f'gmail-{account}-{item["id"]}', thread_id=f'gmail-{account}-{item["threadId"]}',
                                    subject=headers.get('subject') or '(no subject)', sender=headers.get('from') or '(unknown sender)',
                                    received_at=datetime.fromtimestamp(int(item['internalDate']) / 1000, timezone.utc), body=body,
                                    external_url='https://mail.google.com/mail/u/0/#all/' + item['id']))
        return messages

    def disconnect(self):
        if self.path.exists():
            tokens = json.loads(self.path.read_text())
            token = tokens.get('refresh_token') or tokens.get('access_token')
            with httpx.Client(timeout=20) as client:
                response = client.post('https://oauth2.googleapis.com/revoke', data={'token': token})
            if response.status_code not in (200, 400):
                raise ValueError('Google revocation failed; retry disconnect or revoke access in your Google account')
            self.path.unlink()
        self.pending.clear()
