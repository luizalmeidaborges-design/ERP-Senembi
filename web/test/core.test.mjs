// Confere se as fórmulas portadas (src/core.js) dão os mesmos valores do core.py do app desktop.
// Executar na pasta web/:  node --test test/
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { addProductCost, amount, electronicQuote, filamentPrefix, isoDate, mechatronicQuote, money, number, printQuote, UserError } from '../src/core.js';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));

function rng(seed) { return () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648); }
const rand = rng(42);
const dec = (max, places = 2) => Number((rand() * max).toFixed(places));

const cases = Array.from({ length: 300 }, (_, i) => ({
  filaments: Array.from({ length: 1 + (i % 3) }, (_, j) => ({ code: `PLA-X-${j}`, reel_g: dec(2000, 0) + 1, value: dec(300) })),
  weight: dec(500, 1), hours: dec(30, 2), kwh: dec(2, 3), watts: dec(500, 0), profit: dec(150, 1),
  laborHours: dec(10, 2), laborRate: dec(200, 2), extra: dec(50, 2),
  parts: Array.from({ length: 1 + (i % 4) }, () => [{ quantity: 1 + Math.floor(rand() * 100), package_value: dec(400) }, 1 + Math.floor(rand() * 10)]),
  prep: dec(8, 2), rate: dec(200, 2),
  products: Array.from({ length: 1 + (i % 3) }, () => ({ cost: dec(800) })),
}));

const PY = `
import json, sys
sys.path.insert(0, sys.argv[1])
from core import print_quote, electronic_quote, add_product_cost, amount, number, filament_prefix
cases = json.load(sys.stdin)
out = []
for c in cases:
    p = print_quote(c['filaments'], c['weight'], c['hours'], c['kwh'], c['watts'], c['profit'], c['laborHours'], c['laborRate'])
    e = electronic_quote([tuple(x) for x in c['parts']], c['prep'], c['rate'], c['profit'])
    m = number(c['profit'])
    labor = number(c['prep']) * number(c['rate'])
    cost = sum((number(i['cost']) for i in c['products']), labor)
    mech = {'material': amount(cost-labor), 'labor': amount(labor), 'energy': 0, 'cost': amount(cost), 'sale': amount(cost * (1+m/100))}
    out.append({'print': p, 'electronic': e, 'mech': mech, 'extra': add_product_cost(p, c['extra'], c['profit'])})
json.dump(out, sys.stdout)
`;

test('orçamentos iguais ao core.py em 300 casos aleatórios', () => {
  const expected = JSON.parse(execFileSync('python3', ['-c', PY, ROOT], { input: JSON.stringify(cases) }).toString());
  cases.forEach((c, i) => {
    const p = printQuote(c.filaments, c.weight, c.hours, c.kwh, c.watts, c.profit, c.laborHours, c.laborRate);
    assert.deepEqual(p, expected[i].print, `impresso #${i}`);
    assert.deepEqual(electronicQuote(c.parts, c.prep, c.rate, c.profit), expected[i].electronic, `eletrônico #${i}`);
    assert.deepEqual(mechatronicQuote(c.products, c.prep, c.rate, c.profit), expected[i].mech, `mecatrônico #${i}`);
    assert.deepEqual(addProductCost(p, c.extra, c.profit), expected[i].extra, `custo adicional #${i}`);
  });
});

test('números no formato brasileiro', () => {
  assert.equal(number('1.234,56'), 1234.56);
  assert.equal(number('R$ 10'), 10);
  assert.equal(number(' 2,5 '), 2.5);
  assert.throws(() => number('abc'), UserError);
  assert.throws(() => number('-1'), UserError);
  assert.throws(() => number('0', 'Peso', 0.001), UserError);
});

test('arredondamento metade para cima e formatação', () => {
  assert.equal(amount(1.005), 1.01);
  assert.equal(amount(2.675), 2.68);
  assert.equal(money(1234.5), 'R$ 1.234,50');
});

test('datas DD/MM/AAAA e ISO', () => {
  assert.equal(isoDate('05/03/2026'), '2026-03-05');
  assert.equal(isoDate('2026-03-05'), '2026-03-05');
  assert.equal(isoDate(''), '');
  assert.throws(() => isoDate('31/02/2026'), UserError);
});

test('prefixo de filamento igual ao desktop', () => {
  assert.equal(filamentPrefix('PLA', 'Laranja'), 'PLA-LAR');
  assert.equal(filamentPrefix('PA-CF', 'Ébano fosco'), 'PACF-EBA');
  assert.equal(filamentPrefix('', ''), 'MAT-SEM');
});
