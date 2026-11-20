# Reiseverlauf – Anforderungen und Übergabe

Stand: 20.11.2026. Übersicht über die Home-Assistant-Integration `reiseverlauftracker`: Ziel, Umgebung,
Datenquellen, Entitäten und Einstellungen. Die einzelnen Features stehen in eigenen Dokumenten (siehe 11).

## 1. Ziel

Eine Custom-Integration (HACS, öffentliches Repository `ha-reiseverlauf`) für ein Wohnmobil:

1. Sie erkennt **automatisch**, wann eine Reise beginnt und endet (über das D+-Signal).
2. Nach dem Ende erstellt sie **automatisch** Statistik, Kartenbild, Höhen-/Geschwindigkeitsprofil,
   GPX und ein Gesamtbild (Verwendung: Fotobuch).
3. Sie löst ein **Event** aus, auf das eine normale Automation eine **Push-Nachricht** sendet.
4. Alles lässt sich über die Oberfläche einstellen (Config-/Options-Flow) und über **Dienste** bedienen.
   Die bisherigen Hilfsmittel (Helfer, Hintergrunddienst in der SSH-App, REST-Sensoren) entfallen.

Warum eine Integration statt Skripten: bessere Wartbarkeit, saubere Entitäten mit Zustandsspeicherung,
keine Abhängigkeit von der SSH-App, Einstellungen in der Oberfläche statt im Code.

## 2. Umgebung

- Home Assistant OS, Core 2026.9.x (Python 3.14, Alpine/musl).
- Fahrzeug-Router: Teltonika RUTC50 (GPS-Daten per Modbus in HA; Höhe per Router-Skript, siehe 3).
- Entwicklungsvorlage: `jpawlowski/hacs.integration_blueprint` (HA 2026.8+, Codespaces/Devcontainer).
- Integrationsdomain: `reiseverlauftracker`. Code-Bezeichner englisch, Oberflächentexte deutsch (+ englisch).

## 3. Vorhandene Entitäten und Datenquellen (Ist-Zustand)

| Zweck           | Entität                         | Hinweise                                                                                                                        |
| --------------- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Position        | `device_tracker.arto88b_gps`    | Template-Tracker aus `sensor.teltonika_gps_lat/_lon`; `gps_accuracy` fest 10                                                    |
| Geschwindigkeit | `sensor.teltonika_gps_speed`    | Modbus, Adresse 179, `float32`, km/h                                                                                            |
| Höhe            | `sensor.teltonika_gps_altitude` | Wird alle 5 s per REST vom Router gesetzt (`gpsctl -a`), Meter, 1 Nachkommastelle. Kein Registry-Eintrag, kein Zustands-Restore |
| D+              | `sensor.dplus_i8`               | **Textsensor** mit `ON`/`OFF` (kein `binary_sensor`)                                                                            |

Wichtig:

- D+ wechselt bei jedem HA-Neustart kurz auf `unavailable`/`unknown`. Diese Zustände dürfen nicht als
  „Aus“ gewertet werden.
- Der Geschwindigkeits-Sensor war bis zum 04.10.2026 falsch als Ganzzahl konfiguriert. Ältere History-Werte
  liegen als rohe Float-Bits vor (z. B. `1118656744` = 86,67 km/h). Beim Lesen alter Daten:
  Werte über 100000 als Big-Endian-`float32` zurückrechnen (`struct.unpack(">f", struct.pack(">I", n))`).
- Höhendaten gibt es erst seit dem 04.10.2026.
- Der Template-Tracker ändert Breite und Länge nacheinander (etwa 1 s Abstand). Jede Änderung ergibt einen
  Zustand, der erste mit neuer Breite und alter Länge. Die Integration fasst Positionen innerhalb von 3 s zu
  einem Punkt zusammen; sonst ergibt sich eine Treppenspur (31.10.2026: 109 km statt 84 km laut Tacho).
- Der Recorder behält standardmäßig nur 10 Tage. Die Integration speichert die Reisepunkte daher selbst
  (siehe [features/feat-03-export.md](features/feat-03-export.md) 5.1).

