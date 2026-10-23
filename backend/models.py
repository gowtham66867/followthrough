"""Nebius transport, explicit fixture mode and source validation."""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import time
import httpx
from .schemas import Extraction

ENDPOINT = 'https://api.tokenfactory.nebius.com/v1'


def validate_evidence(extraction, messages):
    sources = {m.id: m for m in messages}
    identities = {}
    for claim in extraction.claims:
        identity = identities.setdefault(claim.source_id, claim.opportunity_id)
        if identity != claim.opportunity_id:
            raise ValueError('One message cannot silently link multiple opportunities')
        message = sources.get(claim.source_id)
        if not message or message.body[claim.span_start:claim.span_end] != claim.quote:
            raise ValueError('Evidence rejected: unknown source or quote offsets do not match')
        if claim.span_end <= claim.span_start:
            raise ValueError('Evidence rejected: invalid text span')
        if claim.type == 'requirement' and (not claim.key or not claim.title):
            raise ValueError('Requirement needs a stable key and title')
        if claim.type == 'deadline' and claim.due_at:
            value = datetime.fromisoformat(claim.due_at.replace('Z', '+00:00'))
            if value.utcoffset() is None or not claim.timezone:
                raise ValueError('A proposed deadline needs an explicit timezone')
    return extraction


def anchor_quotes(raw, messages):
    """Locate verbatim evidence; never ask a language model to count characters."""
    sources = {m.id: m.body for m in messages}
    for claim in raw.get('claims', []):
        body = sources.get(claim.get('source_id'))
        quote = claim.get('quote')
        if body is None or not isinstance(quote, str) or not quote:
            raise ValueError('Evidence rejected: unknown source or empty quotation')
        start = body.find(quote)
        if start < 0:
            raise ValueError('Evidence rejected: quotation is absent from the source')
        if body.find(quote, start + 1) >= 0:
            raise ValueError('Evidence needs review: quotation occurs more than once')
        claim['span_start'], claim['span_end'] = start, start + len(quote)
    return raw


class Nebius:
    def __init__(self, config):
        self.config = config

    def key(self):
        key = os.environ.get('NEBIUS_API_KEY') or os.environ.get('NEBIUS_TOKEN_FACTORY_API_KEY')
        if not key:
            raise ValueError('Live mode needs NEBIUS_API_KEY in the server environment')
        return key

    def complete(self, prompt_name, payload):
        key = self.key()
        model = self.config.get('model', '')
        if not model.lower().startswith('nvidia/'):
            raise ValueError('Select an available NVIDIA model in config.yaml for live mode')
        prompt = (Path(__file__).parent / 'prompts' / prompt_name).read_text()
        start = time.monotonic()
        template_options = {}
        if 'enable_thinking' in self.config:
            template_options['chat_template_kwargs'] = {
                'enable_thinking': self.config['enable_thinking'],
            }
        with httpx.Client(timeout=self.config.get('request_timeout_seconds', 90)) as client:
            for attempt in range(3):
                response = client.post(ENDPOINT + '/chat/completions', headers={'Authorization': f'Bearer {key}'}, json={
                    'model': model, 'max_tokens': 6000,
                    'response_format': {'type': 'json_object'}, **template_options,
                    'messages': [{'role': 'system', 'content': prompt},
                                 {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
                })
                if response.status_code not in (429, 500, 502, 503, 504) or attempt == 2:
                    break
                wait = response.headers.get('retry-after', str(2 ** attempt))
                try:
                    delay = float(wait)
                except ValueError:
                    delay = 2 ** attempt
                if delay > 10:
                    raise ValueError('Provider requested a longer pause; retry the job later')
                time.sleep(max(0.5, delay))
        if response.status_code >= 400:
            raise ValueError(f'Nebius returned HTTP {response.status_code}; no fixture fallback was used')
        result = response.json()
        choice = result['choices'][0]
        if choice.get('finish_reason') != 'stop':
            raise ValueError('Incomplete model response; output was not applied')
        content = choice['message']['content']
        parsed = json.loads(content)
        return parsed, {'model': model, 'usage': result.get('usage', {}),
                        'latency_ms': round((time.monotonic() - start) * 1000), 'mode': 'live'}

    def extract(self, messages, opportunities):
        opportunities = [{**op, 'id': op['id'].removeprefix('live-')} for op in opportunities]
        raw, usage = self.complete('extract.txt', {
            'messages': [m.model_dump(mode='json') for m in messages],
            'existing_opportunities': opportunities,
        })
        return validate_evidence(Extraction.model_validate(anchor_quotes(raw, messages)), messages), usage
