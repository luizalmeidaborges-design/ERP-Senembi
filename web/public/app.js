// ERP Senembi — interface web. Os cálculos são feitos no Worker (src/core.js); aqui só formulários e listas.

const PAGES = [
  ['filaments', 'Filamentos'], ['components', 'Materiais Eletrônicos'], ['products', 'Produtos'],
  ['orders', 'Pedidos'], ['projects', 'Projetos'], ['settings', 'Informações adicionais'],
  ['calendar', 'Calendário'], ['pending', 'Tarefas Pendentes'],
];
const MATERIALS = ['PLA', 'PETG', 'ABS', 'ASA', 'TPU', 'PA', 'PA-CF', 'Outro'];
const PRODUCT_TYPES = ['Impresso', 'Eletrônico', 'Mecatrônico'];
const ORDER_STATUS = ['Aberto', 'Em produção', 'Pronto', 'Entregue', 'Cancelado'];
const PAYMENT_STATUS = ['Pendente', 'Parcial', 'Pago'];
const PROJECT_STATUS = ['Planejamento', 'Em desenvolvimento', 'Validação', 'Concluído', 'Cancelado'];
const OPEN_STATUS = new Set(['A fazer', 'Em andamento', 'Aberto', 'Em produção', 'Pronto']);
const SETTINGS = [['kwh', 'Tarifa de energia (R$/kWh)'], ['printer_w', 'Potência média da impressora (W)'],
  ['profit', 'Lucro padrão (%)'], ['modeling_hour', 'Hora de modelagem padrão (R$/h)'],
  ['electronics_hour', 'Hora eletrônica padrão (R$/h)'], ['technical_hour', 'Hora técnica de projetos (R$/h)']];
const MONTHS = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];

let state = null;
let page = PAGES.some(([k]) => k === location.hash.slice(1)) ? location.hash.slice(1) : 'filaments';
let month = new Date(); month.setDate(1);
const filters = {};

// ---------- utilitários ----------
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'class') el.className = v;
    else if (k === 'value') el.value = v;
    else if (k === 'checked') el.checked = !!v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) if (c != null && c !== false) el.append(c instanceof Node ? c : String(c));
  return el;
}
const money = (v) => 'R$ ' + Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const br = (n) => (n === '' || n == null ? '' : String(n).replace('.', ','));
const showDate = (iso) => (iso ? iso.split('-').reverse().join('/') : '');
const todayIso = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
const norm = (s) => String(s ?? '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  clearTimeout(toast.timer); toast.timer = setTimeout(() => t.classList.remove('show'), 2600);
}

