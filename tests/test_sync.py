"""Sincronização desktop ⇄ web.

Os testes locais conferem as marcações de alteração. Os de integração rodam contra um Worker real
(ex.: `npm run dev` em web/) quando ERP_SYNC_URL e ERP_SYNC_TOKEN estão definidos; o banco do Worker
deve começar vazio, e o login do navegador usa ERP_WEB_USER / ERP_WEB_PASS.
"""
import http.cookiejar
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from core import ID_SLOTS, Store
from sync import SyncConfig, synchronize

URL = os.environ.get('ERP_SYNC_URL', '')
TOKEN = os.environ.get('ERP_SYNC_TOKEN', '')


class LocalTrackingTests(unittest.TestCase):
    def test_ids_by_device_and_change_marks(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / 'a.db', device=3)
            first = store.save('components', 'ESP32', {'quantity': 1, 'package_value': 10})
            second = store.save('components', 'Relé', {'quantity': 1, 'package_value': 5})
            self.assertEqual((first % ID_SLOTS, second % ID_SLOTS), (3, 3))
            self.assertLess(first, second)
            row = store.db.execute('SELECT dirty, updated_at FROM records WHERE id=?', (first,)).fetchone()
            self.assertEqual(row[0], 1)
            self.assertGreater(row[1], 0)
            self.assertNotIn('dirty', store.get(first))
            store.remove(second)
            self.assertEqual([tuple(r) for r in store.db.execute('SELECT tbl, id, dirty FROM deleted')], [('records', second, 1)])
            # O id excluído não é reaproveitado.
            self.assertGreater(store.save('components', 'Buzzer', {'quantity': 1, 'package_value': 2}), second)
            store.db.close()

    def test_config_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                SyncConfig('ftp://x', 'a' * 30).save(temp)
            with self.assertRaises(ValueError):
                SyncConfig('https://erp.example.com', 'curto').save(temp)
            SyncConfig('https://erp.example.com/', 'b' * 30, 2).save(temp)
            loaded = SyncConfig.load(temp)
            self.assertEqual((loaded.url, loaded.device), ('https://erp.example.com', 2))


class Web:
    """Cliente mínimo da API do navegador (login por cookie)."""
    def __init__(self):
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        data = urllib.parse.urlencode({'username': os.environ.get('ERP_WEB_USER', 'felipe'),
                                       'password': os.environ.get('ERP_WEB_PASS', 'teste123')}).encode()
        try:
            self.opener.open(URL + '/login', data)
        except urllib.error.HTTPError:
            pass
        for cookie in jar:
            cookie.secure = False  # o servidor local de teste usa http

    def call(self, path, method='GET', body=None):
        request = urllib.request.Request(URL + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                         headers={'Content-Type': 'application/json'})
        return json.loads(self.opener.open(request).read())

    def state(self):
        return self.call('/api/estado')


@unittest.skipUnless(URL and TOKEN, 'defina ERP_SYNC_URL e ERP_SYNC_TOKEN para testar com o Worker')
class WorkerSyncTests(unittest.TestCase):
    def test_round_trip_conflicts_deletes_and_codes(self):
        web = Web()
        with tempfile.TemporaryDirectory() as temp:
            config = SyncConfig(URL, TOKEN, 1)
            a = Store(Path(temp) / 'a.db', device=1)
            # 1) desktop → web
            fil = a.save('filaments', 'Preto', {'material': 'PLA', 'reel_g': 1000, 'value': 100, 'density': 1.24, 'supplier': ''})
            project = a.save('projects', 'AGV', {'client': 'Interno', 'cost': 10, 'sale': 13}, '20/11/2026', 'Planejamento')
            a.add_task(project, 'Planejar', '05/11/2026')
            a.set_setting('kwh', 0.9)
            result = synchronize(a.path, config)
            self.assertEqual(result.sent, 4)
            state = web.state()
            self.assertEqual([f['code'] for f in state['filaments']], ['PLA-PRE-00001'])
            self.assertEqual(state['tasks'][0]['title'], 'Planejar')
            self.assertEqual(state['settings']['kwh'], 0.9)
            self.assertEqual(synchronize(a.path, config).received, 0)

            # 2) web → desktop, com o mesmo código criado dos dois lados (OP-00001)
            comp = web.call('/api/registros/components', 'POST', {'name': 'ESP32', 'quantity': 5, 'package_value': 150})['id']
            self.assertEqual(comp % ID_SLOTS, 0)
            web.call('/api/registros/projects', 'POST', {'name': 'Web', 'hours': 1, 'rate': 1, 'materials': 0, 'profit': 0})
            local_order = a.save('orders', 'Cliente Desktop', {'items': [], 'charge': 0}, '', 'Aberto')
            a.save('projects', 'Desktop', {'cost': 0, 'sale': 0}, '', 'Planejamento')  # PRO-00002 dos dois lados
            result = synchronize(a.path, config)
            self.assertEqual([(x['from'], x['to']) for x in result.renamed], [('PRO-00002', 'PRO-00003')])
            codes = {r['name']: r['code'] for r in a.all('projects')}
            self.assertEqual(codes, {'AGV': 'PRO-00001', 'Web': 'PRO-00002', 'Desktop': 'PRO-00003'})
            self.assertEqual(a.get(comp)['name'], 'ESP32')
            self.assertEqual(a.get(local_order)['code'], 'OP-00001')
            self.assertEqual(sorted(r['code'] for r in web.state()['projects']), ['PRO-00001', 'PRO-00002', 'PRO-00003'])

            # 3) conflito: vale a alteração mais recente (a da web, feita depois)
            a.save('filaments', 'Preto fosco', {'material': 'PLA', 'reel_g': 1000, 'value': 110, 'density': 1.24, 'supplier': ''}, id_=fil)
            web.call(f'/api/registros/filaments/{fil}', 'PUT', {'name': 'Preto brilho', 'material': 'PLA', 'reel_g': 1000,
                                                                  'value': 120, 'density': 1.24, 'supplier': ''})
            synchronize(a.path, config)
            self.assertEqual(a.get(fil)['name'], 'Preto brilho')
            self.assertEqual(a.get(fil)['value'], 120)

            # 4) exclusões nos dois sentidos (com cascata das subtarefas)
            web.call(f'/api/registros/components/{comp}', 'DELETE')
            a.remove(project)
            synchronize(a.path, config)
            self.assertIsNone(a.get(comp))
            state = web.state()
            self.assertFalse([p for p in state['projects'] if p['id'] == project])
            self.assertFalse([t for t in state['tasks'] if t['project_id'] == project])

            # 5) segundo computador recebe tudo do zero
            b = Store(Path(temp) / 'b.db', device=2)
            b.db.execute('DELETE FROM settings')
            b.db.commit()
            synchronize(b.path, SyncConfig(URL, TOKEN, 2))
            self.assertEqual(sorted(r['code'] for r in b.all('projects')), ['PRO-00002', 'PRO-00003'])
            self.assertEqual(b.get(fil)['name'], 'Preto brilho')
            self.assertEqual(b.setting('kwh'), 0.9)
            a.db.close()
            b.db.close()

    def test_wrong_token_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / 'x.db')
            with self.assertRaises(RuntimeError) as ctx:
                synchronize(store.path, SyncConfig(URL, 'x' * 40))
            self.assertIn('Token', str(ctx.exception))
            store.db.close()


if __name__ == '__main__':
    unittest.main()
