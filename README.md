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
- **Fahrtenbuch:** Kilometerstand (fortgeschrieben aus der gemessenen Strecke), Füllstände von Kraftstofftank
  und zwei Gastanks, Tank- und Gasstopps mit Menge und Betrag. Erinnerung per Push bei Reisebeginn und jedem
  Halt; Durchschnittsverbrauch, Kosten im Monat und Jahr, CSV-Datei und Werte im Reise-Export.
- **Titel mit Ortsnamen:** z. B. „Hamburg – Kiel, 12.10.2026“; wahlweise nur Datum oder nur Ort.
- **Eigene Aufzeichnung:** Die Punkte jeder Reise werden gespeichert, unabhängig davon, wie lange der Recorder
  Daten behält.
- **Geschützte Ablage:** Alle Dateien liegen im Medienordner von Home Assistant und sind nur mit Anmeldung
  abrufbar.
- **Downloads im Dashboard:** GPX, Statistik, Rohdaten, Bilder, alles einer Reise als ZIP und `fahrtenbuch.csv`
  über signierte Links, die 24 h gelten und stündlich erneuert werden.
- **Bedienung über die Oberfläche:** Einrichtung, Optionen, Entitäten und Aktionen; kein YAML nötig.

## Voraussetzungen

- Home Assistant 2026.10 oder neuer
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

Unter **Konfigurieren**, in vier Bereichen:

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
|                | Mindestdauer eines Halts         | 5 min         |
| Fahrtenbuch    | Tankgröße                        | 90 l          |

Eine Reise, die sich nie weiter als die Mindestbewegung vom Start entfernt, wird verworfen (kein Export, keine
Nachricht). Ist D+ während einer Reise mindestens die Mindestdauer eines Halts aus, gilt das als Halt: Die
Integration fragt den Ort ab und listet den Halt live und später in der Statistik.

## Entitäten

Alle Entitäten gehören zu einem Gerät mit dem Namen des Eintrags. Die Entity-IDs beginnen mit diesem Namen,
z. B. `sensor.wohnmobil_gps_reisestatus`.

