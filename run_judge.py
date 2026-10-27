"""Serve a separate fictional judge workspace behind an HTTPS invitation gate."""
import argparse
import json
import os
from pathlib import Path
import uvicorn
import yaml
from backend.app import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--credentials', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, required=True, help='Dedicated judge data; never your personal workspace')
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8787)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text())
    credentials = json.loads(args.credentials.read_text())
    if not isinstance(config, dict) or not isinstance(credentials, dict):
        parser.error('Use a YAML config mapping and a private JSON credential mapping')
    token = credentials.get('JUDGE_ACCESS_TOKEN', '')
    if not isinstance(token, str) or len(token) < 32:
        parser.error('Credentials need a generated JUDGE_ACCESS_TOKEN of at least 32 characters')
    config['judge_access']['token'] = token
    config['provider_budget']['ledger'] = str(args.data_dir / 'provider-allowance.sqlite3')
    for name in ('NEBIUS_API_KEY', 'NEBIUS_TOKEN_FACTORY_API_KEY'):
        if credentials.get(name):
            os.environ[name] = credentials[name]
    # No personal Gmail OAuth is available in the shared judge deployment.
    config.pop('gmail_client_id', None)
    app = create_app(args.data_dir, config, args.port)
    uvicorn.run(app, host=args.bind, port=args.port, access_log=False, proxy_headers=False)


if __name__ == '__main__':
    main()
