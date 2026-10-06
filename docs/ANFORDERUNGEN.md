# Reiseverlauf – Anforderungen und Übergabe

Stand: 05.10.2026. Dieses Dokument fasst zusammen, was bisher als Skripte und Dashboard umgesetzt
wurde und was die Home-Assistant-Integration `reiseverlauftracker` daraus machen soll.

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
- Der Recorder behält standardmäßig nur 10 Tage. Die Auswertung muss direkt nach Reiseende laufen oder
  die Integration speichert die Punkte selbst (offene Entscheidung, siehe 9).

## 4. Reiseerkennung (neu)

Eingang: D+-Entität (Auswahl in der Einrichtung; `sensor` oder `binary_sensor`; „Ein“-Wert einstellbar,
Standard `ON`/`on`).

- **Start:** D+ geht auf „Ein“ und es läuft keine Reise.
- **Ende:** D+ ist länger als die **Verzögerung** (Standard 60 min, einstellbar) durchgehend „Aus“.
  Als Endzeit gilt der Moment, in dem D+ ausging (nicht der Ablauf der Verzögerung).
- Geht D+ vor Ablauf wieder an, gehört das zur selben Reise (Tankpause, Fähre unter der Verzögerung).
- **Fähre/Autozug:** Ändert sich die Position bei ausgeschaltetem D+ um mehr als die Mindestbewegung, läuft
  die Verzögerung ab der letzten Bewegung neu. Endet die Reise dabei, gilt die letzte Bewegung als Endzeit.
- **Zusammenführung:** Nach dem Ende bleibt die Reise ein **Zusammenführungsfenster** lang (Standard 6 h ab
  Endzeit, einstellbar, 0 = aus) wieder zu öffnen. Bewegung ohne D+ oder D+ „Ein“ in diesem Fenster setzt
  dieselbe Reise fort (z. B. lange Wartezeit am Hafen). Bei ihrem neuen Ende ersetzt ein neuer Export den
  alten und es gibt eine weitere Push-Nachricht. Erst nach Ablauf des Fensters ist die Reise endgültig.
- **Mindestbewegung:** Hat sich das Fahrzeug während der Reise nie weiter als 100 m (einstellbar) vom
  Startpunkt entfernt, gilt es nicht als Reise (kein Export, keine Push-Nachricht).
- **Persistenz:** Reisestart, letzter Aus-Zeitpunkt und laufender Countdown werden gespeichert (`Store`),
  damit ein HA-Neustart die Erkennung nicht zerstört. Beim Start: Countdown aus gespeicherten Zeiten
  neu berechnen; war D+ eingeschaltet und gibt es keinen gespeicherten Zustand, ist `last_changed` des
  D+-Sensors der Start.
- Bewegungsbeginn/-ende innerhalb der Reise werden wie bisher aus den Positionen bestimmt (siehe 5.2).

## 5. Auswertung (Export)

Die Logik existiert vollständig in `reference/ha_track.py` und soll als Bibliothek übernommen werden
(ohne die Kommandozeile, ohne HTTP-Zugriff auf HA; Daten kommen aus dem Recorder).

### 5.1 Eingaben

Zeitraum (von/bis), Titel (optional), Skala (1–4), Rand in Minuten für das Geschwindigkeitsdiagramm
(Standard 10), Schwellenwerte (siehe 7).

### 5.2 Verarbeitung

1. Positionen holen, Punkte mit `gps_accuracy` > 50 m verwerfen.
2. Geschwindigkeit und Höhe als Treppenfunktion zuordnen (letzter Wert gilt bis zur nächsten Änderung).
3. **Abfahrt/Ankunft erkennen:** Abfahrt = letzter Punkt, bevor die Position mehr als 100 m vom Startpunkt
   abweicht; Ankunft rückwärts analog. Alles darauf zuschneiden.
4. Punkte mit weniger als 15 m Abstand ausdünnen (Karte/GPX).
5. Statistik: Zeitraum (Abfahrt/Ankunft), Strecke (km), Fahrzeit (Abschnitte ab 3 km/h, Lücken über 5 min
   zählen nicht), Höchstgeschwindigkeit, Ø in Bewegung (Sensorwerte ab 3 km/h), Höhe min/max,
   Höhenmeter mit Hysterese (derzeit 5 m; evtl. zu niedrig, GPS-Höhe rauscht um mehrere Meter).

### 5.3 Ausgaben

GPX (mit Höhe, Geschwindigkeit in `<extensions><speed>` in m/s), Statistik (TXT), Kartenbild (PNG),
Profil-Diagramm (Höhe über Strecke, Geschwindigkeit über Zeit, mit Rand), **Gesamtbild** (Kopfzeile mit
Titel, Zeitraum und Kennzahlen, darunter Karte und Profile). Skalierung (`--skala`) wirkt auf alle Bilder.
Dateinamen: `<slug des Titels>` oder `track_<von>_<bis>`.

### 5.4 Technik

- Karte mit `staticmap` (OpenStreetMap-Kacheln, eigener User-Agent). Nur einzelne Läufe, kein Massenabruf.
- Schrift: DejaVu Sans wird mit der Integration ausgeliefert (`export/fonts/`, Lizenzdatei dabei).
- Diagramme und Gesamtbild nur mit **Pillow** (kein matplotlib: auf Python 3.14/musl gibt es keine
  Wheels, Kompilieren schlägt ohne Compiler fehl).
- Pillow-Standardschrift kennt kein „ö“, „–“, „Ø“: TrueType-Schrift suchen (DejaVu/Liberation), sonst
  Texte ohne Umlaute schreiben.
