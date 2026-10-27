"""Opt-in single-workspace invitation gate; public deployments require HTTPS."""
from datetime import datetime, timezone
import html
import secrets
from urllib.parse import parse_qs, urlsplit

from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse


class JudgeAccess:
    def __init__(self, settings):
        self.settings = settings
        self.origin = settings['origin'].rstrip('/')
        parsed = urlsplit(self.origin)
        if (parsed.scheme != 'https' or parsed.path or parsed.query or parsed.fragment
                or parsed.username or parsed.password or not parsed.hostname):
            raise ValueError('Judge origin must be one exact HTTPS origin')
        if len(settings['token']) < 32:
            raise ValueError('Use a generated judge invitation token of at least 32 characters')
        self.host = parsed.netloc
        self.session = secrets.token_urlsafe(40)
        self.expires = datetime.fromisoformat(settings['expires_at'].replace('Z', '+00:00'))
        if self.expires.utcoffset() is None:
            raise ValueError('Judge expiry must include its timezone')

    def expired(self):
        return datetime.now(timezone.utc) >= self.expires

    async def handle(self, request):
        if self.expired():
            return JSONResponse({'error': 'Judge access expired'}, status_code=403)
        if request.url.path == '/health':
            return None
        if request.url.path.startswith('/api/gmail') or request.url.path == '/api/connectors/gmail':
            return JSONResponse({'error': 'Gmail is disabled in the shared judge workspace'}, status_code=404)
        if request.url.path == '/judge/session' and request.method == 'POST':
            if request.headers.get('origin') != self.origin:
                return JSONResponse({'error': 'Open the judge sign-in page first'}, status_code=403)
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 2048:
                    return JSONResponse({'error': 'Invitation rejected'}, status_code=400)
            supplied = parse_qs(raw.decode('utf-8', errors='replace')).get('token', [''])[0]
            if not secrets.compare_digest(supplied.encode(), self.settings['token'].encode()):
                return JSONResponse({'error': 'Invitation rejected'}, status_code=403)
            response = RedirectResponse('/', status_code=303)
            remaining = max(0, int((self.expires - datetime.now(timezone.utc)).total_seconds()))
            response.set_cookie('followthrough_judge', self.session, secure=True, httponly=True,
                                samesite='strict', max_age=min(remaining, 86400))
            return response
        if secrets.compare_digest(request.cookies.get('followthrough_judge', '').encode(), self.session.encode()):
            return None
        if request.url.path == '/' and request.method == 'GET':
            return HTMLResponse('''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>FollowThrough judge access</title>
<body style="font:16px/1.7 system-ui;background:#f5f6f0;color:#243b33;max-width:620px;margin:8vh auto;padding:24px">
<h1>FollowThrough / judge workspace</h1><p>One shared, temporary demonstration workspace.
Use fictional documents only. Other invited judges can see its contents. This is not an organization account.</p>
<p>Live NVIDIA inference uses the owner’s Nebius key on the server, with a finite request allowance.
Exhausted or failed calls never switch to simulated success. No automatic top-up is provided.</p>
<form method="post" action="/judge/session"><label>Invitation token<br>
<input name="token" type="password" required autocomplete="off" style="width:100%;padding:12px"></label>
<button style="margin-top:18px;padding:12px">Open judge workspace</button></form>
<p>Access expires: ''' + html.escape(self.settings['expires_at']) + '</p></body></html>')
        return JSONResponse({'error': 'Judge invitation required'}, status_code=401)
