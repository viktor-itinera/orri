#!/usr/bin/env python3
"""Test de fumée d'Orri : import GPX, données de points locales, étapes, fins d'étape, export, tracé.

Le réseau extérieur est simulé (BRouter, IGN, Photon, tuiles) et Overpass est en panne :
les points doivent venir de data/poi/, servi en local avec le reste du site.
Voir CLAUDE.md, section « Tester ».
"""
import json, math, os, struct, sys, urllib.parse, zlib
from playwright.sync_api import sync_playwright

URL = os.environ.get("ORRI_URL", "http://localhost:8765/")
GPX = os.environ.get("ORRI_GPX")
LEAF = os.environ.get("ORRI_LEAFLET", os.path.join(os.path.dirname(os.path.abspath(__file__)), "node_modules/leaflet/dist/"))
NM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "node_modules/")
CHROME = os.environ.get("ORRI_CHROME")
if not GPX: sys.exit("Indique un fichier GPX : ORRI_GPX=/chemin/trek.gpx python3 smoke_test.py")


def png(w, h, rgb):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")


TILE = png(256, 256, (232, 236, 226))
SAT = png(256, 256, (70, 98, 60))   # image satellite simulée
TERRAIN = png(256, 256, (128, 200, 0))   # terrarium : 1 200 m partout
calls = {"brouter": 0, "overpass": 0}
JSON_HDR = {"Access-Control-Allow-Origin": "*"}


def handler(route):
    u = route.request.url
    q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
    if u.startswith(URL): return route.continue_()
    if "unpkg.com/maplibre-gl@5" in u: return route.fulfill(path=NM + "maplibre-gl5/dist/maplibre-gl.js", content_type="application/javascript")
    if "unpkg.com/maplibre-gl@" in u: return route.fulfill(path=NM + "maplibre-gl/dist/maplibre-gl" + (".css" if u.endswith(".css") else ".js"), content_type="text/css" if u.endswith(".css") else "application/javascript")
    if "elevation-tiles-prod" in u:
        if os.environ.get("ORRI_REAL_TERRAIN"):
            from urllib.request import urlopen
            return route.fulfill(body=urlopen(u, timeout=30).read(), content_type="image/png", headers=JSON_HDR)
        return route.fulfill(body=TERRAIN, content_type="image/png", headers=JSON_HDR)
    if "unpkg.com/d3-" in u:
        nm = u.split("unpkg.com/")[1].split("@")[0]
        return route.fulfill(path=NM + nm + "/dist/" + nm + ".min.js", content_type="application/javascript")
    if "unpkg.com/@maplibre/maplibre-gl-leaflet" in u: return route.fulfill(path=NM + "@maplibre/maplibre-gl-leaflet/leaflet-maplibre-gl.js", content_type="application/javascript")
    if "cdnjs.cloudflare.com" in u and u.endswith(".js"): return route.fulfill(path=LEAF + "leaflet.js", content_type="application/javascript")
    if "cdnjs.cloudflare.com" in u and u.endswith(".css"): return route.fulfill(path=LEAF + "leaflet.css", content_type="text/css")
    if "tiles.maps.eox.at" in u: calls["sat"] = calls.get("sat", 0) + 1; return route.fulfill(body=SAT, content_type="image/png", headers=JSON_HDR)
    if "/wmts" in u or "opentopomap" in u or "kartverket" in u: return route.fulfill(body=TILE, content_type="image/png")
    if "brouter.de" in u:
        calls["brouter"] += 1
        (lo1, la1), (lo2, la2) = [tuple(map(float, s.split(","))) for s in q["lonlats"][0].split("|")]
        c = [[lo1 + (lo2 - lo1) * t / 30, la1 + (la2 - la1) * t / 30, 1000 + 400 * math.sin(t / 30 * math.pi)] for t in range(31)]
        return route.fulfill(body=json.dumps({"features": [{"geometry": {"coordinates": c}}]}), content_type="application/json", headers=JSON_HDR)
    if "altimetrie" in u:
        n = len(q["lon"][0].split("|"))
        return route.fulfill(body=json.dumps({"elevations": [1200 + 5 * i for i in range(n)]}), content_type="application/json", headers=JSON_HDR)
    if "photon.komoot.io/api" in u:
        return route.fulfill(body=json.dumps({"features": [{"properties": {"name": "Besseggen", "state": "Innlandet", "country": "Norvège"}, "geometry": {"coordinates": [8.73, 61.5]}}]}), content_type="application/json", headers=JSON_HDR)
    if "geocodage/reverse" in u or "photon" in u:
        return route.fulfill(body=json.dumps({"features": [{"properties": {"city": "Lieu", "distance": 100}}]}), content_type="application/json", headers=JSON_HDR)
    if "geocodage/search" in u:
        return route.fulfill(body=json.dumps({"features": [{"properties": {"label": "Cauterets"}, "geometry": {"coordinates": [-0.1103, 42.8889]}}]}), content_type="application/json", headers=JSON_HDR)
    if "overpass" in u or "maps.mail.ru" in u:
        calls["overpass"] += 1
        return route.abort()
    return route.abort()


