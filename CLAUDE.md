# Trans Bavaria Trail – Arbeitsregeln

## Git
- Es gibt nur den Branch `main`. Keine Feature-Branches anlegen.
- Änderungen immer direkt auf `main` committen und pushen, damit sie live gehen (GitHub Pages deployt automatisch von `main`).
- Vor jedem Push `python3 tools/build.py` ausführen und die Seite prüfen.

## Seite
- `index.html` wird generiert. Texte in `tools/index.src.html` ändern, Brauerei-Daten in `tools/breweries.json`.
- Ehrlich bleiben: Die Route ist in Planung, Brauereien sind Kandidaten, keine Kooperationen.
