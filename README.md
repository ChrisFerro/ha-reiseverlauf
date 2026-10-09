# Reiseverlauf Tracker für Wohnmobile

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]

[English version](README.en.md)

Die Integration erkennt Reisen eines Wohnmobils automatisch über das D+-Signal. Nach jeder Reise erstellt sie
eine Karte, ein Höhen- und Geschwindigkeitsprofil, eine GPX-Datei, eine Statistik und ein Gesamtbild (z. B. für
ein Fotobuch) und meldet das Ende per Event. Ein mitgelieferter Blueprint schickt daraufhin eine Push-Nachricht
mit dem Gesamtbild aufs Handy.

## Funktionen

- **Automatische Reiseerkennung:** Start, wenn D+ angeht; Ende, wenn D+ länger als eine einstellbare Verzögerung
  (Standard 60 min) aus ist. Tankpausen gehören zur selben Reise.
- **Fähre und Autozug:** Bewegt sich das Fahrzeug bei ausgeschaltetem D+, läuft die Reise weiter.
- **Zusammenführung:** Geht es innerhalb eines Fensters (Standard 6 h) nach dem Ende weiter, z. B. nach langer
  Wartezeit am Hafen, wird dieselbe Reise fortgesetzt und neu ausgewertet.
- **Auswertung:** Strecke, Fahrzeit, Höchst- und Durchschnittsgeschwindigkeit, Höhe und Höhenmeter; Karte auf
  OpenStreetMap-Kacheln, Profile, GPX mit Höhe und Geschwindigkeit, Gesamtbild.
- **Titel mit Ortsnamen:** z. B. „Hamburg – Kiel, 12.10.2026“; wahlweise nur Datum oder nur Ort.
- **Eigene Aufzeichnung:** Die Punkte jeder Reise werden gespeichert, unabhängig davon, wie lange der Recorder
  Daten behält.
- **Geschützte Ablage:** Alle Dateien liegen im Medienordner von Home Assistant und sind nur mit Anmeldung
  abrufbar.
- **Bedienung über die Oberfläche:** Einrichtung, Optionen, Entitäten und Aktionen; kein YAML nötig.

## Voraussetzungen

