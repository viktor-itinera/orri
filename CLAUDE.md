# Orri — notes pour Claude

Orri est un planificateur gratuit de randos et de treks au long cours. On trace un itinéraire (ou on importe un GPX),
l'appli le découpe en étapes et montre l'eau, les refuges, les bivouacs, le ravitaillement et les gares le long du parcours.
En ligne : https://viktor-itinera.github.io/orri/ (GitHub Pages, branche `main`, racine). Interface en **français**.

Le dépôt est **public** : n'y mets jamais d'information personnelle ou commerciale (plan d'affaires, contraintes de
l'associé, chiffres). Les décisions et la feuille de route vivent dans le carnet d'associés privé de Viktor.

## Fichiers

| Fichier | Rôle |
| --- | --- |
| `index.html` | Toute l'appli : HTML, CSS et JS dans un seul fichier, sans étape de build. Leaflet 1.9.4 depuis cdnjs. |
| `sw.js` | Service worker : l'appli s'ouvre hors ligne (réseau d'abord, cache ensuite pour les fichiers du site). **Incrémenter `VERSION` à chaque publication.** |
| `manifest.webmanifest`, `icons/` | Appli installable (Android : Chrome → ⋮ → Installer l'application). Icône = un orri (cabane de berger en pierre sèche). |
| `data/poi/` | Points d'intérêt générés par le robot — **ne pas éditer à la main**. |
| `tools/build_pois.py` | Construit `data/poi/` à partir d'exports OpenStreetMap. |
| `.github/workflows/poi-data.yml` | Robot mensuel qui lance l'extraction et publie les données. |
| `tests/` | Test de fumée Playwright avec services réseau simulés. |

## Interface

- Mobile d'abord : carte plein écran, barre de recherche flottante, **tiroir** (`sheet` : `peek` / `mid` / `full`) avec
  3 onglets **Tracer / Étapes / Préparer**. Le profil est dans le tiroir sur mobile, sous la carte à partir de 900 px
  (panneau latéral, `placeProfile`). Recentrer la carte avec `fitPad(p)` pour ne pas cacher le tracé sous le tiroir.
- Pastilles de catégories sur la carte (`#chips`, `setShow`) synchronisées avec les cases de l'onglet Préparer (`S.show`).
- Recherche : IGN + Photon en parallèle (IGN d'abord si la carte est en France), suggestions dès 3 lettres ;
  bouton « me localiser » (la position n'est demandée qu'au toucher).
- Identité : vert forêt `--forest` et tons pierre ; icônes SVG en ligne (`<symbol id="i-…">`) ; cibles tactiles ≥ 44 px.

## Services externes (tous gratuits, sans clé)

- **BRouter** `brouter.de` (profil `hiking-mountain`, GeoJSON) : tracé qui suit les sentiers. Serveur communautaire : usage modéré.
- **IGN Géoplateforme** `data.geopf.fr` : tuiles Plan IGN v2 et ortho (le SCAN 25 n'est pas libre), altimétrie (`ign_rge_alti_wld`), géocodage et géocodage inverse.
- **Kartverket** (topo Norvège, CC BY 4.0), **OpenTopoMap** (monde), **Photon** `photon.komoot.io` (noms de lieux hors France).
- **Overpass** (4 serveurs en cascade, 25 s max chacun) : seulement pour les zones hors couverture de `data/poi/`.
- Les attributions (OSM ODbL, IGN, Kartverket) doivent rester dans le pied de page.

## Données des points (`data/poi/`)

- `index.json` : `generated` (date), `ts` (taille des tuiles = 0,25°), `kinds` (liste `[catégorie, libellé]`), `counts`,
  `cov` (clés des tuiles couvertes, centre de la tuile dans un polygone Geofabrik), `tiles` (clés des tuiles non vides).
- `t/<lat>_<lon>.json` (clé = `floor(lat/0.25)_floor(lon/0.25)`) : tableau de `[lat, lon, indiceKind, nom, idOSM]`.
- Catégories : `water`, `hut`, `bivouac`, `shop`, `train`. **`KINDS` dans `build_pois.py` et `classify()` dans `index.html`
  (utilisé pour les réponses Overpass) doivent rester alignés.**
- L'appli charge les tuiles nécessaires autour du tracé ; une portion dont les tuiles ne sont pas dans `cov` passe par Overpass.

## Robot (`poi-data.yml`)

- Le 2 de chaque mois à 03:17 UTC, ou à la main (workflow_dispatch), ou quand `tools/build_pois.py` change.
- `plan` lit l'index Geofabrik et liste les **régions feuilles** de `COUNTRIES` (France, Espagne, Andorre, Norvège, Suisse, Italie : ~57 régions).
  Le fichier France entier (4,5 Go) était coupé par Geofabrik : on télécharge région par région.
- `extract` (matrice, `max-parallel: 4`, `fail-fast: false`) : téléchargement avec reprise et attente croissante
  (Geofabrik refuse des connexions si on en ouvre trop), `osmium tags-filter`, `osmium export` en GeoJSONSeq.
- `build` : part de `main` à jour (une relance repartirait sinon d'un vieux commit), assemble avec `build_pois.py`,
  commit seulement si changement, `pull --rebase -X theirs` puis push. Une région en échec n'empêche pas la publication.
- Un run complet dure ~30 min. Ne pas le relancer pour rien : modifier `build_pois.py` le déclenche.

## Algorithmes clés (dans `index.html`)

- Altitude : interpolation des trous, lissage sur 200 m, dénivelé avec hystérésis de 3 m.
- Temps : DIN 33466 (4 km/h, 300 m/h en montée, 500 m/h en descente, max + min/2) par tronçons d'1 km, divisé par l'allure.
- Étapes : `nextEnd` (la plus longue étape sous les limites h / D+ / km), `findScale` (équilibrage : même nombre d'étapes,
  limites resserrées), `splitDays` (N jours d'effort égal), fins d'étape fixées à la main (`S.pins`, coordonnées).
- Fin d'étape choisie pour une étape précise : `S.over[k]` (k = n° d'étape, 0 = 1re), via `setStageEnd`. Dans `snap`,
  `ends.length` donne le n° de l'étape en cours ; si rien dans la tolérance, recherche élargie à ±2 h pour cette étape.
- Fin d'étape refuge/bivouac : `snap` cherche un candidat dans ±`S.tol` h (détour compris) ; une vraie aire de bivouac
  vaut 15 min de mieux qu'un point d'eau ; micro-étape finale fusionnée ou rééquilibrée.
- Points le long du tracé : projection sur une grille de 0,01° ; distances max 1 km (1,5 km commerces, 3 km gares).
- Soleil : algorithme de SunCalc (`sunTimes`).
- État sauvegardé dans `localStorage` sous `trekplanner.v0` (garder la clé : les brouillons des utilisateurs en dépendent).

## Conventions

- Pas de service payant, pas de clé d'API, pas d'étape de build tant qu'elle n'est pas indispensable.
- Textes de l'interface en français, ton simple ; l'utilisateur principal teste sur Android.
- Messages de commit en français.
- Tester avant de publier (ci-dessous) ; après publication, vérifier le site en ligne.

## Tester

L'environnement de Claude n'atteint pas les services externes : le test simule le réseau (BRouter, IGN, Photon,
Overpass en panne, tuiles) et utilise les vraies données `data/poi/` servies en local.

```bash
python3 -m http.server 8765            # à la racine du dépôt, dans un autre terminal
cd tests && npm install leaflet@1.9.4 && pip install playwright
ORRI_GPX=/chemin/vers/un/trek.gpx python3 smoke_test.py
```

Variables : `ORRI_URL` (défaut `http://localhost:8765/`), `ORRI_CHROME` (chemin de Chrome/Chromium, sinon celui de Playwright).
Le GPX doit traverser une zone couverte (ex. le GR10). Chaque contrôle affiche OK ou ÉCHEC ; le code de sortie vaut 1 si au moins un contrôle échoue.