- Ganze Skalenfaktoren (2, 4) treffen die Kartenzoomstufen sauber; bei 1,5 füllt die Route das Bild anders.
- Bei Skala 2 braucht das Gesamtbild beim Zeichnen über 100 MB RAM: **nicht im Event-Loop**, sondern in
  einem Executor oder Unterprozess rendern. Fehlende Kacheln dürfen den Export nicht abbrechen.

## 6. Entitäten, Dienste, Events der Integration

Entitäten (Vorschlag):

- `binary_sensor.reise_aktiv`
- `sensor.reise_status` (`bereit`, `unterwegs`, `auswertung`, `fertig`, `fehler`) mit Attributen
- Laufende Reise: Start, Strecke, Fahrzeit; letzte Reise: Titel, Strecke, Dauer, Dateien (Attribute)

Dienste (Vorschlag):

- `reiseverlauftracker.exportieren` (von, bis, titel, skala, rand_min): manueller Export beliebiger Zeiträume
- `reiseverlauftracker.aufraeumen` (export, dateitypen): löscht Dateien eines Exports; Auswahl „alle Exporte“;
  nur im Ausgabeordner, nur bekannte Dateitypen (Gesamtbild, Karte, Profil, GPX, Statistik)
- optional: `reiseverlauftracker.reise_beenden` / `reise_starten` (manuell)

Events:

- `reiseverlauftracker_gestartet`
- `reiseverlauftracker_beendet` mit Daten: Titel, Start, Ende, Strecke_km, Fahrzeit, Dateiliste (Name, URL),
  Statistiktext, Pfad des Gesamtbilds

Push-Nachricht: **nicht** in der Integration, sondern als Automation auf `reiseverlauftracker_beendet`
(Empfänger/Text frei änderbar). Ein Automations-Blueprint soll mitgeliefert werden. Hinweis: Bildanhänge
in Push-Nachrichten brauchen eine vom Handy erreichbare URL.

## 7. Einstellungen (Config-/Options-Flow)

D+-Entität und „Ein“-Wert, Verzögerung (min), Zusammenführungsfenster (h), Mindestbewegung (m), Positions-Tracker, Geschwindigkeits-
und Höhensensor (Höhe optional), Ausgabeordner, Standard-Skala, Standard-Rand (min), Schwellen:
Stillstand 3 km/h, GPS-Genauigkeit 50 m, Punktabstand 15 m, Höhen-Hysterese (5 m, ggf. 15 m).

## 8. Bisheriger Aufbau (wird abgelöst)

- `reference/ha_track.py`: Export als Kommandozeilenskript (Logik wiederverwenden).
- `reference/track_daemon.py`: Hintergrunddienst in der SSH-App; reagiert auf Knopf-Helfer, startet
  das Skript, meldet `sensor.track_export`/`sensor.track_aufraeumen`. Enthält das Aufräum-Verhalten
  (Auswahlliste der Exporte, Löschen nach Dateityp, Bereinigen der angezeigten Ergebnisse).
- Helfer: `input_datetime.track_start/track_ende`, `input_text.track_titel`,
  `input_number.track_skala/track_rand_min`, `input_button.track_generieren/track_aufraeumen`,
  `input_select.track_loeschen`, `input_boolean.track_del_gesamt/_karte/_profil/_gpx/_statistik`.
- Dashboard `dashboard-reiseverlauf` mit drei Ansichten: Export (Einstellungen, Generieren, Ergebnis mit
  Vorschau/Downloads/Statistik), Aufräumen, Tracker (Karte, 30 Tage Spur).
- Router: Skript im Custom-Scripts-Block des RUTC50, das alle 5 s `gpsctl -a` liest, auf eine Nachkommastelle
  formatiert und per REST als `sensor.teltonika_gps_altitude` setzt. Bleibt zunächst extern bestehen.
- Ausgaben liegen in `/config/www/tracks` (erreichbar unter `/local/tracks/...`, ohne Anmeldung abrufbar).

Migration: Dashboard auf Dienste umstellen, Helfer und Hintergrunddienst entfernen.

## 9. Offene Entscheidungen

1. ~~Datenhaltung~~ – entschieden (06.10.2026): eigene Speicherung der Reisepunkte (Position, Genauigkeit,
   Geschwindigkeit, Höhe) pro Reise, aufbewahrt bis zum Löschen über `aufraeumen` (Dateityp „Rohdaten“).
2. Ausgabeort: `/config/www` (offen abrufbar) oder `/media` (geschützt, Zugriff über Anmeldung)?
3. ~~Sprachen~~ – entschieden (06.10.2026): Deutsch + Englisch für Oberfläche und Exporte (Sprache der HA-Instanz).
4. ~~Höhen-Hysterese~~ – vorläufig 5 m (06.10.2026): im Stand driftet die Höhe über 48 h um knapp 4 m.
   Nach der ersten echten Fahrt erneut prüfen.
5. ~~Reise mit langen Pausen~~ – entschieden (06.10.2026): automatische Zusammenführung, siehe 4.
6. Soll die Integration später auch die Höhe selbst vom Router holen (statt Skript)?

## 10. Empfohlene Reihenfolge

1. Reines Python-Modul `trip_detector` (Zustandsmaschine D+/Verzögerung/Mindestbewegung/Persistenz) mit Tests.
2. Exportbibliothek aus `reference/ha_track.py` (Statistik, GPX, Bilder) mit Tests auf Testdaten.
3. Integrationsrahmen: Config-Flow, Koordinator, Entitäten, Dienste, Events, Übersetzungen.
4. Automations-Blueprint für die Push-Nachricht, README (deutsch), HACS-Metadaten.
5. Migration des Dashboards und Abbau der alten Helfer/des Dienstes (erst nach Freigabe).
