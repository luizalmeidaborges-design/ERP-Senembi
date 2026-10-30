# ERP Senembi — versão web (Cloudflare)

Versão do ERP para o navegador, publicada como **Cloudflare Worker** com banco **D1**. Tem as mesmas páginas do app desktop (filamentos, materiais eletrônicos, produtos, pedidos, projetos com Kanban, informações adicionais, calendário e tarefas pendentes) e funciona no computador e no celular.

- `src/core.js`: fórmulas de orçamento e regras de cadastro, portadas de `core.py`/`app.py`. Os cálculos rodam no Worker; o teste `test/core.test.mjs` compara 300 casos com o `core.py`.
- `src/worker.js`: login (usuário e senha, cookie de sessão de 30 dias) e API `/api/*`.
- `public/`: interface (HTML/CSS/JS sem build). `public/vendor/` traz o sql.js 1.10.3 (licença MIT), usado só para ler o `senembi.db` na importação.
- `migrations/0001_esquema.sql`: o mesmo esquema do `senembi.db` (tabelas `records`, `counters`, `settings`, `tasks`).
- `migrations/0002_sincronizacao.sql`: versões (`rev`, `updated_at`), exclusões (`tombstones`) e gatilhos usados pela sincronização com o app desktop.

## Publicar (uma vez)

O banco D1 `erp-senembi` já existe na conta Cloudflare, com as migrações 0001 e 0002 aplicadas, e o ID está em `wrangler.jsonc`. Para futuras migrações: `npx wrangler d1 migrations apply erp-senembi --remote`.

1. Cloudflare → **Workers & Pages** → **Create** → **Import a repository** → escolher `ERP-Senembi`.
2. Em **Build settings**: *Root directory* = `web`, *Deploy command* = `npx wrangler deploy` e *Production branch* = `main`. Não há comando de build.
3. Depois do primeiro deploy: Worker `erp-senembi` → **Settings → Variables and Secrets**:
   - `ERP_USUARIO` (Text) com o seu usuário;
   - `ERP_SENHA` (**Secret**) com uma senha forte;
   - `ERP_SYNC_TOKEN` (**Secret**) com 24 caracteres ou mais, usado pelo app desktop para sincronizar.
   Sem `ERP_USUARIO` e `ERP_SENHA` o site responde 503 e não mostra nada. Sem `ERP_SYNC_TOKEN` a sincronização fica desligada.
4. Abra `https://erp-senembi.luiz-almeidaborges.workers.dev`, entre e, em **Informações adicionais → Importar e exportar dados**, escolha o `senembi.db` (`%LOCALAPPDATA%\Senembi\ERP\senembi.db`). Feche o app desktop antes de copiar o arquivo.

A cada push na `main` que altere `web/`, o Cloudflare publica de novo. O workflow do EXE continua disparando só por `release-version.txt`.

### Opcional

- **Domínio próprio:** Worker → Settings → Domains & Routes → Add → Custom domain (o domínio precisa estar na Cloudflare).
- **Camada extra de acesso:** Zero Trust → Access → Applications → Self-hosted, com o domínio do ERP e a política "Emails = seu e-mail". O Cloudflare pede um código por e-mail antes do login do ERP.

## Dados e backup

- A importação **substitui** todos os dados da versão web, numa única transação: ou importa tudo, ou nada.
- **Baixar cópia (.json)** exporta tudo e pode ser importado de volta.
- O D1 guarda automaticamente 30 dias de histórico (*Time Travel*). Para restaurar: `npx wrangler d1 time-travel restore erp-senembi --timestamp=...`.
- A importação vale para o primeiro carregamento. Depois de ativar a sincronização, use-a no lugar da importação: importar de novo substitui tudo, e os computadores recebem essa substituição.

## Sincronização com o app desktop

No app desktop, use **Configurar web** e informe o endereço (`https://erp-senembi.luiz-almeidaborges.workers.dev`), o `ERP_SYNC_TOKEN` e o número do computador (1 no primeiro PC, 2 no segundo, e assim por diante). Depois disso o app sincroniza ao abrir, a cada 5 minutos, ao fechar e pelo botão **Sincronizar**.

- **O que vai:** filamentos, materiais, produtos, pedidos, projetos, subtarefas, parâmetros e exclusões.
- **Mesmo item alterado nos dois lados:** vale a alteração mais recente, comparando o relógio de quem alterou. Mantenha o relógio do PC no automático.
- **Exclusão contra alteração:** se a alteração for posterior à exclusão, o item continua existindo.
- **Mesmo código criado dos dois lados sem sincronizar** (por exemplo, `OP-00007` na web e no PC): o registro que chegou por último recebe o próximo número, e o app mostra a troca na barra lateral.
- **IDs:** a web usa `id % 16 = 0` e cada PC usa o seu número, então os ids nunca colidem.
- **Sem internet:** as alterações ficam marcadas e são enviadas na próxima sincronização.
- O primeiro PC que sincronizar envia todo o banco local, o que substitui a importação manual.

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
# teste da sincronização contra o Worker local (banco local vazio; acrescente ERP_SYNC_TOKEN ao .dev.vars):
cd .. && ERP_SYNC_URL=http://127.0.0.1:8787 ERP_SYNC_TOKEN=... python -m unittest tests.test_sync
```
