# Feat-03: Export und Verwaltung

Stand: 17.11.2026, umgesetzt (Etappe 2 und 3).
Übergeordnete Anforderungen, Datenquellen und Einstellungen: [ANFORDERUNGEN.md](../ANFORDERUNGEN.md).

## 1. Ziel

Nach jeder Reise (automatisch, siehe [feat-01-reiseerkennung.md](feat-01-reiseerkennung.md)) oder auf Anfrage (Dienst
`exportieren`) entstehen Statistik, Kartenbild, Höhen-/Geschwindigkeitsprofil, GPX und ein Gesamtbild
(Verwendung: Fotobuch). Exporte lassen sich auswählen und aufräumen.

Die Logik stammt aus `reference/ha_track.py` und ist als Bibliothek `export/` übernommen (ohne Kommandozeile,
ohne HTTP-Zugriff auf HA; Daten aus den eigenen Reisepunkten oder dem Recorder).

## 2. Anforderungen

### 2.1 Eingaben

Zeitraum (von/bis), Titel (optional), Skala (1–4), Rand in Minuten für das Geschwindigkeitsdiagramm
(Standard 10), Schwellenwerte (siehe [ANFORDERUNGEN.md](../ANFORDERUNGEN.md) 7).

### 2.2 Verarbeitung

1. Positionen holen, Punkte mit `gps_accuracy` > 50 m verwerfen.
2. Positionen innerhalb von 3 s zu einem Punkt zusammenfassen (der Tracker meldet Breite und Länge nacheinander,
   siehe [ANFORDERUNGEN.md](../ANFORDERUNGEN.md) 3).
3. Geschwindigkeit und Höhe als Treppenfunktion zuordnen (letzter Wert gilt bis zur nächsten Änderung).
4. **Abfahrt/Ankunft erkennen:** Abfahrt = letzter Punkt, bevor die Position mehr als 100 m vom Startpunkt
   abweicht; Ankunft rückwärts analog. Alles darauf zuschneiden.
5. Punkte mit weniger als 15 m Abstand ausdünnen (Karte/GPX).
6. Statistik: Zeitraum (Abfahrt/Ankunft), Strecke (km), Fahrzeit (Abschnitte ab 3 km/h, Lücken über 5 min
   zählen nicht), Höchstgeschwindigkeit, Ø in Bewegung (Sensorwerte ab 3 km/h), Höhe min/max,
   Höhenmeter mit Hysterese (5 m), Halte (siehe [feat-02-halte.md](feat-02-halte.md)).

### 2.3 Ausgaben

GPX (mit Höhe, Geschwindigkeit in `<extensions><speed>` in m/s), Statistik (TXT), Kartenbild (PNG),
Profil-Diagramm (Höhe über Strecke, Geschwindigkeit über Zeit, mit Rand), **Gesamtbild** (Kopfzeile mit
Titel, Zeitraum und Kennzahlen, darunter Karte und Profile), Rohdaten (JSON) und `export.json`.
Die Skalierung wirkt auf alle Bilder. Dateinamen: `<slug des Titels>` oder `track_<von>_<bis>`.

### 2.4 Verwaltung

- `select.…_export_auswahl`: alle Exporte und „Alle Exporte“, aktualisiert nach Export/Löschen.
  - Kennzeichen im Eintrag (seit 23.11.2026): Touren „Tour“, manuelle Exporte „Manuell“ (englisch „Manual“),
    automatisch erkannte Reisen keines, z. B. `31.10.26 14:00 · Manuell · Fahrt Pullach zum…`.
  - Attribut `exporte`: alle Exporte mit `auswahl` (Eintrag der Auswahl), `ordner`, `art` (`reise`/`tour`),
    `automatisch`, `start`, `ende`, `strecke_km` und `rohdaten` (ja/nein), damit ein Dashboard manuelle und automatische
    Exporte unterscheiden und beim Aufräumen anzeigen kann, welche noch Rohdaten haben.
- Dienst `aufraeumen` (export, dateitypen): löscht Dateien eines Exports oder aller Exporte; ohne `export` gilt
  die Export-Auswahl; nur im Ausgabeordner, nur Dateien aus `export.json`.