async function api(path, method = 'GET', body) {
  const res = await fetch(path, { method, headers: body ? { 'content-type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined, credentials: 'same-origin' });
  if (res.status === 401) { location.href = '/login'; throw new Error('Sessão expirada.'); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.erro || `Erro ${res.status}`);
  return data;
}
async function reload() { state = await api('/api/estado'); render(); }

// ---------- campos de formulário ----------
function field(label, input, full = false) {
  return h('label', { class: 'field' + (full ? ' full' : '') }, h('span', {}, label), input);
}
const input = (name, value = '', attrs = {}) => h('input', { name, value: value ?? '', autocomplete: 'off', ...attrs });
const numInput = (name, value) => input(name, br(value), { inputmode: 'decimal' });
const select = (name, options, value) => h('select', { name }, options.map((o) => h('option', { value: o, selected: o === value }, o)));
const section = (title) => h('div', { class: 'section' }, title);

function checklist(name, records, selected = [], withQty = null) {
  const box = h('div', { class: 'checks' });
  if (!records.length) box.append(h('div', { class: 'empty' }, 'Nenhum item cadastrado.'));
  for (const r of records) {
    const qty = withQty ? withQty.get(r.id) : null;
    const cb = h('input', { type: 'checkbox', name, value: r.id, checked: selected.includes(r.id) || qty != null });
    const row = h('div', { class: 'check' }, h('label', {}, cb, `${r.code} · ${r.name}`));
    if (withQty) {
      const q = h('input', { type: 'number', min: '1', step: 'any', 'data-qty': r.id, value: br(qty ?? 1), 'aria-label': `Quantidade de ${r.name}` });
      row.append(q);
    }
    box.append(row);
  }
  return box;
}
const checkedIds = (form, name) => [...form.querySelectorAll(`input[name="${name}"]:checked`)].map((x) => Number(x.value));
const checkedQty = (form, name) => checkedIds(form, name).map((id) => ({ id, qty: form.querySelector(`[data-qty="${id}"]`).value }));

// ---------- diálogo ----------
const dlg = document.getElementById('dlg');
const dlgForm = document.getElementById('dlg-form');
function openDialog(title, body, { onSave, onDelete, extra, saveLabel = 'Salvar cadastro' } = {}) {
  const err = h('p', { class: 'err', hidden: true, role: 'alert' });
  const save = onSave ? h('button', { class: 'btn primary', type: 'submit' }, saveLabel) : null;
  dlgForm.replaceChildren(...[
    h('h2', { class: 'dlg-title' }, title),
    onSave ? h('p', { class: 'dlg-sub' }, 'Preencha os dados abaixo para salvar o cadastro.') : null,
    err, body,
    h('div', { class: 'footer' },
      h('div', { class: 'left' },
        onDelete ? h('button', { class: 'btn danger', type: 'button', onclick: async () => {
          if (!confirm('Excluir este registro?')) return;
          try { await onDelete(); dlg.close(); await reload(); toast('Registro excluído.'); } catch (e) { showErr(e); }
        } }, 'Excluir') : null,
        extra || null),
      h('button', { class: 'btn', type: 'button', onclick: () => dlg.close() }, onSave ? 'Cancelar' : 'Fechar'),
      save)].filter(Boolean));
  function showErr(e) { err.textContent = e.message; err.hidden = false; err.scrollIntoView({ block: 'nearest' }); }
  dlgForm.onsubmit = async (ev) => {
    ev.preventDefault();
    if (!onSave) return;
    save.disabled = true; err.hidden = true;
    try { await onSave(new FormData(dlgForm)); dlg.close(); await reload(); toast('Cadastro salvo.'); }
    catch (e) { showErr(e); }
    finally { save.disabled = false; }
  };
  dlg.showModal();
  dlgForm.scrollTop = 0;
  return { showErr };
}
const fd = (form) => Object.fromEntries(form.entries());

// ---------- cadastros ----------
function filament(old) {
  const g = (k, d = '') => (old ? old[k] ?? d : d);
  openDialog('Filamento' + (old ? ` · ${old.code}` : ''), h('div', { class: 'grid' },
    section('Identificação'),
    field('Material', select('material', MATERIALS, g('material', 'PLA'))),
    field('Descrição (cor, fabricante, acabamento)', input('name', g('name'), { required: true })),
    section('Estoque e custos'),
    field('Peso de filamento no carretel (g)', numInput('reel_g', g('reel_g', 1000))),
    field('Valor do carretel (R$)', numInput('value', g('value'))),
    field('Densidade (g/cm³)', numInput('density', g('density', 1.24))),
    field('Fornecedor', input('supplier', g('supplier')))),
  { onSave: (f) => saveRecord('filaments', old, fd(f)), onDelete: old && (() => api(`/api/registros/filaments/${old.id}`, 'DELETE')) });
}

function component(old) {
  const g = (k, d = '') => (old ? old[k] ?? d : d);
  openDialog('Material eletrônico' + (old ? ` · ${old.code}` : ''), h('div', { class: 'grid' },
    section('Identificação'),
    field('Nome (Arduino, ESP32, transistor...)', input('name', g('name'), { required: true })),
    field('Descrição', input('description', g('description'))),
    section('Compra e referência'),
    field('Quantidade no pacote', numInput('quantity', g('quantity', 1))),
    field('Valor do pacote (R$)', numInput('package_value', g('package_value'))),
    field('Fornecedor', input('supplier', g('supplier'))),
    field('Link do datasheet (https://...)', input('datasheet', g('datasheet'), { type: 'url' })),
    old?.datasheet ? h('p', { class: 'full' }, h('a', { href: old.datasheet, target: '_blank', rel: 'noopener noreferrer' }, 'Abrir datasheet')) : null),
  { onSave: (f) => saveRecord('components', old, fd(f)), onDelete: old && (() => api(`/api/registros/components/${old.id}`, 'DELETE')) });
}

function product(old) {
  const s = state.settings;
  const g = (k, d = '') => (old ? old[k] ?? d : d);
  const detail = h('div', { class: 'grid full' });
  const quote = h('div', { class: 'quote' });
  const type = select('type', PRODUCT_TYPES, g('type', 'Impresso'));
  let currentType = type.value;
  const sameType = () => old && old.type === currentType;

  function draw() {
    currentType = type.value;
    const keep = (k, d) => (sameType() ? g(k, d) : d);
    if (currentType === 'Impresso') {
      detail.replaceChildren(
        field('Filamentos possíveis', checklist('filament_ids', state.filaments, keep('filament_ids', [])), true),
        field('Peso de filamento por unidade (g)', numInput('weight_g', keep('weight_g', 0))),
        field('Tempo de impressão por unidade (h)', numInput('print_hours', keep('print_hours', 0))),
        field('Horas de modelagem por unidade', numInput('labor_hours', keep('labor_hours', 0))),
        field('Hora de modelagem (R$/h)', numInput('hour_rate', keep('hour_rate', s.modeling_hour))));
    } else if (currentType === 'Eletrônico') {
      const qty = new Map((keep('parts', [])).map((p) => [p.id, p.qty]));
      detail.replaceChildren(
        field('Componentes e quantidades por unidade', checklist('parts', state.components, [], qty), true),
        field('Tempo de preparo (h)', numInput('prep_hours', keep('prep_hours', 0))),
        field('Hora técnica (R$/h)', numInput('hour_rate', keep('hour_rate', s.electronics_hour))));
    } else {
      const options = state.products.filter((p) => ['Impresso', 'Eletrônico'].includes(p.type) && p.id !== old?.id);
      detail.replaceChildren(
        field('Produtos impressos e eletrônicos do conjunto', checklist('product_ids', options, keep('product_ids', [])), true),
        field('Horas de montagem/integração', numInput('assembly_hours', keep('assembly_hours', 0))),
        field('Hora técnica (R$/h)', numInput('hour_rate', keep('hour_rate', s.technical_hour))));
    }
    detail.append(h('div', { class: 'note' }, 'O orçamento é recalculado ao salvar. Custo = materiais + energia + trabalho + custo adicional; preço = custo × (1 + lucro/100).'));
    simulate();
  }
  const collect = () => {
    const f = new FormData(dlgForm);
    const b = fd(f);
    b.filament_ids = checkedIds(dlgForm, 'filament_ids');
    b.product_ids = checkedIds(dlgForm, 'product_ids');
    b.parts = currentType === 'Eletrônico' ? checkedQty(dlgForm, 'parts') : [];
    b.id = old?.id ?? null;
    return b;
  };
  async function simulate() {
    clearTimeout(simulate.t);
    simulate.t = setTimeout(async () => {
      try {
        const q = await api('/api/produtos/simular', 'POST', collect());
        quote.replaceChildren(...[['Materiais', q.material], ['Energia', q.energy], ['Trabalho', q.labor], ['Custo', q.cost], ['Preço sugerido', q.sale]]
          .map(([l, v]) => h('div', {}, h('small', {}, l), h('b', {}, money(v)))));
      } catch (e) { quote.replaceChildren(h('div', { class: 'full' }, h('small', {}, 'Prévia do orçamento'), h('span', {}, e.message))); }
    }, 350);
  }
  type.addEventListener('change', draw);
  const body = h('div', { class: 'grid', oninput: simulate, onchange: simulate },
    section('Dados do produto'),
    field('Nome do produto', input('name', g('name'), { required: true })),
    field('Tipo de produto', type),
    field('Lucro sobre o custo (%)', numInput('profit', g('profit', s.profit)), true),
    section('Composição e produção'), detail,
    section('Itens adicionais'),
    field('Descrição (bucha, parafuso...)', input('additional_items', g('additional_items'))),
    field('Custo adicional por unidade (R$)', numInput('additional_cost', g('additional_cost', 0))),
    section('Prévia do orçamento'), quote);
  openDialog('Produto' + (old ? ` · ${old.code}` : ''), body, {
    onSave: () => saveRecord('products', old, collect()),
    onDelete: old && (() => api(`/api/registros/products/${old.id}`, 'DELETE')) });
  draw();
}

function order(old) {
  const g = (k, d = '') => (old ? old[k] ?? d : d);
  const qty = new Map((g('items', [])).map((x) => [x.id, x.qty]));
  const total = h('p', { class: 'note' });
  const update = () => {
    const prices = new Map(state.products.map((p) => [p.id, p.sale]));
    const frozen = new Map((g('items', [])).map((x) => [x.id, x.unit_sale]));
    const sum = checkedQty(dlgForm, 'items').reduce((t, x) => t + (frozen.get(x.id) ?? prices.get(x.id) ?? 0) * (Number(String(x.qty).replace(',', '.')) || 0), 0);
    total.textContent = `Valor sugerido: ${money(sum)}. Itens já existentes no pedido mantêm o preço unitário da criação.`;
  };
  openDialog('Pedido' + (old ? ` · ${old.code}` : ''), h('div', { class: 'grid', oninput: update, onchange: update },
    section('Cliente e entrega'),
    field('Cliente', input('name', g('name'), { required: true })),
    field('Entrega', input('due', g('due'), { type: 'date' })),
    section('Produtos do pedido'),
    field('Produtos e quantidades', checklist('items', state.products, [], qty), true),
    total,
    section('Acompanhamento e cobrança'),
    field('Status', select('status', ORDER_STATUS, g('status', 'Aberto'))),
    field('Pagamento', select('payment', PAYMENT_STATUS, g('payment', 'Pendente'))),
    field('Cobrança manual (R$) · opcional', input('manual_charge', g('manual_charge'), { inputmode: 'decimal' }), true)),
  { onSave: (f) => saveRecord('orders', old, { ...fd(f), items: checkedQty(dlgForm, 'items') }),
    onDelete: old && (() => api(`/api/registros/orders/${old.id}`, 'DELETE')) });
  update();
}

function project(old) {
  const s = state.settings;
  const g = (k, d = '') => (old ? old[k] ?? d : d);
  const spec = select('specialization', ['Hora técnica geral', ...state.rates], g('specialization', 'Hora técnica geral'));
  const rate = numInput('rate', g('rate', s.technical_hour));
  if (!old) spec.addEventListener('change', () => { rate.value = br(spec.value in s ? s[spec.value] : s.technical_hour); });
  openDialog('Projeto de mecatrônica' + (old ? ` · ${old.code}` : ''), h('div', { class: 'grid' },
    section('Dados do projeto'),
    field('Nome do projeto', input('name', g('name'), { required: true })),
    field('Cliente', input('client', g('client'))),
    field('Prazo', input('due', g('due'), { type: 'date' })),
    field('Status', select('status', PROJECT_STATUS, g('status', 'Planejamento'))),
    section('Escopo e qualidade'),
    field('Oportunidade ou problema', h('textarea', { name: 'scope' }, g('scope'))),
    field('Objetivo e entregáveis', h('textarea', { name: 'objective' }, g('objective'))),
    field('Restrições e premissas', h('textarea', { name: 'constraints' }, g('constraints'))),
    field('Critérios de qualidade e aceitação', h('textarea', { name: 'quality' }, g('quality'))),
    field('Riscos e testes previstos', h('textarea', { name: 'risks' }, g('risks')), true),
    section('Estimativa e preço'),
    field('Especialidade para estimativa de hora', spec),
    field('Horas técnicas previstas', numInput('hours', g('hours', 0))),
    field('Valor da hora técnica (R$/h)', rate),
    field('Materiais e serviços externos (R$)', numInput('materials', g('materials', 0))),
    field('Lucro (%)', numInput('profit', g('profit', s.profit)), true),
    old ? h('p', { class: 'note' }, `Custo: ${money(old.cost)} · Orçamento: ${money(old.sale)}`) : null),
  { onSave: (f) => saveRecord('projects', old, fd(f)),
    onDelete: old && (() => api(`/api/registros/projects/${old.id}`, 'DELETE')),
    extra: old ? h('button', { class: 'btn', type: 'button', onclick: () => kanban(old) }, 'Abrir Kanban') : null });
}

async function saveRecord(kind, old, body) {
  return old ? api(`/api/registros/${kind}/${old.id}`, 'PUT', body) : api(`/api/registros/${kind}`, 'POST', body);
}

function kanban(project) {
  const board = h('div', { class: 'kanban' });
  const title = input('task_title', '', { placeholder: 'Nova subtarefa' });
  const due = input('task_due', '', { type: 'date', 'aria-label': 'Prazo da subtarefa' });
  const ui = openDialog('Kanban · ' + project.name, h('div', {},
    h('div', { class: 'addtask' }, field('Subtarefa', title), field('Prazo', due),
      h('button', { class: 'btn primary', type: 'button', style: 'margin-bottom:14px', onclick: add }, 'Adicionar subtarefa')),
    board));
  const act = async (fn) => { try { await fn(); await reload(); draw(); } catch (e) { ui.showErr(e); } };
  async function add() {
    await act(() => api(`/api/projetos/${project.id}/tarefas`, 'POST', { title: title.value, due: due.value }));
    title.value = ''; due.value = '';
  }
  function draw() {
    const tasks = state.tasks.filter((t) => t.project_id === project.id);
    board.replaceChildren(...['A fazer', 'Em andamento', 'Concluído'].map((status) => h('div', { class: 'col' },
      h('h3', {}, status),
      tasks.filter((t) => t.status === status).map((t) => {
        const back = status === 'Em andamento' ? 'A fazer' : 'Em andamento';
        const fwd = status === 'A fazer' ? 'Em andamento' : 'Concluído';
        return h('div', { class: 'card' },
          h('p', {}, t.title, t.due ? h('br') : null, t.due ? h('small', {}, showDate(t.due)) : null),
          h('div', { class: 'acts' },
            status !== 'A fazer' ? h('button', { class: 'btn small', type: 'button', 'aria-label': `Mover para ${back}`, onclick: () => act(() => api(`/api/tarefas/${t.id}`, 'PATCH', { status: back })) }, '←') : null,
            status !== 'Concluído' ? h('button', { class: 'btn small', type: 'button', 'aria-label': `Mover para ${fwd}`, onclick: () => act(() => api(`/api/tarefas/${t.id}`, 'PATCH', { status: fwd })) }, '→') : null,
            h('button', { class: 'btn small danger', type: 'button', onclick: () => confirm('Excluir subtarefa?') && act(() => api(`/api/tarefas/${t.id}`, 'DELETE')) }, 'Excluir')));
      }))));
  }
  title.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } });
  draw();
}

