#!/usr/bin/env python3
"""Construit les données de points d'intérêt d'Orri à partir d'extraits OpenStreetMap.

Entrée : des fichiers GeoJSONSeq produits par `osmium export` (un par pays) et les
polygones Geofabrik (.poly) de ces pays.
Sortie : data/poi/index.json (couverture + liste des tuiles) et data/poi/t/<clé>.json,
une tuile par carré de 0,25° contenant au moins un point.

Usage : build_pois.py OUT_DIR pays1.geojsonseq:pays1.poly [pays2.geojsonseq:pays2.poly ...]
Données © contributeurs OpenStreetMap, licence ODbL.
"""
import json, math, os, sys, datetime

TS = 0.25  # taille des tuiles en degrés

# Doit rester identique à KINDS dans index.html (même ordre).
KINDS = [
    ("hut", "Refuge gardé"), ("hut", "Cabane non gardée"), ("hut", "Abri"),
    ("hut", "Gîte / auberge"), ("hut", "Gîte / chambre d'hôtes"),
    ("bivouac", "Aire de bivouac"), ("bivouac", "Camping"), ("bivouac", "Emplacement de bivouac"),
    ("water", "Eau potable"), ("water", "Point d'eau"), ("water", "Robinet"),
    ("water", "Source (potabilité non garantie)"),
    ("shop", "Boulangerie"), ("shop", "Épicerie / supérette"),
    ("train", "Gare"),
]
K = {k: i for i, k in enumerate(KINDS)}


def classify(t):
    """Même logique que classify() dans index.html."""
    tour, am = t.get("tourism"), t.get("amenity")
    if tour == "alpine_hut": return K[("hut", "Refuge gardé")]
    if tour == "wilderness_hut": return K[("hut", "Cabane non gardée")]
    if am == "shelter" and t.get("shelter_type") in ("basic_hut", "lean_to"): return K[("hut", "Abri")]
    if tour == "hostel": return K[("hut", "Gîte / auberge")]
    if tour == "guest_house": return K[("hut", "Gîte / chambre d'hôtes")]
    if tour == "camp_site":
        basic = t.get("camp_site") == "basic" or t.get("backcountry") == "yes"
        return K[("bivouac", "Aire de bivouac" if basic else "Camping")]
    if tour == "camp_pitch": return K[("bivouac", "Emplacement de bivouac")]
    if t.get("drinking_water") == "no": return None
    if am == "drinking_water": return K[("water", "Eau potable")]
    if am == "water_point": return K[("water", "Point d'eau")]
    if t.get("man_made") == "water_tap": return K[("water", "Robinet")]
    if t.get("natural") == "spring": return K[("water", "Source (potabilité non garantie)")]
    if t.get("shop") == "bakery": return K[("shop", "Boulangerie")]
    if t.get("shop") in ("supermarket", "convenience", "general"): return K[("shop", "Épicerie / supérette")]
    if t.get("railway") in ("station", "halt"): return K[("train", "Gare")]
    return None


def point_of(geom):
    """Point représentatif : le point lui-même, ou la moyenne des sommets (anneau extérieur)."""
    gt, c = geom["type"], geom["coordinates"]
    if gt == "Point": return c[0], c[1]
    if gt == "LineString": ring = c
    elif gt == "Polygon": ring = c[0]
    elif gt == "MultiPolygon": ring = c[0][0]
    elif gt == "MultiLineString": ring = c[0]
    else: return None
    if not ring: return None
    return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)


def read_poly(path):
    """Fichier .poly Geofabrik -> liste d'anneaux (lon, lat) ; les anneaux '!' sont des trous."""
    rings, cur, hole = [], None, False
    with open(path) as f:
        lines = [l.strip() for l in f if l.strip()]
    for l in lines[1:]:
        if l == "END":
            if cur is not None: rings.append((hole, cur)); cur = None
            continue
        if cur is None:
            hole = l.startswith("!"); cur = []
            continue
        x, y = map(float, l.split()[:2]); cur.append((x, y))
    return rings


def in_ring(r, x, y):
    c = False
    for i in range(len(r)):
        (x1, y1), (x2, y2) = r[i], r[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: c = not c
    return c


def inside(rings, x, y):
    ok = False
    for hole, r in rings:
        if in_ring(r, x, y):
            if hole: return False
            ok = True
    return ok


def coverage(rings):
    xs = [p[0] for _, r in rings for p in r]; ys = [p[1] for _, r in rings for p in r]
    out = set()
    for ty in range(math.floor(min(ys) / TS), math.floor(max(ys) / TS) + 1):
        for tx in range(math.floor(min(xs) / TS), math.floor(max(xs) / TS) + 1):
            if inside(rings, (tx + 0.5) * TS, (ty + 0.5) * TS): out.add(f"{ty}_{tx}")
    return out


def main(out_dir, pairs):
    tiles, seen, cov, counts = {}, set(), set(), [0] * len(KINDS)
    for pair in pairs:
        seq, poly = pair.split(":")
        cov |= coverage(read_poly(poly))
        with open(seq, encoding="utf-8") as f:
            for line in f:
                line = line.strip().lstrip("\x1e")
                if not line: continue
                ft = json.loads(line)
                p = ft.get("properties") or {}
                oid = f"{p.get('@type', 'x')[0]}{p.get('@id', '')}"
                if oid in seen: continue
                k = classify(p)
                if k is None: continue
                pt = point_of(ft["geometry"]) if ft.get("geometry") else None
                if not pt: continue
                seen.add(oid)
                lon, lat = pt
                key = f"{math.floor(lat / TS)}_{math.floor(lon / TS)}"
                tiles.setdefault(key, []).append([round(lat, 5), round(lon, 5), k, (p.get("name") or "").strip()[:80], oid])
                counts[k] += 1
    tdir = os.path.join(out_dir, "t")
    os.makedirs(tdir, exist_ok=True)
    for fn in os.listdir(tdir):
        if fn.endswith(".json") and fn[:-5] not in tiles: os.remove(os.path.join(tdir, fn))
    for key, pts in tiles.items():
        pts.sort(key=lambda q: q[4])
        with open(os.path.join(tdir, key + ".json"), "w", encoding="utf-8") as f:
            json.dump(pts, f, ensure_ascii=False, separators=(",", ":"))
    index = {
        "generated": datetime.date.today().isoformat(), "ts": TS,
        "kinds": KINDS, "counts": counts,
        "cov": sorted(cov), "tiles": sorted(tiles),
        "source": "© contributeurs OpenStreetMap (ODbL)",
    }
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{sum(counts)} points, {len(tiles)} tuiles, {len(cov)} tuiles couvertes")
    for (cat, kind), n in zip(KINDS, counts): print(f"  {kind}: {n}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
