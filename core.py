"""Persistência e cálculos do ERP Senembi (sem dependências externas)."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


DEFAULT_RATES = {
    'Modelagem 3D|Decoração': 70, 'Modelagem 3D|Modelagem orgânica': 100,
    'Modelagem 3D|Projetos de engenharia': 130,
    'Modelagem 3D|Peças de substituição': 85,
    'Modelagem 3D|Engenharia reversa': 140,
    'Eletrônica|Desenvolvimento analógico': 120,
    'Eletrônica|Redes (Wi-Fi, Bluetooth, RF, LoRa)': 150,
    'Eletrônica|Automotivo': 170,
    'Eletrônica|Engenharia reversa': 170,
    'TI|Site': 100, 'TI|Python': 120, 'TI|Mobile': 150,
}
DEFAULT_SETTINGS = {'kwh': 1.0, 'printer_w': 350, 'profit': 30,
                    'modeling_hour': 100, 'electronics_hour': 120, 'technical_hour': 120}
PREFIXES = {'filaments': 'FIL', 'components': 'ELE', 'products': 'PRD',
            'orders': 'OP', 'projects': 'PRO'}


def number(value, label='Valor', *, minimum=0):
    try:
        value = str(value).strip().replace('R$', '').replace(' ', '')
        if ',' in value:
            value = value.replace('.', '').replace(',', '.')
        result = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError(f'{label}: informe um número válido.') from None
    if not result.is_finite() or result < minimum:
        raise ValueError(f'{label}: use um número a partir de {minimum}.')
    return result


def money(value):
    amount = Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    return 'R$ ' + f'{amount:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def amount(value):
    return float(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def iso_date(value, optional=True):
    value = str(value).strip()
    if not value and optional:
        return ''
    try:
        if re.fullmatch(r'\d{2}/\d{2}/\d{4}', value):
            day, month, year = map(int, value.split('/'))
            return date(year, month, day).isoformat()
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError('Data inválida. Use DD/MM/AAAA.') from None


def display_date(value):
    return date.fromisoformat(value).strftime('%d/%m/%Y') if value else ''


def energy_cost(watts, hours, kwh):
    return amount(number(watts, 'Potência') * number(hours, 'Horas') *
                  number(kwh, 'Tarifa') / 1000)


def print_quote(filaments, weight_g, hours, kwh, watts, profit, labor_hours=0, labor_rate=0):
    if not filaments:
        raise ValueError('Selecione ao menos um filamento.')
    # Valor corresponde ao carretel completo; usar o filamento de maior R$/g.
    candidates = []
    for item in filaments:
        reel = number(item['reel_g'], 'Peso do carretel', minimum=Decimal('.001'))
        candidates.append((number(item['value'], 'Valor do carretel') / reel, item['code']))
    rate, worst_code = max(candidates)
    material = number(weight_g, 'Peso da peça') * rate
    energy = Decimal(str(energy_cost(watts, hours, kwh)))
    labor = number(labor_hours, 'Horas de modelagem') * number(labor_rate, 'Hora de modelagem')
    cost = material + energy + labor
    sale = cost * (1 + number(profit, 'Lucro (%)') / 100)
    return {'material': amount(material), 'energy': amount(energy), 'labor': amount(labor),
            'cost': amount(cost), 'sale': amount(sale), 'worst_code': worst_code}


def electronic_quote(parts, prep_hours, hour_rate, profit):
    materials = Decimal('0')
    for part, qty in parts:
        package_qty = number(part['quantity'], 'Quantidade no pacote', minimum=Decimal('1'))
        materials += number(part['package_value'], 'Valor do pacote') / package_qty * number(qty, 'Quantidade')
    labor = number(prep_hours, 'Tempo de preparo') * number(hour_rate, 'Hora técnica')
    cost = materials + labor
    return {'material': amount(materials), 'labor': amount(labor), 'energy': 0,
            'cost': amount(cost), 'sale': amount(cost * (1 + number(profit, 'Lucro (%)') / 100))}


def data_dir():
    path = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local' / 'share') / 'Senembi' / 'ERP'
    path.mkdir(parents=True, exist_ok=True)
    return path


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY, kind TEXT NOT NULL, code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL, due TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_records_kind_due ON records(kind,due);
            CREATE TABLE IF NOT EXISTS counters (kind TEXT PRIMARY KEY, last_value INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
                title TEXT NOT NULL, due TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'A fazer');
        ''')
        self.db.commit()

    def setting(self, key):
        row = self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row['value']) if row else DEFAULT_SETTINGS.get(key, DEFAULT_RATES.get(key))

    def set_setting(self, key, value):
        with self.db:
            self.db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                            (key, json.dumps(value, ensure_ascii=False)))

    def all(self, kind):
        return [self._unpack(r) for r in self.db.execute(
            'SELECT * FROM records WHERE kind=? ORDER BY id DESC', (kind,))]

    def get(self, id_):
        row = self.db.execute('SELECT * FROM records WHERE id=?', (id_,)).fetchone()
        return self._unpack(row) if row else None

    @staticmethod
    def _unpack(row):
        result = dict(row)
        result.update(json.loads(result.pop('payload')))
        return result

    def save(self, kind, name, payload, due='', status='', id_=None, code_prefix=None):
        if not name.strip():
            raise ValueError('O nome é obrigatório.')
        due = iso_date(due)
        with self.db:
            if id_ is None:
                prefix = code_prefix or PREFIXES[kind]
                row = self.db.execute('SELECT last_value FROM counters WHERE kind=?', (kind,)).fetchone()
                count = row[0] + 1 if row else 1
                self.db.execute('INSERT INTO counters VALUES (?,?) ON CONFLICT(kind) DO UPDATE SET last_value=excluded.last_value',
                                (kind, count))
                code = f'{prefix}-{count:05d}'
                cur = self.db.execute('INSERT INTO records(kind,code,name,due,status,payload) VALUES (?,?,?,?,?,?)',
                                      (kind, code, name.strip(), due, status, json.dumps(payload, ensure_ascii=False)))
                return cur.lastrowid
            old = self.get(id_)
            if not old or old['kind'] != kind:
                raise ValueError('Registro não encontrado.')
            self.db.execute('UPDATE records SET name=?,due=?,status=?,payload=? WHERE id=?',
                            (name.strip(), due, status, json.dumps(payload, ensure_ascii=False), id_))
            return id_

    def remove(self, id_):
        with self.db:
            self.db.execute('DELETE FROM records WHERE id=?', (id_,))

    def add_task(self, project_id, title, due=''):
        if not self.get(project_id):
            raise ValueError('Projeto não encontrado.')
        with self.db:
            self.db.execute('INSERT INTO tasks(project_id,title,due) VALUES (?,?,?)',
                            (project_id, title.strip(), iso_date(due)))

    def tasks(self, project_id=None):
        query = '''SELECT t.*,r.name AS project FROM tasks t JOIN records r ON r.id=t.project_id'''
        args = ()
        if project_id is not None:
            query += ' WHERE project_id=?'
            args = (project_id,)
        return [dict(x) for x in self.db.execute(query + ' ORDER BY t.due="",t.due,t.id', args)]

    def task_status(self, id_, status):
        if status not in ('A fazer', 'Em andamento', 'Concluído'):
            raise ValueError('Status inválido.')
        with self.db:
            self.db.execute('UPDATE tasks SET status=? WHERE id=?', (status, id_))

    def delete_task(self, id_):
        with self.db:
            self.db.execute('DELETE FROM tasks WHERE id=?', (id_,))

    def agenda(self):
        orders = [{'date': r['due'], 'source': r['code'], 'description': 'Entrega: '+r['name'],
                   'status': r['status']} for r in self.all('orders') if r['due']]
        tasks = [{'date': t['due'], 'source': 'Projeto', 'description': t['project']+' · '+t['title'],
                  'status': t['status']} for t in self.tasks() if t['due']]
        return sorted(orders + tasks, key=lambda x: x['date'])