## 4. Reiseerkennung

Siehe [features/feat-01-reiseerkennung.md](features/feat-01-reiseerkennung.md).

## 5. Auswertung (Export)

Siehe [features/feat-03-export.md](features/feat-03-export.md).

## 6. Entitäten, Dienste, Events der Integration

Entitäten (Entity-IDs: `<Gerät>_<Name>`, Gerät = Name des Eintrags, z. B. `sensor.arto88b_gps_reisestatus`):

- `binary_sensor.…_reise_aktiv`
- `sensor.…_reisestatus` (`bereit`, `unterwegs`, `pause`, `auswertung`, `zusammenfuehrbar`, `fehler`, siehe [Reiseerkennung](features/feat-01-reiseerkennung.md) 5.3)
- Laufende Reise: `sensor.…_reisebeginn` (Attribut `startort`), `…_strecke_laufende_reise`, `…_fahrzeit_laufende_reise`,
  `…_pausenzeit_laufende_reise` (Attribut `halte`), `…_durchschnitt_laufende_reise` (siehe [Halte](features/feat-02-halte.md))
- Letzte Reise: `sensor.…_letzte_reise` (Titel; Attribute `dateien`, `downloads`, `statistik`, `ordner`, `start`),
  `…_letzte_reise_strecke`, `…_fahrzeit`, `…_dauer`, `…_ende`; `image.…_letzte_reise_gesamtbild` (siehe 9.11)
- `select.…_export_auswahl` (siehe [Export](features/feat-03-export.md) 2.4); `downloads` an Letzte Reise, Export-Auswahl und
  Fahrtenbuch-Eintrag: signierte Links (siehe [Downloads](features/feat-07-downloads.md))
- Fahrtenbuch-Formular: `number.…_fahrtenbuch_*` (Kilometerstand, Kraftstoff, Gas 1/2, Diesel und Gas getankt und
  Betrag), `button.…_fahrtenbuch_speichern`/`_verwerfen`, `sensor.…_fahrtenbuch_eintrag` (siehe
  [Fahrtenbuch](features/feat-06-fahrtenbuch.md) 6.2)
- Fahrtenbuch-Auswertung: `sensor.…_kilometerstand`, `…_kraftstoff`, `…_gas_1`, `…_gas_2`, `…_durchschnittsverbrauch`,
  `…_tank_und_gaskosten_monat`, `…_tank_und_gaskosten_jahr` (siehe [Fahrtenbuch](features/feat-06-fahrtenbuch.md) 6.5),
  `…_heizung_im_stand_abgelesen` (siehe [Verbrauchsmodell](features/feat-08-verbrauchsmodell.md) 5.5)

Dienste (alle mit Pflichtfeld `config_entry_id`):

- `reiseverlauftracker.exportieren` (von, bis, titel, skala, rand_min): manueller Export beliebiger Zeiträume aus
  dem Recorder in einen eigenen Ordner `<Start>-<Ende>`, inkl. Rohdaten
- `reiseverlauftracker.aufraeumen` (export, dateitypen): löscht Dateien eines Exports oder aller Exporte (`all`);
  ohne `export` gilt die Export-Auswahl; nur im Ausgabeordner, nur Dateien aus `export.json` (Gesamtbild, Karte,
  Profil, GPX, Statistik, Rohdaten)
- `reiseverlauftracker.reise_starten` / `reise_beenden` (manuell, siehe [Reiseerkennung](features/feat-01-reiseerkennung.md) 5.2)
- `reiseverlauftracker.fahrtenbuch_eintragen` / `_speichern` / `_aendern` / `_loeschen` / `_csv` (siehe [Fahrtenbuch](features/feat-06-fahrtenbuch.md) 6.4)

Events:

