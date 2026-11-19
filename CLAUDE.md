# Orri — notes pour Claude

Orri est un planificateur gratuit de randos et de treks au long cours. On trace un itinéraire (ou on importe un GPX),
l'appli le découpe en étapes et montre l'eau, les refuges, les bivouacs, le ravitaillement et les gares le long du parcours.
En ligne : https://viktor-itinera.github.io/orri/ (GitHub Pages, branche `main`, racine). Interface en **français**.

Le dépôt est **public** : n'y mets jamais d'information personnelle ou commerciale (plan d'affaires, contraintes de
l'associé, chiffres). Les décisions et la feuille de route vivent dans le carnet d'associés privé de Viktor.

## Fichiers

| Fichier | Rôle |
| --- | --- |
| `index.html` | Toute l'appli : HTML, CSS et JS dans un seul fichier, sans étape de build. Leaflet 1.9.4 depuis cdnjs ; MapLibre GL 4.7.1 + maplibre-gl-leaflet 0.1.4 depuis unpkg. |
| `carte/orri-style.json` | Style MapLibre de la **carte Orri** (fond par défaut). |
| `carte/relief.jpg` | Texture du globe : relief ombré + teintes d'altitude (2048 × 1024, AWS Terrain Tiles), générée par `tools/build_relief.py`. |
| `carte/monde.json` | Terres et frontières du **globe souvenir** (Natural Earth 1:110m, domaine public), généré par `tools/build_globe.mjs`. |
| `sw.js` | Service worker : l'appli s'ouvre hors ligne (réseau d'abord, cache ensuite pour les fichiers du site). **Incrémenter `VERSION` à chaque publication.** |
| `manifest.webmanifest`, `icons/` | Appli installable (Android : Chrome → ⋮ → Installer l'application). Icône = un orri (cabane de berger en pierre sèche). |
| `data/poi/` | Points d'intérêt générés par le robot — **ne pas éditer à la main**. |
| `tools/build_pois.py` | Construit `data/poi/` à partir d'exports OpenStreetMap. |
| `.github/workflows/poi-data.yml` | Robot mensuel qui lance l'extraction et publie les données. |
| `.github/workflows/supabase-reveil.yml` | Robot qui appelle `ping()` (lundi et jeudi) pour que le projet Supabase gratuit ne soit pas mis en pause (7 jours sans activité). Clé publique lue dans `index.html`, aucun secret. |
| `tests/` | Test de fumée Playwright avec services réseau simulés. |

## Interface

- Mobile d'abord : carte plein écran, barre de recherche flottante, **tiroir** (`sheet` : `peek` / `mid` / `full`) avec
  3 onglets **Tracer / Étapes / Préparer**. Le profil est dans le tiroir sur mobile, sous la carte à partir de 900 px
  (panneau latéral, `placeProfile`). Recentrer la carte avec `fitPad(p)` pour ne pas cacher le tracé sous le tiroir.
- **Barre du bas** (`#bnav`, `navSync`) : **Carte · Carnet · Amis**. Carnet (`#page-profile`) et Amis (`#page-amis`) sont des
  `.page.tabpage` qui s'arrêtent au-dessus de la barre (`--nav`) ; les autres pages la recouvrent. Le carnet a 3 parties
  (`#cSec`, `carnetSec`) : Mes treks / Profil (`#rando`) / Réglages (globe, sauvegarde). Amis : Randos autour de moi, Mon compte, Mes amis.
- `#app` est en `position: fixed; inset: 0` : il suit la barre d'adresse d'Android quand elle se cache (sinon bande vide en bas).
- Pastilles de catégories sur la carte (`#chips`, `setShow`) synchronisées avec les cases de l'onglet Préparer (`S.show`).
- Recherche : IGN + Photon en parallèle (IGN d'abord si la carte est en France), suggestions dès 3 lettres ;
  bouton « me localiser » (la position n'est demandée qu'au toucher).
- **Mes parcours** (profil sans compte, onglet Carnet de la barre du bas) : `treks`, gardés dans `localStorage`
  sous `orri.treks.v1` (`{v, list:[{id, name, created, updated, data, sum}]}`) et `orri.current` (parcours ouvert).
  `data` = `draftData()` (même format que le brouillon `trekplanner.v0`). Sauvegarde/restauration en fichier JSON
  (`app: 'orri'`, fusion par `id`). Actions sensibles : 2e touche (`confirmTap`), jamais de boîte de dialogue du navigateur.
- **Mon carnet** (page profil, `renderProfile`) : statistiques (`#cStats` : treks faits, km parcourus, D+, à faire), parcours en cours,
  liste filtrable (Tous / À faire / Faits) et triable (`carnet`, gardé sous `orri.carnet`) avec mini-carte SVG du tracé (`trackSVG`, `trekPts`).
  Un trek du carnet porte aussi `status` (`'todo'` | `'done'`), `doneDate` (AAAA-MM-JJ, saisie à la main : pas de suivi GPS), `note`,
  `photos` (`[{id, lat, lon, date}]`). Page **Souvenirs** (`#page-trek`, `renderTrekPage`) : statut, date, souvenir, photos, renommer /
  dupliquer / supprimer. Photos dans **IndexedDB** (`photoDB`, base `orri-photos`) réduites à 1600 px + vignette 360 px (`shrink`) ;
  date et GPS lus dans l'EXIF avant réduction (`exifInfo`). La sauvegarde JSON ne contient pas les images. Visionneuse `#viewer`.
- **Globe 3D** (`class Globe3D`, par défaut) : MapLibre GL **5.24.0** chargé à la demande depuis unpkg (`loadML5`, l'ancien
  `maplibregl` 4.7.1 global est remis en place juste après), projection `globe`, ciel/atmosphère, altitudes AWS Terrain Tiles :
  couche `color-relief` (`RELIEF_COLORS` : fonds marins, plaines, forêts, alpages, roche, neige) + `hillshade` multidirectionnel,
  relief en volume (`setTerrain`, ×1,5) à partir du zoom 5,5. Treks en couches GeoJSON (`tline`, `tline2` pointillés, `tpt` points de loin,
  `sline` trek choisi qui se dessine), photos en `Marker` (`.gph`, de près). Toucher un trek : vol incliné (`focus`) puis la caméra en fait
  le tour (`orbit`). Accueil : globe en grand dans `.whero.g3d` (titre par-dessus), la Terre tourne puis plonge en 3D sur le parcours en cours.
  Sans WebGL, hors ligne, si le chargement échoue ou avec `?globe3d=0` : globe dessiné ci-dessous (`can3D`). `globeCard` = carte du trek touché.
  Le service worker garde les tuiles d'altitude (cache `orri-relief`, cache d'abord, 1 500 tuiles max).
- **Globe dessiné** (`class Globe`, repli) : la Terre en projection orthographique (d3-geo 3.1.1 + d3-array 3.2.4 depuis unpkg,
  chargés à la demande par `loadGlobeLibs`), terres et frontières de `carte/monde.json` (Natural Earth 1:110m, généré par
  `tools/build_globe.mjs`), océan vert forêt, terres crème. Treks du carnet (`globeTreks`) : faits en terracotta, à faire en pointillés,
  parcours en cours en jaune ; photos géolocalisées en vignettes à partir du zoom 6. Glisser / pincer / molette, toucher un trek =
  vol jusqu'à lui (`fly`, `focus`) + carte `.gcard` (Souvenirs, Préparer). Rotation lente au repos (coupée si mouvement réduit).
  **Relief** : le globe est rendu pixel par pixel (`raster`, orthographique inverse) depuis `carte/relief.jpg` (géométrie gardée
  en cache tant que seule la longitude change), puis, à partir du zoom 4, depuis les AWS Terrain Tiles de la zone vue (`wantRegion`,
  `buildRegion` : ≤ 24 tuiles, ombrage et teintes calculés à la volée). Résolution réduite pendant les mouvements.
  Placement réglable dans le carnet (`#gPlace`, `orri.globe`, ou `?globe=both|welcome|profile|off` dans l'URL) : accueil et carnet par défaut.
- **Fiche du trek** (`sheetHTML`) : page HTML autonome (tracé et profil en SVG, étapes, nuits, eau, points), affichée
  dans une iframe, téléchargeable et imprimable ; elle ne dépend d'aucun réseau.
- **Onglet Étapes** : résumé du trek (`renderSummary` : nom, dates, nuits refuge/bivouac/libres, manque d'eau, « Garder ce trek »
  = `saveTrek`, « Ajuster ») puis frise **Jour après jour** (`renderStages`, `li.day`) : une carte par jour avec sa nuit
  (`nightOf`) et un bouton « Changer » (`state.chg`) qui propose Refuge / Bivouac / Libre pour ce soir-là (`setStageEnd`).
  Les réglages du découpage (rythme, nuits, tolérance, allure) sont dans la page **Ajuster** (`#page-adjust`, `#adjLive`).
- **Choisir ses nuits** (libre arbitre) : « Changer » ouvre `sleepPanel` : − / + 30 min (`adjustDay`), la liste de tous les refuges,
  abris, bivouacs et sources atteignables ce jour-là (`nightOptions`, ±3 h, filtres `FLT`), « Laisser Orri choisir » (ancien choix
  Refuge / Bivouac / Libre, `S.over`) et le jour de repos (`S.rest`, décale les dates). Choisir un lieu (`chooseNight`) : fige les
  journées d'avant (`freezeBefore`), fait passer le tracé par le lieu si `S.via` (`viaPoint` : détour local BRouter de ±max(400 m, 2×écart)
  autour du point le plus proche, le tronçon est coupé en deux, le reste du tracé ne bouge pas) et pose une épingle
  `[lat, lon, {one: 1, poi}]`. Sur la carte, la bulle d'un point propose « Dormir ici » (`nightFor`) et « Passer par ici » (`passBy`).
  Chaque modification passe par `remember()` : le message propose « Annuler » (`undoLast`). « Rendre toutes les nuits à Orri » dans Ajuster.
- **Appui long / clic droit sur la carte** (`contextmenu`) : « Dormir ici » (nuit posée à cet endroit, tracé dévié jusque-là) ou
  « Passer par ici ». **Variante d'une journée** (`startVariant` depuis le détail d'un jour) : points de passage touchés sur la carte,
  `compareVariant` (BRouter + `trackStats`), tableau Actuel / Variante dans `#varBar`, `keepVariant` remplace le morceau de tracé
  du jour (journées d'avant figées). **Tracé animé** (`animateRoute`) à l'ouverture d'un trek, à l'import et dans l'exemple.
  **Souvenirs** (`showSouvenirs`, bouton de la page Souvenirs) : cartes 1080 × 1920 façon « story » (`#story`, `storyGo`) : couverture
  (photo ou relief), le parcours sur une carte en relief (`svRelief` : tuiles d'altitude, couleurs `NAT`, fins de journée numérotées,
  échelle), en chiffres (km, D+/D−, jours, heures, point culminant, profil, nuits), jour après jour, photos. Données : `svData` (le résumé
  `sum` garde désormais `days`, `prof`, `dn`, `h` ; repli calculé depuis le tracé). Partage d'une carte ou de toutes (`shareFiles`,
  `navigator.share`, sinon téléchargement). Dernière carte : **survol 3D** (`startFly`, `flyPlay` : vue d'ensemble, caméra qui suit le
  tracé au-dessus du relief en **images satellite** : Esri World Imagery `SAT` (sans clé, crédit obligatoire) sur Sentinel-2 cloudless 2016 d'EOX `SAT0` (CC BY 4.0), couleurs d'altitude en dessous si une tuile manque ; caméra sur un chemin lissé `smoothAlong` réglé sur la vitesse, cap limité à 20°/s ; recul final) et **vidéo** (`#stRec` : `MediaRecorder` sur un canevas 720 × 1280, mp4 si possible sinon webm,
  pause tant que les tuiles chargent), tout sur le téléphone.
- **Accueil** (`#page-welcome`) à **chaque ouverture** (demande de Viktor) : `renderWelcome` met en premier « Reprendre » le parcours
  en cours (`#wGo`) et « Mes parcours » (`#wTreks`) ; puis Nouveau parcours / Tracer (`#wDraw`, 2e touche si non enregistré),
  Importer un GPX, Voir un exemple (`DEMO` : 4 villages des Pyrénées reliés par BRouter, 3 requêtes). Lien depuis le profil.
  Conseils uniques au bon moment (`coach`, clés `orri.tip.*`).
- Identité chaleureuse : crème `--bg`, vert forêt `--forest`, terracotta `--terra` (actions principales, tracé) ;
  polices **Fraunces** (titres) et **Figtree** (texte) auto-hébergées dans `fonts/` (OFL, en cache hors ligne) ;
  icônes SVG du sprite `#sprite` (`<symbol id="i-…">`), jamais d'emoji : `I('drop')`, `CI(cat)` (icône de catégorie en couleur) ;
  textes au tutoiement, simples ; le technique va dans un `<details class="why">`. Animations courtes, coupées si
  `prefers-reduced-motion`. Cibles tactiles ≥ 44 px.

## Compte en ligne (facultatif)

- **Supabase**, offre gratuite, région UE : `SUPA` (URL + clé *publishable*, publique par nature) dans `index.html`. Schéma et règles
  d'accès (RLS : chacun ne voit que ses données) dans `supabase/schema.sql`, à coller dans le SQL Editor de Supabase (relançable).
  Pas de bibliothèque : `supa(path, {method, body, auth, prefer})` appelle Auth (`/auth/v1`) et PostgREST (`/rest/v1`) en `fetch`.
- E-mail + mot de passe, **sans e-mail de confirmation** (le SMTP intégré de Supabase n'envoie qu'à l'équipe). Pas de « mot de passe oublié » pour l'instant.
  Session sous `orri.account` (rafraîchie par `acctToken`), pseudo dans `profiles.name`.
- Carte **Mon compte** dans la page Amis (`renderAcct`, `#acct`) : créer / se connecter, synchroniser, se déconnecter (le carnet reste),
  **supprimer le compte** (RPC `delete_my_account`, tout part en cascade).
- Synchro du carnet (`acct.sync`) : table `treks` (`data` = le trek sans `photos` ni clés `_…`, `deleted`, `share` = `private` par défaut).
  Empreinte `trekHash` + `updated_at` mémorisés sous `orri.sync.v1` ; conflit = le plus récent gagne ; suppression = trace `deleted`.
  `treks.store()` déclenche une synchro 4 s plus tard (`acct.soon`) ; aussi à l'ouverture, au retour du réseau et au retour sur l'appli.
  Sans compte, aucun appel réseau. Test : `tests/account_test.mjs` (Supabase simulé, plusieurs appareils et deux comptes).
- **Amis** (`friends`, gardé sous `orri.friends.v1`) : code ami `profiles.code` (8 caractères), invitation par lien `?ami=CODE`
  (retenu sous `orri.invite` jusqu'à la connexion) ou saisi à la main ; RPC `add_friend` (amis des deux côtés : partager son code = accepter),
  `my_friends`, `remove_friend` ; table `friends (a < b)`. Carte **Mes amis** (`renderFriends`, `#friendsBox`) sous Mon compte.
  Un trek est **privé par défaut** ; choix « Qui le voit ? » sur la page Souvenirs (`t.share = 'friends'`, colonne `share`,
  règle RLS `is_friend`). Treks des amis (`friendsRefresh` après chaque synchro, au plus une fois par minute) : en bleu `FRIEND_COL`
  sur le globe (`globeTreks` → `g.friend`, couches 3D `k = 'ami' | 'ami2'`) et sur la carte (`friendLayer`, case « Voir leurs treks sur la carte »),
  page `#page-ftrek` (`renderFriendTrek` : lecture seule, « Copier dans mon carnet »).
- **Suivi partagé** (C3) : photos partagées **une par une** depuis la visionneuse (`#vShare`, seulement sur un trek partagé) : `sharePhoto`
  envoie la photo 1600 px et la vignette dans le stockage privé `photos/<uid>/<id>.jpg` (+ `_t.jpg`, règles RLS : l'auteur et ses amis),
  la liste dans `t.pub` (synchronisée, maintenue à la main, jamais déduite des photos locales). Chez l'ami, id `f/<uid>/<id>` :
  `photoURL` → `storageGet`, donc globe, grille et visionneuse marchent pareil (Supprimer / Partager cachés). Retirer / supprimer une photo
  ou un trek efface les fichiers (`unsharePaths`) ; supprimer le compte vide d'abord le dossier (`deleteAllPhotos`).
  **« Je suis ici »** (`checkIn` / `checkOut`, table `checkins`, une ligne par compte) : point bleu à étiquette sur la carte des amis
  (`friendLayer`) et sur leur globe (`g.checkin`), 7 jours max. **« En route : jour X sur N »** (`trekProgress`, `friendProg` : date de
  départ, étapes + jours de repos) dans la liste d'amis, la page du trek et la carte du globe.
- **Profil de randonneur** (C4, avec ou sans compte, `#rando` en haut de Mon carnet, `renderRando`) : tout est calculé depuis les treks
  « faits » (`randoStats`). Points = 1 par km + 1 par 100 m de montée (`trekPoints`) ; grades `GRADES` ; 12 badges `BADGES`
  (`[id, nom, description, icône, test]`, point culminant tiré de `sum.prof`) ; défi du mois `challengeOf(AAAA-MM)` (rotation sur `CHALLENGES`,
  réussi d'après les treks faits ce mois-là, `doneDate`). Nouveau grade / badge : message de fête (`randoCheck` dans `treks.store`,
  déjà vus sous `orri.rando.seen`, premier passage silencieux). Avec un compte : totaux publiés dans la table `stats` (`publishStats`,
  dans `friendsRefresh`), **classement** entre amis dans Mes amis (`renderBoard` : mois / année × km / dénivelé, `friends.lb`).
  Classement de toute la communauté : pas encore (il faudra un accord explicite de chacun pour apparaître).
- **Randos publiques « autour de moi »** : sur la page Souvenirs, « Qui le voit ? » (`#tdShare` : Moi seul / Mes amis / Tout le monde,
  `t.share` = absent | `'friends'` | `'public'`, 2e touche pour public). Un trek public est envoyé avec son départ `lat`/`lon` et un tracé
  simplifié `line` (80 points, `pubRow`) ; les amis le voient aussi (`isShared`). Recherche **sans compte** possible : page `#page-near`
  (`renderNear`, `nearSearch`, carte `#wNear` à l'accueil) → RPC `nearby_treks(lat, lon, km)` (rayon 25/50/100/200 km, 40 résultats,
  clé publique seule), autour de soi (position au toucher) ou du centre de la carte. Détail dans `#page-ftrek` (`friends.open.pub`,
  `renderPubTrek`), en violet `PUB_COL` sur la carte (`nearLayer`), « Copier dans mon carnet » via RPC `public_trek` (sans `note` ni `pub`).
  Pastille **« Randos publiques »** (`#chNear`, première des `#chips`, visible même sans parcours, `orri.near.map`) : à cocher à tout moment,
  `refreshNearMap` cherche autour du centre de la carte (rayon = demi-diagonale de la vue, 10 à 200 km) à chaque `moveend` (700 ms)
  quand la zone change assez. Retour à l'accueil : logo de la barre de recherche (`#bHome`).
  Jamais publics : e-mail, souvenir écrit, photos, « Je suis ici ».
- La synchro ne lit que ses propres lignes (`user_id=eq.<moi>`) : la règle RLS laisse aussi passer les treks partagés des amis.

## Services externes (tous gratuits, sans clé)

- **BRouter** `brouter.de` (profil `hiking-mountain`, GeoJSON) : tracé qui suit les sentiers. Serveur communautaire : usage modéré.
- **IGN Géoplateforme** `data.geopf.fr` : tuiles Plan IGN v2 et ortho (le SCAN 25 n'est pas libre), altimétrie (`ign_rge_alti_wld`), géocodage et géocodage inverse.
- **Carte Orri** (fond par défaut, toute l'Europe) : tuiles vectorielles **OpenFreeMap** (`tiles.openfreemap.org/planet`, schéma
  OpenMapTiles, polices Noto du même serveur) + relief ombré **AWS Terrain Tiles** (terrarium) + Natural Earth aux petits zooms,
  dessinées par MapLibre dans Leaflet (`L.maplibreGL`). Sans WebGL, repli sur OpenTopoMap. Choix du fond gardé sous `orri.base`.
  Couleurs du style alignées sur la palette (crème, vert forêt, sentiers terre). IGN (France seulement) reste en option.
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
- Épingles `S.pins` : `[lat, lon, meta?]`, `meta.one` = la section qui finit là fait exactement une journée (pas de redécoupage ;
  en mode « Nb de jours », `allocDays` lui donne 1 jour), `meta.poi` = la nuit choisie (affichée même sans les points chargés),
  `meta.auto` = journée figée telle qu'Orri l'avait calculée. `flatten` donne `legOf` / `posOf` (tronçon et rang de chaque point).
- Fin d'étape choisie pour une étape précise : `S.over[k]` (k = n° d'étape, 0 = 1re), via `setStageEnd`. Dans `snap`,
  `ends.length` donne le n° de l'étape en cours ; si rien dans la tolérance, recherche élargie à ±2 h pour cette étape.
- Fin d'étape refuge/bivouac : `snap` cherche un candidat dans ±`S.tol` h (détour compris) ; une vraie aire de bivouac
  vaut 15 min de mieux qu'un point d'eau ; micro-étape finale fusionnée ou rééquilibrée.
- Points le long du tracé : projection sur une grille de 0,01° ; distances max 1 km (1,5 km commerces, 3 km gares).
- Soleil : algorithme de SunCalc (`sunTimes`).
- État sauvegardé dans `localStorage` sous `trekplanner.v0` (garder la clé : les brouillons des utilisateurs en dépendent).

## Conventions

- Pas de service payant, pas de clé d'API secrète (la clé publique Supabase est faite pour être publique), pas d'étape de build tant qu'elle n'est pas indispensable.
- Textes de l'interface en français, ton simple ; l'utilisateur principal teste sur Android.
- Messages de commit en français.
- Tester avant de publier (ci-dessous) ; après publication, vérifier le site en ligne.

## Tester

L'environnement de Claude n'atteint pas les services externes : le test simule le réseau (BRouter, IGN, Photon,
Overpass en panne, tuiles) et utilise les vraies données `data/poi/` servies en local.

```bash
python3 -m http.server 8765            # à la racine du dépôt, dans un autre terminal
cd tests && npm install leaflet@1.9.4 maplibre-gl@4.7.1 @maplibre/maplibre-gl-leaflet@0.1.4 d3-array@3.2.4 d3-geo@3.1.1 && pip install playwright pillow
ORRI_GPX=/chemin/vers/un/trek.gpx python3 smoke_test.py
```

Variables : `ORRI_URL` (défaut `http://localhost:8765/`), `ORRI_CHROME` (chemin de Chrome/Chromium, sinon celui de Playwright).
Le GPX doit traverser une zone couverte (ex. le GR10). Chaque contrôle affiche OK ou ÉCHEC ; le code de sortie vaut 1 si au moins un contrôle échoue.
