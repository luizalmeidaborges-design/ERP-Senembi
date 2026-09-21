import tempfile
import unittest
from pathlib import Path

from backup import Backup
from core import Store, add_product_cost, electronic_quote, energy_cost, filament_prefix, print_quote


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

    def test_additional_items_are_charged_in_printed_and_electronic_products(self):
        filament = [dict(code='PLA-PRE-00001', reel_g=1000, value=100)]
        printed = print_quote(filament, 50, 0, 1, 350, 30)
        self.assertEqual((printed['cost'], printed['sale']), (5, 6.5))
        printed = add_product_cost(printed, '2,50', 30)
        self.assertEqual((printed['material'], printed['cost'], printed['sale']),
                         (7.5, 7.5, 9.75))

        component = dict(quantity=2, package_value=10)
        electronic = electronic_quote([(component, 1)], 1, 100, 20)
        electronic = add_product_cost(electronic, 3, 20)
        self.assertEqual((electronic['material'], electronic['cost'], electronic['sale']),
                         (8, 108, 129.6))
        with self.assertRaises(ValueError):
            add_product_cost(printed, '-1', 30)

    def test_backup_and_sequential_codes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            store = Store(path / 'senembi.db')
            a = store.save('filaments', 'Preto', {'material': 'PLA'})
            store.remove(a)
            b = store.save('filaments', 'Branco', {'material': 'PLA'})
            self.assertEqual(store.get(b)['code'], 'PLA-BRA-00002')
            backup = Backup(path)
            backup.select(path)
            result = backup.create(store.path)
            self.assertTrue(result.local.is_file())
            self.assertTrue(result.selected.is_file())
            store.db.close()

    def test_migrates_existing_filaments_and_product_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'senembi.db'
            store = Store(path)
            first = store.save('filaments', 'Laranja', {'material': 'PLA'})
            second = store.save('filaments', 'Cobre V Silk', {'material': 'PLA'})
            legacy = {'PLA-LAR-00001': 'FIL-PLA-LARANJA-00001',
                      'PLA-COB-00002': 'FIL-PLA-COBREVSI-00002'}
            with store.db:
                for new, old in legacy.items():
                    store.db.execute('UPDATE records SET code=? WHERE code=?', (old, new))
            product = store.save('products', 'Peça', {'worst_code': legacy['PLA-LAR-00001']})
            store.db.close()

            store = Store(path)
            self.assertEqual(store.get(first)['code'], 'PLA-LAR-00001')
            self.assertEqual(store.get(second)['code'], 'PLA-COB-00002')
            self.assertEqual(store.get(product)['worst_code'], 'PLA-LAR-00001')
            store.save('filaments', 'Amarelo', {'material': 'PETG'}, id_=first)
            self.assertEqual(store.get(first)['code'], 'PETG-AMA-00001')
            self.assertEqual(store.get(product)['worst_code'], 'PETG-AMA-00001')
            third = store.save('filaments', 'Preto', {'material': 'TPU'})
            self.assertEqual(store.get(third)['code'], 'TPU-PRE-00003')
            store.db.close()
            store = Store(path)
            self.assertEqual(store.get(first)['code'], 'PETG-AMA-00001')
            self.assertEqual(store.get(product)['worst_code'], 'PETG-AMA-00001')
            store.db.close()

    def test_filament_prefix_removes_accents(self):
        self.assertEqual(filament_prefix('PA-CF', 'Peça branca'), 'PACF-PEC')


if __name__ == '__main__':
    unittest.main()
