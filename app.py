"""ERP Senembi T-Labs: catálogo, orçamentos, pedidos e projetos."""
from __future__ import annotations

import calendar
import json
import queue
import sys
import threading
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from backup import Backup
from core import (DEFAULT_RATES, Store, amount, data_dir, display_date,
                  electronic_quote, energy_cost, iso_date, money, number, print_quote)
from updater import check_and_stage, launch_cached, read_config

BG, PANEL, DARK, GREEN, MINT, INK = '#edf5f1', '#ffffff', '#153b36', '#228659', '#d9f3dc', '#183831'
PAGES = [('Filamentos', 'filaments'), ('Materiais Eletrônicos', 'components'),
         ('Produtos', 'products'), ('Pedidos', 'orders'), ('Projetos', 'projects'),
         ('Informações adicionais', 'settings'), ('Calendário', 'calendar'),
         ('Tarefas Pendentes', 'pending')]
KINDS = {'Impresso': 'printed', 'Eletrônico': 'electronic', 'Mecatrônico': 'mechatronic'}


def resource(filename):
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    return root / 'assets' / filename


class ActionButton(tk.Canvas):
    """Botão de ação com cantos arredondados, estados de foco e hover."""
    COLORS = {
        'primary': (GREEN, '#1a704c', '#14583d', '#ffffff'),
        'secondary': ('#deeee6', '#c7e4d4', '#afd6c1', DARK),
        'danger': ('#fce9e5', '#f6d2cc', '#ebbbb3', '#963d35'),
    }

    def __init__(self, parent, text, command, variant='secondary', background=BG):
        self.face, self.hover, self.pressed, self.ink = self.COLORS[variant]
        self.command = command
        self.label = text
        self.text_font = tkfont.Font(family='Segoe UI', size=10, weight='bold')
        width = max(48, self.text_font.measure(text) + 34)
        super().__init__(parent, width=width, height=38, bg=background,
                         highlightthickness=0, bd=0, cursor='hand2', takefocus=1)
        self._state = 'normal'
        self.bind('<Enter>', lambda e: self._set_state('hover'))
        self.bind('<Leave>', lambda e: self._set_state('normal'))
        self.bind('<ButtonPress-1>', lambda e: (self.focus_set(), self._set_state('pressed')))
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<Return>', lambda e: self.command())
        self.bind('<space>', lambda e: self.command())
        self.bind('<FocusIn>', lambda e: self._draw())
        self.bind('<FocusOut>', lambda e: self._draw())
        self._draw()

    def _set_state(self, state):
        self._state = state
        self._draw()

    def _release(self, event):
        inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        self._set_state('hover' if inside else 'normal')
        if inside:
            self.command()

    def _draw(self):
        self.delete('all')
        w, h, r = int(self['width']), int(self['height']), 11
        fill = {'normal': self.face, 'hover': self.hover, 'pressed': self.pressed}[self._state]
        self.create_rectangle(r, 1, w-r, h-1, fill=fill, outline='')
        self.create_rectangle(1, r, w-1, h-r, fill=fill, outline='')
        for x in (1, w-2*r-1):
            for y in (1, h-2*r-1):
                self.create_oval(x, y, x+2*r, y+2*r, fill=fill, outline='')
        self.create_text(w/2, h/2, text=self.label, font=self.text_font, fill=self.ink)
        if self.focus_get() == self:
            self.create_rectangle(3, 3, w-3, h-3, outline=self.ink, dash=(2, 3))


def entry(parent, label, value='', width=26):
    box = ttk.Frame(parent)
    ttk.Label(box, text=label).pack(anchor='w', pady=(8, 2))
    var = tk.StringVar(value=str(value if value is not None else ''))
    ttk.Entry(box, textvariable=var, width=width).pack(fill='x')
    box.pack(fill='x', padx=8)
    return var


def choice(parent, label, options, value=''):
    box = ttk.Frame(parent)
    ttk.Label(box, text=label).pack(anchor='w', pady=(8, 2))
    var = tk.StringVar(value=value or (options[0] if options else ''))
    ttk.Combobox(box, values=options, textvariable=var, state='readonly').pack(fill='x')
    box.pack(fill='x', padx=8)
    return var