// ---------- páginas ----------
const COLUMNS = {
  filaments: [['Código', (r) => r.code], ['Material', (r) => r.material], ['Descrição', (r) => r.name],
    ['Carretel (g)', (r) => br(r.reel_g), 'num'], ['Valor', (r) => money(r.value), 'num'], ['Fornecedor', (r) => r.supplier]],
  components: [['Código', (r) => r.code], ['Nome', (r) => r.name], ['Descrição', (r) => r.description],
    ['Qtd/pacote', (r) => r.quantity, 'num'], ['Valor/pacote', (r) => money(r.package_value), 'num'], ['Fornecedor', (r) => r.supplier]],
  products: [['Código', (r) => r.code], ['Produto', (r) => r.name], ['Tipo', (r) => r.type],
    ['Custo', (r) => money(r.cost), 'num'], ['Preço sugerido', (r) => money(r.sale), 'num']],
  orders: [['OP', (r) => r.code], ['Cliente', (r) => r.name], ['Produtos', (r) => r.summary], ['Entrega', (r) => showDate(r.due)],
    ['Cobrança', (r) => money(r.charge), 'num'], ['Status', (r) => r.status], ['Pagamento', (r) => r.payment]],
  projects: [['Código', (r) => r.code], ['Projeto', (r) => r.name], ['Cliente', (r) => r.client], ['Prazo', (r) => showDate(r.due)],
    ['Orçamento', (r) => money(r.sale), 'num'], ['Status', (r) => r.status]],
};
const EDITORS = { filaments: filament, components: component, products: product, orders: order, projects: project };

