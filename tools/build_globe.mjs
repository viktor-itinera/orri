// Construit carte/monde.json pour le globe souvenir : terres et frontières Natural Earth au 1:110 000 000
// (paquet npm world-atlas, domaine public), coordonnées arrondies à 0,01°.
// Usage (une fois, depuis tests/ où sont les paquets) : node ../tools/build_globe.mjs
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(process.cwd() + '/');
const topojson = require('topojson-client');
const land = JSON.parse(readFileSync(require.resolve('world-atlas/land-110m.json')));
const countries = JSON.parse(readFileSync(require.resolve('world-atlas/countries-110m.json')));
const r = a => Array.isArray(a[0]) ? a.map(r) : [Math.round(a[0] * 100) / 100, Math.round(a[1] * 100) / 100];
const L = topojson.feature(land, land.objects.land);
const geomL = L.type === 'FeatureCollection' ? L.features[0].geometry : L.geometry;
const B = topojson.mesh(countries, countries.objects.countries, (a, b) => a !== b);
const out = { src: 'Natural Earth 1:110m (domaine public) via world-atlas 2.0.2', land: { type: geomL.type, coordinates: r(geomL.coordinates) }, borders: { type: B.type, coordinates: r(B.coordinates) } };
writeFileSync(new URL('../carte/monde.json', import.meta.url), JSON.stringify(out));
console.log('carte/monde.json', JSON.stringify(out).length, 'octets');
