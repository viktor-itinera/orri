#!/usr/bin/env python3
"""Construit carte/relief.jpg : la texture du globe souvenir (relief ombré aux couleurs d'Orri).

Source : AWS Terrain Tiles (Mapzen, format terrarium, zoom 4), libres avec attribution
« relief : Mapzen, AWS Terrain Tiles » (déjà dans le pied de page). Reprojeté en équirectangulaire 2048 × 1024,
teinte hypsométrique (crème → sable → brun clair), ombrage venant du nord-ouest, océans vert forêt selon la profondeur.
Usage : python3 tools/build_relief.py   (à lancer une fois ; demande numpy et pillow)
"""
import io, math, os, urllib.request
import numpy as np
from PIL import Image

Z, T = 4, 256
N = 2 ** Z
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "carte", "relief.jpg")

merc = np.zeros((N * T, N * T), dtype=np.float32)
for y in range(N):
    for x in range(N):
        u = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{x}/{y}.png"
        a = np.asarray(Image.open(io.BytesIO(urllib.request.urlopen(u, timeout=60).read())).convert("RGB"), dtype=np.float32)
        merc[y * T:(y + 1) * T, x * T:(x + 1) * T] = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
    print("ligne", y + 1, "/", N, flush=True)

W, H = 2048, 1024
lon = (np.arange(W) + 0.5) / W * 360 - 180
lat = 90 - (np.arange(H) + 0.5) / H * 180
latc = np.clip(lat, -85.05, 85.05)
my = (1 - np.log(np.tan(np.pi / 4 + np.radians(latc) / 2)) / np.pi) / 2 * N * T
mx = (lon + 180) / 360 * N * T
yy = np.clip(my.astype(int), 0, N * T - 1)[:, None]
xx = np.clip(mx.astype(int), 0, N * T - 1)[None, :]
z = merc[yy, xx]
# pôles : l'Antarctique est un plateau de glace, l'Arctique de la mer
z[lat < -85.05, :] = 2800
z[lat > 85.05, :] = -3000

# ombrage (lumière du nord-ouest), en tenant compte du rétrécissement des longitudes
cell = 40075000 / W
dx = (np.roll(z, -1, 1) - np.roll(z, 1, 1)) / (2 * cell * np.maximum(np.cos(np.radians(lat))[:, None], 0.05))
dy = (np.roll(z, 1, 0) - np.roll(z, -1, 0)) / (2 * cell)
ex = 30.0
nx, ny, nz = -dx * ex, -dy * ex, np.ones_like(z)
nl = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
L = np.array([-1.0, 1.0, 1.2]); L /= np.linalg.norm(L)
shade = np.clip((nx * L[0] + ny * L[1] + nz * L[2]) / nl, 0, 1)

def ramp(v, stops):
    v = np.clip(v, stops[0][0], stops[-1][0]); out = np.zeros(v.shape + (3,), np.float32)
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        m = (v >= a) & (v <= b); t = ((v - a) / (b - a))[m][:, None]
        out[m] = np.array(ca) * (1 - t) + np.array(cb) * t
    return out

land = ramp(z, [(0, (236, 229, 210)), (400, (239, 231, 216)), (1200, (230, 214, 186)), (2500, (214, 186, 150)), (4000, (196, 160, 128)), (6000, (246, 242, 234))])
sea = ramp(-z, [(0, (52, 108, 86)), (200, (40, 92, 72)), (2000, (29, 72, 56)), (6000, (21, 55, 42))])
isl = (z > 0)[..., None]
col = np.where(isl, land * (0.55 + 0.55 * shade[..., None]), sea * (0.9 + 0.2 * shade[..., None]))
Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).save(OUT, "JPEG", quality=84, optimize=True, progressive=True)
print(OUT, os.path.getsize(OUT), "octets")