function table(columns, rows, onClick) {
  return h('div', { class: 'tablewrap' }, h('table', {},
    h('thead', {}, h('tr', {}, columns.map(([t, , c]) => h('th', { class: c || null, scope: 'col' }, t)))),
    h('tbody', {}, rows.length ? rows.map((r) => h('tr', onClick ? { tabindex: '0', onclick: () => onClick(r),
      onkeydown: (e) => { if (e.key === 'Enter') onClick(r); } } : {}, columns.map(([, f, c]) => h('td', { class: c || null }, f(r) ?? ''))))
      : h('tr', {}, h('td', { colspan: columns.length, class: 'empty' }, 'Nenhum registro.')))));
}

function listPage(main, kind) {
  const rows = state[kind];
  const search = h('input', { class: 'search', type: 'search', placeholder: 'Buscar…', value: filters[kind] || '', 'aria-label': 'Buscar' });
  const wrap = h('div');
  const draw = () => {
    const q = norm(search.value); filters[kind] = search.value;
    const list = q ? rows.filter((r) => COLUMNS[kind].some(([, f]) => norm(f(r)).includes(q))) : rows;
    wrap.replaceChildren(table(COLUMNS[kind], list, EDITORS[kind]));
  };
  search.addEventListener('input', draw);
  main.append(h('div', { class: 'bar' }, h('h1', {}, title(kind)), search,
    h('button', { class: 'btn primary', onclick: () => EDITORS[kind]() }, '+ Adicionar')),
  h('p', { class: 'muted' }, kind === 'projects' ? 'Clique em um projeto para editar ou abrir o Kanban.' : 'Clique em um registro para editar ou excluir.'), wrap);
  draw();
}