fails, errors = [], []
def check(ok, what):
    print(("OK   " if ok else "ÉCHEC") + " " + what)
    if not ok: fails.append(what)

J = lambda pg, js: pg.evaluate(js)
is3d_ok = True
GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]   # WebGL logiciel : globe 3D

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"] + GL) if CHROME else p.chromium.launch(args=GL)
    ctx = b.new_context(viewport={"width": 1400, "height": 900}, accept_downloads=True)
    ctx.route("**/*", handler)
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(URL); pg.wait_for_timeout(500)
    pg.evaluate("() => localStorage.clear()"); pg.reload(); pg.wait_for_timeout(500)
    check(pg.is_visible("#page-welcome"), "accueil affiché au premier lancement")
    gl = J(pg, """() => new Promise(ok => { if (!hasGL) return ok('sans WebGL : ' + $('#base').value);
      const t0 = Date.now(), w = () => { const m = base.getMaplibreMap && base.getMaplibreMap(); const st = m && m.style && m.style._order && m.style._order.length && { layers: m.style._order };
        if (st) ok(st.layers.length); else if (Date.now() - t0 > 8000) ok('style non chargé'); else setTimeout(w, 200); }; w(); })""")
    check(gl == 28 or str(gl).endswith("otm"), "carte Orri par défaut (style chargé : %s)" % gl)
    pg.click("#wDraw"); pg.wait_for_timeout(300)
    check(not pg.is_visible("#page-welcome") and J(pg, "() => state.draw"), "accueil : « Tracer mon itinéraire » ouvre la carte")

    pg.set_input_files("#file", GPX)
    pg.wait_for_function("R && R.n > 1 && (poiState === 'ok' || poiState === 'error')", timeout=90000)
    pg.wait_for_timeout(500)
    n, pois, tiles = J(pg, "() => R.n"), J(pg, "() => R.pois.length"), J(pg, "() => tileLoaded.size")
    print(f"     GPX : {n} points, {J(pg, '() => (R.dist/1000).toFixed(1)')} km, {pois} points d'intérêt depuis {tiles} tuiles locales")
    check(n > 100, "GPX importé")
    check(pois > 0 and tiles > 0, "points d'intérêt chargés depuis data/poi/ (Overpass en panne)")

    pg.click("#tabs button[data-tab=stages]"); pg.wait_for_timeout(200)
    check(pg.is_visible("#trekSum .tsum") and pg.is_visible("#bKeep"), "résumé du trek affiché (« Garder ce trek »)")
    pg.click("#bAdjust"); pg.wait_for_timeout(300)
    check(pg.is_visible("#page-adjust #modeSeg"), "« Ajuster » ouvre les réglages")
    pg.click("#modeSeg button[data-m=limits]"); pg.wait_for_timeout(800)
    worst = J(pg, "() => Math.max(...R.stages.map(s => s.time))")
    check(worst <= 7.01, f"limite 7 h/jour respectée (max {worst:.2f} h)")

    pg.select_option("#endType", "refuge"); pg.wait_for_timeout(1500)
    hits = J(pg, "() => R.stages.filter(s => s.endPoi).length")
    dmax = J(pg, "() => Math.max(0, ...R.stages.filter(s => s.endPoi).map(s => Math.abs(s.endDelta)))")
    check(hits > 0, f"fins d'étape au refuge trouvées ({hits})")
    check(dmax <= J(pg, "() => S.tol") + 1e-6, f"écart dans la tolérance (max {dmax:.2f} h)")
    check("jour" in (pg.text_content("#adjLive") or ""), "« Ajuster » montre l'effet des réglages")
    pg.click("#bAdjDone"); pg.wait_for_timeout(300)
    nights = len(pg.query_selector_all("#stages li.day .night"))
    check(nights == J(pg, "() => R.stages.length") and pg.query_selector("#stages li.day.last .night.arr") is not None, f"frise : une nuit par jour + l'arrivée ({nights})")

    # Modifier une étape : dormir en bivouac à la fin de l'étape 2 au lieu du refuge
    pg.locator("#stages li.day").nth(1).locator(".chg").click(); pg.wait_for_timeout(400)
    pg.locator("#stages li.day").nth(1).locator(".sleep details summary").click(); pg.wait_for_timeout(200)
    pg.locator("#stages li.day").nth(1).locator("[data-sleep=bivouac]").click(); pg.wait_for_timeout(1200)
    st = J(pg, "() => ({ t: R.stages[1].endType, c: R.stages[1].endPoi && R.stages[1].endPoi.cat, miss: R.stages[1].endMiss, o: S.over[1], first: R.stages[0].endPoi && R.stages[0].endPoi.cat })")
    check(st["o"] == "bivouac" and st["t"] == "bivouac" and (st["c"] in ("bivouac", "water") or st["miss"]), f"étape 2 modifiée : fin en bivouac ({st})")
    check(st["first"] == "hut", "les autres étapes gardent le refuge")
    pg.locator("#stages li.day").nth(1).locator(".reset").click(); pg.wait_for_timeout(1000)
    check(J(pg, "() => !(1 in S.over) && R.stages[1].endType === 'refuge'"), "retour au réglage général")

    # Choisir sa nuit : la liste propose tous les lieux atteignables, le tracé passe par le lieu choisi
    day2 = pg.locator("#stages li.day").nth(1)
    n_opts = day2.locator(".opt").count()
    check(n_opts > 1, f"jour 2 : plusieurs nuits proposées ({n_opts})")
    J(pg, "() => { state.optFlt = 'all'; renderStages(); }"); pg.wait_for_timeout(200)
    target = J(pg, """() => { const o = nightOptions(R.stages[1]).filter(o => o.p.cat !== 'water' && o.p.id !== (R.stages[1].endPoi || {}).id);
      const far = o.filter(x => x.p.d >= 60); const c = (far.length ? far : o)[0]; return c && { id: c.p.id, d: c.p.d, legs: state.legs.length, end0: R.lat[R.stages[0].i1] }; }""")
    b0 = calls["brouter"]
    pg.locator(f"#stages li.day >> nth=1 >> [data-opt='{target['id']}']").click(); pg.wait_for_timeout(1500)
    res = J(pg, f"""() => {{ const s = R.stages[1], p = R.pois.find(q => q.id === '{target['id']}') || s.endPoi;
      return {{ chosen: s.endChosen && s.endPoi && s.endPoi.id === '{target['id']}', fixed: s.dayFixed, frozen: R.stages[0].pinEnd, end0: R.lat[R.stages[0].i1],
        m: nearestIdx(R, s.endPoi.lat, s.endPoi.lon).m, legs: state.legs.length }}; }}""")
    check(res["chosen"] and res["fixed"], f"nuit choisie : le jour 2 finit au lieu choisi ({res})")
    check(res["frozen"] and abs(res["end0"] - target["end0"]) < 1e-4, "le jour 1 ne bouge pas")
    if target["d"] >= 40:
        check(res["m"] < 60 and res["legs"] == target["legs"] + 1 and calls["brouter"] >= b0 + 2, f"le tracé passe par le lieu choisi (à {res['m']:.0f} m, détour recalculé)")
    check("Annuler" in (pg.text_content("#status") or ""), "message avec « Annuler »")

    # Raccourcir / allonger une journée
    t3 = J(pg, "() => R.stages[2].time")
    pg.locator("#stages li.day").nth(2).locator(".chg").click(); pg.wait_for_timeout(300)
    pg.locator("#stages li.day").nth(2).locator("[data-adj='0.5']").click(); pg.wait_for_timeout(800)
    t3b = J(pg, "() => R.stages[2].time")
    check(0.3 < t3b - t3 < 0.7 and J(pg, "() => R.stages[2].dayFixed && R.stages[1].endChosen"), f"jour 3 allongé de 30 min ({t3:.2f} → {t3b:.2f} h), jour 2 gardé")
    pg.locator("#status .tact-btn").last.click(); pg.wait_for_timeout(800)
    check(abs(J(pg, "() => R.stages[2].time") - t3) < 0.02, "« Annuler » revient en arrière")

    # Depuis la carte : « Dormir ici » sur un refuge
    hut = J(pg, """() => { const s = R.stages[3]; const o = nightOptions(s).find(o => o.p.cat === 'hut' && o.p.id !== (s.endPoi || {}).id); return o && o.p.id; }""")
    if hut:
        J(pg, f"() => {{ map.setView([R.pois.find(q => q.id === '{hut}').lat, R.pois.find(q => q.id === '{hut}').lon], 14); }}"); pg.wait_for_timeout(300)
        J(pg, f"() => poiMarkers.get('{hut}').openPopup()"); pg.wait_for_timeout(300)
        pg.click(".leaflet-popup [data-pa=sleep]"); pg.wait_for_timeout(1500)
        check(J(pg, f"() => R.stages.some(s => s.endChosen && s.endPoi.id === '{hut}')"), "carte : « Dormir ici » fixe la nuit à ce refuge")
    # Jour de repos
    J(pg, "() => toggleRest(0)"); pg.wait_for_timeout(300)
    check(pg.query_selector("#stages li.restday") is not None and "de repos" in (pg.text_content("#trekSum") or ""), "jour de repos ajouté dans la frise")
    J(pg, "() => toggleRest(0)")
    # Appui long sur la carte : dormir ici
    pt = J(pg, "() => { const s = R.stages[4], i = Math.round((s.i0 + s.i1) / 2); return [R.lat[i] + 0.002, R.lon[i]]; }")
    J(pg, f"() => map.fire('contextmenu', {{ latlng: L.latLng({pt[0]}, {pt[1]}) }})"); pg.wait_for_timeout(300)
    pg.click(".leaflet-popup [data-ua=sleep]"); pg.wait_for_timeout(1500)
    check(J(pg, "() => R.stages.some(s => s.endChosen && s.endPoi.kind === 'Lieu choisi sur la carte' && nearestIdx(R, s.endPoi.lat, s.endPoi.lon).m < 60)"), "appui long : nuit posée là où on a touché, le tracé y passe")
    # Variante d'une journée
    c0 = calls["brouter"]
    J(pg, "() => startVariant(1)"); pg.wait_for_timeout(200)
    vp = J(pg, "() => { const s = R.stages[1], i = Math.round((s.i0 + s.i1) / 2); return [R.lat[i] + 0.02, R.lon[i]]; }")
    J(pg, f"() => map.fire('click', {{ latlng: L.latLng({vp[0]}, {vp[1]}) }})"); pg.wait_for_timeout(200)
    pg.click("#varBar [data-v=cmp]"); pg.wait_for_timeout(1500)
    check(pg.is_visible("#varBar .vtab") and calls["brouter"] - c0 == 2, "variante : comparaison affichée (2 tronçons calculés)")
    end1 = J(pg, "() => [R.lat[R.stages[1].i1], R.lon[R.stages[1].i1], R.stages[0].i1 ? R.lat[R.stages[0].i1] : 0]")
    pg.click("#varBar [data-v=keep]"); pg.wait_for_timeout(1000)
    after = J(pg, f"() => {{ const s = R.stages[1]; return {{ end: hav([R.lat[s.i1], R.lon[s.i1]], [{end1[0]}, {end1[1]}]), d0: Math.abs(R.lat[R.stages[0].i1] - {end1[2]}), via: nearestIdx(R, {vp[0]}, {vp[1]}).m, bar: !$('#varBar').hidden }}; }}")
    check(after["end"] < 60 and after["d0"] < 1e-4 and after["via"] < 60 and not after["bar"], f"variante gardée : le jour 2 passe par le point, mêmes départ et arrivée ({after})")
    # Tracé animé
    check(J(pg, "() => { animateRoute(); return routeLines.length > 0 && routeLines.some(l => l._path && l._path.style.strokeDasharray); }"), "tracé animé : le tracé se dessine")
    # Tout rendre à Orri
    pg.click("#bAdjust"); pg.wait_for_timeout(200)
    pg.click("#bFreeAll"); pg.click("#bFreeAll"); pg.wait_for_timeout(800)
    check(J(pg, "() => S.pins.length === 0 && !R.stages.some(s => s.endChosen)"), "« Rendre toutes les nuits à Orri » efface les choix")
    pg.click("#bAdjDone"); pg.wait_for_timeout(300)

    # Pastilles : masquer l'eau sur la carte
    pg.click("#chips .chip[data-k=water]"); pg.wait_for_timeout(500)
    check(J(pg, "() => !S.show.water && !document.querySelector('#show_water').checked"), "pastille Eau : masque les points d'eau")
    pg.click("#chips .chip[data-k=water]"); pg.wait_for_timeout(500)

    # Recherche hors de France (Photon)
    pg.fill("#q", "Besseggen"); pg.press("#q", "Enter"); pg.wait_for_timeout(800)
    check("Norvège" in (pg.text_content("#results") or ""), "recherche hors de France (Photon)")
    pg.click("#results li >> nth=0"); pg.wait_for_timeout(300)

    pg.click("#bAdjust"); pg.wait_for_timeout(300)
    pg.click("#modeSeg button[data-m=days]"); pg.fill("#vDays", "12"); pg.dispatch_event("#vDays", "input"); pg.wait_for_timeout(1500)
    check(J(pg, "() => R.stages.length") == 12, "12 jours imposés = 12 étapes")
    pg.click("#bAdjDone"); pg.wait_for_timeout(300)

    pg.locator("#stages li").first.click(); pg.wait_for_timeout(500)
    check(pg.query_selector("#stages li.sel .detail") is not None, "feuille d'étape affichée")

    pg.click("#tabs button[data-tab=trace]"); pg.wait_for_timeout(200)
    with pg.expect_download() as dl:
        pg.click("#bExport")
    x = open(dl.value.path(), encoding="utf-8").read()
    check(x.count("<trk>") == 12 and "<wpt" in x, "export GPX : 12 traces + points")

    # Mes parcours : enregistrer, fiche, effacer puis rouvrir
    pg.click("#bProfile"); pg.wait_for_timeout(300)
    pg.fill("#trekName", "Traversée test"); pg.click("#bSaveTrek"); pg.wait_for_timeout(300)
    check(J(pg, "() => treks.list.length === 1 && treks.list[0].name === 'Traversée test' && !treks.dirty()"), "parcours enregistré dans Mes parcours")
    check(J(pg, "() => JSON.parse(localStorage.getItem('orri.treks.v1')).list.length") == 1, "parcours gardé dans le navigateur")
    pg.click("#page-profile .close"); pg.click("#tabs button[data-tab=prep]"); pg.click("#bSheet"); pg.wait_for_timeout(800)
    fiche = pg.frame_locator("#sheetFrame").locator("body").inner_text()
    check("Traversée test" in fiche and "Jour 12" in fiche and "Nuit" in fiche, "fiche du trek générée (12 étapes)")
    with pg.expect_download() as dl2:
        pg.click("#bSheetDl")
    check("<svg" in open(dl2.value.path(), encoding="utf-8").read(), "fiche téléchargeable (HTML autonome)")
    pg.click("#page-sheet .close"); pg.click("#tabs button[data-tab=trace]")
    pg.click("#bClear"); pg.click("#bClear"); pg.wait_for_timeout(300)
    pg.click("#bProfile"); pg.wait_for_timeout(300)
    pg.click("#trekList .trek .tmain"); pg.wait_for_timeout(1500)
    check(J(pg, "() => R.n > 100 && R.stages.length === 12 && treks.cur === treks.list[0].id"), "parcours rouvert depuis Mes parcours")

    # Mon carnet : marquer fait avec une date, souvenir, photo avec position GPS
    import io, tempfile
    from PIL import Image
    im = Image.new("RGB", (900, 600), (90, 140, 110)); ex = Image.Exif()
    ex[0x0132] = "2026:08:12 14:30:00"
    gps = ex.get_ifd(0x8825); gps[1] = "N"; gps[2] = (42.0, 52.0, 30.0); gps[3] = "W"; gps[4] = (0.0, 20.0, 0.0)
    photo = os.path.join(tempfile.gettempdir(), "orri-test-photo.jpg"); im.save(photo, "JPEG", exif=ex)
    pg.click("#bProfile"); pg.wait_for_timeout(300)
    pg.click("#trekList .trek [data-a=memo]"); pg.wait_for_timeout(300)
    check(pg.is_visible("#page-trek") and "Traversée test" in pg.text_content("#tdName"), "carnet : page souvenirs du trek")
    pg.click("#tdStatus [data-s=done]"); pg.wait_for_timeout(200)
    pg.fill("#tdDate", "2026-08-10"); pg.dispatch_event("#tdDate", "change")
    pg.fill("#tdNote", "Superbe traversée"); pg.wait_for_timeout(700)
    pg.set_input_files("#photoIn", photo); pg.wait_for_function("(treks.list[0].photos || []).length === 1", timeout=10000); pg.wait_for_timeout(500)
    ph = J(pg, "() => treks.list[0].photos[0]")
    check(abs(ph.get("lat", 0) - 42.875) < 1e-3 and abs(ph.get("lon", 0) + 0.3333) < 1e-3 and ph.get("date", "").startswith("2026-08-12"), f"photo : position GPS et date lues ({ph})")
    check(J(pg, "() => { const t = treks.list[0]; return t.status === 'done' && t.doneDate === '2026-08-10' && t.note === 'Superbe traversée'; }"), "trek marqué fait le 10 août, souvenir gardé")
    check(J(pg, "() => new Promise(ok => { const im = document.querySelector('#tdBody .ph img'); const w = () => im.naturalWidth ? ok(im.naturalWidth) : setTimeout(w, 100); w(); })") > 0, "vignette affichée (IndexedDB)")
    pg.click("#tdBody .ph[data-i='0']"); pg.wait_for_timeout(500)
    check(pg.is_visible("#viewer") and J(pg, "() => $('#vImg').naturalWidth") >= 800, "visionneuse : photo en grand")
    pg.click("#vClose")
    pg.click("#tdCard"); pg.wait_for_function("!$('#story').hidden && $('#stImg').naturalWidth > 0", timeout=30000)
    sv = J(pg, "() => ({ wh: [$('#stImg').naturalWidth, $('#stImg').naturalHeight], n: story.slides.length, days: (story.d.days || []).length, relief: !!story.d.prof })")
    check(sv["wh"] == [1080, 1920] and sv["n"] == (5 if sv["days"] > 1 else 4), f"souvenirs : plusieurs cartes 1080 × 1920 ({sv})")
    J(pg, "() => storyGo(story.slides.length)")
    if is3d_ok:
        pg.wait_for_function("flyer && flyer.playing && flyer.m.getTerrain() && flyer.m.getPitch() > 30", timeout=90000)
        check(J(pg, "() => flyer.m.getPitch() > 30 && flyer.m.getSource('done') && $('#stRec').offsetParent !== null"), "survol 3D du parcours, bouton vidéo")
        check(J(pg, "() => !!(flyer.m.getLayer('sat') && flyer.m.getSource('sat'))") and calls.get("sat", 0) > 0, "survol 3D : images satellite sur le relief")
        J(pg, "() => { $('#stRec').onclick(); }"); pg.wait_for_timeout(1500)
        check(J(pg, "() => !!(flyer.rec && ['recording', 'paused'].includes(flyer.rec.state))"), "survol 3D : enregistrement vidéo lancé")
    pg.click("#stClose"); pg.wait_for_timeout(300)
    check(J(pg, "() => $('#story').hidden && !flyer"), "souvenirs fermés, survol arrêté")
    pg.click("#bTrekBack"); pg.wait_for_timeout(300)
    pg.click("#tFilter [data-f=done]"); pg.wait_for_timeout(200)
    check(len(pg.query_selector_all("#trekList .trek.done")) == 1 and "1" in pg.text_content("#cStats") and "km parcourus" in pg.text_content("#cStats"), "carnet : filtre « Faits » et statistiques")
    pg.click("#tFilter [data-f=all]")
    # Globe souvenir : dans le carnet et sur l'accueil
    pg.wait_for_function("globes.profile && globes.profile.w > 0", timeout=10000)
    gp = J(pg, "() => ({ n: globes.profile.data.length, done: globes.profile.data.filter(g => g.done).length, ph: globes.profile.data.reduce((x, g) => x + g.photos.length, 0) })")
    check(gp["n"] == 1 and gp["done"] == 1 and gp["ph"] == 1, f"globe du carnet : le trek fait et sa photo ({gp})")
    is3d = J(pg, "() => !!globes.profile.is3d")
    check(is3d, "globe 3D (MapLibre 5, WebGL) plutôt que le globe dessiné")
    if is3d:
        pg.wait_for_function("globes.profile.ready", timeout=20000)
        J(pg, "() => { const G = globes.profile; G.select(G.data[0]); G.focus(G.data[0], 800); }")
        pg.wait_for_function("globes.profile.zoom > 5 && !globes.profile.map.isMoving()", timeout=20000)
        check(pg.is_visible("#globeSlotProfile .gcard"), "globe 3D : toucher un trek y vole et affiche sa carte")
        check(J(pg, "() => !!globes.profile.map.getTerrain() && globes.profile.map.getPitch() > 30"), "globe 3D : relief en volume et vue inclinée de près")
        pg.wait_for_timeout(500)
        check(J(pg, "() => globes.profile.wrap.classList.contains('near') && document.querySelectorAll('#globeSlotProfile .gph').length === 1"), "globe 3D : la photo du trek apparaît de près")
    else:
        J(pg, "() => { const G = globes.profile; G.select(G.data[0]); G.focus(G.data[0]); }"); pg.wait_for_timeout(1500)
        check(pg.is_visible("#globeSlotProfile .gcard") and J(pg, "() => globes.profile.zoom") > 5, "globe : toucher un trek zoome dessus et affiche sa carte")
        pg.wait_for_function("globes.profile.region", timeout=10000)
        check(J(pg, "() => !!globes.profile.tex && globes.profile.region.W > 0"), "globe : relief mondial et relief détaillé de près")
    pg.click("#page-profile .close"); pg.click("#bProfile"); pg.click("#bWelcome"); pg.wait_for_function("globes.welcome && globes.welcome.w > 0", timeout=10000)
    check(pg.is_visible("#globeSlotWelcome canvas") and pg.is_visible("#wDraw"), "globe sur l'accueil, boutons de préparation visibles")
    J(pg, "() => { $('#gPlace').value = 'profile'; $('#gPlace').onchange({ target: $('#gPlace') }); }"); pg.wait_for_timeout(300)
    check(not pg.is_visible("#globeSlotWelcome canvas"), "réglage : globe dans le carnet seulement")
    J(pg, "() => { $('#gPlace').value = 'both'; $('#gPlace').onchange({ target: $('#gPlace') }); closePage(); }")
    pg.click("#bClear"); pg.click("#bClear"); pg.wait_for_timeout(300)
    pg.evaluate("() => { map.setView([42.89, -0.11], 12); }"); pg.wait_for_timeout(300)
    mb = pg.query_selector("#map").bounding_box(); c0 = calls["brouter"]
    for fx, fy in [(0.3, 0.5), (0.5, 0.4), (0.7, 0.6)]:
        pg.mouse.click(mb["x"] + mb["width"] * fx, mb["y"] + mb["height"] * fy); pg.wait_for_timeout(500)
    try: pg.wait_for_function("state.legs.length >= 2", timeout=15000)   # la 3D logicielle du test ralentit la page
    except Exception: pass
    pg.wait_for_timeout(500); nl = J(pg, "() => state.legs.length")
    check(nl == 2 and calls["brouter"] - c0 == 2, f"tracé en 3 clics = 2 tronçons calculés ({nl}, {calls['brouter'] - c0} appels)")

    # Exemple de l'accueil : 4 villages reliés par BRouter
    pg.click("#bClear"); pg.click("#bClear"); pg.wait_for_timeout(300)
    pg.click("#bProfile"); pg.click("#bWelcome"); pg.wait_for_timeout(300); c0 = calls["brouter"]
    pg.click("#wDemo")
    pg.wait_for_function("state.legs.length === 3 && R.n > 1", timeout=30000); pg.wait_for_timeout(800)
    check(calls["brouter"] - c0 == 3 and J(pg, "() => S.endType === 'both' && R.stages.length >= 1"), "accueil : exemple calculé (3 tronçons)")
    pg.reload(); pg.wait_for_timeout(800)
    check(pg.is_visible("#page-welcome") and pg.is_visible("#wGo") and pg.is_visible("#wTreks"), "accueil à chaque ouverture, avec « Reprendre » et « Mes parcours »")
    n0 = J(pg, "() => R.n")
    pg.click("#wGo"); pg.wait_for_timeout(300)
    check(not pg.is_visible("#page-welcome") and J(pg, "() => R.n") == n0 and n0 > 1, "« Reprendre » rouvre le parcours en cours")
    pg.click("#bProfile"); pg.click("#bWelcome"); pg.wait_for_timeout(300)
    # le globe 3D de l'accueil plonge et tourne : en WebGL logiciel (test), chaque image bloque la page plusieurs secondes,
    # plus que les 3,5 s de la 2e touche. On le met au repos pour ce contrôle.
    J(pg, "() => { const G = globes.welcome; if (G && G.is3d) { clearTimeout(G.diveT); G.idleAt = Infinity; G.map.stop(); } }"); pg.wait_for_timeout(1500)
    pg.click("#wDraw")
    try: pg.wait_for_function("$('#wDraw').textContent.includes('touche encore')", timeout=20000)
    except Exception: pass
    check(pg.is_visible("#page-welcome") and "touche encore" in (pg.text_content("#wDraw") or ""), "« Nouveau parcours » demande confirmation si non enregistré (%s)" % J(pg, "() => [treks.dirty(), !!state.start, $('#wDraw').textContent.slice(0, 40)]"))
    pg.click("#wDraw")
    try: pg.wait_for_function("!state.start && state.draw", timeout=20000)
    except Exception: pass
    check(not pg.is_visible("#page-welcome") and J(pg, "() => !state.start && state.draw"), "« Nouveau parcours » repart d'une carte vide")

    # Mobile : tiroir à 3 hauteurs, onglets, carte utilisable au-dessus du tiroir
    m = b.new_context(**p.devices["Pixel 7"]); m.route("**/*", handler)
    mp = m.new_page(); mp.on("pageerror", lambda e: errors.append(str(e)))
    mp.goto(URL); mp.wait_for_timeout(500)
    mp.click("#wDraw"); mp.wait_for_timeout(300)
    snap = lambda: J(mp, "() => sheet.snap")
    check(snap() == "peek", "mobile : tiroir replié au démarrage")
    mp.click("#tabs button[data-tab=prep]"); mp.wait_for_timeout(400)
    check(snap() == "mid" and mp.is_visible("#poiRows"), "mobile : un onglet ouvre le tiroir à mi-hauteur")
    mp.click("#grab"); mp.wait_for_timeout(400)
    check(snap() == "peek", "mobile : toucher la poignée replie le tiroir")
    check(J(mp, "() => document.documentElement.scrollWidth <= innerWidth"), "mobile : pas de défilement horizontal")
    mp.set_input_files("#file", GPX)
    mp.wait_for_function("R && R.n > 1", timeout=90000); mp.wait_for_timeout(500)
    check(mp.is_visible("#sDist") and not mp.is_visible("#hint"), "mobile : chiffres clés visibles après import")
    mp.click("#tabs button[data-tab=stages]"); mp.wait_for_timeout(400)
    check(mp.is_visible("#profile") and len(mp.query_selector_all("#stages li")) > 1, "mobile : profil et étapes visibles")
    m.close()

    check(not errors, "aucune erreur JavaScript" + (f" ({errors[0][:80]})" if errors else ""))
    b.close()

print(f"\n{len(fails)} échec(s)" if fails else "\nTout est vert.")
sys.exit(1 if fails else 0)