class Dialog(tk.Toplevel):
    def __init__(self, app, title, width=660, height=710):
        super().__init__(app.root)
        self.app = app
        self.title(title)
        self.geometry(f'{width}x{height}')
        self.minsize(530, 480)
        self.transient(app.root)
        self.configure(bg=BG)
        self.body = tk.Canvas(self, bg=PANEL, highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient='vertical', command=self.body.yview)
        self.body.configure(yscrollcommand=scroll.set)
        self.body.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.content = ttk.Frame(self.body, padding=18)
        window = self.body.create_window((0, 0), window=self.content, anchor='nw')
        self.content.bind('<Configure>', lambda e: self.body.configure(scrollregion=self.body.bbox('all')))
        self.body.bind('<Configure>', lambda e: self.body.itemconfigure(window, width=e.width))
        self.grab_set()

    def save_button(self, action):
        ActionButton(self.content, 'Salvar', lambda: self.safe(action), 'primary', PANEL).pack(
            anchor='e', padx=8, pady=22)

    def safe(self, action):
        try:
            action()
            self.app.render()
            self.destroy()
        except (ValueError, KeyError) as exc:
            messagebox.showerror('Verifique os dados', str(exc), parent=self)


class ERP:
    def __init__(self, root):
        self.root = root
        self.folder = data_dir()
        self.store = Store(self.folder / 'senembi.db')
        self.backup = Backup(self.folder)
        self.current = 'filaments'
        self.month = date.today().replace(day=1)
        self.events = queue.Queue()
        self.closing = False
        self.config = read_config(resource('update_config.json'))
        root.title('Senembi T-Labs | ERP')
        root.geometry('1330x820')
        root.minsize(1080, 640)
        root.configure(bg=BG)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame', background=PANEL)
        style.configure('TLabel', background=PANEL, foreground=INK, font=('Segoe UI', 10))
        style.configure('TButton', font=('Segoe UI', 10, 'bold'), padding=(15, 9),
                        background='#deeee6', foreground=DARK, borderwidth=0, relief='flat')
        style.map('TButton', background=[('pressed', '#afd6c1'), ('active', '#c7e4d4')])
        style.configure('Accent.TButton', background=GREEN, foreground='white')
        style.map('Accent.TButton', background=[('pressed', '#14583d'), ('active', '#1a704c')],
                  foreground=[('active', 'white')])
        style.configure('Treeview', font=('Segoe UI', 10), rowheight=30, background=PANEL)
        style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'), background=MINT, foreground=DARK)
        try:
            self.window_icon = tk.PhotoImage(file=str(resource('icon.png')))
            root.iconphoto(True, self.window_icon)
            if sys.platform == 'win32':
                root.iconbitmap(str(resource('senembi.ico')))
        except (tk.TclError, OSError):
            pass
        self.shell()
        self.render()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(1200, self.start_update)
        root.after(120000, self.daily_backup)

    def shell(self):
        header = tk.Frame(self.root, bg=DARK, height=110)
        header.pack(fill='x')
        header.pack_propagate(False)
        try:
            self.logo = tk.PhotoImage(file=str(resource('logo.png')))
            tk.Label(header, image=self.logo, bg=DARK).pack(side='left', padx=22)
        except tk.TclError:
            tk.Label(header, text='SENEMBI T-LABS', fg='white', bg=DARK,
                     font=('Segoe UI', 18, 'bold')).pack(side='left', padx=20)
        tk.Label(header, text='ERP · Laboratório de projetos mecatrônicos', bg=DARK,
                 fg=MINT, font=('Segoe UI', 15)).pack(side='left')
        ActionButton(header, 'Pasta de backup', self.select_backup, 'secondary', DARK).pack(
            side='right', padx=18)
        self.sidebar = tk.Frame(self.root, bg=DARK, width=230)
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)
        self.nav = {}
        for title, key in PAGES:
            b = tk.Button(self.sidebar, text=title, command=lambda k=key: self.go(k),
                          font=('Segoe UI', 11), anchor='w', padx=19, pady=12,
                          relief='flat', bd=0, bg=DARK, fg='white', cursor='hand2')
            b.pack(fill='x')
            self.nav[key] = b
        self.status = tk.StringVar(value='Dados salvos neste computador')
        tk.Label(self.sidebar, textvariable=self.status, wraplength=205,
                 bg=DARK, fg=MINT, padx=10, pady=20).pack(side='bottom')
        self.main = tk.Frame(self.root, bg=BG)
        self.main.pack(side='left', fill='both', expand=True)

    def go(self, key):
        self.current = key
        self.render()

    def render(self):
        for w in self.main.winfo_children():
            w.destroy()
        for k, button in self.nav.items():
            button.configure(bg=GREEN if k == self.current else DARK)
        title = dict((k, t) for t, k in PAGES)[self.current]
        bar = tk.Frame(self.main, bg=BG)
        bar.pack(fill='x', padx=24, pady=(23, 10))
        tk.Label(bar, text=title, bg=BG, fg=DARK, font=('Segoe UI', 22, 'bold')).pack(side='left')
        if self.current in ('filaments', 'components', 'products', 'orders', 'projects'):
            ActionButton(bar, '+ Adicionar', self.add, 'primary').pack(side='right')
            self.list_page()
        elif self.current == 'settings':
            self.settings_page()
        elif self.current == 'calendar':
            self.calendar_page()
        else:
            self.pending_page()

    def table(self, columns):
        wrap = tk.Frame(self.main, bg=PANEL)
        wrap.pack(fill='both', expand=True, padx=24, pady=(5, 24))
        tree = ttk.Treeview(wrap, columns=columns, show='headings', selectmode='browse')
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=145, minwidth=90)
        y = ttk.Scrollbar(wrap, orient='vertical', command=tree.yview)
        x = ttk.Scrollbar(wrap, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        tree.pack(side='left', fill='both', expand=True)
        y.pack(side='right', fill='y')
        x.pack(side='bottom', fill='x')
        return tree

    def list_page(self):
        kind = self.current
        columns = {
            'filaments': ('Código', 'Material', 'Descrição', 'Carretel (g)', 'Valor', 'Fornecedor'),
            'components': ('Código', 'Nome', 'Descrição', 'Qtd/pacote', 'Valor/pacote', 'Fornecedor'),
            'products': ('Código', 'Produto', 'Tipo', 'Custo', 'Preço sugerido'),
            'orders': ('OP', 'Cliente', 'Produtos', 'Entrega', 'Cobrança', 'Status', 'Pagamento'),
            'projects': ('Código', 'Projeto', 'Cliente', 'Prazo', 'Orçamento', 'Status'),
        }[kind]
        tools = tk.Frame(self.main, bg=BG)
        tools.pack(fill='x', padx=24, pady=4)
        ActionButton(tools, 'Editar selecionado', self.edit).pack(side='left', padx=(0, 9))
        ActionButton(tools, 'Excluir selecionado', self.delete, 'danger').pack(side='left')
        if kind == 'projects':
            ActionButton(tools, 'Abrir Kanban', self.kanban, 'primary').pack(side='left', padx=9)
        self.rows = {str(r['id']): r for r in self.store.all(kind)}
        self.tree = self.table(columns)
        for r in self.rows.values():
            if kind == 'filaments':
                values = (r['code'], r['material'], r['name'], r['reel_g'], money(r['value']), r['supplier'])
            elif kind == 'components':
                values = (r['code'], r['name'], r['description'], r['quantity'], money(r['package_value']), r['supplier'])
            elif kind == 'products':
                values = (r['code'], r['name'], r['type'], money(r['cost']), money(r['sale']))
            elif kind == 'orders':
                values = (r['code'], r['name'], r['summary'], display_date(r['due']),
                          money(r['charge']), r['status'], r['payment'])
            else:
                values = (r['code'], r['name'], r['client'], display_date(r['due']),
                          money(r['sale']), r['status'])
            self.tree.insert('', 'end', iid=str(r['id']), values=values)
        self.tree.bind('<Double-1>', lambda e: self.edit())

    def selected(self):
        ids = self.tree.selection()
        return self.rows.get(ids[0]) if ids else None

    def add(self):
        {'filaments': self.filament, 'components': self.component,
         'products': self.product, 'orders': self.order, 'projects': self.project}[self.current]()

    def edit(self):
        old = self.selected()
        if not old:
            messagebox.showinfo('Seleção', 'Selecione um registro.', parent=self.root)
            return
        {'filaments': self.filament, 'components': self.component,
         'products': self.product, 'orders': self.order, 'projects': self.project}[self.current](old)

    def delete(self):
        old = self.selected()
        if old and messagebox.askyesno('Excluir', f'Excluir {old["code"]}?', parent=self.root):
            self.store.remove(old['id'])
            self.render()

    def filament(self, old=None):
        d = Dialog(self, 'Filamento' + (f' · {old["code"]}' if old else ''))
        get = lambda k, default='': old.get(k, default) if old else default
        material = choice(d.content, 'Material', ['PLA', 'PETG', 'ABS', 'ASA', 'TPU', 'PA', 'PA-CF', 'Outro'], get('material', 'PLA'))
        name = entry(d.content, 'Descrição (cor, fabricante, acabamento)', get('name'))
        reel = entry(d.content, 'Peso de filamento no carretel (g)', get('reel_g', '1000'))
        value = entry(d.content, 'Valor do carretel (R$)', get('value'))
        density = entry(d.content, 'Densidade (g/cm³)', get('density', '1,24'))
        supplier = entry(d.content, 'Fornecedor', get('supplier'))
        def save():
            self.store.save('filaments', name.get(), {'material': material.get(),
                'reel_g': float(number(reel.get(), 'Peso', minimum=0.001)),
                'value': float(number(value.get(), 'Valor')),
                'density': float(number(density.get(), 'Densidade', minimum=0.001)),
                'supplier': supplier.get()}, id_=get('id') or None)
        d.save_button(save)

    def component(self, old=None):
        d = Dialog(self, 'Material eletrônico' + (f' · {old["code"]}' if old else ''))
        get = lambda k, default='': old.get(k, default) if old else default
        name = entry(d.content, 'Nome (Arduino, ESP32, transistor...)', get('name'))
        description = entry(d.content, 'Descrição', get('description'))
        quantity = entry(d.content, 'Quantidade no pacote', get('quantity', '1'))
        value = entry(d.content, 'Valor do pacote (R$)', get('package_value'))
        supplier = entry(d.content, 'Fornecedor', get('supplier'))
        datasheet = entry(d.content, 'Link do datasheet (https://...)', get('datasheet'))
        def save():
            qty = number(quantity.get(), 'Quantidade', minimum=1)
            if qty != int(qty): raise ValueError('Quantidade deve ser inteira.')
            url = datasheet.get().strip()
            if url and not url.startswith(('https://', 'http://')):
                raise ValueError('O datasheet deve ser um endereço HTTP ou HTTPS.')
            self.store.save('components', name.get(), {'description': description.get(),
                'quantity': int(qty), 'package_value': float(number(value.get(), 'Valor')),
                'supplier': supplier.get(), 'datasheet': url}, id_=get('id') or None)
        d.save_button(save)

    def multi_select(self, parent, label, records, selected=None):
        ttk.Label(parent, text=label).pack(anchor='w', padx=8, pady=(14, 3))
        lst = tk.Listbox(parent, selectmode='multiple', exportselection=False, height=min(7, max(3, len(records))))
        lst.pack(fill='x', padx=8)
        selected = set(selected or [])
        for i, r in enumerate(records):
            lst.insert('end', f'{r["code"]} · {r["name"]}')
            if r['id'] in selected: lst.selection_set(i)
        return lambda: [records[i] for i in lst.curselection()]

    def product(self, old=None):
        d = Dialog(self, 'Produto' + (f' · {old["code"]}' if old else ''), height=780)
        get = lambda k, default='': old.get(k, default) if old else default
        name = entry(d.content, 'Nome do produto', get('name'))
        kind = choice(d.content, 'Tipo de produto', list(KINDS), get('type', 'Impresso'))
        margin = entry(d.content, 'Lucro sobre o custo (%)', get('profit', self.store.setting('profit')))
        detail = ttk.Frame(d.content)
        detail.pack(fill='x')
        state = {}
        def draw(*_):
            for w in detail.winfo_children(): w.destroy()
            state.clear()
            mode = kind.get()
            if mode == 'Impresso':
                filaments = self.store.all('filaments')
                state['selected'] = self.multi_select(detail, 'Filamentos possíveis (Ctrl+clique)', filaments, get('filament_ids', []))
                state['weight'] = entry(detail, 'Peso de filamento por unidade (g)', get('weight_g', '0'))
                state['hours'] = entry(detail, 'Tempo de impressão por unidade (h)', get('print_hours', '0'))
                state['labor_hours'] = entry(detail, 'Horas de modelagem por unidade', get('labor_hours', '0'))
                state['hour_rate'] = entry(detail, 'Hora de modelagem (R$/h)', get('hour_rate', self.store.setting('modeling_hour')))
            elif mode == 'Eletrônico':
                parts = self.store.all('components')
                state['parts'] = self.multi_select(detail, 'Componentes (Ctrl+clique)', parts, [x['id'] for x in get('parts', [])])
                state['quantities'] = entry(detail, 'Quantidades na ordem acima (ex.: 2,1,4)',
                                            ','.join(str(x['qty']) for x in get('parts', [])))
                state['hours'] = entry(detail, 'Tempo de preparo (h)', get('prep_hours', '0'))
                state['hour_rate'] = entry(detail, 'Hora técnica (R$/h)', get('hour_rate', self.store.setting('electronics_hour')))
            else:
                products = [r for r in self.store.all('products') if r['type'] in ('Impresso', 'Eletrônico') and r['id'] != get('id')]
                state['selected'] = self.multi_select(detail, 'Produtos impressos e eletrônicos do conjunto (Ctrl+clique)',
                                                       products, get('product_ids', []))
                state['hours'] = entry(detail, 'Horas de montagem/integração', get('assembly_hours', '0'))
                state['hour_rate'] = entry(detail, 'Hora técnica (R$/h)', get('hour_rate', self.store.setting('technical_hour')))
            ttk.Label(detail, text='O orçamento é recalculado e salvo ao confirmar.\n'
                      'Custo = materiais + energia + trabalho; preço = custo × (1 + lucro/100).').pack(anchor='w', padx=8, pady=15)
        kind.trace_add('write', draw)
        draw()
        def save():
            m = number(margin.get(), 'Lucro')
            mode = kind.get()
            payload = {'type': mode, 'profit': float(m)}
            if mode == 'Impresso':
                items = state['selected']()
                quote = print_quote(items, state['weight'].get(), state['hours'].get(),
                    self.store.setting('kwh'), self.store.setting('printer_w'), m,
                    state['labor_hours'].get(), state['hour_rate'].get())
                payload.update(filament_ids=[i['id'] for i in items], weight_g=float(number(state['weight'].get())),
                    print_hours=float(number(state['hours'].get())), labor_hours=float(number(state['labor_hours'].get())),
                    hour_rate=float(number(state['hour_rate'].get())), worst_code=quote['worst_code'])
            elif mode == 'Eletrônico':
                items = state['parts']()
                amounts = [s.strip() for s in state['quantities'].get().split(',') if s.strip()]
                if len(items) != len(amounts) or not items: raise ValueError('Selecione componentes e informe uma quantidade para cada um.')
                parts = [(item, float(number(q, 'Quantidade', minimum=1))) for item, q in zip(items, amounts)]
                quote = electronic_quote(parts, state['hours'].get(), state['hour_rate'].get(), m)
                payload.update(parts=[{'id': i['id'], 'qty': q} for i, q in parts],
                    prep_hours=float(number(state['hours'].get())), hour_rate=float(number(state['hour_rate'].get())))
            else:
                items = state['selected']()
                if not items: raise ValueError('Selecione pelo menos um produto do conjunto.')
                labor = number(state['hours'].get()) * number(state['hour_rate'].get())
                cost = sum((number(i['cost']) for i in items), labor)
                quote = {'material': amount(cost-labor), 'labor': amount(labor), 'energy': 0,
                         'cost': amount(cost), 'sale': amount(cost * (1+m/100))}
                payload.update(product_ids=[i['id'] for i in items], assembly_hours=float(number(state['hours'].get())),
                               hour_rate=float(number(state['hour_rate'].get())))
            payload.update(quote)
            self.store.save('products', name.get(), payload, id_=get('id') or None)
        d.save_button(save)

    def order(self, old=None):
        d = Dialog(self, 'Pedido' + (f' · {old["code"]}' if old else ''))
        get = lambda k, default='': old.get(k, default) if old else default
        client = entry(d.content, 'Cliente', get('name'))
        due = entry(d.content, 'Entrega (DD/MM/AAAA)', display_date(get('due')))
        products = self.store.all('products')
        selected = self.multi_select(d.content, 'Produtos (Ctrl+clique)', products, [x['id'] for x in get('items', [])])
        qty = entry(d.content, 'Quantidades na ordem acima (ex.: 2,1)',
                    ','.join(str(x['qty']) for x in get('items', [])))
        status = choice(d.content, 'Status', ['Aberto', 'Em produção', 'Pronto', 'Entregue', 'Cancelado'], get('status', 'Aberto'))
        payment = choice(d.content, 'Pagamento', ['Pendente', 'Parcial', 'Pago'], get('payment', 'Pendente'))
        charge = entry(d.content, 'Valor de cobrança manual (R$; deixe vazio para calcular)', get('manual_charge'))
        def save():
            items = selected()
            amounts = [s.strip() for s in qty.get().split(',') if s.strip()]
            if not items or len(items) != len(amounts): raise ValueError('Selecione produtos e informe uma quantidade para cada um.')
            lines = []
            total = 0
            for product, q in zip(items, amounts):
                n = number(q, 'Quantidade', minimum=1)
                if int(n) != n: raise ValueError('A quantidade deve ser inteira.')
                # Congela o preço unitário no pedido para não mudar com edições no catálogo.
                lines.append({'id': product['id'], 'code': product['code'], 'name': product['name'],
                              'qty': int(n), 'unit_sale': product['sale']})
                total += product['sale'] * int(n)
            manual = charge.get().strip()
            self.store.save('orders', client.get(), {'items': lines,
                'summary': ', '.join(f'{x["qty"]}× {x["name"]}' for x in lines),
                'suggested': amount(total), 'manual_charge': manual,
                'charge': amount(number(manual, 'Cobrança') if manual else total),
                'payment': payment.get()}, due.get(), status.get(), get('id') or None)
        d.save_button(save)

    def project(self, old=None):
        d = Dialog(self, 'Projeto de mecatrônica' + (f' · {old["code"]}' if old else ''), height=780)
        get = lambda k, default='': old.get(k, default) if old else default
        name = entry(d.content, 'Nome do projeto', get('name'))
        client = entry(d.content, 'Cliente', get('client'))
        due = entry(d.content, 'Prazo (DD/MM/AAAA)', display_date(get('due')))
        status = choice(d.content, 'Status', ['Planejamento', 'Em desenvolvimento', 'Validação', 'Concluído', 'Cancelado'],
                        get('status', 'Planejamento'))
        scope = entry(d.content, 'Oportunidade ou problema', get('scope'))
        objective = entry(d.content, 'Objetivo e entregáveis', get('objective'))
        constraints = entry(d.content, 'Restrições e premissas', get('constraints'))
        quality = entry(d.content, 'Critérios de qualidade e aceitação', get('quality'))
        risks = entry(d.content, 'Riscos e testes previstos', get('risks'))
        specialization = choice(d.content, 'Especialidade para estimativa de hora',
                                ['Hora técnica geral'] + list(DEFAULT_RATES), get('specialization', 'Hora técnica geral'))
        hours = entry(d.content, 'Horas técnicas previstas', get('hours', '0'))
        rate = entry(d.content, 'Valor da hora técnica (R$/h)', get('rate', self.store.setting('technical_hour')))
        def choose_rate(*_):
            if old: return
            rate.set(str(self.store.setting(specialization.get()) if specialization.get() in DEFAULT_RATES
                         else self.store.setting('technical_hour')))
        specialization.trace_add('write', choose_rate)
        materials = entry(d.content, 'Materiais e serviços externos (R$)', get('materials', '0'))
        profit = entry(d.content, 'Lucro (%)', get('profit', self.store.setting('profit')))
        def save():
            cost = number(hours.get(), 'Horas') * number(rate.get(), 'Hora técnica') + number(materials.get(), 'Materiais')
            sale = cost * (1 + number(profit.get(), 'Lucro')/100)
            project_id = self.store.save('projects', name.get(), {'client': client.get(), 'scope': scope.get(),
                'objective': objective.get(), 'constraints': constraints.get(), 'quality': quality.get(),
                'risks': risks.get(), 'specialization': specialization.get(),
                'hours': float(number(hours.get())), 'rate': float(number(rate.get())),
                'materials': float(number(materials.get())), 'profit': float(number(profit.get())),
                'cost': amount(cost), 'sale': amount(sale)}, due.get(), status.get(), get('id') or None)
            if not old:
                # O marco inicial também aparece no calendário e no Kanban.
                self.store.add_task(project_id, 'Planejar e validar escopo', due.get())
        d.save_button(save)

    def kanban(self):
        project = self.selected()
        if not project: return messagebox.showinfo('Seleção', 'Selecione um projeto.', parent=self.root)
        d = tk.Toplevel(self.root)
        d.title('Kanban · '+project['name'])
        d.geometry('950x570')
        d.configure(bg=BG)
        d.transient(self.root)
        form = tk.Frame(d, bg=BG)
        form.pack(fill='x', padx=15, pady=14)
        title = ttk.Entry(form, width=45)
        title.pack(side='left', padx=5)
        due = ttk.Entry(form, width=16)
        due.insert(0, 'DD/MM/AAAA')
        due.pack(side='left', padx=5)
        board = tk.Frame(d, bg=BG)
        board.pack(fill='both', expand=True, padx=12)
        def refresh():
            for widget in board.winfo_children(): widget.destroy()
            tasks = self.store.tasks(project['id'])
            for col, status in enumerate(('A fazer', 'Em andamento', 'Concluído')):
                frame = tk.Frame(board, bg=PANEL, padx=10, pady=10)
                frame.grid(row=0, column=col, sticky='nsew', padx=5)
                board.grid_columnconfigure(col, weight=1)
                tk.Label(frame, text=status, bg=PANEL, fg=DARK,
                         font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=8)
                for task in tasks:
                    if task['status'] != status: continue
                    card = tk.Frame(frame, bg=MINT, padx=8, pady=8)
                    card.pack(fill='x', pady=5)
                    tk.Label(card, text=task['title']+'\n'+display_date(task['due']),
                             bg=MINT, fg=INK, justify='left', wraplength=250).pack(anchor='w')
                    actions = tk.Frame(card, bg=MINT)
                    actions.pack(anchor='w')
                    for label, target in (('←', 'A fazer' if status == 'Em andamento' else 'Em andamento'),
                                          ('→', 'Em andamento' if status == 'A fazer' else 'Concluído')):
                        if target != status:
                            ActionButton(actions, label,
                                lambda i=task['id'], s=target: (self.store.task_status(i,s), refresh()),
                                background=MINT).pack(side='left', padx=(0, 5))
                    ActionButton(actions, 'Excluir', lambda i=task['id']: (
                        self.store.delete_task(i), refresh()), 'danger', MINT).pack(side='left')
        def add():
            try:
                self.store.add_task(project['id'], title.get(), '' if due.get() == 'DD/MM/AAAA' else due.get())
                title.delete(0, 'end')
                refresh()
            except ValueError as exc: messagebox.showerror('Tarefa', str(exc), parent=d)
        ActionButton(form, 'Adicionar subtarefa', add, 'primary').pack(side='left')
        refresh()

    def settings_page(self):
        canvas = tk.Canvas(self.main, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(self.main, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side='left', fill='both', expand=True, padx=(24, 0), pady=8)
        scroll.pack(side='right', fill='y', pady=8)
        panel = ttk.Frame(canvas, padding=18)
        slot = canvas.create_window((0, 0), window=panel, anchor='nw')
        panel.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(slot, width=e.width))
        ttk.Label(panel, text='Energia e precificação', font=('Segoe UI', 14, 'bold')).pack(anchor='w')
        keys = [('kwh', 'Tarifa de energia (R$/kWh)'), ('printer_w', 'Potência média da impressora (W)'),
                ('profit', 'Lucro padrão (%)'), ('modeling_hour', 'Hora de modelagem padrão (R$/h)'),
                ('electronics_hour', 'Hora eletrônica padrão (R$/h)'),
                ('technical_hour', 'Hora técnica de projetos (R$/h)')]
        vars_ = {key: entry(panel, label, self.store.setting(key)) for key, label in keys}
        ttk.Label(panel, text='Calculadora: consumo (kWh) = potência (W) × horas / 1000.').pack(anchor='w', pady=12)
        calc_w = entry(panel, 'Potência do equipamento para simulação (W)', self.store.setting('printer_w'))
        calc_h = entry(panel, 'Horas de uso por dia', 8)
        calc_days = entry(panel, 'Dias de uso por mês', 22)
        result = ttk.Label(panel, text='')
        result.pack(anchor='w', pady=8)
        def calculate():
            try:
                hours = number(calc_h.get()) * number(calc_days.get())
                kwh = number(calc_w.get()) * hours / 1000
                result.configure(text=f'Consumo: {kwh:.2f} kWh/mês · Custo: {money(energy_cost(calc_w.get(), hours, vars_["kwh"].get()))}/mês')
            except ValueError as exc: messagebox.showerror('Energia', str(exc), parent=self.root)
        ActionButton(panel, 'Calcular energia', calculate, background=PANEL).pack(anchor='w', pady=8)
        ttk.Label(panel, text='Horas sugeridas por especialidade · altere para sua realidade',
                  font=('Segoe UI', 14, 'bold')).pack(anchor='w', pady=(22, 6))
        ttk.Label(panel, text='Estimativas iniciais editáveis em R$/h; não são tabela oficial.').pack(anchor='w')
        rates = {key: entry(panel, key.replace('|', ' · '), self.store.setting(key)) for key in DEFAULT_RATES}
        ttk.Label(panel, text='Simular preço de serviço', font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=(18, 0))
        service = choice(panel, 'Tipo de trabalho', list(DEFAULT_RATES))
        service_hours = entry(panel, 'Horas estimadas', '1')
        quote_label = ttk.Label(panel, text='')
        quote_label.pack(anchor='w', pady=8)
        def service_quote():
            try:
                subtotal = number(rates[service.get()].get()) * number(service_hours.get(), 'Horas')
                sale = subtotal * (1 + number(vars_['profit'].get(), 'Lucro') / 100)
                quote_label.configure(text=f'Base: {money(subtotal)} · Com lucro: {money(sale)}')
            except ValueError as exc: messagebox.showerror('Simulação', str(exc), parent=self.root)
        ActionButton(panel, 'Calcular serviço', service_quote, background=PANEL).pack(anchor='w', pady=6)
        def save():
            try:
                # Valida tudo antes de qualquer alteração persistente.
                values = {key: float(number(var.get(), key)) for key, var in {**vars_, **rates}.items()}
                for key, val in values.items(): self.store.set_setting(key, val)
                self.status.set('Parâmetros de cálculo salvos')
                messagebox.showinfo('Parâmetros', 'Valores salvos. Reabra um produto para recalcular seu orçamento.', parent=self.root)
            except ValueError as exc: messagebox.showerror('Verifique os valores', str(exc), parent=self.root)
        ActionButton(panel, 'Salvar parâmetros', save, 'primary', PANEL).pack(anchor='w', pady=20)
        ttk.Label(panel, text='Referências: adrianoaoli.com/eletronica/calculadora-consumo-eletrico.html\n'
                  'workana.com/pt/freelancers/brasil/modelacao-3d · sebrae.com.br (precificação).',
                  wraplength=800).pack(anchor='w', pady=10)

    def calendar_page(self):
        line = tk.Frame(self.main, bg=BG)
        line.pack(fill='x', padx=24)
        ActionButton(line, '◀', lambda: self.move_month(-1)).pack(side='left')
        tk.Label(line, text=f'{calendar.month_name[self.month.month]} {self.month.year}',
                 bg=BG, fg=DARK, font=('Segoe UI', 14, 'bold')).pack(side='left', padx=15)
        ActionButton(line, '▶', lambda: self.move_month(1)).pack(side='left')
        events = self.store.agenda()
        month_events = [r for r in events if r['date'].startswith(self.month.strftime('%Y-%m'))]
        weeks = calendar.monthcalendar(self.month.year, self.month.month)
        frame = tk.Frame(self.main, bg=BG)
        frame.pack(fill='both', expand=True, padx=24, pady=12)
        for col, label in enumerate(('Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom')):
            frame.grid_columnconfigure(col, weight=1)
            tk.Label(frame, text=label, bg=DARK, fg='white', pady=7).grid(row=0, column=col, sticky='ew', padx=2)
        for row, week in enumerate(weeks, 1):
            frame.grid_rowconfigure(row, weight=1)
            for col, day in enumerate(week):
                box = tk.Frame(frame, bg=PANEL if day else BG, bd=1, relief='solid')
                box.grid(row=row, column=col, sticky='nsew', padx=2, pady=2)
                if not day: continue
                tk.Label(box, text=str(day), bg=PANEL, fg=GREEN if day == date.today().day and
                         self.month.month == date.today().month else INK, font=('Segoe UI', 10, 'bold')).pack(anchor='nw', padx=5)
                for event in [x for x in month_events if int(x['date'][-2:]) == day][:3]:
                    tk.Label(box, text=event['source']+' '+event['description'], bg=MINT, fg=INK,
                             wraplength=155, anchor='w', justify='left').pack(fill='x', padx=3, pady=2)

    def move_month(self, delta):
        m = self.month.year * 12 + self.month.month - 1 + delta
        self.month = date(m//12, m%12+1, 1)
        self.render()

    def pending_page(self):
        tree = self.table(('Prazo', 'Origem', 'Tarefa ou entrega', 'Status'))
        open_status = {'A fazer', 'Em andamento', 'Aberto', 'Em produção', 'Pronto'}
        for i, event in enumerate(self.store.agenda()):
            if event['status'] in open_status:
                tree.insert('', 'end', iid=str(i), values=(display_date(event['date']), event['source'],
                            event['description'], event['status']))

    def select_backup(self):
        folder = filedialog.askdirectory(title='Escolha a pasta para backups automáticos')
        if folder:
            try:
                self.backup.select(folder)
                self.status.set('Backup diário: '+folder)
            except (OSError, ValueError) as exc: messagebox.showerror('Backup', str(exc), parent=self.root)

    def daily_backup(self):
        if self.closing: return
        def work():
            try:
                result = self.backup.create(self.store.path)
                self.events.put(('backup', result))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=work, daemon=True).start()
        self.root.after(3600000, self.daily_backup)

    def start_update(self):
        def work():
            try:
                version = check_and_stage(self.config, self.folder)
                if version: self.events.put(('update', version))
            except Exception as exc:
                self.events.put(('error', 'Atualização: '+str(exc)))
        threading.Thread(target=work, daemon=True).start()
        self.poll_events()

    def poll_events(self):
        try:
            while True:
                kind, message = self.events.get_nowait()
                if kind == 'backup':
                    self.status.set('Backup concluído' if not message.selected_error else
                                    'Backup local salvo; pasta escolhida indisponível')
                elif kind == 'update':
                    self.status.set(f'Versão {message} pronta. Reinicie para atualizar.')
                else: self.status.set(message)
        except queue.Empty: pass
        if not self.closing: self.root.after(900, self.poll_events)

    def close(self):
        if self.closing: return
        self.closing = True
        self.store.db.commit()
        dialog = tk.Toplevel(self.root)
        dialog.title('Cópia de segurança')
        dialog.geometry('370x140')
        dialog.transient(self.root)
        dialog.protocol('WM_DELETE_WINDOW', lambda: None)
        ttk.Label(dialog, text='Backup sendo realizado', font=('Segoe UI', 14, 'bold')).pack(pady=(22, 10))
        ttk.Progressbar(dialog, mode='indeterminate').pack(fill='x', padx=35, pady=10)
        dialog.grab_set()
        done = queue.Queue()
        def work():
            try: done.put(self.backup.create(self.store.path))
            except Exception as exc: done.put(exc)
        threading.Thread(target=work, daemon=True).start()
        def poll():
            try: result = done.get_nowait()
            except queue.Empty: return self.root.after(120, poll)
            if isinstance(result, Exception):
                messagebox.showerror('Backup', f'Não foi possível concluir o backup: {result}', parent=dialog)
                self.closing = False
                dialog.destroy()
                return
            dialog.destroy()
            self.store.db.close()
            self.root.destroy()
        poll()


def main():
    config = read_config(resource('update_config.json'))
    if launch_cached(config, data_dir()): return
    root = tk.Tk()
    ERP(root)
    root.mainloop()


if __name__ == '__main__':
    main()
