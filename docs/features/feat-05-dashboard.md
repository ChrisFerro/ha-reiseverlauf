# Feat-05: Dashboard und Migration

Stand: 17.11.2026, umgesetzt (Etappe 5, Migration erledigt am 09.10.2026 mit v0.1.3).
Übergeordnete Anforderungen und Entitäten: [ANFORDERUNGEN.md](../ANFORDERUNGEN.md).

## 1. Ziel

Das Dashboard `dashboard-reiseverlauf` zeigt die aktuelle und die letzte Reise, bietet den manuellen Export und
das Aufräumen an und nutzt dafür nur Entitäten und Dienste der Integration. Die alten Helfer und der
Hintergrunddienst entfallen.

## 2. Anforderungen

- Ansichten: „Aktuelle Reise“, „Letzte Reise“ (Ziel der Push-Nachricht), „Export“, „Aufräumen“, „Tracker“.
- Export-Formular über das Skript „Reise exportieren“ (keine Helfer).
- Downloads über den Medienbrowser (Ausgaben liegen geschützt in `/media`); seit Feat-07 alle Dateien über signierte
  Links im Dashboard (siehe [feat-07-downloads.md](feat-07-downloads.md)).
- Knöpfe „Reise jetzt beenden“ und „Reise starten / fortsetzen“.

## 3. Ausgangslage

### 3.1 Bisheriger Aufbau (abgelöst)

- `reference/ha_track.py`: Export als Kommandozeilenskript (Logik wiederverwendet, siehe [feat-03-export.md](feat-03-export.md)).
- `reference/track_daemon.py`: Hintergrunddienst in der SSH-App; reagierte auf Knopf-Helfer, startete
  das Skript, meldete `sensor.track_export`/`sensor.track_aufraeumen`. Enthielt das Aufräum-Verhalten
  (Auswahlliste der Exporte, Löschen nach Dateityp, Bereinigen der angezeigten Ergebnisse).
- Helfer: `input_datetime.track_start/track_ende`, `input_text.track_titel`,
  `input_number.track_skala/track_rand_min`, `input_button.track_generieren/track_aufraeumen`,
  `input_select.track_loeschen`, `input_boolean.track_del_gesamt/_karte/_profil/_gpx/_statistik`.
- Dashboard mit drei Ansichten: Export (Einstellungen, Generieren, Ergebnis mit Vorschau/Downloads/Statistik),
  Aufräumen, Tracker (Karte, 30 Tage Spur).
- Ausgaben in `/config/www/tracks` (erreichbar unter `/local/tracks/...`, ohne Anmeldung abrufbar).
- Router: Skript im Custom-Scripts-Block des RUTC50, das alle 5 s `gpsctl -a` liest, auf eine Nachkommastelle
  formatiert und per REST als `sensor.teltonika_gps_altitude` setzt. **Bleibt bestehen.**

### 3.2 Migration (erledigt 09.10.2026, v0.1.3)

Dashboard mit vier Ansichten auf die Entitäten der Integration und das Skript `script.reise_exportieren`
umgestellt, Push-Automation aus dem Blueprint eingerichtet, Startbefehle des Dienstes aus der SSH-App entfernt,
die 13 Helfer gelöscht, Skripte, Log und `/config/www/tracks` entfernt. Später kam die Ansicht „Aktuelle Reise“
dazu.

## 4. Offene Fragen

Keine.

## 5. Entscheidungen

1. ~~Export-Formular im Dashboard~~ – entschieden (09.10.2026, früher 9.17): Skript „Reise exportieren“ mit
   Feldern (Von, Bis, Titel, Skalierung, Rand), das `exportieren` aufruft; Formular über den Skript-Dialog,
   keine Helfer.
2. ~~Aufbau des Dashboards~~ – entschieden (09.10.2026, früher 9.18): Ansichten „Letzte Reise“ (neu, erste, Ziel
   der Push-Nachricht), „Export“ (Skript + Exportliste), „Aufräumen“ (Export-Auswahl, Knöpfe „Export löschen“ und
   „Nur Rohdaten löschen“), „Tracker“ (unverändert). Downloads über den Medienbrowser statt direkter Links.
3. ~~Knöpfe im Dashboard~~ – entschieden (09.10.2026, früher 9.21): „Reise jetzt beenden“ (während einer Reise)
   und „Reise starten / fortsetzen“ (ohne laufende Reise) in der neuen Ansicht „Aktuelle Reise“.
