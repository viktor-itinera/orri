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
CHROME = os.environ.get("ORRI_CHROME")
if not GPX: sys.exit("Indique un fichier GPX : ORRI_GPX=/chemin/trek.gpx python3 smoke_test.py")


def png(w, h, rgb):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")


TILE = png(256, 256, (232, 236, 226))
calls = {"brouter": 0, "overpass": 0}
JSON_HDR = {"Access-Control-Allow-Origin": "*"}


def handler(route):
    u = route.request.url
    q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
    if u.startswith(URL): return route.continue_()
    if "cdnjs.cloudflare.com" in u and u.endswith(".js"): return route.fulfill(path=LEAF + "leaflet.js", content_type="application/javascript")
    if "cdnjs.cloudflare.com" in u and u.endswith(".css"): return route.fulfill(path=LEAF + "leaflet.css", content_type="text/css")
    if "/wmts" in u or "opentopomap" in u or "kartverket" in u: return route.fulfill(body=TILE, content_type="image/png")
    if "brouter.de" in u:
        calls["brouter"] += 1
        (lo1, la1), (lo2, la2) = [tuple(map(float, s.split(","))) for s in q["lonlats"][0].split("|")]
        c = [[lo1 + (lo2 - lo1) * t / 30, la1 + (la2 - la1) * t / 30, 1000 + 400 * math.sin(t / 30 * math.pi)] for t in range(31)]
        return route.fulfill(body=json.dumps({"features": [{"geometry": {"coordinates": c}}]}), content_type="application/json", headers=JSON_HDR)
    if "altimetrie" in u:
        n = len(q["lon"][0].split("|"))
        return route.fulfill(body=json.dumps({"elevations": [1200 + 5 * i for i in range(n)]}), content_type="application/json", headers=JSON_HDR)
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

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"]) if CHROME else p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1400, "height": 900}, accept_downloads=True)
    ctx.route("**/*", handler)
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(URL); pg.wait_for_timeout(500)
    pg.evaluate("() => localStorage.clear()"); pg.reload(); pg.wait_for_timeout(500)

    pg.set_input_files("#file", GPX)
    pg.wait_for_function("R && R.n > 1 && (poiState === 'ok' || poiState === 'error')", timeout=90000)
    pg.wait_for_timeout(500)
    n, pois, tiles = J(pg, "() => R.n"), J(pg, "() => R.pois.length"), J(pg, "() => tileLoaded.size")
    print(f"     GPX : {n} points, {J(pg, '() => (R.dist/1000).toFixed(1)')} km, {pois} points d'intérêt depuis {tiles} tuiles locales")
    check(n > 100, "GPX importé")
    check(pois > 0 and tiles > 0, "points d'intérêt chargés depuis data/poi/ (Overpass en panne)")

    pg.click("#modeSeg button[data-m=limits]"); pg.wait_for_timeout(800)
    worst = J(pg, "() => Math.max(...R.stages.map(s => s.time))")
    check(worst <= 7.01, f"limite 7 h/jour respectée (max {worst:.2f} h)")

    pg.select_option("#endType", "refuge"); pg.wait_for_timeout(1500)
    hits = J(pg, "() => R.stages.filter(s => s.endPoi).length")
    dmax = J(pg, "() => Math.max(0, ...R.stages.filter(s => s.endPoi).map(s => Math.abs(s.endDelta)))")
    check(hits > 0, f"fins d'étape au refuge trouvées ({hits})")
    check(dmax <= J(pg, "() => S.tol") + 1e-6, f"écart dans la tolérance (max {dmax:.2f} h)")

    pg.click("#modeSeg button[data-m=days]"); pg.fill("#vDays", "12"); pg.dispatch_event("#vDays", "input"); pg.wait_for_timeout(1500)
    check(J(pg, "() => R.stages.length") == 12, "12 jours imposés = 12 étapes")

    pg.query_selector_all("#stages li")[0].click(); pg.wait_for_timeout(500)
    check(pg.query_selector("#stages li.sel .detail") is not None, "feuille d'étape affichée")

    with pg.expect_download() as dl:
        pg.click("#bExport")
    x = open(dl.value.path(), encoding="utf-8").read()
    check(x.count("<trk>") == 12 and "<wpt" in x, "export GPX : 12 traces + points")

    pg.click("#bClear"); pg.click("#bClear"); pg.wait_for_timeout(300)
    pg.evaluate("() => { map.setView([42.89, -0.11], 12); }"); pg.wait_for_timeout(300)
    mb = pg.query_selector("#map").bounding_box(); c0 = calls["brouter"]
    for fx, fy in [(0.3, 0.5), (0.5, 0.4), (0.7, 0.6)]:
        pg.mouse.click(mb["x"] + mb["width"] * fx, mb["y"] + mb["height"] * fy); pg.wait_for_timeout(500)
    check(J(pg, "() => state.legs.length") == 2 and calls["brouter"] - c0 == 2, "tracé en 3 clics = 2 tronçons calculés")

    check(not errors, "aucune erreur JavaScript" + (f" ({errors[0][:80]})" if errors else ""))
    b.close()

print(f"\n{len(fails)} échec(s)" if fails else "\nTout est vert.")
sys.exit(1 if fails else 0)
