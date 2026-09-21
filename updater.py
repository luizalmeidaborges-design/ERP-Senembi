"""Baixa releases mais recentes com verificação SHA-256 antes de executar."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

REPO = 'luizalmeidaborges-design/ERP-Senembi'
VERSION = re.compile(r'^\d+\.\d+\.\d+$')


def ver(value):
    if not isinstance(value, str) or not VERSION.fullmatch(value): raise ValueError('Versão inválida.')
    return tuple(int(x) for x in value.split('.'))


def read_config(path):
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    ver(config['version'])
    return config


def safe_url(url):
    parts = urlparse(url)
    allowed = ('github.com', 'objects.githubusercontent.com', 'release-assets.githubusercontent.com')
    if parts.scheme != 'https' or parts.hostname not in allowed:
        raise ValueError('O download deve vir do release do GitHub por HTTPS.')
    if parts.hostname == 'github.com':
        prefix = '/'+REPO+'/releases/'
        latest_manifest = prefix+'latest/download/update.json'
        versioned_asset = re.fullmatch(
            re.escape(prefix)+r'download/v\d+\.\d+\.\d+/(?:update\.json|ERP_Senembi\.exe)',
            parts.path)
        if parts.path != latest_manifest and not versioned_asset:
            raise ValueError('Endereço fora do repositório Senembi.')
    return url


def cached(config, folder):
    marker = Path(folder) / 'updates' / 'ready.json'
    try:
        info = json.loads(marker.read_text(encoding='utf-8'))
        if ver(info['version']) <= ver(config['version']): return None
        exe = marker.parent / ('ERP_Senembi-'+info['version']+'.exe')
        if not re.fullmatch('[a-f0-9]{64}', info['sha256']) or not exe.is_file(): return None
        if hashlib.sha256(exe.read_bytes()).hexdigest() == info['sha256']: return exe
    except (OSError, KeyError, TypeError, ValueError): pass
    return None


def launch_cached(config, folder):
    if not getattr(sys, 'frozen', False): return False
    exe = cached(config, folder)
    if exe is None: return False
    env = dict(os.environ)
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    try: subprocess.Popen([str(exe)], env=env, close_fds=True)
    except OSError: return False
    return True


def check_and_stage(config, folder, opener=urllib.request.urlopen):
    if not getattr(sys, 'frozen', False): return None
    manifest_url = f'https://github.com/{REPO}/releases/latest/download/update.json'
    with opener(safe_url(manifest_url), timeout=15) as response:
        safe_url(response.geturl())
        raw = response.read(65537)
    if len(raw) > 65536: raise ValueError('Manifesto muito grande.')
    manifest = json.loads(raw)
    version = manifest['version']
    if manifest.get('schema') != 1 or ver(version) <= ver(config['version']): return None
    expected = manifest['sha256']
    size = manifest['size_bytes']
    if not re.fullmatch('[a-f0-9]{64}', expected) or type(size) is not int or not 0 < size <= 300_000_000:
        raise ValueError('Manifesto inválido.')
    url = safe_url(manifest['url'])
    if cached(config, folder) and ver(version) <= ver(json.loads((Path(folder)/'updates'/'ready.json').read_text())['version']):
        return None
    update_dir = Path(folder) / 'updates'
    update_dir.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='download-', suffix='.part', dir=update_dir)
    digest = hashlib.sha256()
    count = 0
    try:
        with os.fdopen(fd, 'wb') as out, opener(url, timeout=45) as response:
            safe_url(response.geturl())
            while chunk := response.read(1024*1024):
                count += len(chunk)
                if count > size: raise ValueError('Tamanho incorreto do EXE.')
                out.write(chunk)
                digest.update(chunk)
            out.flush()
            os.fsync(out.fileno())
        if count != size or digest.hexdigest() != expected: raise ValueError('SHA-256 incorreto do EXE.')
        target = update_dir / ('ERP_Senembi-'+version+'.exe')
        os.replace(temp, target)
        marker_temp = update_dir / 'ready.tmp'
        marker_temp.write_text(json.dumps({'version': version, 'sha256': expected}), encoding='utf-8')
        os.replace(marker_temp, update_dir/'ready.json')
        return version
    finally:
        if os.path.exists(temp): os.unlink(temp)
