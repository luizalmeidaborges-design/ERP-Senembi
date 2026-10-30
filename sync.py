"""Sincronização do banco local com a versão web (Cloudflare Worker, rota /api/sync).

Cada lado marca o que mudou. Aqui: colunas dirty/updated_at e a tabela deleted (gatilhos em core.Store).
Na web: rev/updated_at e tombstones. Em cada sincronização o app envia o que mudou localmente,
recebe o que mudou na web desde o último cursor e aplica tudo numa transação.
Quando o mesmo item mudou dos dois lados, vale a alteração mais recente (updated_at).
"""
from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

from core import ID_SLOTS, NOW_MS, filament_prefix, PREFIXES

CONFIG_NAME = 'sync.json'
USER_AGENT = 'ERP-Senembi-Desktop'


@dataclass
class SyncConfig:
    url: str = ''
    token: str = ''
    device: int = 1

    @property
    def ready(self):
        return bool(self.url and self.token)

    @classmethod
    def load(cls, folder):
        try:
            data = json.loads((Path(folder) / CONFIG_NAME).read_text(encoding='utf-8'))
            return cls(str(data.get('url', '')), str(data.get('token', '')), int(data.get('device', 1)))
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self, folder):
        url = self.url.strip().rstrip('/')
        if not url.startswith('https://') and not url.startswith('http://127.0.0.1') and not url.startswith('http://localhost'):
            raise ValueError('Informe o endereço do ERP web começando com https://')
        if len(self.token.strip()) < 24:
            raise ValueError('O token de sincronização deve ter pelo menos 24 caracteres.')
        if not 1 <= int(self.device) < ID_SLOTS:
            raise ValueError(f'O número do computador deve estar entre 1 e {ID_SLOTS - 1}.')
        self.url, self.token = url, self.token.strip()
        folder = Path(folder)
        temp = folder / (CONFIG_NAME + '.tmp')
        temp.write_text(json.dumps({'url': self.url, 'token': self.token, 'device': int(self.device)}), encoding='utf-8')
        os.replace(temp, folder / CONFIG_NAME)


@dataclass
class SyncResult:
    sent: int = 0
    received: int = 0
    renamed: list = field(default_factory=list)


def _rows(db, sql, args=()):
    return [dict(r) for r in db.execute(sql, args)]


def _post(config, body, timeout):
    request = urllib.request.Request(
        config.url.rstrip('/') + '/api/sync', data=json.dumps(body, ensure_ascii=False).encode('utf-8'), method='POST',
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {config.token}', 'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read().decode('utf-8')).get('erro')
        except (ValueError, AttributeError):
            message = None
        raise RuntimeError(message or f'Servidor respondeu {exc.code}.') from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, 'reason', exc)
        raise RuntimeError(f'Sem conexão com o ERP web ({reason}).') from None


def _free_code(db, kind, row_id, code, name, payload):
    """Dá outro código a um registro local que ainda não foi enviado e colidiu com um código vindo da web."""
    prefix = filament_prefix(payload.get('material', ''), name) if kind == 'filaments' else PREFIXES.get(kind, 'REG')
    db.execute('INSERT INTO counters VALUES (?,1) ON CONFLICT(kind) DO UPDATE SET last_value=last_value+1', (kind,))
    number = db.execute('SELECT last_value FROM counters WHERE kind=?', (kind,)).fetchone()[0]
    db.execute('UPDATE records SET code=?, updated_at=? WHERE id=?',
               (f'{prefix}-{number:05d}', db.execute(f'SELECT {NOW_MS}').fetchone()[0], row_id))


