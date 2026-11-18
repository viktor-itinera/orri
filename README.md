# Orri

Planificateur de randos et treks au long cours : tracé sur carte, découpage automatique en étapes, eau, refuges, bivouacs, ravitaillement et gares le long du parcours.

Application web installable (Android : Chrome → menu ⋮ → « Installer l'application »).

Données et services : itinéraires BRouter sur données © contributeurs OpenStreetMap (ODbL), points d'intérêt OpenStreetMap via Overpass, cartes et altitudes © IGN, carte topographique de Norvège © Kartverket (CC BY 4.0), OpenTopoMap, noms de lieux IGN et Photon.

## Données des points d'intérêt

`data/poi/` est produit automatiquement chaque mois par le robot GitHub Actions
`.github/workflows/poi-data.yml` (script `tools/build_pois.py`) à partir des extraits
OpenStreetMap de Geofabrik : France, Espagne, Andorre, Norvège, Suisse, Italie.
Ailleurs, l'appli interroge les serveurs publics Overpass.
