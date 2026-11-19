// Test du compte facultatif d'Orri : inscription, synchro du carnet entre deux appareils, suppression, amis (code, lien,
// trek partagé visible sur le globe et la carte, copie, retrait), déconnexion, suppression du compte. Supabase est simulé en mémoire (Auth + PostgREST), le reste du réseau est coupé.
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
const db = { users: [], profiles: {}, treks: [], friends: [], files: {}, checkins: {}, stats: {}, tick: 0 };
const isFriend = (x, y) => db.friends.some(f => (f.a === x && f.b === y) || (f.a === y && f.b === x));
const now = () => new Date(Date.UTC(2026, 10, 19, 8, 0, 0) + ++db.tick).toISOString();
const CORS = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*' };
const sess = u => ({ access_token: 'tok-' + u.id, refresh_token: 'ref-' + u.id, expires_in: 3600, expires_at: Math.floor(Date.now() / 1000) + 3600, user: { id: u.id, email: u.email, user_metadata: u.meta } });
let badKey = 0;
async function supa(route) {
  const rq = route.request(), u = new globalThis.URL(rq.url()), h = rq.headers(), m = rq.method();
  const send = (status, body) => route.fulfill({ status, headers: CORS, contentType: 'application/json', body: body == null ? '' : JSON.stringify(body) });
  if (m === 'OPTIONS') return send(204);
  if (h.apikey !== 'sb_publishable_OY8bVQK6AKjK2hfGuxZzGQ_8TAM6pJZ') badKey++;
  let body = null; try { body = rq.postData() ? JSON.parse(rq.postData()) : null; } catch (e) { }
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
  if (p === '/rest/v1/rpc/delete_my_account') { db.users = db.users.filter(x => x !== me); db.treks = db.treks.filter(r => r.user_id !== me.id); db.friends = db.friends.filter(f => f.a !== me.id && f.b !== me.id); delete db.profiles[me.id]; return send(204); }
  if (p === '/rest/v1/rpc/add_friend') {
    const f = Object.values(db.profiles).find(x => x.code === body.friend_code);
    if (!f) return send(400, { code: 'P0001', message: 'code_inconnu' });
    if (f.id === me.id) return send(400, { code: 'P0001', message: 'code_perso' });
    if (!isFriend(me.id, f.id)) db.friends.push({ a: me.id, b: f.id });
    return send(200, [{ id: f.id, name: f.name }]);
  }
  if (p === '/rest/v1/rpc/my_friends') return send(200, Object.values(db.profiles).filter(x => isFriend(me.id, x.id)).map(x => ({ id: x.id, name: x.name })));
  if (p === '/rest/v1/rpc/remove_friend') { db.friends = db.friends.filter(f => !((f.a === me.id && f.b === body.other) || (f.b === me.id && f.a === body.other))); return send(204); }
  if (p.startsWith('/storage/v1/')) {
    const own = path => path.split('/')[0] === me.id, see = path => own(path) || isFriend(me.id, path.split('/')[0]);
    if (p === '/storage/v1/object/list/photos') return send(200, Object.keys(db.files).filter(k => k.startsWith(body.prefix + '/')).map(k => ({ name: k.slice(body.prefix.length + 1) })));
    if (p === '/storage/v1/object/photos' && m === 'DELETE') { body.prefixes.forEach(k => { if (own(k)) delete db.files[k]; }); return send(200, []); }
    if (p.startsWith('/storage/v1/object/photos/') && m === 'POST') { const k = p.slice(26); if (!own(k)) return send(403, { message: 'RLS' }); db.files[k] = rq.postDataBuffer(); return send(200, { Key: k }); }
    if (p.startsWith('/storage/v1/object/authenticated/photos/')) { const k = p.slice(40); return see(k) && db.files[k] ? route.fulfill({ status: 200, headers: CORS, contentType: 'image/jpeg', body: db.files[k] }) : send(400, { message: 'not found' }); }
  }
  if (p === '/rest/v1/stats') {
    if (m === 'POST') { body.forEach(r => { if (r.user_id === me.id) db.stats[me.id] = r; }); return send(201); }
    return send(200, Object.values(db.stats).filter(c => c.user_id === me.id || isFriend(me.id, c.user_id)));
  }
  if (p === '/rest/v1/checkins') {
    if (m === 'POST') { body.forEach(r => { if (r.user_id === me.id) db.checkins[me.id] = r; }); return send(201); }
    if (m === 'DELETE') { delete db.checkins[me.id]; return send(204); }
    return send(200, Object.values(db.checkins).filter(c => c.user_id === me.id || isFriend(me.id, c.user_id)));
  }
  if (p === '/rest/v1/profiles') {
    if (m === 'POST') { body.forEach(r => { if (r.id === me.id) db.profiles[me.id] = Object.assign({ code: ('K' + me.id).toUpperCase().padEnd(8, 'X') }, db.profiles[me.id], r); }); return send(201); }
    const pr = db.profiles[me.id]; return send(200, pr ? [{ name: pr.name, code: pr.code }] : []);
  }
  if (p === '/rest/v1/treks') {
    if (m === 'POST') {
      const out = body.map(r => {
        if (r.user_id !== me.id) throw new Error('user_id');
        let row = db.treks.find(x => x.user_id === me.id && x.id === r.id);
        if (!row) { row = { user_id: me.id, id: r.id }; db.treks.push(row); }
        Object.assign(row, { data: r.data, deleted: r.deleted, share: r.share || 'private', updated_at: now() });
        return { id: row.id, updated_at: row.updated_at };
      });
      return send(201, out);
    }
    let rows = db.treks.filter(r => r.user_id === me.id || (r.share === 'friends' && !r.deleted && isFriend(me.id, r.user_id)));   // RLS
    for (const [k, v] of q) {
      if (k === 'share') rows = rows.filter(r => r.share === v.slice(3));
      if (k === 'deleted') rows = rows.filter(r => String(r.deleted) === v.slice(3));
      if (k === 'user_id') rows = rows.filter(r => v.startsWith('neq.') ? r.user_id !== v.slice(4) : r.user_id === v.slice(3));
    }
    const inq = q.get('id'); if (inq) { const ids = inq.startsWith('in.') ? inq.slice(4, -1).split(',') : [inq.slice(3)]; rows = rows.filter(r => ids.includes(r.id)); }
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

// Amis : Léa (appareil D) reçoit le lien d'invitation de Viktor
await A.evaluate(() => friendsRefresh(true)); await A.waitForTimeout(300);
const code = await A.evaluate(() => friends.code);
check(/^[A-Z0-9]{8}$/.test(code) && (await A.textContent('#friendsBox')).includes(code), 'code ami affiché dans Mon carnet (' + code + ')');
await A.evaluate(() => openTrekPage('t1')); await A.waitForTimeout(200);
check(await A.isVisible('#tdShare') && !(await A.isChecked('#tdShare')), 'trek privé par défaut, case « Partager avec mes amis »');
await A.check('#tdShare');
check(await until(A, () => treks.get('t1').share === 'friends' && !acct.busy && acct.m.rows.t1.h === trekHash(treks.get('t1')), 9000) && db.treks.find(r => r.id === 't1').share === 'friends', 'trek partagé : colonne share = friends en ligne');
const D = await (async () => {
  const ctx = await b.newContext({ ...require('playwright').devices['Pixel 7'] }); await ctx.route('**/*', handler);
  const pg = await ctx.newPage(); pg.on('pageerror', e => errors.push(String(e)));
  await pg.goto(URL + '?globe=off'); await pg.evaluate(() => localStorage.clear());
  await pg.goto(URL + '?globe=off&ami=' + code); await pg.waitForTimeout(1500); return pg;
})();
check(await D.evaluate(() => localStorage.getItem('orri.invite')) === code && !(await D.evaluate(() => location.search.includes('ami='))), 'lien d\'invitation retenu, retiré de l\'adresse');
check((await D.textContent('#status')).includes('invite'), 'message « un ami t\'invite » sans compte');
await D.evaluate(() => openPage('profile')); await D.fill('#aName', 'Léa'); await D.fill('#aMail', 'lea@exemple.fr'); await D.fill('#aPw', 'motdepasse2'); await D.click('#aGo');
check(await until(D, () => friends.list.length === 1 && friends.treks.length === 1), 'Léa inscrite : amie avec Viktor, voit son trek partagé');
check(isFriend('u1', 'u2'), 'amitié enregistrée des deux côtés');
check(await D.evaluate(() => globeTreks().some(g => g.friend && g.name === 'GR10 étape 1')), 'trek de Viktor dans le globe de Léa');
check(await D.evaluate(() => friendLayer.getLayers().length === 1), 'trek de Viktor sur la carte de Léa');
check(await D.evaluate(() => !treks.list.length), 'le trek de l\'ami n\'entre pas dans le carnet de Léa');
await D.click('[data-ft]'); await D.waitForTimeout(200);
check((await D.textContent('#ftBody')).includes('Viktor') && (await D.textContent('#ftBody')).includes('Superbe'), 'page du trek de Viktor : auteur et souvenir');
await D.click('#ftCopy'); await D.waitForTimeout(300);
check(await D.evaluate(() => treks.list.length === 1 && treks.list[0].status === 'todo' && !treks.list[0].note && !treks.list[0].share), 'copie dans le carnet de Léa (à faire, privée, sans souvenir)');
await A.evaluate(() => friendsRefresh(true));
check(await until(A, () => friends.list.length === 1 && friends.list[0].name === 'Léa'), 'Léa apparaît chez Viktor');
check(await A.evaluate(() => friends.treks.length === 0), 'Viktor ne voit pas la copie privée de Léa');
// C3 : photo partagée, position, jour en cours
await A.evaluate(async () => {
  const c = document.createElement('canvas'); c.width = 40; c.height = 30; c.getContext('2d').fillStyle = '#c63'; c.getContext('2d').fillRect(0, 0, 40, 30);
  const bl = await new Promise(ok => c.toBlob(ok, 'image/jpeg'));
  await photoDB.put({ id: 'p1', trek: 't1', full: bl, thumb: bl });
  const t = treks.get('t1'); t.status = 'todo'; t.data.S.startDate = new Date().toISOString().slice(0, 10); t.sum.stages = 3; treks.store();
  openTrekPage('t1'); await viewPhoto(t, 0);
});
check(await A.isVisible('#vShare') && (await A.textContent('#vShare')).includes('Partager'), 'visionneuse : bouton « Partager » sur un trek partagé');
await A.click('#vShare');
check(await until(A, () => (treks.get('t1').pub || []).length === 1 && $('#vShare').textContent.includes('Partagée')) && !!db.files['u1/p1.jpg'] && !!db.files['u1/p1_t.jpg'], 'photo envoyée (grande + vignette) et notée partagée');
check(await until(A, () => !acct.busy && acct.m.rows.t1.h === trekHash(treks.get('t1')), 9000) && (db.treks.find(r => r.id === 't1').data.pub || []).length === 1, 'liste des photos partagées synchronisée');
await A.evaluate(() => { closeViewer(); openPage('profile'); });
await A.context().grantPermissions(['geolocation']); await A.context().setGeolocation({ latitude: 42.91, longitude: 0.12 });
await A.click('#fHere');
check(await until(A, () => !!friends.me) && db.checkins.u1 && Math.abs(db.checkins.u1.lat - 42.91) < 1e-6, '« Je suis ici » : position enregistrée');
await D.evaluate(() => friendsRefresh(true));
check(await until(D, () => friends.treks.length === 1 && friends.treks[0].photos.length === 1 && friends.pos.length === 1), 'Léa reçoit la photo partagée et la position de Viktor');
check(await D.evaluate(() => /En route : jour 1 sur 3/.test($('#friendsBox').textContent)), 'chez Léa : « En route : jour 1 sur 3 »');
check(await D.evaluate(() => friendLayer.getLayers().length === 2 && globeTreks().some(g => g.checkin) && globeTreks().find(g => g.friend && !g.checkin).photos.length === 1), 'carte : trek + point de position ; globe : position et photo géolocalisée');
await D.evaluate(() => openPage('profile')); await D.click('[data-ft]');
check(await until(D, () => { const im = $('#ftBody .ph img'); return im && im.src.startsWith('blob:'); }), 'page du trek : photo de Viktor téléchargée');
check((await D.textContent('#ftBody')).includes('jour 1 sur 3'), 'page du trek : jour en cours');
await D.click('#ftBody .ph');
check(await until(D, () => !$('#viewer').hidden && $('#vImg').src.startsWith('blob:') && $('#vDel').hidden && $('#vShare').hidden), 'photo de l\'ami en grand, sans boutons Supprimer / Partager');
await D.evaluate(() => closeViewer());
await A.evaluate(() => { openTrekPage('t1'); return viewPhoto(treks.get('t1'), 0); }); await A.click('#vShare');
check(await until(A, () => !(treks.get('t1').pub || []).length) && !db.files['u1/p1.jpg'], 'photo retirée du partage : effacée du serveur');
await A.evaluate(() => { closeViewer(); openPage('profile'); }); await A.click('#fOff');
check(await until(A, () => !friends.me) && !db.checkins.u1, 'position effacée');
// C4 : points, badges, classement
await A.evaluate(() => { const t = treks.get('t1'); t.status = 'done'; t.doneDate = new Date().toISOString().slice(0, 10); t.sum.prof = [900, 2150, 1200]; treks.store(); renderProfile(); });
check(await until(A, () => /badges? : .*Au-dessus de 2/.test($('#status').textContent)), 'trek fait : message « Nouveau badge »');
check(await A.evaluate(() => /Promeneur/.test($('#rando').textContent) && /17 points/.test($('#rando').textContent) && document.querySelectorAll('#rando .badge.on').length >= 3), 'profil : grade, 17 points (12 km + 500 m), badges gagnés');
check(await A.evaluate(() => /Défi d.novembre|Défi de /.test($('#rando').textContent)), 'défi du mois affiché');
await A.evaluate(() => friendsRefresh(true));
check(await until(A, () => true) && db.stats.u1 && db.stats.u1.m_km === 12 && db.stats.u1.points === 17, 'totaux publiés pour le classement');
await D.evaluate(() => friendsRefresh(true));
check(await until(D, () => { const t = $('#friendsBox .lb'); return t && /Viktor/.test(t.textContent) && /12,0 km/.test(t.textContent); }), 'classement chez Léa : Viktor 12 km ce mois-ci');
check(await D.evaluate(() => $('#friendsBox .lb li').textContent.includes('Viktor')), 'Viktor premier du classement');
await D.evaluate(() => acct.sync()); await D.waitForTimeout(600);
check(await D.evaluate(() => !treks.get('t1') && treks.list.length === 1), 'après synchro, les treks de Viktor n\'entrent pas dans le carnet de Léa');
await D.evaluate(() => openPage('profile')); await D.click('#lbMet [data-v=up]');
check(await D.evaluate(() => /500 m/.test($('#friendsBox .lb').textContent)), 'classement au dénivelé');

await D.evaluate(() => openPage('profile')); await D.fill('#fCode', 'ZZZZ9999'); await D.click('#fAdd');
check(await until(D, () => /ne correspond/.test($('#friendsBox').textContent)), 'code inconnu : message clair');
await A.evaluate(() => openTrekPage('t1')); await A.uncheck('#tdShare');
for (let i = 0; i < 60 && db.treks.find(r => r.id === 't1').share !== 'private'; i++) await A.waitForTimeout(150);
check(db.treks.find(r => r.id === 't1').share === 'private', 'case décochée : trek de nouveau privé en ligne');
await D.evaluate(() => friendsRefresh(true));
check(await until(D, () => friends.treks.length === 0 && friendLayer.getLayers().length === 0), 'trek redevenu privé : disparaît chez Léa');
await D.evaluate(() => openPage('profile')); await D.click('.fdel'); await D.click('.fdel');
check(await until(D, () => friends.list.length === 0) && !isFriend('u1', 'u2'), 'Léa retire Viktor de ses amis');

// Déconnexion sur B : le carnet reste
await B.click('#aOut'); await B.click('#aOut');
check(await until(B, () => !acct.s && treks.list.length === 1 && !!$('#aGo')), 'déconnexion : carnet gardé sur l\'appareil');

// Suppression du compte depuis A
await A.evaluate(() => openPage('profile')); await A.click('#acct summary'); await A.click('#aDel'); await A.click('#aDel');
check(await until(A, () => !acct.s), 'compte supprimé depuis A');
check(!db.users.some(u => u.id === 'u1') && !db.treks.some(r => r.user_id === 'u1') && !db.profiles.u1, 'plus rien de Viktor en ligne après suppression');
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