def synchronize(db_path, config, timeout=30):
    if not config.ready:
        raise RuntimeError('Sincronização não configurada.')
    with closing(sqlite3.connect(db_path, timeout=15)) as db:
        db.row_factory = sqlite3.Row
        db.isolation_level = None
        db.execute('PRAGMA foreign_keys=ON')
        records = _rows(db, 'SELECT id,kind,code,name,due,status,payload,updated_at FROM records WHERE dirty=1')
        tasks = _rows(db, 'SELECT id,project_id,title,due,status,updated_at FROM tasks WHERE dirty=1')
        settings = _rows(db, 'SELECT key,value,updated_at FROM settings WHERE dirty=1')
        deleted = _rows(db, 'SELECT tbl,id,deleted_at FROM deleted WHERE dirty=1')
        counters = _rows(db, 'SELECT kind,last_value FROM counters')
        cursor = db.execute('SELECT cursor FROM sync_state WHERE id=1').fetchone()[0]

        answer = _post(config, {'since': cursor, 'device': config.device, 'records': records, 'tasks': tasks,
                                'settings': settings, 'deleted': deleted, 'counters': counters}, timeout)

        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('UPDATE sync_state SET applying=1 WHERE id=1')
            # Enviados: deixam de estar pendentes, salvo se foram alterados durante o envio.
            db.executemany('UPDATE records SET dirty=0 WHERE id=? AND updated_at=?', [(r['id'], r['updated_at']) for r in records])
            db.executemany('UPDATE tasks SET dirty=0 WHERE id=? AND updated_at=?', [(t['id'], t['updated_at']) for t in tasks])
            db.executemany('UPDATE settings SET dirty=0 WHERE key=? AND updated_at=?', [(s['key'], s['updated_at']) for s in settings])
            db.executemany('UPDATE deleted SET dirty=0 WHERE tbl=? AND id=? AND deleted_at=?',
                           [(d['tbl'], d['id'], d['deleted_at']) for d in deleted])
            for c in answer.get('counters', []):
                db.execute('INSERT INTO counters VALUES (?,?) ON CONFLICT(kind) DO UPDATE SET '
                           'last_value=max(last_value,excluded.last_value)', (c['kind'], int(c['last_value'])))
            for d in answer.get('deleted', []):
                if d['tbl'] not in ('records', 'tasks'):
                    continue
                local = db.execute(f"SELECT dirty FROM {d['tbl']} WHERE id=?", (d['id'],)).fetchone()
                if local and local[0]:
                    continue  # alterado aqui depois: será enviado na próxima vez
                if local:
                    db.execute(f"DELETE FROM {d['tbl']} WHERE id=?", (d['id'],))
                db.execute('INSERT OR REPLACE INTO deleted VALUES (?,?,?,0)', (d['tbl'], d['id'], int(d['deleted_at'])))
            incoming = answer.get('records', [])
            # Libera códigos que a web passou para outro registro (o registro antigo vem na mesma resposta).
            for r in incoming:
                other = db.execute('SELECT id,kind,name,payload,dirty FROM records WHERE code=? AND id<>?', (r['code'], r['id'])).fetchone()
                if other and other['dirty']:
                    _free_code(db, other['kind'], other['id'], r['code'], other['name'], json.loads(other['payload']))
                elif other:
                    db.execute('UPDATE records SET code=? WHERE id=?', (f"__sincronizando_{other['id']}__", other['id']))
            for r in incoming:
                local = db.execute('SELECT dirty FROM records WHERE id=?', (r['id'],)).fetchone()
                if local and local[0]:
                    continue
                db.execute('INSERT INTO records(id,kind,code,name,due,status,payload,updated_at,dirty) VALUES (?,?,?,?,?,?,?,?,0) '
                           'ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, code=excluded.code, name=excluded.name, '
                           'due=excluded.due, status=excluded.status, payload=excluded.payload, '
                           'updated_at=excluded.updated_at, dirty=0',
                           (r['id'], r['kind'], r['code'], r['name'], r['due'], r['status'], r['payload'], int(r['updated_at'])))
                db.execute("DELETE FROM deleted WHERE tbl='records' AND id=?", (r['id'],))
            for t in answer.get('tasks', []):
                local = db.execute('SELECT dirty FROM tasks WHERE id=?', (t['id'],)).fetchone()
                if (local and local[0]) or not db.execute('SELECT 1 FROM records WHERE id=?', (t['project_id'],)).fetchone():
                    continue
                db.execute('INSERT INTO tasks(id,project_id,title,due,status,updated_at,dirty) VALUES (?,?,?,?,?,?,0) '
                           'ON CONFLICT(id) DO UPDATE SET project_id=excluded.project_id, title=excluded.title, '
                           'due=excluded.due, status=excluded.status, updated_at=excluded.updated_at, dirty=0',
                           (t['id'], t['project_id'], t['title'], t['due'], t['status'], int(t['updated_at'])))
                db.execute("DELETE FROM deleted WHERE tbl='tasks' AND id=?", (t['id'],))
            for s in answer.get('settings', []):
                local = db.execute('SELECT dirty FROM settings WHERE key=?', (s['key'],)).fetchone()
                if local and local[0]:
                    continue
                db.execute('INSERT INTO settings(key,value,updated_at,dirty) VALUES (?,?,?,0) ON CONFLICT(key) DO UPDATE SET '
                           'value=excluded.value, updated_at=excluded.updated_at, dirty=0',
                           (s['key'], s['value'], int(s['updated_at'])))
            if db.execute("SELECT 1 FROM records WHERE code LIKE '\\_\\_sincronizando\\_%' ESCAPE '\\'").fetchone():
                raise RuntimeError('Resposta de sincronização incompleta; nada foi alterado.')
            db.execute('UPDATE sync_state SET applying=0, cursor=? WHERE id=1', (int(answer['cursor']),))
            db.execute('COMMIT')
        except BaseException:
            db.execute('ROLLBACK')
            raise
    # O servidor devolve também o que acabou de receber; isso não conta como novidade.
    gone = {(d['tbl'], d['id']) for d in deleted}
    pushed = {('r', r['id']) for r in records} | {('t', t['id']) for t in tasks} | {('s', x['key']) for x in settings}
    pulled = ([('r', r['id']) for r in incoming] + [('t', t['id']) for t in answer.get('tasks', [])]
              + [('s', x['key']) for x in answer.get('settings', [])])
    return SyncResult(sent=len(records) + len(tasks) + len(settings) + len(deleted),
                      received=sum(1 for k in pulled if k not in pushed)
                      + sum(1 for d in answer.get('deleted', []) if (d['tbl'], d['id']) not in gone),
                      renamed=answer.get('renamed', []))
