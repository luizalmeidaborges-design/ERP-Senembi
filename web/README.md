# ERP Senembi — versão web (Cloudflare)

Versão do ERP para o navegador, publicada como **Cloudflare Worker** com banco **D1**. Tem as mesmas páginas do app desktop (filamentos, materiais eletrônicos, produtos, pedidos, projetos com Kanban, informações adicionais, calendário e tarefas pendentes) e funciona no computador e no celular.

- `src/core.js`: fórmulas de orçamento e regras de cadastro, portadas de `core.py`/`app.py`. Os cálculos rodam no Worker; o teste `test/core.test.mjs` compara 300 casos com o `core.py`.
- `src/worker.js`: login (usuário e senha, cookie de sessão de 30 dias) e API `/api/*`.
- `public/`: interface (HTML/CSS/JS sem build). `public/vendor/` traz o sql.js 1.10.3 (licença MIT), usado só para ler o `senembi.db` na importação.
- `migrations/0001_esquema.sql`: o mesmo esquema do `senembi.db` (tabelas `records`, `counters`, `settings`, `tasks`).

## Publicar (uma vez)

O banco D1 `erp-senembi` já existe na conta Cloudflare, com o esquema criado, e o ID está em `wrangler.jsonc`.

1. Cloudflare → **Workers & Pages** → **Create** → **Import a repository** → escolher `ERP-Senembi`.
2. Em **Build settings**: *Root directory* = `web`, *Deploy command* = `npx wrangler deploy` e *Production branch* = `main`. Não há comando de build.
3. Depois do primeiro deploy: Worker `erp-senembi` → **Settings → Variables and Secrets**:
   - `ERP_USUARIO` (Text) com o seu usuário;
   - `ERP_SENHA` (**Secret**) com uma senha forte.
   Sem essas duas variáveis o site responde 503 e não mostra nada.
4. Abra `https://erp-senembi.luiz-almeidaborges.workers.dev`, entre e, em **Informações adicionais → Importar e exportar dados**, escolha o `senembi.db` (`%LOCALAPPDATA%\Senembi\ERP\senembi.db`). Feche o app desktop antes de copiar o arquivo.

A cada push na `main` que altere `web/`, o Cloudflare publica de novo. O workflow do EXE continua disparando só por `release-version.txt`.

### Opcional

- **Domínio próprio:** Worker → Settings → Domains & Routes → Add → Custom domain (o domínio precisa estar na Cloudflare).
- **Camada extra de acesso:** Zero Trust → Access → Applications → Self-hosted, com o domínio do ERP e a política "Emails = seu e-mail". O Cloudflare pede um código por e-mail antes do login do ERP.

## Dados e backup

- A importação **substitui** todos os dados da versão web, numa única transação: ou importa tudo, ou nada.
- **Baixar cópia (.json)** exporta tudo e pode ser importado de volta.
- O D1 guarda automaticamente 30 dias de histórico (*Time Travel*). Para restaurar: `npx wrangler d1 time-travel restore erp-senembi --timestamp=...`.
- A versão web e o app desktop têm bancos separados; não há sincronização automática entre eles.

## Diferenças em relação ao desktop

- Produto eletrônico e pedido: a quantidade é digitada ao lado de cada item marcado, e não mais numa lista "2,1,4".
- Produto: o formulário mostra uma prévia do orçamento, calculada no servidor, antes de salvar.
- Pedido: ao editar, os itens que já estavam no pedido mantêm o preço unitário da criação (como descrito no README principal). O desktop recalcula com o preço atual do catálogo ao salvar de novo.
- Backup em pasta e atualizador do EXE não se aplicam à web.

## Desenvolvimento local

```bash
cd web
npm install
printf 'ERP_USUARIO=felipe\nERP_SENHA=teste\n' > .dev.vars
npm run dev      # aplica o esquema no D1 local e abre http://localhost:8787
npm test         # compara as fórmulas com o core.py (precisa de python3)
```
