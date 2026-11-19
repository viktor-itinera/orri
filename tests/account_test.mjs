// Test du compte facultatif d'Orri : inscription, synchro du carnet entre deux appareils, suppression, déconnexion,
// suppression du compte. Supabase est simulé en mémoire (Auth + PostgREST), le reste du réseau est coupé.
// Lancer : python3 -m http.server 8765 (à la racine), puis : cd tests && node account_test.mjs
// (node_modules : voir CLAUDE.md, section « Tester » ; Playwright pour Node doit être installé.)
import { createRequire } from 'module';
import path from 'path';
import { fileURLToPath } from 'url';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const URL = process.env.ORRI_URL || 'http://localhost:8765/';
const NM = path.join(path.dirname(fileURLToPath(import.meta.url)), 'node_modules/');

// ---- Faux Supabase ----
const db = { users: [], profiles: {}, treks: [], tick: 0 };
const now = () => new Date(Date.UTC(2026, 10, 19, 8, 0, 0) + ++db.tick).toISOString();
const CORS = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*' };
const sess = u => ({ access_token: 'tok-' + u.id, refresh_token: 'ref-' + u.id, expires_in: 3600, expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: u.id, email: u.email, user_metadata: u.meta } });
let badKey = 0;
async function supa(route) {
  const rq = route.request(), u = new globalThis.URL(rq.url()), h = rq.headers(), m = rq.method();
  const send = (status, body) => route.fulfill({ status, headers: CORS, contentType: 'application/json', body: body == null ? '' : JSON.stringify(body) });
  if (m === 'OPTIONS') return send(204);
  if (h.apikey !== 'sb_publishable_OY8bVQK6AKjK2hfGuxZzGQ_8TAM6pJZ') badKey++;
  const body = rq.postData() ? JSON.parse(rq.postData()) : null;
  const p = u.pathname, q = u.searchParams;
  if (p === '/auth/v1/signup') {
    if (db.users.find(x => x.email === body.email)) return send(422, { code: 422, error_code: 'user_already_exists', msg: 'User already registered' });
    const us = { id: 'u' + (db.users.length + 1), email: body.email, pw: body.password, meta: body.data || {} }; db.users.push(us); return send(200, sess(us));
  }
  if (p === '/auth/v1/token') {
    const us = q.get('grant_type') === 'password' ? db.users.find(x => x.email === body.email && x.pw === body.password) : db.users.find(x => 'ref-' + x.id === body.refresh_token);
    return us ? send(200, sess(us)) : send(400, { error_code: 'invalid_credentials', msg: 'Invalid login credentials' });
  }
  const tok = (h.authorization || '').replace('Bearer ', ''), me = db.users.find(x => 'tok-' + x.id === tok);
  if (p === '/auth/v1/logout') return send(204);
  if (!me) return send(401, { message: 'JWT invalide' });
  if (p === '/rest/v1/rpc/delete_my_account') { db.users = db.users.filter(x => x !== me); db.treks = db.treks.filter(r => r.user_id !== me.id); delete db.profiles[me.id]; return send(204); }
  if (p === '/rest/v1/profiles') {
    if (m === 'POST') { body.forEach(r => { if (r.id === me.id) db.profiles[me.id] = r; }); return send(201); }
    return send(200, db.profiles[me.id] ? [{ name: db.profiles[me.id].name }] : []);
  }
  if (p === '/rest/v1/treks') {
    if (m === 'POST') {
      const out = body.map(r => {
        if (r.user_id !== me.id) throw new Error('user_id');
        let row = db.treks.find(x => x.user_id === me.id && x.id === r.id);
        if (!row) { row = { user_id: me.id, id: r.id }; db.treks.push(row); }
        Object.assign(row, { data: r.data, deleted: r.deleted, updated_at: now() });
        return { id: row.id, updated_at: row.updated_at };
      });
      return send(201, out);
    }
    let rows = db.treks.filter(r => r.user_id === me.id);
    const inq = q.get('id'); if (inq) { const ids = inq.slice(4, -1).split(','); rows = rows.filter(r => ids.includes(r.id)); }
    const cols = q.get('select').split(',');
    return send(200, rows.map(r => Object.fromEntries(cols.map(c => [c, r[c]]))));
  }
  return send(404, { message: 'inconnu ' + p });
}
async function handler(route) {
  const u = route.request().url();
  if (u.startsWith(URL)) return route.continue();
  if (u.includes('.supabase.co/')) return supa(route);
  if (u.includes('cdnjs.cloudflare.com')) return route.fulfill({ path: NM + 'leaflet/dist/leaflet' + (u.endsWith('.css') ? '.css' : '.js') });
  if (u.includes('unpkg.com/maplibre-gl@4')) return route.fulfill({ path: NM + 'maplibre-gl/dist/maplibre-gl' + (u.endsWith('.css') ? '.css' : '.js') });
  if (u.includes('unpkg.com/@maplibre/maplibre-gl-leaflet')) return route.fulfill({ path: NM + '@maplibre/maplibre-gl-leaflet/leaflet-maplibre-gl.js' });
  return route.abort();
}

