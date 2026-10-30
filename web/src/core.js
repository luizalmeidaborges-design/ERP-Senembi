// Cálculos e persistência do ERP Senembi na web — porte de core.py e das rotinas de salvar do app.py.
// Os valores e formatos gravados no D1 são os mesmos do senembi.db do aplicativo desktop.

export const DEFAULT_RATES = {
  'Modelagem 3D|Decoração': 70, 'Modelagem 3D|Modelagem orgânica': 100,
  'Modelagem 3D|Projetos de engenharia': 130,
  'Modelagem 3D|Peças de substituição': 85,
  'Modelagem 3D|Engenharia reversa': 140,
  'Eletrônica|Desenvolvimento analógico': 120,
  'Eletrônica|Redes (Wi-Fi, Bluetooth, RF, LoRa)': 150,
  'Eletrônica|Automotivo': 170,
  'Eletrônica|Engenharia reversa': 170,
  'TI|Site': 100, 'TI|Python': 120, 'TI|Mobile': 150,
};
export const DEFAULT_SETTINGS = { kwh: 1.0, printer_w: 350, profit: 30,
  modeling_hour: 100, electronics_hour: 120, technical_hour: 120 };
export const PREFIXES = { components: 'ELE', products: 'PRD', orders: 'OP', projects: 'PRO' };
export const KINDS = ['filaments', 'components', 'products', 'orders', 'projects'];
export const MATERIALS = ['PLA', 'PETG', 'ABS', 'ASA', 'TPU', 'PA', 'PA-CF', 'Outro'];
export const PRODUCT_TYPES = ['Impresso', 'Eletrônico', 'Mecatrônico'];
export const ORDER_STATUS = ['Aberto', 'Em produção', 'Pronto', 'Entregue', 'Cancelado'];
export const PAYMENT_STATUS = ['Pendente', 'Parcial', 'Pago'];
export const PROJECT_STATUS = ['Planejamento', 'Em desenvolvimento', 'Validação', 'Concluído', 'Cancelado'];
export const TASK_STATUS = ['A fazer', 'Em andamento', 'Concluído'];

export class UserError extends Error {}

// IDs separados por dispositivo (id % 16): 0 = web, 1–15 = computadores com o app desktop.
// Assim um registro criado na web e outro criado no desktop nunca recebem o mesmo id.
export const ID_SLOTS = 16;
export const WEB_DEVICE = 0;
// Ids de registros excluídos não são reaproveitados (o outro lado pode ainda não ter recebido a exclusão).
const NEXT_ID = (table) => `(SELECT (MAX(m)/${ID_SLOTS}+1)*${ID_SLOTS}+${WEB_DEVICE} FROM (SELECT COALESCE(MAX(id),0) AS m FROM ${table} UNION ALL SELECT COALESCE(MAX(id),0) FROM tombstones WHERE tbl='${table}'))`;

export function filamentPrefix(material, description) {
  const letters = (v) => String(v ?? '').toUpperCase().normalize('NFKD').replace(/[^A-Z0-9]/g, '');
  return `${letters(material).slice(0, 5) || 'MAT'}-${letters(description).slice(0, 3) || 'SEM'}`;
}

// Mesmo comportamento de core.number: aceita "1.234,56", "R$ 10" ou números.
export function number(value, label = 'Valor', minimum = 0) {
  let text = String(value ?? '').trim().replace('R$', '').replace(/ /g, '');
  if (text.includes(',')) text = text.replace(/\./g, '').replace(',', '.');
  const result = /^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i.test(text) ? Number(text) : NaN;
  if (!Number.isFinite(result)) throw new UserError(`${label}: informe um número válido.`);
  if (result < minimum) throw new UserError(`${label}: use um número a partir de ${String(minimum).replace('.', ',')}.`);
  return result;
}

