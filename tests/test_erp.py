import tempfile
import unittest
from pathlib import Path

from backup import Backup
from core import Store, electronic_quote, energy_cost, print_quote


class ERPTests(unittest.TestCase):
    def test_costs_select_most_expensive_filament(self):
        filaments = [dict(code='FIL-A', reel_g=1000, value=100),
                     dict(code='FIL-B', reel_g=750, value=150)]
        quote = print_quote(filaments, 50, 2, 1.0, 350, 30, 1, 80)
        self.assertEqual(quote['worst_code'], 'FIL-B')
        self.assertEqual((quote['material'], quote['energy'], quote['cost'], quote['sale']),
                         (10, 0.70, 90.70, 117.91))
        self.assertEqual(energy_cost(1000, 8, 1.2), 9.6)

    def test_component_package_and_order_calendar(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / 'data.db')
            component = store.save('components', 'ESP32', {'quantity': 4, 'package_value': 80,
                'description': '', 'supplier': '', 'datasheet': ''})
            item = store.get(component)
            quote = electronic_quote([(item, 2)], 1.5, 100, 25)
            self.assertEqual((quote['material'], quote['cost'], quote['sale']), (40, 190, 237.5))
            project = store.save('projects', 'Painel', {}, '30/09/2026', 'Planejamento')
            store.add_task(project, 'Validar CAN', '28/09/2026')
            store.save('orders', 'Cliente A', {'charge': 20}, '29/09/2026', 'Aberto')
            self.assertEqual([x['date'] for x in store.agenda()], ['2026-09-28', '2026-09-29'])
            self.assertEqual(store.get(component)['code'], 'ELE-00001')
            store.remove(project)
            self.assertEqual(store.tasks(), [])
            store.db.close()

    def test_backup_and_sequential_codes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            store = Store(path / 'senembi.db')
            a = store.save('filaments', 'Preto', {}, code_prefix='FIL-PLA-PRETO')
            store.remove(a)
            b = store.save('filaments', 'Branco', {}, code_prefix='FIL-PLA-BRANCO')
            self.assertEqual(store.get(b)['code'], 'FIL-PLA-BRANCO-00002')
            backup = Backup(path)
            backup.select(path)
            result = backup.create(store.path)
            self.assertTrue(result.local.is_file())
            self.assertTrue(result.selected.is_file())
            store.db.close()


if __name__ == '__main__':
    unittest.main()
