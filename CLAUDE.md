# Reiseverlauf – Projektkontext für Claude Code

Home-Assistant-Custom-Integration `reiseverlauftracker` (HACS, öffentliches Repository): erkennt Reisen eines
Wohnmobils automatisch über das D+-Signal, erstellt danach Statistik, Karte, Höhen-/Geschwindigkeitsprofil,
GPX und ein Gesamtbild und löst ein Event aus, auf das eine Automation eine Push-Nachricht sendet.

Ausführliche Anforderungen und der Ist-Zustand stehen in der importierten Datei:

@docs/ANFORDERUNGEN.md

## Arbeitsweise

- Antworten, Erklärungen, README und Oberflächentexte auf **Deutsch**. Code-Bezeichner und Kommentare
  englisch. Übersetzungen in `translations/de.json` und `translations/en.json`.
- Der Nutzer möchte **Schritt-für-Schritt-Anleitungen mit konkreten Befehlen und Prüfpunkten** („Checkpoints“).
- Keine Änderungen an der Live-Home-Assistant-Instanz des Nutzers ohne ausdrückliche Zustimmung.
  Entwickelt und getestet wird in der Entwicklungsumgebung des Repositories (`script/develop`).
- Keine Zugangsdaten, IP-Adressen, Tokens oder persönliche Angaben ins Repository (es ist öffentlich).
- Vorlage des Repositories: `jpawlowski/hacs.integration_blueprint` (HA 2026.8+, Python 3.14).
  Domain: `reiseverlauftracker`. Verzeichnis: `custom_components/reiseverlauftracker/`.
- Tests mit `pytest-homeassistant-custom-component`; Linting und Validierung (ruff, hassfest, HACS) laufen
  in den Workflows der Vorlage und müssen grün bleiben.
- `reference/` enthält die bisherigen Skripte nur als **Vorlage** (nicht importieren, nicht ausliefern).

## Vorgehen in Etappen

1. `trip_detector`: reine Python-Zustandsmaschine (D+, Verzögerung, Mindestbewegung, Persistenz) mit Tests.
2. Exportbibliothek aus `reference/ha_track.py` (Statistik, GPX, Bilder) mit Tests auf Testdaten.
3. Integrationsrahmen: Config-/Options-Flow, Koordinator, Entitäten, Dienste, Events, Übersetzungen.
4. Automations-Blueprint für die Push-Nachricht, README, HACS-Metadaten.
5. Migration des Dashboards und Abbau der alten Helfer/des Hintergrunddienstes (erst nach Freigabe).

Vor jeder Etappe kurz die offenen Entscheidungen in `docs/ANFORDERUNGEN.md` (Abschnitt 9) prüfen
und dem Nutzer die nötigen Fragen stellen, jeweils eine Frage auf einmal.

## Wichtige Fallstricke (aus dem bisherigen Projekt)

- Kein matplotlib: auf Python 3.14/musl nicht installierbar. Diagramme nur mit Pillow zeichnen.
- Pillow-Standardschrift hat kein „ö“, „–“, „Ø“: TrueType-Schrift suchen, sonst Texte ohne Umlaute.
- Rendern (Skala 2: über 100 MB RAM, Kachel-Downloads) nie im Event-Loop.
- Alte Geschwindigkeitswerte in der History sind Float-Bits als Ganzzahl (Werte über 100000 zurückrechnen).
- `sensor.dplus_i8` ist ein Textsensor mit `ON`/`OFF`, kein `binary_sensor`.
- Recorder behält standardmäßig nur 10 Tage.
- OpenStreetMap-Kacheln: nur einzelne Läufe, eigener User-Agent.