- Event `reiseverlauftracker_exportiert` nach manuellem Export, `reiseverlauftracker_beendet` nach einer Reise.

### 2.5 Technik

- Karte mit `staticmap` (OpenStreetMap-Kacheln, eigener User-Agent). Nur einzelne Läufe, kein Massenabruf.
- Schrift: DejaVu Sans wird mit der Integration ausgeliefert (`export/fonts/`, Lizenzdatei dabei).
- Diagramme und Gesamtbild nur mit **Pillow** (kein matplotlib: auf Python 3.14/musl gibt es keine
  Wheels, Kompilieren schlägt ohne Compiler fehl).
- Pillow-Standardschrift kennt kein „ö“, „–“, „Ø“: TrueType-Schrift suchen (DejaVu/Liberation), sonst
  Texte ohne Umlaute schreiben.
- Ganze Skalenfaktoren (2, 4) treffen die Kartenzoomstufen sauber; bei 1,5 füllt die Route das Bild anders.
- Bei Skala 2 braucht das Gesamtbild beim Zeichnen über 100 MB RAM: **nicht im Event-Loop**, sondern in
  einem Executor oder Unterprozess rendern. Fehlende Kacheln dürfen den Export nicht abbrechen.

## 3. Ausgangslage

- Fahrt vom 31.10.2026: Strecke bis v0.1.4 109,2 km, seit v0.1.5 84,2 km (Tacho 84 km; OSRM-Abgleich 84,0 km).
- Höhe geprüft gegen EU-DEM (25 m): GPS-Höhe weicht im Mittel 1,4 m ab (80 % innerhalb ±6 m).
- Ein manueller Export enthält keine Halte (siehe [feat-02-halte.md](feat-02-halte.md) 4).

## 4. Offene Fragen

Keine.

## 5. Entscheidungen

1. ~~Datenhaltung~~ – entschieden (06.10.2026, früher 9.1): eigene Speicherung der Reisepunkte (Position,
   Genauigkeit, Geschwindigkeit, Höhe) pro Reise, aufbewahrt bis zum Löschen über `aufraeumen` (Dateityp
   „Rohdaten“).
2. ~~Ausgabeort~~ – entschieden (09.10.2026, früher 9.2): `/media` (geschützt, Zugriff nur mit Anmeldung über die
   Medienquelle `/media/local/...`). Standard-Ausgabeordner `reiseverlauf` im lokalen Medienordner von HA,
   in der Einrichtung änderbar. `/config/www` wird nicht mehr verwendet.
3. ~~Höhen-Hysterese~~ – entschieden (17.11.2026, früher 9.4): bleibt 5 m. Geprüft an der Fahrt vom 31.10.2026
   gegen EU-DEM (25 m); die Summe der Höhenmeter hängt vor allem von der Glättung ab, 5 m liegen im plausiblen
   Bereich.
4. ~~Titel automatisch erkannter Reisen~~ – entschieden (09.10.2026, früher 9.7): einstellbar „nur Datum“,
   „nur Ort“ oder „Datum und Ort“ (Standard). Ortsnamen für Start und Ende per Nominatim (OpenStreetMap,
   eigener User-Agent, Sprache der HA-Instanz, Ebene Stadt/Ort/Dorf), keine HA-Zonen. Ohne Ortsname:
   nur Datum (auch bei „nur Ort“, damit der Titel nie leer ist).
5. ~~Event bei manuellem Export~~ – entschieden (09.10.2026, früher 9.9): `exportieren` löst
   `reiseverlauftracker_exportiert` aus (Daten wie `_beendet`), nicht `_beendet`. Der Push-Blueprint
   reagiert standardmäßig nur auf `_beendet`.
6. ~~Auswahl beim Aufräumen~~ – entschieden (09.10.2026, früher 9.12): `select.export_auswahl` (alle Exporte +
   „Alle Exporte“, aktualisiert nach Export/Löschen) und Dienst `aufraeumen` (Export, Dateitypen als
   Mehrfachauswahl inkl. Rohdaten). Keine Schalter-Entitäten für Dateitypen.