- `reiseverlauftracker_gestartet`
- `reiseverlauftracker_exportiert` nach manuellem Export (Daten wie `_beendet`, siehe [Export](features/feat-03-export.md) 5.5)
- `reiseverlauftracker_beendet` mit Daten: Titel, Start, Ende, Strecke_km, Fahrzeit, Dateiliste (Name, URL),
  Statistiktext, Pfad des Gesamtbilds, Halte, Fahrtenbuch (Kilometerstand, Liter, Kosten, Verbrauch)
- `reiseverlauftracker_fahrtenbuch` bei Reisestart und bei jedem Halt ab der Mindestdauer: Anlass, Zeit, Ort,
  Reise- und Halt-Start, Vorschlag (Kilometerstand, Kraftstoff, Gas 1, Gas 2), siehe [Fahrtenbuch](features/feat-06-fahrtenbuch.md) 6.3

Push-Nachricht: **nicht** in der Integration, sondern als Automation aus einem mitgelieferten Blueprint, siehe
[features/feat-04-push-benachrichtigung.md](features/feat-04-push-benachrichtigung.md); die Fahrtenbuch-Erinnerung hat einen eigenen
Blueprint (siehe [Fahrtenbuch](features/feat-06-fahrtenbuch.md) 5.9).

## 7. Einstellungen (Config-/Options-Flow)

D+-Entität und „Ein“-Wert, Verzögerung (min), Zusammenführungsfenster (h), Mindestbewegung (m), Positions-Tracker, Geschwindigkeits-
und Höhensensor (Höhe optional), Ausgabeordner, Standard-Skala, Standard-Rand (min), Schwellen:
Stillstand 3 km/h, GPS-Genauigkeit 50 m, Punktabstand 15 m, Höhen-Hysterese 5 m, Mindestdauer eines Halts 5 min.
Fahrtenbuch: Tankgröße (Liter, Standard 90, siehe [Fahrtenbuch](features/feat-06-fahrtenbuch.md) 5.8).

## 8. Bisheriger Aufbau (abgelöst)

Skripte, Helfer, Hintergrunddienst und das alte Dashboard sowie die Migration (erledigt am 09.10.2026, v0.1.3)
stehen in [features/feat-05-dashboard.md](features/feat-05-dashboard.md) 3. Das Router-Skript für die Höhe bleibt bestehen.

## 9. Offene Entscheidungen

Hier stehen nur noch Entscheidungen, die alle Features betreffen. Die übrigen sind mit Verweis auf ihre bisherige Nummer (z. B. „früher 9.8“) in
das Dokument ihres Features umgezogen (Abschnitt 5 „Entscheidungen“ dort).

- **9.3** ~~Sprachen~~ – entschieden (06.10.2026): Deutsch + Englisch für Oberfläche und Exporte (Sprache der HA-Instanz).
- **9.6** Soll die Integration später auch die Höhe selbst vom Router holen (statt Skript)?
- **9.11** ~~Entitäten~~ – entschieden (09.10.2026): eigene Entitäten je Wert (siehe 6) statt Attribute,
  dazu eine Bild-Entität für das Gesamtbild (geschützte Dashboard-Vorschau trotz `/media`).
  Strecke ohne Langzeitstatistik (Wert pro Reise); Gesamtkilometer ggf. später.
- **9.16** ~~Sprache der README~~ – entschieden (09.10.2026): `README.md` auf Deutsch und `README.en.md` auf Englisch.

| Frühere Nummer                | Thema                                                   | Jetzt in                                                                      |
| ----------------------------- | ------------------------------------------------------- | ----------------------------------------------------------------------------- |
| 9.1, 9.2, 9.4, 9.7, 9.9, 9.12 | Datenhaltung, Ausgabeort, Höhe, Titel, Event, Aufräumen | [feat-03-export.md](features/feat-03-export.md)                               |
| 9.5, 9.8, 9.10                | Pausen, manueller Start/Ende, Statuswerte               | [feat-01-reiseerkennung.md](features/feat-01-reiseerkennung.md)               |
| 9.13, 9.14, 9.15              | Inhalt, Empfänger, weitere Benachrichtigungen           | [feat-04-push-benachrichtigung.md](features/feat-04-push-benachrichtigung.md) |
| 9.17, 9.18, 9.21              | Export-Formular, Aufbau, Knöpfe                         | [feat-05-dashboard.md](features/feat-05-dashboard.md)                         |
| 9.19, 9.20                    | Live-Werte, Halte                                       | [feat-02-halte.md](features/feat-02-halte.md)                                 |
| 9.22                          | Fahrtenbuch (entschieden)                               | [feat-06-fahrtenbuch.md](features/feat-06-fahrtenbuch.md)                     |

