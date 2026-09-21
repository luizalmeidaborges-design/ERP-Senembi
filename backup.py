"""Backups íntegros do SQLite, com cópia opcional em pasta sincronizada."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass
class Result:
    local: Path
    selected: Path | None
    selected_error: str | None = None


class Backup:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.destination = None
        try:
            data = json.loads((self.folder / 'backup_settings.json').read_text(encoding='utf-8'))
            self.destination = Path(data['folder']) if data.get('folder') else None
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def select(self, path):
        path = Path(path).expanduser().resolve()
        if not path.is_dir(): raise ValueError('Selecione uma pasta existente.')
        self.folder.mkdir(parents=True, exist_ok=True)
        temp = self.folder / 'backup_settings.tmp'
        temp.write_text(json.dumps({'folder': str(path)}), encoding='utf-8')
        os.replace(temp, self.folder / 'backup_settings.json')
        self.destination = path

    def create(self, source, today=None):
        local_dir = self.folder / 'backups'
        local_dir.mkdir(parents=True, exist_ok=True)
        name = 'senembi_' + (today or date.today()).isoformat() + '.db'
        local = local_dir / name
        fd, temp = tempfile.mkstemp(prefix='.senembi-', suffix='.db', dir=local_dir)
        os.close(fd)
        try:
            with sqlite3.connect(source, timeout=20) as original, sqlite3.connect(temp) as target:
                original.backup(target)
            with sqlite3.connect(temp) as check:
                if check.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('A cópia não passou na verificação de integridade.')
            os.replace(temp, local)
        finally:
            if os.path.exists(temp): os.unlink(temp)
        if self.destination is None: return Result(local, None)
        try:
            if not self.destination.is_dir(): raise OSError('Pasta de backup indisponível.')
            target = self.destination / name
            if target.resolve() != local.resolve():
                fd, temp = tempfile.mkstemp(prefix='.senembi-', suffix='.tmp', dir=self.destination)
                os.close(fd)
                try:
                    shutil.copy2(local, temp)
                    os.replace(temp, target)
                finally:
                    if os.path.exists(temp): os.unlink(temp)
            return Result(local, target)
        except OSError as exc:
            return Result(local, None, str(exc))