function settingsPage(main) {
  const s = state.settings;
  const form = h('form', { class: 'grid', onsubmit: async (e) => {
    e.preventDefault();
    try { state.settings = await api('/api/parametros', 'PUT', fd(new FormData(form))); toast('Valores salvos. Reabra um produto para recalcular seu orçamento.'); }
    catch (err) { toast(err.message); }
  } },
  h('h2', { class: 'full' }, 'Energia e precificação'),
  SETTINGS.map(([k, l]) => field(l, numInput(k, s[k]))),
  h('h2', { class: 'full' }, 'Horas sugeridas por especialidade'),
  h('p', { class: 'full muted' }, 'Estimativas iniciais editáveis em R$/h; não são tabela oficial.'),
  state.rates.map((k) => field(k.replace('|', ' · '), numInput(k, s[k]))),
  h('div', { class: 'full' }, h('button', { class: 'btn primary', type: 'submit' }, 'Salvar parâmetros')));

  const num = (v) => { const t = String(v).trim().replace(/\s/g, ''); const n = Number(t.includes(',') ? t.replace(/\./g, '').replace(',', '.') : t); if (!Number.isFinite(n) || n < 0) throw new Error('Informe números válidos.'); return n; };
  const cw = numInput('cw', s.printer_w), ch = numInput('ch', 8), cd = numInput('cd', 22), eres = h('p', { class: 'result' });
  const calc = () => { try { const hours = num(ch.value) * num(cd.value); const kwh = num(cw.value) * hours / 1000;
    eres.textContent = `Consumo: ${kwh.toFixed(2).replace('.', ',')} kWh/mês · Custo: ${money(kwh * num(form.elements.kwh.value))}/mês`; } catch (e) { eres.textContent = e.message; } };
  const svc = select('svc', state.rates, state.rates[0]), sh = numInput('sh', 1), sres = h('p', { class: 'result' });
  const squote = () => { try { const base = num(form.elements[svc.value].value) * num(sh.value);
    sres.textContent = `Base: ${money(base)} · Com lucro: ${money(base * (1 + num(form.elements.profit.value) / 100))}`; } catch (e) { sres.textContent = e.message; } };

  const fileIn = h('input', { type: 'file', accept: '.db,.sqlite,.json', 'aria-label': 'Arquivo para importar' });
  const ires = h('p', { class: 'result' });
  main.append(h('div', { class: 'bar' }, h('h1', {}, 'Informações adicionais')),
    h('div', { class: 'panel' }, form),
    h('div', { class: 'panel' }, h('h2', {}, 'Calculadora de energia'),
      h('p', { class: 'muted' }, 'Consumo (kWh) = potência (W) × horas / 1000.'),
      h('div', { class: 'grid' }, field('Potência do equipamento (W)', cw), field('Horas de uso por dia', ch), field('Dias de uso por mês', cd)),
      h('button', { class: 'btn', onclick: calc }, 'Calcular energia'), eres),
    h('div', { class: 'panel' }, h('h2', {}, 'Simular preço de serviço'),
      h('div', { class: 'grid' }, field('Tipo de trabalho', svc), field('Horas estimadas', sh)),
      h('button', { class: 'btn', onclick: squote }, 'Calcular serviço'), sres),
    h('div', { class: 'panel' }, h('h2', {}, 'Importar e exportar dados'),
      h('p', {}, 'Para trazer os dados do app desktop, escolha o arquivo ', h('code', {}, 'senembi.db'),
        ' (no Windows: ', h('code', {}, '%LOCALAPPDATA%\\Senembi\\ERP'), ', ou uma cópia da pasta de backups). Também aceita um arquivo .json exportado por este site. ',
        h('strong', {}, 'A importação substitui todos os dados da versão web.')),
      h('div', { class: 'bar' }, fileIn, h('button', { class: 'btn primary', onclick: () => importFile(fileIn.files[0], ires) }, 'Importar'),
        h('a', { class: 'btn', href: '/api/exportar', download: '' }, 'Baixar cópia (.json)')), ires),
    h('p', { class: 'muted' }, 'Referências: adrianoaoli.com/eletronica/calculadora-consumo-eletrico.html · workana.com/pt/freelancers/brasil/modelacao-3d · sebrae.com.br (precificação).'));
}

