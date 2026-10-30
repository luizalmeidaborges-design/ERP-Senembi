// ERP Senembi — Cloudflare Worker
// 1) Pede usuário e senha (ERP_USUARIO / ERP_SENHA) para tudo: páginas e API.
// 2) /api/*: cadastros, orçamentos, Kanban, parâmetros, importação e exportação no D1 (binding DB).
// 3) O resto vem da pasta public/ (binding ASSETS).
import { DEFAULT_RATES, KINDS, Store, UserError } from './core.js';

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json; charset=utf-8' } });

// ---------- login com formulário + cookie de sessão (30 dias) ----------
const COOKIE = 'erp_sessao';
const DIAS = 30;
const enc = new TextEncoder();
const b64url = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

async function hmac(env, texto) {
  const key = await crypto.subtle.importKey('raw', enc.encode(env.ERP_USUARIO + '\u0000' + env.ERP_SENHA),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return b64url(await crypto.subtle.sign('HMAC', key, enc.encode(texto)));
}
async function iguais(a, b) {
  // comparação em tempo constante (compara os hashes)
  const [ha, hb] = await Promise.all([crypto.subtle.digest('SHA-256', enc.encode(a)), crypto.subtle.digest('SHA-256', enc.encode(b))]);
  return crypto.subtle.timingSafeEqual ? crypto.subtle.timingSafeEqual(ha, hb) : b64url(ha) === b64url(hb);
}
function lerCookie(request, nome) {
  for (const parte of (request.headers.get('Cookie') || '').split(';')) {
    const [k, ...v] = parte.trim().split('=');
    if (k === nome) return v.join('=');
  }
  return null;
}
async function sessaoValida(request, env) {
  const v = lerCookie(request, COOKIE);
  if (!v) return false;
  const [exp, sig] = v.split('.');
  if (!exp || !sig || !(Number(exp) > Date.now())) return false;
  return iguais(sig, await hmac(env, exp));
}
async function novaSessao(env) {
  const exp = String(Date.now() + DIAS * 86400000);
  return `${COOKIE}=${exp}.${await hmac(env, exp)}; Path=/; Max-Age=${DIAS * 86400}; HttpOnly; Secure; SameSite=Lax`;
}

function paginaLogin(erro = '') {
  return new Response(`<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex"><title>Senembi T-Labs | ERP</title>
<link rel="icon" href="/icon.png">
<style>
:root{--bg:#edf5f1;--card:#fff;--text:#183831;--muted:#60776b;--line:#cddfd3;--accent:#228659;--bad:#963d35;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#0e1a17;--card:#152521;--text:#e3efe9;--muted:#9bb5a8;--line:#29413a;--accent:#4cc38a;--bad:#f0a49a;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--text);font:16px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding:16px}
form{width:100%;max-width:340px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:24px;display:grid;gap:14px}
.brand{background:#153b36;border-radius:10px;padding:10px;display:grid;place-items:center}
.brand img{max-width:100%;height:56px}
h1{margin:0;font-size:20px}
label{display:grid;gap:4px;font-size:13px;color:var(--muted)}
input{width:100%;min-height:44px;background:var(--bg);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:10px 12px;font:16px inherit}
input:focus-visible,button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
button{min-height:44px;border:0;border-radius:8px;background:var(--accent);color:#fff;font:600 16px inherit;cursor:pointer}
.err{color:var(--bad);font-size:14px;margin:0}
</style></head><body>
<form method="post" action="/login">
  <div class="brand"><img src="/logo.png" alt="Senembi T-Labs"></div>
  <h1>ERP · Entrar</h1>
  ${erro ? `<p class="err" role="alert">${erro}</p>` : ''}
  <label>Usuário<input name="username" autocomplete="username" autocapitalize="none" autocorrect="off" spellcheck="false" required></label>
  <label>Senha<input name="password" type="password" autocomplete="current-password" required></label>
  <button type="submit">Entrar</button>
</form>
</body></html>`, {
    status: erro ? 401 : 200,
    headers: { 'content-type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex' },
  });
}

// ---------- API ----------
async function corpo(request) {
  try { return await request.json(); } catch { throw new UserError('JSON inválido.'); }
}
const SAVERS = { filaments: 'saveFilament', components: 'saveComponent', products: 'saveProduct',
  orders: 'saveOrder', projects: 'saveProject' };

async function api(request, env, path) {
  const store = new Store(env.DB);
  const m = request.method;
  let r;
  if (path === '/api/estado' && m === 'GET') {
    const data = { settings: await store.settings(), rates: Object.keys(DEFAULT_RATES), tasks: await store.tasks() };
    for (const k of KINDS) data[k] = await store.all(k);
    return json(data);
  }
  if ((r = path.match(/^\/api\/registros\/(\w+)(?:\/(\d+))?$/)) && KINDS.includes(r[1])) {
    const id = r[2] ? Number(r[2]) : null;
    if (m === 'POST' && id == null) return json({ id: await store[SAVERS[r[1]]](await corpo(request), null) }, 201);
    if (m === 'PUT' && id != null) return json({ id: await store[SAVERS[r[1]]](await corpo(request), id) });
    if (m === 'DELETE' && id != null) {
      const old = await store.get(id);
      if (!old || old.kind !== r[1]) return json({ erro: 'Registro não encontrado.' }, 404);
      await store.remove(id);
      return json({ ok: true });
    }
  }
  if (path === '/api/produtos/simular' && m === 'POST') {
    const b = await corpo(request);
    return json(await store.productQuote(b, b.id == null ? null : Number(b.id)));
  }
  if ((r = path.match(/^\/api\/projetos\/(\d+)\/tarefas$/)) && m === 'POST') {
    const b = await corpo(request);
    await store.addTask(Number(r[1]), b.title, b.due);
    return json({ ok: true }, 201);
  }
  if ((r = path.match(/^\/api\/tarefas\/(\d+)$/))) {
    if (m === 'PATCH') { await store.taskStatus(Number(r[1]), (await corpo(request)).status); return json({ ok: true }); }
    if (m === 'DELETE') { await store.deleteTask(Number(r[1])); return json({ ok: true }); }
  }
  if (path === '/api/parametros' && m === 'PUT') {
    await store.saveSettings(await corpo(request));
    return json(await store.settings());
  }
  if (path === '/api/exportar' && m === 'GET') {
    const res = json(await store.exportAll());
    res.headers.set('Content-Disposition', `attachment; filename="erp-senembi-${new Date().toISOString().slice(0, 10)}.json"`);
    return res;
  }
  if (path === '/api/importar' && m === 'POST') {
    const b = await corpo(request);
    if (b.confirmar !== 'SUBSTITUIR') throw new UserError('Confirme a substituição dos dados.');
    return json(await store.importAll(b.dados));
  }
  return json({ erro: 'Rota não encontrada.' }, 404);
}

// Sincronização do app desktop: autenticada por token (ERP_SYNC_TOKEN), não pelo login do navegador.
async function sincronizar(request, env) {
  if (!env.ERP_SYNC_TOKEN || env.ERP_SYNC_TOKEN.length < 24) {
    return json({ erro: 'Sincronização desligada: crie o segredo ERP_SYNC_TOKEN (mínimo 24 caracteres) no Cloudflare.' }, 503);
  }
  const auth = request.headers.get('Authorization') || '';
  if (!(await iguais(auth, `Bearer ${env.ERP_SYNC_TOKEN}`))) {
    await new Promise((r) => setTimeout(r, 800));
    return json({ erro: 'Token de sincronização inválido.' }, 401);
  }
  if (request.method !== 'POST') return json({ erro: 'Método não permitido.' }, 405);
  if (!env.DB) return json({ erro: 'Banco D1 ainda não ligado (binding DB).' }, 503);
  try {
    return json(await new Store(env.DB).sync(await corpo(request)));
  } catch (e) {
    if (e instanceof UserError || e instanceof SyntaxError) return json({ erro: e.message }, 400);
    console.error(e);
    return json({ erro: 'Erro interno ao sincronizar.' }, 500);
  }
}

export default {
  async fetch(request, env) {
    // Sem usuário/senha configurados, nada é servido (falha fechada).
    if (!env.ERP_USUARIO || !env.ERP_SENHA) {
      return new Response('ERP bloqueado: configure ERP_USUARIO e ERP_SENHA no Cloudflare.', { status: 503 });
    }
    const url = new URL(request.url);

    if (url.pathname === '/login') {
      if (request.method === 'POST') {
        const f = await request.formData();
        const okU = await iguais(String(f.get('username') || '').trim(), env.ERP_USUARIO);
        const okS = await iguais(String(f.get('password') || ''), env.ERP_SENHA);
        if (okU && okS) {
          return new Response(null, { status: 303, headers: { Location: '/', 'Set-Cookie': await novaSessao(env), 'Cache-Control': 'no-store' } });
        }
        await new Promise((r) => setTimeout(r, 800)); // freia tentativas
        return paginaLogin('Usuário ou senha incorretos.');
      }
      return (await sessaoValida(request, env))
        ? new Response(null, { status: 303, headers: { Location: '/' } })
        : paginaLogin();
    }
    if (url.pathname === '/api/sync') return sincronizar(request, env);
    if (url.pathname === '/logo.png' || url.pathname === '/icon.png') return env.ASSETS.fetch(request);
    if (url.pathname === '/sair') {
      return new Response(null, { status: 303, headers: { Location: '/login', 'Set-Cookie': `${COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax` } });
    }
    if (!(await sessaoValida(request, env))) {
      if (url.pathname.startsWith('/api/')) return json({ erro: 'Sessão expirada. Entre novamente.' }, 401);
      return new Response(null, { status: 303, headers: { Location: '/login', 'Cache-Control': 'no-store' } });
    }
    let res;
    if (url.pathname.startsWith('/api/')) {
      // Alterações só a partir do próprio site (o cookie SameSite=Lax já barra a maioria dos casos).
      const origin = request.headers.get('Origin');
      if (request.method !== 'GET' && origin && origin !== url.origin) return json({ erro: 'Origem não permitida.' }, 403);
      if (!env.DB) return json({ erro: 'Banco D1 ainda não ligado (binding DB).' }, 503);
      try {
        res = await api(request, env, url.pathname);
      } catch (e) {
        if (e instanceof UserError) res = json({ erro: e.message }, 400);
        else { console.error(e); res = json({ erro: 'Erro interno ao acessar o banco.' }, 500); }
      }
    } else {
      res = await env.ASSETS.fetch(request);
    }
    const out = new Response(res.body, res);
    out.headers.set('Cache-Control', 'no-store');
    out.headers.set('X-Robots-Tag', 'noindex');
    return out;
  },
};
