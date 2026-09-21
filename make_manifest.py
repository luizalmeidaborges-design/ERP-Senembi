"""Cria o manifesto do release, incluindo SHA-256 e tamanho exato do EXE."""
import hashlib
import json
import os
from pathlib import Path

version = os.environ['RELEASE_VERSION']
repo = os.environ['GITHUB_REPOSITORY']
exe = Path('dist/ERP_Senembi.exe')
data = {'schema': 1, 'version': version,
        'url': f'https://github.com/{repo}/releases/download/v{version}/ERP_Senembi.exe',
        'sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
        'size_bytes': exe.stat().st_size}
Path('dist/update.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
