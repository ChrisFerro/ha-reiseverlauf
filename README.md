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
- **Nachträge:** Tankstopp später einem Halt, einem kurzen Stopp oder einer Uhrzeit zuordnen; Kilometerstand und
  Verbrauch stimmen, als wäre er sofort eingetragen worden.
- **Reisekosten:** Maut je Reise und Land, Vignette, Fähre, Tunnel, Stellplatz; die Länder der Reise werden
  vorgeschlagen, eine Erinnerung meldet Reisen durch Mautländer ohne Maut-Eintrag. Statistik und Gesamtbild einer
  Reise werden nach jedem Nachtrag erneuert.
- **Touren:** Mehrere Reisen mit den Standzeiten dazwischen (Urlaub, Werkstattaufenthalt) im Nachhinein
  zusammenfassen: Gesamtkarte, Tagesübersicht mit Standorten („10.–15.10. · Camping Seeblick · 5 Nächte“), alle
  Kosten je Kategorie und Land, geschätzter Verbrauch, GPX und Gesamtbild für das Fotobuch.
- **Titel mit Ortsnamen:** z. B. „Hamburg – Kiel, 12.10.2026“; wahlweise nur Datum oder nur Ort.
- **Eigene Aufzeichnung:** Die Punkte jeder Reise werden gespeichert, unabhängig davon, wie lange der Recorder
  Daten behält.
- **Geschützte Ablage:** Alle Dateien liegen im Medienordner von Home Assistant und sind nur mit Anmeldung
  abrufbar.
- **Downloads im Dashboard:** GPX, Statistik, Rohdaten, Bilder, alles einer Reise als ZIP, `fahrtenbuch.csv` und
  `reisekosten.csv` über signierte Links, die 24 h gelten und stündlich erneuert werden.
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
|                | Mautländer                       | siehe unten   |

Eine Reise, die sich nie weiter als die Mindestbewegung vom Start entfernt, wird verworfen (kein Export, keine
Nachricht). Ist D+ während einer Reise mindestens die Mindestdauer eines Halts aus, gilt das als Halt: Die
Integration fragt den Ort ab und listet den Halt live und später in der Statistik.

Mautländer sind die Länder, in denen das Fahrzeug Maut zahlt. Standard: AT, BE, CH, CZ, ES, FR, HR, HU, IT, NO, PL,
PT, SI, SK (streckenabhängige Maut oder Gebühr für Wohnmobile über 3,5 t; Deutschland nicht, Wohnmobile sind von der
Lkw-Maut befreit). Sie stehen in der Länder-Auswahl der Reisekosten und bestimmen die Maut-Erinnerung.

## Entitäten

Alle Entitäten gehören zu einem Gerät mit dem Namen des Eintrags. Die Entity-IDs beginnen mit diesem Namen,
z. B. `sensor.wohnmobil_gps_reisestatus`.