| Entität                                                                                                             | Inhalt                                                                                                                             |
| ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Reise aktiv                                                                                                         | An, solange eine Reise läuft (auch in Pausen)                                                                                      |
| Reisestatus                                                                                                         | Bereit, Unterwegs, Pause, Auswertung, Fortsetzbar, Fehler; Attribute „Voraussichtliches Ende“ und „Fortsetzbar bis“                |
| Reisebeginn (Attribut `startort`), Strecke, Fahrzeit, Pausenzeit (Attribut `halte`) und Durchschnitt laufende Reise | Werte der laufenden Reise; Durchschnitt = Ø in Bewegung, Pausenzeit = Zeit seit Start minus Fahrzeit                               |
| Letzte Reise                                                                                                        | Titel; Attribute `dateien` (Typ, Name, URL), `downloads` (siehe [Downloads](#downloads)), `statistik`, `ordner`, `start`           |
| Letzte Reise Strecke, Fahrzeit, Dauer, Ende                                                                         | Kennzahlen der letzten automatisch erkannten Reise                                                                                 |
| Letzte Reise Gesamtbild                                                                                             | Bild-Entität, zeigt das Gesamtbild auf dem Dashboard                                                                               |
| Fahrtenbuch Kilometerstand, Kraftstoff, Gas 1, Gas 2, Diesel getankt, Diesel Betrag, Gas getankt, Gas Betrag        | Formular für den nächsten Fahrtenbuch-Eintrag, vorbelegt mit dem Vorschlag (siehe [Fahrtenbuch](#fahrtenbuch))                     |
| Fahrtenbuch speichern, Fahrtenbuch verwerfen                                                                        | Knöpfe des Formulars                                                                                                               |
| Fahrtenbuch Eintrag                                                                                                 | „Offen“, solange ein Anlass auf den Eintrag wartet, sonst „Gespeichert“; Attribute Anlass, Ort, `letzte_eintraege`, `downloads`    |
| Kilometerstand, Kraftstoff, Gas 1, Gas 2                                                                            | Aktueller Kilometerstand und letzte Füllstände                                                                                     |
| Durchschnittsverbrauch, Tank- und Gaskosten Monat und Jahr                                                          | Auswertung des Fahrtenbuchs (Verbrauch ab dem zweiten vollen Tank)                                                                 |
| Export-Auswahl                                                                                                      | Alle Exporte (neueste zuerst) und „Alle Exporte“; wird von „Exporte aufräumen“ genutzt; Attribut `downloads` des gewählten Exports |

## Aktionen

Alle Aktionen brauchen das Feld **Fahrzeug** (den Eintrag der Integration).

| Aktion                                                                       | Zweck                                                                                                                                          |
| ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Zeitraum exportieren (`reiseverlauftracker.exportieren`)                     | Beliebigen Zeitraum aus dem Recorder auswerten; optional mit Titel, Skalierung und Rand; liefert das Ergebnis als Antwort                      |
| Exporte aufräumen (`reiseverlauftracker.aufraeumen`)                         | Dateitypen (Gesamtbild, Karte, Profil, GPX, Statistik, Rohdaten) eines Exports oder aller Exporte löschen; ohne Angabe gilt die Export-Auswahl |
| Reise starten (`reiseverlauftracker.reise_starten`)                          | Reise ohne D+ starten oder die letzte im Zusammenführungsfenster fortsetzen                                                                    |
| Reise beenden (`reiseverlauftracker.reise_beenden`)                          | Laufende Reise sofort beenden und auswerten                                                                                                    |
| Fahrtenbuch-Formular speichern (`reiseverlauftracker.fahrtenbuch_speichern`) | Formular speichern wie der Knopf; mit `anlass_zeit` nur, solange dieser Anlass offen ist (für Push-Knöpfe)                                     |
| Fahrtenbuch-Eintrag anlegen (`reiseverlauftracker.fahrtenbuch_eintragen`)    | Eintrag ohne Formular, z. B. aus einer Automation; liefert den Eintrag als Antwort                                                             |
| Fahrtenbuch-Eintrag ändern (`reiseverlauftracker.fahrtenbuch_aendern`)       | Felder eines Eintrags ändern; Liter 0 entfernt einen Tank- oder Gasstopp                                                                       |
| Fahrtenbuch-Eintrag löschen (`reiseverlauftracker.fahrtenbuch_loeschen`)     | Eintrag löschen; die ID steht im Attribut `letzte_eintraege`                                                                                   |
| Fahrtenbuch als CSV (`reiseverlauftracker.fahrtenbuch_csv`)                  | `fahrtenbuch.csv` im Ausgabeordner schreiben (geschieht auch nach jeder Änderung)                                                              |

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

Im Ausgabeordner selbst liegt außerdem `fahrtenbuch.csv` (siehe [Fahrtenbuch](#fahrtenbuch)).

Die Bilder sind im Medienbrowser unter **Medien → Lokale Medien** zu finden. GPX, Statistik, Rohdaten und
`fahrtenbuch.csv` zeigt der Medienbrowser von Home Assistant nicht an; sie lassen sich über das Dashboard
herunterladen (siehe [Downloads](#downloads)). Die Integration löscht nur Dateien, die in `export.json` stehen;
eigene Dateien im Ordner bleiben erhalten.

### Downloads

Die Entitäten „Letzte Reise“, „Export-Auswahl“ und „Fahrtenbuch Eintrag“ haben ein Attribut `downloads`: eine Liste
mit `typ`, `name` und `url` für jede Datei, bei Reisen zusätzlich `zip` mit allen Dateien der Reise. Ein Link gilt
24 h und wird stündlich erneuert, nach einem Neustart sofort; im Dashboard ist er daher immer gültig. Wer einen
Link kopiert, kann ihn bis zu einen Tag ohne Anmeldung öffnen. Ohne gültigen Link liefert Home Assistant nichts.
Die Links landen nicht in der History, und das ZIP wird beim Abruf erzeugt und nicht gespeichert.

Beispiel für eine Markdown-Karte. Die Links brauchen `target="_blank"`, sonst öffnet das Dashboard sie als eigene
Seite statt als Download:

```yaml
type: markdown
title: Downloads
content: >-
  **Letzte Reise**

  {% for d in state_attr('sensor.wohnmobil_gps_letzte_reise', 'downloads') or [] %}
  - <a href="{{ d.url }}" target="_blank">{{ d.name }}</a>
  {% endfor %}

  **Export-Auswahl:** {{ states('select.wohnmobil_gps_export_auswahl') }}

  {% for d in state_attr('select.wohnmobil_gps_export_auswahl', 'downloads') or [] %}
  - <a href="{{ d.url }}" target="_blank">{{ d.name }}</a>
  {% endfor %}

  **Fahrtenbuch**

  {% for d in state_attr('sensor.wohnmobil_gps_fahrtenbuch_eintrag', 'downloads') or [] %}
  - <a href="{{ d.url }}" target="_blank">{{ d.name }}</a>
  {% endfor %}
```

## Push-Nachricht (Blueprint)

[![Blueprint importieren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FChrisFerro%2Fha-reiseverlauf%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Freiseverlauftracker%2Fbenachrichtigung.yaml)

1. Blueprint über den Knopf importieren.
2. **Einstellungen → Automationen & Szenen → Blueprints → „Reiseverlauf – Push-Nachricht“ → Automation
   erstellen**.
3. Fahrzeug und Empfänger (Handys mit der Companion-App) wählen, unter **Ansicht beim Tippen** den Pfad einer
   Dashboard-Ansicht eintragen (Standard `/dashboard-reiseverlauf`) und speichern.

Nach dem Reiseende kommt eine Nachricht wie:

```text
Reise beendet: Hamburg – Kiel, 12.10.2026
96,4 km · 1 h 12 min Fahrzeit · 10:05–11:28 Uhr
```

Tippen öffnet die eingestellte Dashboard-Ansicht, z. B. eine mit der Entität „Letzte Reise Gesamtbild“. Wird die
Reise fortgesetzt, ersetzt „Reise aktualisiert: …“ die alte Nachricht.
Optional meldet der Blueprint auch den Reisebeginn (Standard an) und manuelle Exporte (Standard aus); die
Überschriften sind änderbar.

Die Nachricht enthält bewusst kein Bild: Das Gesamtbild ist für das Fotobuch so groß, dass iOS es als Anhang
nicht anzeigt.

## Fahrtenbuch

Das Fahrtenbuch hält Kilometerstand, Füllstände (Kraftstofftank, Gastank 1 und 2) sowie Tank- und Gasstopps fest.
Ein Eintrag entsteht zu einem **Anlass**:

- **Reisebeginn:** um die Füllstände nach der Standzeit zu bestätigen (die Heizung verbraucht auch im Stand).
- **Halt:** sobald D+ während einer Reise die Mindestdauer eines Halts aus ist, z. B. an der Tankstelle.
- **Manuell:** jederzeit über den Knopf „Fahrtenbuch speichern“ ohne offenen Anlass oder die Aktion
  „Fahrtenbuch-Eintrag anlegen“, z. B. nach dem Gasfüllen auf dem Campingplatz.

Zu jedem Anlass belegt die Integration das Formular vor: Kilometerstand = letzter Stand + gemessene Strecke,
Füllstände wie zuletzt eingetragen. Sobald ein Durchschnittsverbrauch vorliegt, wird der Kraftstoff aus Strecke,
Verbrauch und Tankgröße berechnet vorgeschlagen. Liter bei „Diesel getankt“ oder „Gas getankt“ setzen den
Füllstand auf 100 % (beim Gas beide Tanks). Der Durchschnittsverbrauch ergibt sich aus vollen Tankfüllungen
(Füllstand 100 %), Teilbetankungen dazwischen werden mitgezählt.

Die Einträge liegen im Speicher der Integration und sind damit im Backup von Home Assistant enthalten.
`fahrtenbuch.csv` im Ausgabeordner (Semikolon, Dezimalkomma, für Excel) wird nach jeder Änderung neu geschrieben.
Nach einer Reise stehen Kilometerstand von/bis, getankte Liter, Kosten und Verbrauch auch in Statistik und
Gesamtbild.

### Erinnerung per Push (Blueprint)

[![Blueprint importieren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FChrisFerro%2Fha-reiseverlauf%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Freiseverlauftracker%2Ffahrtenbuch.yaml)

1. Blueprint über den Knopf importieren.
2. **Einstellungen → Automationen & Szenen → Blueprints → „Reiseverlauf – Fahrtenbuch-Erinnerung“ → Automation
   erstellen**.
3. Fahrzeug und Empfänger wählen, unter **Ansicht beim Tippen** den Pfad der Ansicht mit dem Formular eintragen
   (Standard `/dashboard-reiseverlauf/fahrtenbuch`, siehe unten) und speichern.

Bei Reisebeginn und jedem Halt kommt dann eine Nachricht wie:

```text
Fahrtenbuch: Halt in Kiel
34439 km · Diesel 72 % · Gas 81 % / 60 %
```

- **Übernehmen** (Knopf in der Nachricht) speichert den Vorschlag; eine Bestätigung ersetzt die Nachricht.
  Ein Tipp auf eine alte Nachricht, deren Anlass schon gespeichert oder ersetzt ist, speichert nichts.
- **Tippen** auf die Nachricht öffnet das Formular zum Korrigieren oder für einen Tankstopp.

Reisebeginn, Halt und der Knopf lassen sich einzeln abschalten, die Texte sind änderbar.

### Dashboard-Ansicht

Beispiel für eine Ansicht mit dem Formular und der Auswertung (Dashboard bearbeiten → **Ansicht hinzufügen** →
⋮ → **YAML bearbeiten**). `wohnmobil_gps` durch den Namen des eigenen Eintrags ersetzen:

```yaml
title: Fahrtenbuch
path: fahrtenbuch
icon: mdi:notebook-edit
type: sections
sections:
  - type: grid
    cards:
      - type: heading
        heading: Eintrag
      - type: tile
        entity: sensor.wohnmobil_gps_fahrtenbuch_eintrag
      - type: entities
        entities:
          - number.wohnmobil_gps_fahrtenbuch_kilometerstand
          - number.wohnmobil_gps_fahrtenbuch_kraftstoff
          - number.wohnmobil_gps_fahrtenbuch_gas_1
          - number.wohnmobil_gps_fahrtenbuch_gas_2
      - type: entities
        title: Tank- und Gasstopp
        entities:
          - number.wohnmobil_gps_fahrtenbuch_diesel_getankt
          - number.wohnmobil_gps_fahrtenbuch_diesel_betrag
          - number.wohnmobil_gps_fahrtenbuch_gas_getankt
          - number.wohnmobil_gps_fahrtenbuch_gas_betrag
      - type: entities
        entities:
          - button.wohnmobil_gps_fahrtenbuch_speichern
          - button.wohnmobil_gps_fahrtenbuch_verwerfen
  - type: grid
    cards:
      - type: heading
        heading: Auswertung
      - type: tile
        entity: sensor.wohnmobil_gps_kilometerstand
      - type: tile
        entity: sensor.wohnmobil_gps_durchschnittsverbrauch
      - type: tile
        entity: sensor.wohnmobil_gps_kraftstoff
      - type: tile
        entity: sensor.wohnmobil_gps_gas_1
      - type: tile
        entity: sensor.wohnmobil_gps_gas_2
      - type: tile
        entity: sensor.wohnmobil_gps_tank_und_gaskosten_monat
      - type: tile
        entity: sensor.wohnmobil_gps_tank_und_gaskosten_jahr
```

Der Pfad der Ansicht ist dann `/<Dashboard>/fahrtenbuch`, z. B. `/dashboard-reiseverlauf/fahrtenbuch`.

## Events

Für eigene Automationen:

| Event                             | Wann                                      | Daten                                                                                                                                                                                             |
| --------------------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `reiseverlauftracker_gestartet`   | Reise beginnt oder wird fortgesetzt       | `entry_id`, `start`, `resumed`, `startort`                                                                                                                                                        |
| `reiseverlauftracker_beendet`     | Auswertung einer beendeten Reise fertig   | `entry_id`, `titel`, `start`, `ende`, `abfahrt`, `ankunft`, `strecke_km`, `fahrzeit_min`, `ordner`, `dateien`, `statistik`, `gesamtbild`, `gesamtbild_url`, `halte`, `fortgesetzt`, `fahrtenbuch` |
| `reiseverlauftracker_exportiert`  | Manueller Export fertig                   | wie `_beendet`, ohne `fortgesetzt`                                                                                                                                                                |
| `reiseverlauftracker_fahrtenbuch` | Fahrtenbuch-Anlass: Reisebeginn oder Halt | `entry_id`, `anlass` (`reisestart`, `halt`), `zeit`, `ort`, `reise_start`, `halt_start`, `vorschlag` (`kilometerstand`, `kraftstoff`, `gas_1`, `gas_2`)                                           |

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
> - **Automatische Tests:** rund 380 Tests (Reiseerkennung, Auswertung, Fahrtenbuch, Downloads, Einrichtung, Entitäten,
>   Aktionen, Blueprints)
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
