"""Run the single-owner workspace on loopback. Keep one server per data directory."""
import argparse
import json
import os
from pathlib import Path
import uvicorn
import yaml
from backend.app import create_app

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', type=int, default=8787)
parser.add_argument('--data-dir', type=Path, default=Path(__file__).parent / '.data')
parser.add_argument('--config', type=Path, default=Path(__file__).parent / 'config.yaml')
parser.add_argument('--credentials', type=Path, help='Private JSON file containing provider secrets')
args = parser.parse_args()
credentials_path = args.credentials or args.data_dir / 'credentials.json'
if credentials_path.exists():
    credentials = json.loads(credentials_path.read_text())
    allowed_secrets = {'NEBIUS_API_KEY', 'NEBIUS_TOKEN_FACTORY_API_KEY', 'GOOGLE_CLIENT_SECRET'}
    if not isinstance(credentials, dict) or any(
        name not in allowed_secrets or not isinstance(value, str) or not value.strip()
        for name, value in credentials.items()
    ):
        parser.error('Credentials must contain only nonempty supported secret values')
    for name, value in credentials.items():
        os.environ.setdefault(name, value)
config = yaml.safe_load(args.config.read_text()) if args.config.exists() else {}
if not isinstance(config, dict):
    parser.error('Configuration must be a YAML mapping')
app = create_app(args.data_dir, config, args.port)
uvicorn.run(app, host='127.0.0.1', port=args.port, access_log=False)