const fails = [], errors = [];
const check = (ok, what) => { console.log((ok ? 'OK    ' : 'ÉCHEC ') + what); if (!ok) fails.push(what); };
const TREK = (id, name) => ({ id, name, created: '2026-11-01T10:00:00Z', updated: '2026-11-01T10:00:00Z', data: { start: [42.9, -0.1], legs: [{ pts: [[42.9, -0.1, 1000], [42.95, 0.0, 1500]] }], S: {} }, sum: { km: 12, up: 500, stages: 1 }, status: 'todo', photos: [{ id: 'p1', lat: 42.9, lon: -0.1 }] });

const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader'] });
async function device(seed) {
  const ctx = await b.newContext({ ...require('playwright').devices['Pixel 7'] }); await ctx.route('**/*', handler);
  const pg = await ctx.newPage(); pg.on('pageerror', e => errors.push(String(e)));
  await pg.goto(URL + '?globe=off'); await pg.evaluate(s => { localStorage.clear(); if (s) localStorage.setItem('orri.treks.v1', JSON.stringify({ v: 1, list: s })); }, seed);
  await pg.reload(); await pg.waitForTimeout(600);
  await pg.evaluate(() => openPage('profile')); await pg.waitForTimeout(200);
  return pg;
}
const until = async (pg, js, ms = 8000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await pg.evaluate(js)) return true; await pg.waitForTimeout(150); } return false; };

// Appareil A : un trek local, puis inscription
const A = await device([TREK('t1', 'GR10 étape 1')]);
check(await A.isVisible('#acct #aGo'), 'formulaire de compte visible dans Mon carnet');
await A.click('#aGo'); check((await A.textContent('#acct')).includes('pseudo'), 'pseudo demandé à l\'inscription');
await A.fill('#aName', 'Viktor'); await A.fill('#aMail', 'v@exemple.fr'); await A.fill('#aPw', 'court'); await A.click('#aGo');
check((await A.textContent('#acct')).includes('8 caractères'), 'mot de passe trop court refusé');
await A.fill('#aPw', 'motdepasse1'); await A.click('#aGo');
check(await until(A, () => !!acct.s && !acct.busy && acct.m.last > 0), 'compte créé et première synchro faite');
check(db.profiles.u1 && db.profiles.u1.name === 'Viktor', 'pseudo enregistré dans le profil');
const r1 = db.treks.find(r => r.id === 't1');
check(r1 && r1.data.name === 'GR10 étape 1' && !('photos' in r1.data), 'trek local envoyé en ligne, sans les photos');
check((await A.textContent('#acct')).includes('Viktor') && (await A.textContent('#acct')).includes('synchronisé'), 'carte du compte : pseudo et état de synchro');