async function importFile(file, out) {
  if (!file) { out.textContent = 'Escolha um arquivo.'; return; }
  try {
    out.textContent = 'Lendo arquivo…';
    let dados;
    if (/\.json$/i.test(file.name)) {
      dados = JSON.parse(await file.text());
    } else {
      if (!window.initSqlJs) {
        await new Promise((ok, fail) => document.head.append(h('script', { src: '/vendor/sql-wasm.js', onload: ok,
          onerror: () => fail(new Error('leitor de SQLite indisponível')) })));
      }
      const SQL = await window.initSqlJs({ locateFile: () => '/vendor/sql-wasm.wasm' });
      const db = new SQL.Database(new Uint8Array(await file.arrayBuffer()));
      const rows = (sql) => { const r = db.exec(sql)[0]; return r ? r.values.map((v) => Object.fromEntries(r.columns.map((c, i) => [c, v[i]]))) : []; };
      dados = { records: rows('SELECT id,kind,code,name,due,status,payload FROM records ORDER BY id'), counters: rows('SELECT kind,last_value FROM counters'),
        settings: rows('SELECT key,value FROM settings'), tasks: rows('SELECT id,project_id,title,due,status FROM tasks ORDER BY id') };
      db.close();
    }
    const n = (dados.records || []).length;
    if (!confirm(`Substituir todos os dados da versão web por ${n} registros e ${(dados.tasks || []).length} subtarefas deste arquivo?`)) { out.textContent = 'Importação cancelada.'; return; }
    const r = await api('/api/importar', 'POST', { confirmar: 'SUBSTITUIR', dados });
    out.textContent = `Importados ${r.records} registros e ${r.tasks} subtarefas.`;
    await reload();
  } catch (e) { out.textContent = 'Não foi possível importar: ' + e.message; }
}