// Arredondamento para centavos, metade para cima (ROUND_HALF_UP do Decimal).
// toPrecision(12) descarta o ruído binário (ex.: 1.005*100 = 100.49999…) antes de arredondar.
export function amount(value) {
  const cents = Number((Number(value) * 100).toPrecision(12));
  return Math.sign(cents) * Math.round(Math.abs(cents)) / 100;
}

export function money(value) {
  return 'R$ ' + amount(value).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function isoDate(value, optional = true) {
  const text = String(value ?? '').trim();
  if (!text && optional) return '';
  let m = text.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!m) {
    const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (iso) m = [text, iso[3], iso[2], iso[1]];
  }
  if (m) {
    const [d, mo, y] = [Number(m[1]), Number(m[2]), Number(m[3])];
    const dt = new Date(Date.UTC(y, mo - 1, d));
    if (y >= 1 && dt.getUTCFullYear() === y && dt.getUTCMonth() === mo - 1 && dt.getUTCDate() === d) {
      return `${String(y).padStart(4, '0')}-${String(mo).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    }
  }
  throw new UserError('Data inválida. Use DD/MM/AAAA.');
}

export function energyCost(watts, hours, kwh) {
  return amount(number(watts, 'Potência') * number(hours, 'Horas') * number(kwh, 'Tarifa') / 1000);
}

export function printQuote(filaments, weightG, hours, kwh, watts, profit, laborHours = 0, laborRate = 0) {
  if (!filaments.length) throw new UserError('Selecione ao menos um filamento.');
  // Valor corresponde ao carretel completo; usar o filamento de maior R$/g.
  let best = null;
  for (const item of filaments) {
    const reel = number(item.reel_g, 'Peso do carretel', 0.001);
    const rate = number(item.value, 'Valor do carretel') / reel;
    // max() do Python compara (taxa, código): empate decide pelo maior código.
    if (!best || rate > best.rate || (rate === best.rate && item.code > best.code)) best = { rate, code: item.code };
  }
  const material = number(weightG, 'Peso da peça') * best.rate;
  const energy = energyCost(watts, hours, kwh);
  const labor = number(laborHours, 'Horas de modelagem') * number(laborRate, 'Hora de modelagem');
  const cost = material + energy + labor;
  const sale = cost * (1 + number(profit, 'Lucro (%)') / 100);
  return { material: amount(material), energy: amount(energy), labor: amount(labor),
    cost: amount(cost), sale: amount(sale), worst_code: best.code };
}

export function electronicQuote(parts, prepHours, hourRate, profit) {
  let materials = 0;
  for (const [part, qty] of parts) {
    const packageQty = number(part.quantity, 'Quantidade no pacote', 1);
    materials += number(part.package_value, 'Valor do pacote') / packageQty * number(qty, 'Quantidade');
  }
  const labor = number(prepHours, 'Tempo de preparo') * number(hourRate, 'Hora técnica');
  const cost = materials + labor;
  return { material: amount(materials), labor: amount(labor), energy: 0,
    cost: amount(cost), sale: amount(cost * (1 + number(profit, 'Lucro (%)') / 100)) };
}

export function mechatronicQuote(products, hours, hourRate, profit) {
  if (!products.length) throw new UserError('Selecione pelo menos um produto do conjunto.');
  const labor = number(hours) * number(hourRate);
  const cost = products.reduce((sum, p) => sum + number(p.cost), labor);
  return { material: amount(cost - labor), labor: amount(labor), energy: 0,
    cost: amount(cost), sale: amount(cost * (1 + number(profit) / 100)) };
}

export function addProductCost(quote, extra, profit) {
  const add = number(extra, 'Custo adicional');
  const result = { ...quote };
  result.material = amount(result.material + add);
  result.cost = amount(result.cost + add);
  result.sale = amount(result.cost * (1 + number(profit, 'Lucro (%)') / 100));
  return result;
}

const text = (v, max = 2000) => String(v ?? '').trim().slice(0, max);
const ids = (list) => [...new Set((Array.isArray(list) ? list : []).map(Number).filter(Number.isInteger))];
const pick = (options, value, fallback) => (options.includes(value) ? value : fallback);

export class Store {
  constructor(db) { this.db = db; }

  static unpack(row) {
    const { payload, rev: _rev, updated_at: _updated, ...rest } = row;
    return { ...rest, ...JSON.parse(payload) };
  }

  async nextCode(kind, name, payload, codePrefix = null) {
    const prefix = kind === 'filaments' ? filamentPrefix(payload.material, name) : codePrefix || PREFIXES[kind];
    const counter = await this.db.prepare(
      'INSERT INTO counters VALUES (?,1) ON CONFLICT(kind) DO UPDATE SET last_value=last_value+1 RETURNING last_value'
    ).bind(kind).first();
    return `${prefix}-${String(counter.last_value).padStart(5, '0')}`;
  }

  async setting(key) {
    const row = await this.db.prepare('SELECT value FROM settings WHERE key=?').bind(key).first();
    return row ? JSON.parse(row.value) : (DEFAULT_SETTINGS[key] ?? DEFAULT_RATES[key]);
  }

  async settings() {
    const { results } = await this.db.prepare('SELECT key,value FROM settings').all();
    const out = { ...DEFAULT_SETTINGS, ...DEFAULT_RATES };
    for (const r of results) out[r.key] = JSON.parse(r.value);
    return out;
  }

  async saveSettings(input) {
    // Valida tudo antes de qualquer alteração persistente.
    const keys = [...Object.keys(DEFAULT_SETTINGS), ...Object.keys(DEFAULT_RATES)];
    const values = keys.filter((k) => k in input).map((k) => [k, number(input[k], k)]);
    await this.db.batch(values.map(([k, v]) => this.db.prepare(
      'INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value').bind(k, JSON.stringify(v))));
  }

  async all(kind) {
    const { results } = await this.db.prepare('SELECT * FROM records WHERE kind=? ORDER BY id DESC').bind(kind).all();
    return results.map(Store.unpack);
  }

  async get(id) {
    const row = await this.db.prepare('SELECT * FROM records WHERE id=?').bind(id).first();
    return row ? Store.unpack(row) : null;
  }

  async byIds(kind, list) {
    const wanted = ids(list);
    const rows = (await this.all(kind)).filter((r) => wanted.includes(r.id));
    if (rows.length !== wanted.length) throw new UserError('Um dos itens selecionados não existe mais. Recarregue a página.');
    return rows;
  }

  async save(kind, name, payload, due = '', status = '', id = null, codePrefix = null) {
    name = text(name, 200);
    if (!name) throw new UserError('O nome é obrigatório.');
    due = isoDate(due);
    const body = JSON.stringify(payload);
    if (id == null) {
      const code = await this.nextCode(kind, name, payload, codePrefix);
      const row = await this.db.prepare(`INSERT INTO records(id,kind,code,name,due,status,payload) VALUES (${NEXT_ID('records')},?,?,?,?,?,?) RETURNING id`)
        .bind(kind, code, name, due, status, body).first();
      return row.id;
    }
    const old = await this.get(id);
    if (!old || old.kind !== kind) throw new UserError('Registro não encontrado.');
    let code = old.code;
    const stmts = [];
    if (kind === 'filaments') {
      const suffix = code.match(/-(\d+)$/);
      if (!suffix) throw new UserError('Código de filamento sem número sequencial.');
      code = `${filamentPrefix(payload.material, name)}-${String(Number(suffix[1])).padStart(5, '0')}`;
      if (code !== old.code) {
        // Mantém as referências textuais dos orçamentos já cadastrados.
        for (const p of await this.all('products')) {
          if (p.worst_code === old.code) {
            const { id: pid, kind: _k, code: _c, name: _n, due: _d, status: _s, ...rest } = p;
            stmts.push(this.db.prepare('UPDATE records SET payload=? WHERE id=?')
              .bind(JSON.stringify({ ...rest, worst_code: code }), pid));
          }
        }
      }
    }
    stmts.unshift(this.db.prepare('UPDATE records SET code=?,name=?,due=?,status=?,payload=? WHERE id=?')
      .bind(code, name, due, status, body, id));
    await this.db.batch(stmts);
    return id;
  }

  async remove(id) {
    await this.db.prepare('DELETE FROM records WHERE id=?').bind(id).run();
  }

  async addTask(projectId, title, due = '') {
    const project = await this.get(projectId);
    if (!project || project.kind !== 'projects') throw new UserError('Projeto não encontrado.');
    title = text(title, 300);
    if (!title) throw new UserError('Informe o título da subtarefa.');
    await this.db.prepare(`INSERT INTO tasks(id,project_id,title,due) VALUES (${NEXT_ID('tasks')},?,?,?)`).bind(projectId, title, isoDate(due)).run();
  }

  async tasks() {
    const { results } = await this.db.prepare(
      'SELECT t.*,r.name AS project FROM tasks t JOIN records r ON r.id=t.project_id ORDER BY t.due=\'\',t.due,t.id').all();
    return results;
  }

  async taskStatus(id, status) {
    if (!TASK_STATUS.includes(status)) throw new UserError('Status inválido.');
    await this.db.prepare('UPDATE tasks SET status=? WHERE id=?').bind(status, id).run();
  }

  async deleteTask(id) {
    await this.db.prepare('DELETE FROM tasks WHERE id=?').bind(id).run();
  }

  // ---------- cadastros: mesmas regras das janelas do app desktop ----------

  async saveFilament(input, id) {
    return this.save('filaments', input.name, {
      material: pick(MATERIALS, input.material, 'Outro'),
      reel_g: number(input.reel_g, 'Peso', 0.001),
      value: number(input.value, 'Valor'),
      density: number(input.density, 'Densidade', 0.001),
      supplier: text(input.supplier, 200),
    }, '', '', id);
  }

  async saveComponent(input, id) {
    const qty = number(input.quantity, 'Quantidade', 1);
    if (!Number.isInteger(qty)) throw new UserError('Quantidade deve ser inteira.');
    const url = text(input.datasheet, 500);
    if (url && !/^https?:\/\//.test(url)) throw new UserError('O datasheet deve ser um endereço HTTP ou HTTPS.');
    return this.save('components', input.name, {
      description: text(input.description), quantity: qty,
      package_value: number(input.package_value, 'Valor'),
      supplier: text(input.supplier, 200), datasheet: url,
    }, '', '', id);
  }

  async productQuote(input, selfId = null) {
    const type = pick(PRODUCT_TYPES, input.type, null);
    if (!type) throw new UserError('Tipo de produto inválido.');
    const m = number(input.profit, 'Lucro');
    const payload = { type, profit: m };
    let quote;
    if (type === 'Impresso') {
      const items = await this.byIds('filaments', input.filament_ids);
      quote = printQuote(items, input.weight_g, input.print_hours, await this.setting('kwh'),
        await this.setting('printer_w'), m, input.labor_hours, input.hour_rate);
      Object.assign(payload, { filament_ids: items.map((i) => i.id), weight_g: number(input.weight_g),
        print_hours: number(input.print_hours), labor_hours: number(input.labor_hours),
        hour_rate: number(input.hour_rate), worst_code: quote.worst_code });
    } else if (type === 'Eletrônico') {
      const list = Array.isArray(input.parts) ? input.parts : [];
      if (!list.length) throw new UserError('Selecione componentes e informe uma quantidade para cada um.');
      const items = await this.byIds('components', list.map((p) => p.id));
      const byId = new Map(items.map((i) => [i.id, i]));
      const parts = list.map((p) => [byId.get(Number(p.id)), number(p.qty, 'Quantidade', 1)]);
      quote = electronicQuote(parts, input.prep_hours, input.hour_rate, m);
      Object.assign(payload, { parts: parts.map(([i, q]) => ({ id: i.id, qty: q })),
        prep_hours: number(input.prep_hours), hour_rate: number(input.hour_rate) });
    } else {
      const items = (await this.byIds('products', input.product_ids))
        .filter((p) => ['Impresso', 'Eletrônico'].includes(p.type) && p.id !== selfId);
      quote = mechatronicQuote(items, input.assembly_hours, input.hour_rate, m);
      Object.assign(payload, { product_ids: items.map((i) => i.id), assembly_hours: number(input.assembly_hours),
        hour_rate: number(input.hour_rate) });
    }
    Object.assign(payload, { additional_items: text(input.additional_items),
      additional_cost: number(input.additional_cost, 'Custo adicional') });
    return Object.assign(payload, addProductCost(quote, input.additional_cost, m));
  }

  async saveProduct(input, id) {
    return this.save('products', input.name, await this.productQuote(input, id), '', '', id);
  }

  async saveOrder(input, id) {
    const list = Array.isArray(input.items) ? input.items : [];
    if (!list.length) throw new UserError('Selecione produtos e informe uma quantidade para cada um.');
    const products = new Map((await this.byIds('products', list.map((x) => x.id))).map((p) => [p.id, p]));
    const old = id != null ? await this.get(id) : null;
    const frozen = new Map((old?.items || []).map((x) => [x.id, x]));
    let total = 0;
    const lines = list.map((x) => {
      const n = number(x.qty, 'Quantidade', 1);
      if (!Number.isInteger(n)) throw new UserError('A quantidade deve ser inteira.');
      const p = products.get(Number(x.id));
      // Congela o preço unitário: itens já existentes no pedido mantêm o preço da criação.
      const unit = frozen.has(p.id) ? frozen.get(p.id).unit_sale : p.sale;
      total += unit * n;
      return { id: p.id, code: p.code, name: p.name, qty: n, unit_sale: unit };
    });
    const manual = text(input.manual_charge, 40);
    return this.save('orders', input.name, {
      items: lines, summary: lines.map((x) => `${x.qty}× ${x.name}`).join(', '),
      suggested: amount(total), manual_charge: manual,
      charge: amount(manual ? number(manual, 'Cobrança') : total),
      payment: pick(PAYMENT_STATUS, input.payment, 'Pendente'),
    }, input.due, pick(ORDER_STATUS, input.status, 'Aberto'), id);
  }

  async saveProject(input, id) {
    const cost = number(input.hours, 'Horas') * number(input.rate, 'Hora técnica') + number(input.materials, 'Materiais');
    const sale = cost * (1 + number(input.profit, 'Lucro') / 100);
    const specialization = input.specialization in DEFAULT_RATES ? input.specialization : 'Hora técnica geral';
    const projectId = await this.save('projects', input.name, {
      client: text(input.client, 200), scope: text(input.scope), objective: text(input.objective),
      constraints: text(input.constraints), quality: text(input.quality), risks: text(input.risks),
      specialization, hours: number(input.hours), rate: number(input.rate),
      materials: number(input.materials), profit: number(input.profit),
      cost: amount(cost), sale: amount(sale),
    }, input.due, pick(PROJECT_STATUS, input.status, 'Planejamento'), id);
    // O marco inicial também aparece no calendário e no Kanban.
    if (id == null) await this.addTask(projectId, 'Planejar e validar escopo', input.due);
    return projectId;
  }

  // ---------- importação / exportação do banco completo ----------

  async exportAll() {
    const q = async (sql) => (await this.db.prepare(sql).all()).results;
    return {
      format: 'erp-senembi', version: 1, exported_at: new Date().toISOString(),
      records: await q('SELECT * FROM records ORDER BY id'),
      counters: await q('SELECT * FROM counters'),
      settings: await q('SELECT * FROM settings'),
      tasks: await q('SELECT * FROM tasks ORDER BY id'),
    };
  }

  async importAll(data) {
    const rows = (k) => (Array.isArray(data?.[k]) ? data[k] : null);
    const [records, counters, settings, tasks] = ['records', 'counters', 'settings', 'tasks'].map(rows);
    if (!records || !counters || !settings || !tasks) throw new UserError('Arquivo sem as tabelas do ERP Senembi.');
    for (const r of records) {
      if (!Number.isInteger(r.id) || !KINDS.includes(r.kind) || typeof r.code !== 'string' || typeof r.payload !== 'string') {
        throw new UserError('Registro inválido no arquivo importado.');
      }
      JSON.parse(r.payload);
    }
    const db = this.db;
    const stmts = [
      db.prepare('DELETE FROM tasks'), db.prepare('DELETE FROM records'),
      db.prepare('DELETE FROM counters'), db.prepare('DELETE FROM settings'),
      ...records.map((r) => db.prepare('INSERT INTO records(id,kind,code,name,due,status,payload) VALUES (?,?,?,?,?,?,?)')
        .bind(r.id, r.kind, r.code, String(r.name ?? ''), String(r.due ?? ''), String(r.status ?? ''), r.payload)),
      ...counters.map((c) => db.prepare('INSERT INTO counters VALUES (?,?)').bind(String(c.kind), Number(c.last_value))),
      ...settings.map((s) => db.prepare('INSERT INTO settings(key,value) VALUES (?,?)').bind(String(s.key), String(s.value))),
      ...tasks.map((t) => db.prepare('INSERT INTO tasks(id,project_id,title,due,status) VALUES (?,?,?,?,?)')
        .bind(Number(t.id), Number(t.project_id), String(t.title ?? ''), String(t.due ?? ''), String(t.status ?? 'A fazer'))),
    ];
    await db.batch(stmts); // batch do D1 é uma transação: ou importa tudo, ou nada.
    return { records: records.length, tasks: tasks.length };
  }

  // ---------- sincronização com o app desktop ----------
  // O desktop envia o que mudou nele (registros, subtarefas, parâmetros e exclusões, com updated_at)
  // e recebe o que mudou aqui desde o último rev que ele viu. Conflito: vale a alteração mais recente.
  async sync(input) {
    const db = this.db;
    const since = Number.isInteger(input?.since) && input.since >= 0 ? input.since : 0;
    const list = (k) => (Array.isArray(input?.[k]) ? input[k] : []);
    const stamp = (v) => (Number.isFinite(Number(v)) && Number(v) > 0 ? Math.floor(Number(v)) : 0);
    const renamed = [];
    const tomb = async (tbl, id) => db.prepare('SELECT deleted_at FROM tombstones WHERE tbl=? AND id=?').bind(tbl, id).first();

    for (const r of list('records')) {
      if (!Number.isInteger(r.id) || r.id <= 0 || !KINDS.includes(r.kind) || typeof r.code !== 'string' || typeof r.payload !== 'string') {
        throw new UserError('Registro inválido na sincronização.');
      }
      const payload = JSON.parse(r.payload);
      const at = stamp(r.updated_at);
      const cur = await db.prepare('SELECT updated_at FROM records WHERE id=?').bind(r.id).first();
      if (cur && cur.updated_at >= at) continue;
      const del = !cur && await tomb('records', r.id);
      if (del && del.deleted_at >= at) continue;
      let code = r.code;
      const clash = await db.prepare('SELECT id FROM records WHERE code=? AND id<>?').bind(code, r.id).first();
      if (clash) {
        // Dois lados criaram o mesmo código (ex.: OP-00007) sem se ver: o registro que chegou ganha o próximo número.
        code = await this.nextCode(r.kind, String(r.name ?? ''), payload);
        renamed.push({ id: r.id, from: r.code, to: code });
      }
      await db.prepare(`INSERT INTO records(id,kind,code,name,due,status,payload,updated_at) VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, code=excluded.code, name=excluded.name, due=excluded.due,
        status=excluded.status, payload=excluded.payload, updated_at=excluded.updated_at`)
        .bind(r.id, r.kind, code, String(r.name ?? ''), String(r.due ?? ''), String(r.status ?? ''), r.payload, at).run();
    }
    for (const t of list('tasks')) {
      if (!Number.isInteger(t.id) || t.id <= 0 || !Number.isInteger(t.project_id)) throw new UserError('Subtarefa inválida na sincronização.');
      const at = stamp(t.updated_at);
      const cur = await db.prepare('SELECT updated_at FROM tasks WHERE id=?').bind(t.id).first();
      if (cur && cur.updated_at >= at) continue;
      const del = !cur && await tomb('tasks', t.id);
      if (del && del.deleted_at >= at) continue;
      if (!await db.prepare("SELECT 1 FROM records WHERE id=? AND kind='projects'").bind(t.project_id).first()) continue;
      await db.prepare(`INSERT INTO tasks(id,project_id,title,due,status,updated_at) VALUES (?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET project_id=excluded.project_id, title=excluded.title, due=excluded.due,
        status=excluded.status, updated_at=excluded.updated_at`)
        .bind(t.id, t.project_id, String(t.title ?? ''), String(t.due ?? ''), TASK_STATUS.includes(t.status) ? t.status : 'A fazer', at).run();
    }
    for (const st of list('settings')) {
      if (typeof st.key !== 'string' || typeof st.value !== 'string') throw new UserError('Parâmetro inválido na sincronização.');
      JSON.parse(st.value);
      const at = stamp(st.updated_at);
      const cur = await db.prepare('SELECT updated_at FROM settings WHERE key=?').bind(st.key).first();
      if (cur && cur.updated_at >= at) continue;
      await db.prepare(`INSERT INTO settings(key,value,updated_at) VALUES (?,?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at`).bind(st.key, st.value, at).run();
    }
    for (const d of list('deleted')) {
      if (!['records', 'tasks'].includes(d.tbl) || !Number.isInteger(d.id)) continue;
      const at = stamp(d.deleted_at);
      const cur = await db.prepare(`SELECT updated_at FROM ${d.tbl} WHERE id=?`).bind(d.id).first();
      if (cur && cur.updated_at > at) continue; // alterado depois da exclusão: a alteração vale
      if (cur) await db.prepare(`DELETE FROM ${d.tbl} WHERE id=?`).bind(d.id).run();
      else {
        await db.batch([db.prepare('UPDATE sync_meta SET rev=rev+1 WHERE id=1'),
          db.prepare('INSERT OR REPLACE INTO tombstones VALUES (?,?,?,(SELECT rev FROM sync_meta WHERE id=1))').bind(d.tbl, d.id, at)]);
      }
    }
    for (const c of list('counters')) {
      if (typeof c.kind !== 'string' || !Number.isInteger(c.last_value)) continue;
      await db.prepare('INSERT INTO counters VALUES (?,?) ON CONFLICT(kind) DO UPDATE SET last_value=max(last_value,excluded.last_value)')
        .bind(c.kind, c.last_value).run();
    }

    // O cursor é lido antes das consultas: o que for gravado no meio volta na próxima vez (nada se perde).
    const cursor = (await db.prepare('SELECT rev FROM sync_meta WHERE id=1').first()).rev;
    const q = async (sql) => (await db.prepare(sql).bind(since).all()).results;
    return {
      cursor, renamed,
      records: await q('SELECT id,kind,code,name,due,status,payload,updated_at FROM records WHERE rev>? ORDER BY id'),
      tasks: await q('SELECT id,project_id,title,due,status,updated_at FROM tasks WHERE rev>? ORDER BY id'),
      settings: await q('SELECT key,value,updated_at FROM settings WHERE rev>?'),
      deleted: await q('SELECT tbl,id,deleted_at FROM tombstones WHERE rev>?'),
      counters: (await db.prepare('SELECT kind,last_value FROM counters').all()).results,
    };
  }
}