// Appareil B : un autre trek, connexion au même compte → fusion
const B = await device([TREK('t2', 'Tour du Mont Blanc')]);
await B.click('#aMode [data-m=in]'); await B.fill('#aMail', 'v@exemple.fr'); await B.fill('#aPw', 'mauvais1'); await B.click('#aGo');
check(await until(B, () => /incorrect/.test($('#acct').textContent)), 'mauvais mot de passe : message clair');
await B.fill('#aPw', 'motdepasse1'); await B.click('#aGo');
check(await until(B, () => !!acct.s && !acct.busy && treks.list.length === 2), 'connexion sur B : le trek de A arrive');
check(await B.evaluate(() => acct.s.name) === 'Viktor', 'pseudo récupéré à la connexion');
check(db.treks.filter(r => !r.deleted).length === 2, 'le trek de B est envoyé en ligne');
check(await B.evaluate(() => (treks.get('t1').photos || []).length === 0 && document.querySelectorAll('#trekList li').length === 2), 'B affiche les 2 treks (photos de A restées sur A)');

// A : modification sur B → arrive sur A, en gardant les photos locales
await B.evaluate(() => { const t = treks.get('t1'); t.status = 'done'; t.doneDate = '2026-11-10'; t.note = 'Superbe'; treks.store(); });
check(await until(B, () => !acct.busy && acct.m.last > 0 && acct.m.rows.t1 && acct.m.rows.t1.h === trekHash(treks.get('t1')), 9000), 'modif sur B envoyée (synchro automatique)');
await A.evaluate(() => acct.sync());
check(await until(A, () => !acct.busy && treks.get('t1').status === 'done' && treks.get('t1').note === 'Superbe' && treks.get('t1').photos.length === 1), 'modif de B reçue sur A, photos locales gardées');
check(await A.evaluate(() => !!treks.get('t2')), 'trek de B reçu sur A');

// Suppression sur A → disparaît sur B
await A.evaluate(() => { treks.list = treks.list.filter(t => t.id !== 't2'); treks.store(); return acct.sync(); });
check(await until(A, () => !acct.busy) && db.treks.find(r => r.id === 't2').deleted === true, 'suppression sur A : trace « supprimé » en ligne');
await B.evaluate(() => acct.sync());
check(await until(B, () => !acct.busy && !treks.get('t2')), 'trek supprimé sur A disparaît de B');

// Déconnexion sur B : le carnet reste
await B.click('#aOut'); await B.click('#aOut');
check(await until(B, () => !acct.s && treks.list.length === 1 && !!$('#aGo')), 'déconnexion : carnet gardé sur l\'appareil');

// Suppression du compte depuis A
await A.click('#acct summary'); await A.click('#aDel'); await A.click('#aDel');
check(await until(A, () => !acct.s), 'compte supprimé depuis A');
check(!db.users.length && !db.treks.length && !Object.keys(db.profiles).length, 'plus rien en ligne après suppression');
check(await A.evaluate(() => treks.list.length === 1 && !localStorage.getItem('orri.account')), 'carnet de A gardé, session effacée');

// Sans compte : aucun appel au serveur
const before = db.tick; const C = await device([TREK('t3', 'Solo')]);
await C.evaluate(() => { treks.get('t3').note = 'x'; treks.store(); }); await C.waitForTimeout(4500);
check(db.tick === before && !(await C.evaluate(() => !!acct.s)), 'sans compte, rien n\'est envoyé');

check(badKey === 0, 'clé publique envoyée à chaque appel');
check(!errors.length, 'aucune erreur JavaScript' + (errors.length ? ' : ' + errors.join(' | ') : ''));
await C.screenshot({ path: '/tmp/claude-0/acct-off.png' });
await b.close();
console.log(fails.length ? `\n${fails.length} échec(s)` : '\nTout est OK');
process.exit(fails.length ? 1 : 0);