function agenda() {
  const orders = state.orders.filter((r) => r.due).map((r) => ({ date: r.due, source: r.code, description: 'Entrega: ' + r.name, status: r.status }));
  const tasks = state.tasks.filter((t) => t.due).map((t) => ({ date: t.due, source: 'Projeto', description: `${t.project} · ${t.title}`, status: t.status }));
  return [...orders, ...tasks].sort((a, b) => a.date.localeCompare(b.date));
}

function calendarPage(main) {
  const y = month.getFullYear(), m = month.getMonth();
  const key = `${y}-${String(m + 1).padStart(2, '0')}`;
  const events = agenda().filter((e) => e.date.startsWith(key));
  const first = (new Date(y, m, 1).getDay() + 6) % 7; // segunda-feira primeiro
  const days = new Date(y, m + 1, 0).getDate();
  const today = todayIso();
  const cells = [];
  for (let i = 0; i < first; i++) cells.push(h('div', { class: 'day out' }));
  for (let d = 1; d <= days; d++) {
    const iso = `${key}-${String(d).padStart(2, '0')}`;
    cells.push(h('div', { class: 'day' + (iso === today ? ' today' : '') }, h('div', { class: 'n' }, d),
      events.filter((e) => e.date === iso).map((e) => h('div', { class: 'ev', title: `${e.source} ${e.description} (${e.status})` }, `${e.source} ${e.description}`))));
  }
  const move = (delta) => { month = new Date(y, m + delta, 1); render(); };
  main.append(h('div', { class: 'bar' }, h('h1', {}, 'Calendário')),
    h('div', { class: 'cal-head' }, h('button', { class: 'btn', onclick: () => move(-1), 'aria-label': 'Mês anterior' }, '◀'),
      h('strong', {}, `${MONTHS[m]} ${y}`), h('button', { class: 'btn', onclick: () => move(1), 'aria-label': 'Próximo mês' }, '▶')),
    h('div', { class: 'cal' }, ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'].map((d) => h('div', { class: 'wd' }, d)), cells));
}

function pendingPage(main) {
  const rows = agenda().filter((e) => OPEN_STATUS.has(e.status));
  main.append(h('div', { class: 'bar' }, h('h1', {}, 'Tarefas Pendentes')),
    table([['Prazo', (e) => showDate(e.date)], ['Origem', (e) => e.source], ['Tarefa ou entrega', (e) => e.description], ['Status', (e) => e.status]], rows));
}

const title = (k) => PAGES.find(([key]) => key === k)[1];

function render() {
  const nav = document.getElementById('nav');
  nav.replaceChildren(...PAGES.map(([k, t]) => h('a', { href: '#' + k, 'aria-current': k === page ? 'page' : null }, t)));
  const main = document.getElementById('main');
  main.replaceChildren();
  if (!state) return;
  if (EDITORS[page]) listPage(main, page);
  else if (page === 'settings') settingsPage(main);
  else if (page === 'calendar') calendarPage(main);
  else pendingPage(main);
  document.title = `${title(page)} · Senembi T-Labs | ERP`;
}

window.addEventListener('hashchange', () => {
  const k = location.hash.slice(1);
  if (PAGES.some(([key]) => key === k)) { page = k; render(); }
  document.getElementById('nav').classList.remove('open');
  document.getElementById('menu').setAttribute('aria-expanded', 'false');
});
document.getElementById('menu').addEventListener('click', (e) => {
  const open = document.getElementById('nav').classList.toggle('open');
  e.currentTarget.setAttribute('aria-expanded', String(open));
});

render();
reload().catch((e) => { document.getElementById('main').replaceChildren(h('p', { class: 'err' }, 'Não foi possível carregar os dados: ' + e.message)); });
