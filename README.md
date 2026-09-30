# Trans Bavaria Trail

High-end One-Pager für den **Trans Bavaria Trail**: eine Enduro-Route der Bavarian Beer Seekers MC. Nomads, offroad von Brauerei zu Brauerei durch alle sieben Regierungsbezirke Bayerns.

> Offroad to Bavaria's best breweries.

## Struktur

| Datei | Zweck |
|---|---|
| `index.html` | **Generiert.** Bitte nicht direkt bearbeiten, sondern `tools/index.src.html`. |
| `tools/index.src.html` | Inhalte und Texte der Seite |
| `tools/build.py` | Baut `index.html`. Erzeugt die Bayern-Karte (echte Bezirksgrenzen), die Route, die Hero-Landschaft, die Roadbook-Tulpen und das BBS-Siegel als Inline-SVG. |
| `tools/paths.json`, `tools/route.json` | Geodaten: Grenzen der Bezirke und Brauerei-Koordinaten |
| `styles.css` | Designsystem (Farbpalette aus dem Patch) |
| `main.js` | Interaktionen: Topo-Linien, Parallax, Route beim Scrollen, Formulare |
| `assets/fonts/` | Selbst gehostete Schriften, damit nichts an Google Fonts übertragen wird (DSGVO) |
| `impressum.html`, `datenschutz.html` | Rechtstexte. Die markierten Platzhalter müssen noch befüllt werden. |

Nach Änderungen an Texten neu bauen:

```bash
python3 tools/build.py
```

## Formulare

Die Formulare für Scout-Liste und Brauerei-Tipp werden in `main.js` über `CONFIG` konfiguriert:

- `formEndpoint`: zum Beispiel ein Formspree-Endpoint. Die Daten werden dann im Hintergrund gesendet.
- `email`: Fallback. Öffnet das Mailprogramm mit einer vorausgefüllten Nachricht.

## Deployment

GitHub Pages deployt automatisch vom Branch `main` (`.github/workflows/deploy.yml`).

## Lokale Vorschau

```bash
python3 -m http.server 8000
```