| Entität                                                                                                             | Inhalt                                                                                                                                                                                   |
| ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reise aktiv                                                                                                         | An, solange eine Reise läuft (auch in Pausen)                                                                                                                                            |
| Reisestatus                                                                                                         | Bereit, Unterwegs, Pause, Auswertung, Fortsetzbar, Fehler; Attribute „Voraussichtliches Ende“ und „Fortsetzbar bis“                                                                      |
| Reisebeginn (Attribut `startort`), Strecke, Fahrzeit, Pausenzeit (Attribut `halte`) und Durchschnitt laufende Reise | Werte der laufenden Reise; Durchschnitt = Ø in Bewegung, Pausenzeit = Zeit seit Start minus Fahrzeit                                                                                     |
| Letzte Reise                                                                                                        | Titel; Attribute `dateien` (Typ, Name, URL), `downloads` (siehe [Downloads](#downloads)), `statistik`, `ordner`, `start`                                                                 |
| Letzte Reise Strecke, Fahrzeit, Dauer, Ende                                                                         | Kennzahlen der letzten automatisch erkannten Reise                                                                                                                                       |
| Letzte Reise Gesamtbild                                                                                             | Bild-Entität, zeigt das Gesamtbild auf dem Dashboard                                                                                                                                     |
| Fahrtenbuch Kilometerstand, Kraftstoff, Gas 1, Gas 2, Diesel getankt, Diesel Betrag, Gas getankt, Gas Betrag        | Formular für den nächsten Fahrtenbuch-Eintrag, vorbelegt mit dem Vorschlag (siehe [Fahrtenbuch](#fahrtenbuch))                                                                           |
| Fahrtenbuch speichern, Fahrtenbuch verwerfen                                                                        | Knöpfe des Formulars                                                                                                                                                                     |
| Fahrtenbuch Zeitpunkt, Fahrtenbuch Nachtrag Zeit, Fahrtenbuch nachtragen                                            | Formular für einen früheren Zeitpunkt (siehe [Nachträge](#nachträge)); Attribute `zeit`, `ort`, `geschaetzt`                                                                             |
| Fahrtenbuch bearbeiten; Fahrtenbuch ändern, Fahrtenbuch löschen                                                     | Gespeicherten Eintrag wählen, ändern oder löschen (siehe [Einträge ändern und löschen](#einträge-ändern-und-löschen)); Attribut `eintrag`                                                |
| Fahrtenbuch Feld leeren                                                                                             | Setzt ein Feld des Formulars zurück auf „nicht abgelesen“ (Liter und Beträge auf 0)                                                                                                      |
| Reisekosten Kategorie, Land, Betrag, Notiz, Datum; Reisekosten speichern, Keine Maut                                | Formular für Reisekosten der Reise in der Export-Auswahl (siehe [Reisekosten](#reisekosten))                                                                                             |
| Reisekosten Eintrag; Reisekosten ändern, Reisekosten löschen                                                        | Gespeicherte Reisekosten wählen, ändern oder löschen; Attribut `eintrag`                                                                                                                 |
| Fahrtenbuch Eintrag                                                                                                 | „Offen“, solange ein Anlass auf den Eintrag wartet, sonst „Gespeichert“; Attribute Anlass, Ort, `nicht_abgelesen`, `letzte_eintraege`, `downloads`                                       |
| Kilometerstand, Kraftstoff, Gas 1, Gas 2                                                                            | Aktueller Kilometerstand und letzte Füllstände                                                                                                                                           |
| Durchschnittsverbrauch                                                                                              | Auswertung des Fahrtenbuchs (ab dem zweiten vollen Tank)                                                                                                                                 |
| Reisekosten Monat, Reisekosten Jahr                                                                                 | Alle Kosten im laufenden Monat bzw. Jahr; Attribute `diesel`, `gas` und je Kategorie (`maut`, `faehre` …)                                                                                |
| Maut offen                                                                                                          | Fertige Reisen der letzten 12 Monate durch ein Mautland ohne Maut-Eintrag; Attribut `reisen`                                                                                             |
| Heizung im Stand (abgelesen)                                                                                        | Diesel der Heizung je Standtag aus den abgelesenen Füllständen (grob); Attribute `standzeiten`, `standtage`, `abnahme_liter`                                                             |
| Export-Auswahl                                                                                                      | Alle Exporte (neueste zuerst, manuelle mit „Manuell“) und „Alle Exporte“; für „Exporte aufräumen“ und Reisekosten; Attribute `downloads`, `reisekosten`, `exporte`                       |
| Tour von, Tour bis, Tour Titel; Tour erstellen, Tour aktualisieren; Tour in Arbeit                                  | Formular für Touren (siehe [Touren](#touren)); „Tour in Arbeit“ ist an, solange eine Tour erstellt wird; bei einer Tour in der Export-Auswahl Attribute `art`, `standorte`, `tourkosten` |

## Aktionen

Alle Aktionen brauchen das Feld **Fahrzeug** (den Eintrag der Integration).

| Aktion                                                                       | Zweck                                                                                                                                                          |
| ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Zeitraum exportieren (`reiseverlauftracker.exportieren`)                     | Beliebigen Zeitraum aus dem Recorder auswerten; optional mit Titel, Skalierung und Rand; liefert das Ergebnis als Antwort                                      |
| Exporte aufräumen (`reiseverlauftracker.aufraeumen`)                         | Dateitypen (Gesamtbild, Karte, Profil, GPX, Statistik, Rohdaten, Tagesübersicht) eines Exports oder aller Exporte löschen; ohne Angabe gilt die Export-Auswahl |
| Reise starten (`reiseverlauftracker.reise_starten`)                          | Reise ohne D+ starten oder die letzte im Zusammenführungsfenster fortsetzen                                                                                    |
| Reise beenden (`reiseverlauftracker.reise_beenden`)                          | Laufende Reise sofort beenden und auswerten                                                                                                                    |
| Fahrtenbuch-Formular speichern (`reiseverlauftracker.fahrtenbuch_speichern`) | Formular speichern wie der Knopf; mit `anlass_zeit` nur, solange dieser Anlass offen ist (für Push-Knöpfe)                                                     |
| Fahrtenbuch-Eintrag anlegen (`reiseverlauftracker.fahrtenbuch_eintragen`)    | Eintrag ohne Formular, z. B. aus einer Automation; liefert den Eintrag als Antwort                                                                             |
| Fahrtenbuch-Eintrag ändern (`reiseverlauftracker.fahrtenbuch_aendern`)       | Felder eines Eintrags ändern; Liter 0 entfernt einen Tank- oder Gasstopp; eine neue Zeit bringt Zählerstände und Ort dieser Zeit                               |
| Fahrtenbuch-Eintrag löschen (`reiseverlauftracker.fahrtenbuch_loeschen`)     | Eintrag löschen; die ID steht im Attribut `letzte_eintraege`                                                                                                   |
| Fahrtenbuch als CSV (`reiseverlauftracker.fahrtenbuch_csv`)                  | `fahrtenbuch.csv` im Ausgabeordner schreiben (geschieht auch nach jeder Änderung)                                                                              |
| Tankstopp nachtragen (`reiseverlauftracker.fahrtenbuch_nachtragen`)          | Tank- oder Gasstopp für eine frühere Zeit; ein Stopp bis 5 min um die Zeit wird zugeordnet                                                                     |
| Reisekosten eintragen (`reiseverlauftracker.reisekosten_eintragen`)          | Kosten für eine Reise (Ordner, Eintrag der Export-Auswahl oder Startzeit) oder nur mit Datum; liefert den Eintrag                                              |
| Reisekosten ändern / löschen (`reisekosten_aendern`, `reisekosten_loeschen`) | Eintrag ändern oder löschen; die ID steht im Attribut `reisekosten` der Export-Auswahl                                                                         |
| Keine Maut (`reiseverlauftracker.keine_maut`)                                | Reise als ohne Maut kennzeichnen (oder mit `an: false` das Kennzeichen entfernen)                                                                              |
| Tour erstellen (`reiseverlauftracker.tour_erstellen`)                        | Alle Reisen, die von `von` bis `bis` beginnen, zu einer Tour zusammenfassen; optional Titel und Skalierung; liefert das Ergebnis                               |
| Tour ändern (`reiseverlauftracker.tour_aendern`)                             | Titel, Zeitraum oder Standortnamen (`standorte`: Liste aus `nacht` und `name`) einer Tour ändern und sie neu erstellen                                         |

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

Eine Tour bekommt einen Ordner `tour-<Start>-<Ende>` (z. B. `tour-2026-10-10-2026-10-17`) mit Gesamtbild, Karte,
GPX (je Reise ein Track), Statistik, `<titel>_tage.csv` (eine Zeile je Tag), Rohdaten und `export.json`; ein
Profil gibt es dort nicht.

Im Ausgabeordner selbst liegen außerdem `fahrtenbuch.csv` (siehe [Fahrtenbuch](#fahrtenbuch)) und `reisekosten.csv`
(siehe [Reisekosten](#reisekosten)).

Die Bilder sind im Medienbrowser unter **Medien → Lokale Medien** zu finden. GPX, Statistik, Rohdaten und
`fahrtenbuch.csv` zeigt der Medienbrowser von Home Assistant nicht an; sie lassen sich über das Dashboard
herunterladen (siehe [Downloads](#downloads)). Die Integration löscht nur Dateien, die in `export.json` stehen;
eigene Dateien im Ordner bleiben erhalten.

In der Export-Auswahl tragen manuelle Exporte das Kennzeichen „Manuell“ (z. B. `31.10.26 14:00 · Manuell · Fahrt
Pullach zum…`), Touren „Tour“; automatisch erkannte Reisen haben keines. Das Attribut `exporte` der Export-Auswahl
listet alle Exporte mit `auswahl`, `ordner`, `art` (`reise`/`tour`), `automatisch`, `start`, `ende`, `strecke_km` und
`rohdaten` (ja/nein), z. B. für eine Übersicht im Dashboard vor dem Aufräumen.

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
Optional meldet der Blueprint auch den Reisebeginn (Standard an), manuelle Exporte (Standard aus), eine fertige Tour
(Standard an) und eine aktualisierte Tour (Standard aus), z. B.
„Tour fertig: Camping Seeblick · 10.–17.10.2026“ mit „10.10.–17.10.2026 · 1712 km · 7 Nächte · Kosten 1245,50 €“.
Die Überschriften sind änderbar.

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

„Heizung im Stand (abgelesen)“ schätzt, wie viel Diesel die Heizung je Standtag verbraucht: die Abnahme des
Kraftstoffs zwischen dem letzten Eintrag vor einer Standzeit und dem nächsten Reisebeginn, summiert über alle
Standzeiten ohne Tanken und ohne Fahrt dazwischen, geteilt durch die Standtage. Weil die Tankanzeige nur grob
abgelesen wird, wird der Wert erst über viele Standzeiten aussagekräftig; er verändert weder den
Durchschnittsverbrauch noch den Vorschlag. Außerdem merkt sich jeder Eintrag die bisher gefahrenen Höhenmeter
bergauf und bergab, als Grundlage für ein späteres Verbrauchsmodell.

Die Einträge liegen im Speicher der Integration und sind damit im Backup von Home Assistant enthalten.
`fahrtenbuch.csv` im Ausgabeordner (Semikolon, Dezimalkomma, für Excel) wird nach jeder Änderung neu geschrieben.
Nach einer Reise stehen Kilometerstand von/bis, getankte Liter, Kosten und Verbrauch auch in Statistik und
Gesamtbild.

### Nachträge

Keine Zeit fürs Formular an der Tankstelle? Der Tankstopp lässt sich später nachtragen, z. B. abends nach dem Beleg:

1. In **Fahrtenbuch Zeitpunkt** den Halt oder kurzen Stopp wählen (z. B. „14.11. 10:42 · Irschenberg · kurz“) oder
   „Andere Uhrzeit …“ und die Zeit in **Fahrtenbuch Nachtrag Zeit** setzen. Zur Auswahl stehen die 30 neuesten
   Stopps und alle Stopps der Reise in der Export-Auswahl; die Integration merkt sich Stopps 120 Tage.
2. Das Formular zeigt den Kilometerstand zu diesem Zeitpunkt (aus der aufgezeichneten Strecke); ist er nur
   geschätzt (Attribut `geschaetzt`), bitte prüfen.
3. Liter und Betrag eintragen und **Fahrtenbuch nachtragen** drücken. Danach springt die Auswahl auf „Aktuell“.

Hatte der Halt schon einen Eintrag, wird er ergänzt. Der Füllstand gilt zu diesem Zeitpunkt als 100 %, spätere
Einträge bleiben unverändert. Ein offener Anlass wartet währenddessen und kommt mit „Aktuell“ zurück.

### Reisekosten

Maut, Vignette, Fähre, Tunnel, Stellplatz und Sonstiges, je Reise und bei Maut je Land:

1. In der **Export-Auswahl** die Reise wählen. **Reisekosten Datum** springt auf den Reisebeginn, **Reisekosten
   Land** schlägt das erste Mautland der Reise vor; die Länder der Reise stehen vorn in der Liste.
2. Kategorie, Land, Betrag und optional Notiz eintragen, **Reisekosten speichern**. Betrag und Notiz werden geleert,
   Kategorie und Land bleiben, sodass das nächste Land schnell folgt.
3. Kosten ohne Reise (z. B. Stellplatz während einer Standzeit): Export-Auswahl auf „Alle Exporte“ und das Datum
   setzen.

Die Kosten zählen im Monat ihres Datums. Die Länder einer Reise ermittelt die Integration nach dem Export aus der
Strecke (etwa alle 20 km, nur mit eingeschalteten Ortsnamen); für ältere Reisen holt sie es beim Start nach (letzte
12 Monate) oder sobald die Reise gewählt wird.
`reisekosten.csv` im Ausgabeordner wird nach jeder Änderung neu geschrieben. Nach jedem Nachtrag zu einer fertigen
Reise erneuert die Integration nach 30 s Statistik, Gesamtbild und `export.json` dieser Reise (Karte, Profil, GPX und
Rohdaten bleiben); die Statistik nennt dann „Reisekosten: Maut 83,30 € · Fähre 85,00 €“, „Kosten“ ist die Summe.

Die Mautbox rechnet meist erst im Folgemonat ab. **Maut offen** zählt deshalb die Reisen durch Mautländer ohne
Maut-Eintrag; eine Reise nur über Landstraßen lässt sich mit **Keine Maut** abhaken.

### Einträge ändern und löschen

Gespeicherte Fahrtenbuch-Einträge und Reisekosten lassen sich im Dashboard korrigieren, ohne IDs:

1. In der **Export-Auswahl** die Reise wählen. **Fahrtenbuch bearbeiten** zeigt dann alle Einträge dieser Reise und
   der Standzeit danach bis zur nächsten Reise, z. B. „27.09. 17:30 · Nachtrag · Irschenberg · 33768 km“;
   **Reisekosten Eintrag** die Kosten dieser Reise. Mit „Alle Exporte“ sind es die 30 neuesten Fahrtenbuch-Einträge
   bzw. die Kosten ohne Reise.
2. Einen Eintrag wählen: Das Formular zeigt seine Werte, beim Fahrtenbuch auch die Zeit in **Fahrtenbuch Nachtrag
   Zeit**. Ein offener Anlass wartet währenddessen.
3. Werte ändern und **Fahrtenbuch ändern** bzw. **Reisekosten ändern** drücken, oder **… löschen** (endgültig, kein
   Wiederherstellen). Danach springt die Auswahl auf „Neu“; „Verwerfen“ kehrt ohne Änderung zurück.

Solange ein Eintrag gewählt ist, sind „Fahrtenbuch speichern“, „Fahrtenbuch nachtragen“ und „Reisekosten speichern“
gesperrt, damit kein zweiter Eintrag entsteht. Eine neue Zeit verschiebt den Eintrag: Strecke und Höhenmeter
werden wie beim Nachtrag für die neue Zeit bestimmt, der Kilometerstand bleibt der im Formular. Danach werden CSV,
Kostensensoren, Ø-Verbrauch und die Exporte der betroffenen Reisen erneuert. Reisekosten behalten ihre Reise; einer
anderen Reise zuordnen geht mit der Aktion „Reisekosten ändern“.

**Leer heißt „nicht abgelesen“:** Ein leeres Feld (z. B. Gas 1 ohne Vorschlag) wird als „nicht abgelesen“
gespeichert, 0 % ist ein abgelesener Wert. Das Attribut `nicht_abgelesen` von **Fahrtenbuch Eintrag** nennt die
leeren Felder; mit **Fahrtenbuch Feld leeren** lässt sich ein Wert wieder auf „nicht abgelesen“ setzen.

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

Am 1. des Monats um 09:00 (Uhrzeit einstellbar) erinnert der Blueprint außerdem an offene Maut, solange „Maut offen“
über 0 ist, z. B. `2 Reisen ohne Maut: Ulm – Bozen, 22.11.2026 (AT, IT); …`. Tippen öffnet die Ansicht unter
**Ansicht beim Tippen** im Abschnitt Maut-Erinnerung (Standard `/dashboard-reiseverlauf/reisekosten`). Die
Erinnerung lässt sich abschalten.

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
      - type: markdown
        show_empty: false
        content: >-
          {% set leer = state_attr('sensor.wohnmobil_gps_fahrtenbuch_eintrag', 'nicht_abgelesen') %}
          {% if leer %}Nicht abgelesen: {{ leer | join(', ') }}{% endif %}
      - type: entities
        entities:
          - select.wohnmobil_gps_fahrtenbuch_bearbeiten
          - select.wohnmobil_gps_fahrtenbuch_zeitpunkt
          - datetime.wohnmobil_gps_fahrtenbuch_nachtrag_zeit
          - number.wohnmobil_gps_fahrtenbuch_kilometerstand
          - number.wohnmobil_gps_fahrtenbuch_kraftstoff
          - number.wohnmobil_gps_fahrtenbuch_gas_1
          - number.wohnmobil_gps_fahrtenbuch_gas_2
          - select.wohnmobil_gps_fahrtenbuch_feld_leeren
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
          - button.wohnmobil_gps_fahrtenbuch_nachtragen
          - button.wohnmobil_gps_fahrtenbuch_verwerfen
        visibility:
          - condition: state
            entity: select.wohnmobil_gps_fahrtenbuch_bearbeiten
            state: new
      - type: horizontal-stack
        cards:
          - type: button
            entity: button.wohnmobil_gps_fahrtenbuch_aendern
            name: Ändern
            tap_action:
              action: perform-action
              perform_action: button.press
              target:
                entity_id: button.wohnmobil_gps_fahrtenbuch_aendern
          - type: button
            entity: button.wohnmobil_gps_fahrtenbuch_loeschen
            name: Löschen
            tap_action:
              action: perform-action
              perform_action: button.press
              target:
                entity_id: button.wohnmobil_gps_fahrtenbuch_loeschen
              confirmation:
                text: Den unter „Fahrtenbuch bearbeiten“ gewählten Eintrag löschen?
          - type: button
            entity: button.wohnmobil_gps_fahrtenbuch_verwerfen
            name: Abbrechen
            tap_action:
              action: perform-action
              perform_action: button.press
              target:
                entity_id: button.wohnmobil_gps_fahrtenbuch_verwerfen
        visibility:
          - condition: state
            entity: select.wohnmobil_gps_fahrtenbuch_bearbeiten
            state_not: new
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
        entity: sensor.wohnmobil_gps_reisekosten_monat
      - type: tile
        entity: sensor.wohnmobil_gps_reisekosten_jahr
```

Der Pfad der Ansicht ist dann `/<Dashboard>/fahrtenbuch`, z. B. `/dashboard-reiseverlauf/fahrtenbuch`.

Eine eigene Ansicht für die Reisekosten (Pfad `reisekosten`, Ziel der Maut-Erinnerung):

```yaml
title: Reisekosten
path: reisekosten
icon: mdi:cash-multiple
type: sections
sections:
  - type: grid
    cards:
      - type: heading
        heading: Reisekosten eintragen
      - type: entities
        entities:
          - select.wohnmobil_gps_export_auswahl
          - select.wohnmobil_gps_reisekosten_eintrag
          - select.wohnmobil_gps_reisekosten_kategorie
          - select.wohnmobil_gps_reisekosten_land
          - number.wohnmobil_gps_reisekosten_betrag
          - text.wohnmobil_gps_reisekosten_notiz
          - date.wohnmobil_gps_reisekosten_datum
          - button.wohnmobil_gps_reisekosten_speichern
          - button.wohnmobil_gps_keine_maut
      - type: horizontal-stack
        cards:
          - type: button
            entity: button.wohnmobil_gps_reisekosten_aendern
            name: Ändern
            tap_action:
              action: perform-action
              perform_action: button.press
              target:
                entity_id: button.wohnmobil_gps_reisekosten_aendern
          - type: button
            entity: button.wohnmobil_gps_reisekosten_loeschen
            name: Löschen
            tap_action:
              action: perform-action
              perform_action: button.press
              target:
                entity_id: button.wohnmobil_gps_reisekosten_loeschen
              confirmation:
                text: Die unter „Reisekosten Eintrag“ gewählten Kosten löschen?
        visibility:
          - condition: state
            entity: select.wohnmobil_gps_reisekosten_eintrag
            state_not: new
      - type: markdown
        content: |
          {% set k = state_attr('select.wohnmobil_gps_export_auswahl', 'reisekosten') %}
          {% if k %}
          {% for e in k.eintraege %}
          - {{ e.kategorie }} {{ e.land or '' }} {{ '%.2f' | format(e.betrag) }} € {{ e.notiz or '' }}
          {% endfor %}
          **Summe {{ '%.2f' | format(k.summe) }} €**{{ ' · keine Maut' if k.keine_maut else '' }}
          {% endif %}
  - type: grid
    cards:
      - type: heading
        heading: Auswertung
      - type: tile
        entity: sensor.wohnmobil_gps_maut_offen
      - type: tile
        entity: sensor.wohnmobil_gps_reisekosten_monat
      - type: tile
        entity: sensor.wohnmobil_gps_reisekosten_jahr
```

## Touren

Eine Tour fasst mehrere Reisen und die Standzeiten dazwischen zusammen, z. B. Hinreise, eine Woche Campingplatz und
Rückreise, oder die Fahrt zur Werkstatt und zurück. Sie wird im Nachhinein angelegt und liest die gespeicherten
Punkte der Reisen, nicht den Recorder; auch Touren über mehr als 10 Tage sind daher vollständig. Manuelle Exporte
mit Rohdaten zählen als Reisen mit (z. B. Reisen von vor der Installation); überschneidet sich einer mit einer
automatisch erkannten Reise, gilt die automatische, damit keine Strecke doppelt zählt.

1. In der **Export-Auswahl** die erste Reise wählen. „Tour von“ zeigt dann deren Start, „Tour bis“ die aktuelle
   Zeit; beide lassen sich ändern.
2. Optional einen **Tour Titel** eintragen. Ohne Titel gilt der Vorschlag aus dem Standort mit den meisten Nächten
   und dem Zeitraum, z. B. „Camping Seeblick · 10.–17.10.2026“.
3. **Tour erstellen** drücken. Solange die Tour entsteht (je nach Länge bis zu einer Minute), ist „Tour in Arbeit“
   an, z. B. für einen Hinweis im Dashboard. Danach wechselt die Export-Auswahl auf die neue Tour (Kennzeichen „Tour“).

Inhalt:

- **Kennzahlen:** Strecke, Fahrzeit, Tage und Nächte, Höhenmeter, Kilometerstand von/bis, Länder.
- **Tagesübersicht:** Standort jeder Nacht ist der Platz um 3 Uhr; liegt er auf einem in OpenStreetMap eingetragenen
  Campingplatz oder Stellplatz, steht dessen Name da, sonst der Ort. Aufeinanderfolgende Nächte am selben Platz
  (bis 500 m Abstand) bilden eine Zeile mit km und Kosten dieser Tage; Ausflüge zurück zum Platz bleiben in der Zeile.
  Die CSV-Datei hat eine Zeile je Tag.
- **Kosten (bezahlt):** Tank- und Gasstopps mit Zeitpunkt in der Tour und alle Reisekosten, deren Datum in die Tour
  fällt, auch solche ohne Reise (z. B. Stellplatz während des Stands); je Kategorie, je Land und gesamt.
- **Verbrauch (geschätzt):** Strecke × Ø-Verbrauch, bewertet mit dem Ø-Literpreis der Tour (sonst dem letzten
  bekannten Preis); Gas aus den Füllständen am Anfang und Ende und den Gasstopps dazwischen, soweit bekannt. Ohne
  Ø-Verbrauch (weniger als zwei volle Tankfüllungen) entfällt die Angabe.

Ändern: Bei einer Tour in der Export-Auswahl zeigt das Formular ihren Zeitraum und Titel; nach Änderungen
**Tour aktualisieren** drücken (leerer Titel = Vorschlag). Standortnamen ändert die Aktion „Tour ändern“ mit der
Nacht aus dem Attribut `standorte` der Export-Auswahl, z. B.:

```yaml
action: reiseverlauftracker.tour_aendern
data:
  config_entry_id: <ID des Eintrags>
  standorte:
    - nacht: "2026-10-10"
      name: Camping Seeblick
```

Ändern sich Fahrtenbuch-Einträge oder Reisekosten im Zeitraum (z. B. Maut im Folgemonat), wird die Tour nach 30 s
neu erstellt, ohne die Karte erneut zu laden. Die Tour behält eine Kopie der Punkte ihrer Reisen; die Rohdaten der
Reisen dürfen danach aufgeräumt werden. „Exporte aufräumen“ löscht bei einer Tour nur deren eigene Dateien.

## Events

Für eigene Automationen:

| Event                             | Wann                                      | Daten                                                                                                                                                                                                                                                |
| --------------------------------- | ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `reiseverlauftracker_gestartet`   | Reise beginnt oder wird fortgesetzt       | `entry_id`, `start`, `resumed`, `startort`                                                                                                                                                                                                           |
| `reiseverlauftracker_beendet`     | Auswertung einer beendeten Reise fertig   | `entry_id`, `titel`, `start`, `ende`, `abfahrt`, `ankunft`, `strecke_km`, `fahrzeit_min`, `ordner`, `dateien`, `statistik`, `gesamtbild`, `gesamtbild_url`, `halte`, `fortgesetzt`, `fahrtenbuch`                                                    |
| `reiseverlauftracker_exportiert`  | Manueller Export fertig                   | wie `_beendet`, ohne `fortgesetzt`                                                                                                                                                                                                                   |
| `reiseverlauftracker_fahrtenbuch` | Fahrtenbuch-Anlass: Reisebeginn oder Halt | `entry_id`, `anlass` (`reisestart`, `halt`), `zeit`, `ort`, `reise_start`, `halt_start`, `vorschlag` (`kilometerstand`, `kraftstoff`, `gas_1`, `gas_2`)                                                                                              |
| `reiseverlauftracker_tour`        | Tour erstellt oder neu erstellt           | `entry_id`, `anlass` (`erstellt`, `aktualisiert`), `titel`, `start`, `ende`, `tage`, `naechte`, `strecke_km`, `fahrzeit_min`, `kosten`, `kostenaufstellung`, `verbrauch`, `reisen`, `ordner`, `dateien`, `statistik`, `gesamtbild`, `gesamtbild_url` |

`fahrtenbuch` enthält Kilometerstand von/bis, Liter, `kosten` (Diesel, Gas und Reisekosten), `reisekosten` je
Kategorie und den Verbrauch.

## Datenschutz

- Für die Karte lädt die Integration Kacheln von OpenStreetMap, einmal pro Reise.
- Für Ortsnamen und Länder schickt sie Positionen an Nominatim (OpenStreetMap): Start, Ende und Stopps einer Reise
  sowie für die Länder der Reise etwa alle 20 km einen Punkt der Strecke. Höchstens eine Anfrage je Sekunde. Die
  Ortsabfrage lässt sich in den Optionen abschalten; dann werden weder Orte noch Länder abgefragt.
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