## 10. Empfohlene Reihenfolge

1. Reines Python-Modul `trip_detector` (Zustandsmaschine D+/Verzögerung/Mindestbewegung/Persistenz) mit Tests.
2. Exportbibliothek aus `reference/ha_track.py` (Statistik, GPX, Bilder) mit Tests auf Testdaten.
3. Integrationsrahmen: Config-Flow, Koordinator, Entitäten, Dienste, Events, Übersetzungen.
4. Automations-Blueprint für die Push-Nachricht, README (deutsch), HACS-Metadaten.
5. Migration des Dashboards und Abbau der alten Helfer/des Dienstes (erst nach Freigabe). – erledigt 09.10.2026
6. Fahrtenbuch (siehe [features/feat-06-fahrtenbuch.md](features/feat-06-fahrtenbuch.md)). – umgesetzt 18.11.2026
7. Geschützter Download aller Dateien (siehe [features/feat-07-downloads.md](features/feat-07-downloads.md)). – umgesetzt 19.11.2026
8. Verbrauchsmodell mit Höhenmetern und Heizung im Stand (siehe [features/feat-08-verbrauchsmodell.md](features/feat-08-verbrauchsmodell.md)),
   erst wenn genug Fahrtenbuch-Daten vorliegen.

## 11. Feature-Dokumente

Jedes Feature hat ein eigenes Dokument in [`docs/features/`](features/) mit Ziel, Anforderungen, Ausgangslage,
offenen Fragen und Entscheidungen. Dieses Dokument bleibt die Übersicht und enthält, was alle Features betrifft
(Umgebung, Datenquellen, Entitäten, Einstellungen).

Die Dokumente sind fortlaufend nummeriert: Dateiname `feat-<NN>-<name>.md`, Überschrift `Feat-<NN>: <Name>`. Ein
neues Feature bekommt die nächste freie Nummer; Nummern werden nicht neu vergeben.

| Nr.     | Feature                 | Dokument                                                                      | Etappe | Stand                     |
| ------- | ----------------------- | ----------------------------------------------------------------------------- | ------ | ------------------------- |
| Feat-01 | Reiseerkennung          | [feat-01-reiseerkennung.md](features/feat-01-reiseerkennung.md)               | 1, 3   | umgesetzt                 |
| Feat-02 | Halte und Live-Werte    | [feat-02-halte.md](features/feat-02-halte.md)                                 | 3      | umgesetzt, 1 Frage offen  |
| Feat-03 | Export und Verwaltung   | [feat-03-export.md](features/feat-03-export.md)                               | 2, 3   | umgesetzt                 |
| Feat-04 | Push-Benachrichtigung   | [feat-04-push-benachrichtigung.md](features/feat-04-push-benachrichtigung.md) | 4      | umgesetzt                 |
| Feat-05 | Dashboard und Migration | [feat-05-dashboard.md](features/feat-05-dashboard.md)                         | 5      | umgesetzt                 |
| Feat-06 | Fahrtenbuch             | [feat-06-fahrtenbuch.md](features/feat-06-fahrtenbuch.md)                     | 6      | umgesetzt                 |
| Feat-07 | Geschützter Download    | [feat-07-downloads.md](features/feat-07-downloads.md)                         | 7      | umgesetzt                 |
| Feat-08 | Verbrauchsmodell        | [feat-08-verbrauchsmodell.md](features/feat-08-verbrauchsmodell.md)           | 8      | Zwischenschritt umgesetzt |