- Home Assistant 2026.8 oder neuer
- [HACS](https://hacs.xyz/)
- Entitäten für:
  - **D+** – ein `sensor` (z. B. mit `ON`/`OFF`) oder `binary_sensor`, der bei laufendem Motor „Ein“ ist
  - **Position** – ein `device_tracker` mit Breiten- und Längengrad
  - **Geschwindigkeit** – ein Sensor in km/h
  - **Höhe** (optional) – ein Sensor in Metern
- Für die Push-Nachricht: die Home-Assistant-Companion-App auf dem Handy

## Installation

1. HACS öffnen, oben rechts **⋮ → Benutzerdefinierte Repositories**.
2. `https://github.com/ChrisFerro/ha-reiseverlauf` mit dem Typ **Integration** hinzufügen.
3. **Reiseverlauf Tracker für Wohnmobile** suchen und herunterladen.
4. Home Assistant neu starten.

[![Repository in HACS öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ChrisFerro&repository=ha-reiseverlauf&category=integration)

## Einrichtung

[![Integration einrichten](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=reiseverlauftracker)

**Einstellungen → Geräte & Dienste → Integration hinzufügen → „Reiseverlauf“** und auswählen:

| Feld              | Bedeutung                                                                              |
| ----------------- | -------------------------------------------------------------------------------------- |
| D+-Signal         | Sensor oder Binärsensor für D+                                                         |
| „Ein“-Wert von D+ | Zustand für „Ein“, z. B. `ON`; Groß-/Kleinschreibung egal                              |
| Positions-Tracker | Device-Tracker des Fahrzeugs; kennzeichnet zugleich das Fahrzeug                       |
| Geschwindigkeit   | Sensor in km/h                                                                         |
| Höhe              | optionaler Sensor in Metern                                                            |
| Ausgabeordner     | Ordner im Medienordner, Standard `reiseverlauf` (also `/media/reiseverlauf` auf HA OS) |

Alles lässt sich später über **Neu konfigurieren** ändern.

### Optionen

Unter **Konfigurieren**, in drei Bereichen:

| Bereich        | Option                           | Standard      |
| -------------- | -------------------------------- | ------------- |
| Reiseerkennung | Verzögerung bis Reiseende        | 60 min        |
|                | Zusammenführungsfenster          | 6 h (0 = aus) |
|                | Mindestbewegung                  | 100 m         |
| Export         | Titel                            | Datum und Ort |
|                | Ortsnamen abfragen               | an            |
|                | Bildskalierung                   | 1 (bis 4)     |
|                | Rand im Geschwindigkeitsdiagramm | 10 min        |
| Schwellenwerte | Stillstand unter                 | 3 km/h        |
|                | Maximale GPS-Ungenauigkeit       | 50 m          |
|                | Mindestabstand der Punkte        | 15 m          |
|                | Höhen-Hysterese                  | 5 m           |

Eine Reise, die sich nie weiter als die Mindestbewegung vom Start entfernt, wird verworfen (kein Export, keine
Nachricht).

## Entitäten

Alle Entitäten gehören zu einem Gerät mit dem Namen des Eintrags. Die Entity-IDs beginnen mit diesem Namen,
z. B. `sensor.wohnmobil_gps_reisestatus`.

| Entität                                          | Inhalt                                                                                                              |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| Reise aktiv                                      | An, solange eine Reise läuft (auch in Pausen)                                                                       |
| Reisestatus                                      | Bereit, Unterwegs, Pause, Auswertung, Fortsetzbar, Fehler; Attribute „Voraussichtliches Ende“ und „Fortsetzbar bis“ |
| Reisebeginn, Strecke und Fahrzeit laufende Reise | Werte der laufenden Reise                                                                                           |
| Letzte Reise                                     | Titel; Attribute `dateien` (Typ, Name, URL), `statistik`, `ordner`, `start`                                         |
| Letzte Reise Strecke, Fahrzeit, Dauer, Ende      | Kennzahlen der letzten automatisch erkannten Reise                                                                  |
| Letzte Reise Gesamtbild                          | Bild-Entität, zeigt das Gesamtbild auf dem Dashboard                                                                |
| Export-Auswahl                                   | Alle Exporte (neueste zuerst) und „Alle Exporte“; wird von „Exporte aufräumen“ genutzt                              |

## Aktionen

Alle Aktionen brauchen das Feld **Fahrzeug** (den Eintrag der Integration).

| Aktion                                                   | Zweck                                                                                                                                          |
| -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Zeitraum exportieren (`reiseverlauftracker.exportieren`) | Beliebigen Zeitraum aus dem Recorder auswerten; optional mit Titel, Skalierung und Rand; liefert das Ergebnis als Antwort                      |
| Exporte aufräumen (`reiseverlauftracker.aufraeumen`)     | Dateitypen (Gesamtbild, Karte, Profil, GPX, Statistik, Rohdaten) eines Exports oder aller Exporte löschen; ohne Angabe gilt die Export-Auswahl |
| Reise starten (`reiseverlauftracker.reise_starten`)      | Reise ohne D+ starten oder die letzte im Zusammenführungsfenster fortsetzen                                                                    |
| Reise beenden (`reiseverlauftracker.reise_beenden`)      | Laufende Reise sofort beenden und auswerten                                                                                                    |

Beispiel für einen Dashboard-Knopf, der den in der Export-Auswahl gewählten Export komplett löscht:

```yaml
type: button
name: Export löschen
icon: mdi:delete
tap_action:
  action: perform-action
  perform_action: reiseverlauftracker.aufraeumen
  data:
    config_entry_id: <ID des Eintrags>
  confirmation:
    text: Den gewählten Export wirklich löschen?
```

## Ablage

Jede Reise bekommt einen eigenen Ordner im Ausgabeordner, benannt nach der Startzeit (z. B. `2026-10-12_1000`;
manuelle Exporte `2026-10-12_1000-1130`). Darin liegen:

| Datei                   | Inhalt                                       |
| ----------------------- | -------------------------------------------- |
| `<titel>_gesamt.png`    | Gesamtbild mit Kopfzeile, Karte und Profilen |
| `<titel>.png`           | Karte                                        |
| `<titel>_profil.png`    | Höhen- und Geschwindigkeitsprofil            |
| `<titel>.gpx`           | Track mit Höhe und Geschwindigkeit           |
| `<titel>_statistik.txt` | Statistik als Text                           |
| `<titel>_rohdaten.json` | Aufgezeichnete Punkte                        |
| `export.json`           | Verwaltungsdaten der Integration             |

Die Dateien sind im Medienbrowser unter **Medien → Lokale Medien** zu finden. Die Integration löscht nur Dateien,
die in `export.json` stehen; eigene Dateien im Ordner bleiben erhalten.

## Push-Nachricht (Blueprint)

[![Blueprint importieren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FChrisFerro%2Fha-reiseverlauf%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Freiseverlauftracker%2Fbenachrichtigung.yaml)

1. Blueprint über den Knopf importieren.
2. **Einstellungen → Automationen & Szenen → Blueprints → „Reiseverlauf – Push-Nachricht“ → Automation
   erstellen**.
3. Fahrzeug und Empfänger (Handys mit der Companion-App) wählen, speichern.

Nach dem Reiseende kommt eine Nachricht wie:

```text
Reise beendet: Hamburg – Kiel, 12.10.2026
96,4 km · 1 h 12 min Fahrzeit · 10:00–11:30 Uhr
[Gesamtbild]
```

Tippen öffnet das Gesamtbild. Wird die Reise fortgesetzt, ersetzt „Reise aktualisiert: …“ die alte Nachricht.
Optional meldet der Blueprint auch den Reisebeginn (Standard an) und manuelle Exporte (Standard aus); die
Überschriften sind änderbar.

Das Handy lädt das Bild über seine Verbindung zu Home Assistant. Unterwegs braucht es dafür Fernzugriff (z. B.
Home Assistant Cloud); ohne Verbindung kommt die Nachricht ohne Bild.

## Events

Für eigene Automationen:

| Event                            | Wann                                    | Daten                                                                                                                                               |
| -------------------------------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `reiseverlauftracker_gestartet`  | Reise beginnt oder wird fortgesetzt     | `entry_id`, `start`, `resumed`                                                                                                                      |
| `reiseverlauftracker_beendet`    | Auswertung einer beendeten Reise fertig | `entry_id`, `titel`, `start`, `ende`, `strecke_km`, `fahrzeit_min`, `ordner`, `dateien`, `statistik`, `gesamtbild`, `gesamtbild_url`, `fortgesetzt` |
| `reiseverlauftracker_exportiert` | Manueller Export fertig                 | wie `_beendet`, ohne `fortgesetzt`                                                                                                                  |

## Datenschutz

- Für die Karte lädt die Integration Kacheln von OpenStreetMap; für die Ortsnamen schickt sie Start- und
  Endposition an Nominatim (OpenStreetMap). Beides nur einmal pro Reise. Die Ortsabfrage lässt sich in den
  Optionen abschalten.
- Die Diagnose der Integration enthält keine Positionen.

## Fehlersuche

Debug-Protokoll einschalten: **Einstellungen → Geräte & Dienste → Reiseverlauf → ⋮ → Debug-Protokoll
aktivieren**. Steht der Reisestatus auf „Fehler“, ist die letzte Auswertung fehlgeschlagen; der Grund steht im
Protokoll.

## Entwicklung

Die Integration basiert auf [jpawlowski/hacs.integration_blueprint](https://github.com/jpawlowski/hacs.integration_blueprint)
und lässt sich in GitHub Codespaces oder einem lokalen Devcontainer entwickeln. Die Entwicklungsinstanz bringt
simulierte Fahrzeugsensoren mit (`config/packages/simulation.yaml`). Siehe [CONTRIBUTING.md](CONTRIBUTING.md),
[docs/development/ARCHITECTURE.md](docs/development/ARCHITECTURE.md) und
[docs/development/CODESPACES.md](docs/development/CODESPACES.md).

[![In GitHub Codespaces öffnen](https://github.com/codespaces/badge.svg)](https://codespaces.new/ChrisFerro/ha-reiseverlauf?quickstart=1)

## KI-gestützte Entwicklung

> [!NOTE]
> Diese Integration wurde mit Unterstützung von KI-Programmierassistenten (Claude) entwickelt.
>
> - **KI-Anteil:** überwiegend
> - **Prüfung durch Menschen:** Anforderungen und Entscheidungen vom Maintainer; jede Ausbaustufe in einer
>   Entwicklungsinstanz geprüft
> - **Automatische Tests:** rund 200 Tests (Reiseerkennung, Auswertung, Einrichtung, Entitäten, Aktionen,
>   Blueprint)
> - **Test mit echtem Fahrzeug:** noch nicht erfolgt, bisher nur mit simulierten Sensoren
> - **Reifegrad:** frühe Version (0.x); Einstellungen und Entitäten können sich noch ändern
>
> Bei unerwartetem Verhalten bitte ein [Issue](https://github.com/ChrisFerro/ha-reiseverlauf/issues) anlegen.

## Lizenz

MIT, siehe [LICENSE](LICENSE). Die mitgelieferte Schrift DejaVu Sans steht unter ihrer eigenen Lizenz
(`custom_components/reiseverlauftracker/export/fonts/LICENSE`). Kartendaten © OpenStreetMap-Mitwirkende.

[commits-shield]: https://img.shields.io/github/commit-activity/y/ChrisFerro/ha-reiseverlauf.svg?style=for-the-badge
[commits]: https://github.com/ChrisFerro/ha-reiseverlauf/commits/main
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/ChrisFerro/ha-reiseverlauf.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/ChrisFerro/ha-reiseverlauf.svg?style=for-the-badge
[releases]: https://github.com/ChrisFerro/ha-reiseverlauf/releases
