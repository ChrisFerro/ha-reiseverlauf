# Feat-02: Halte und Live-Werte

Stand: 17.11.2026, umgesetzt (v0.1.4, Zusammenfassen seit v0.1.5).
Übergeordnete Anforderungen und Entitäten: [ANFORDERUNGEN.md](../ANFORDERUNGEN.md).

## 1. Ziel

Während einer Reise zeigt die Integration laufende Werte (Startort, Strecke, Fahrzeit, Pausenzeit, Ø) und
erfasst Halte mit Ort und Dauer. Halte sind die Grundlage für das [Fahrtenbuch](feat-06-fahrtenbuch.md).

## 2. Anforderungen

- **Halt:** D+ ist während einer Reise mindestens die Mindestdauer aus (Option unter Schwellenwerte, Standard
  5 min). Ein Halt hat Ort (Nominatim), von, bis und Dauer.
- **Zusammenfassen:** Geht D+ während eines Halts kurz an, ohne dass sich das Fahrzeug weiter als die
  Mindestbewegung entfernt (z. B. Tanken und Umparken), setzt das nächste D+-Aus denselben Halt fort.
- **Ankunft:** Das D+-Aus am Ende der Reise ist die Ankunft, kein Halt.
- **Anzeige:** live als Attribut `halte` der Pausenzeit, nach der Reise in Statistik, `export.json` und Event
  `reiseverlauftracker_beendet`.
- **Live-Werte:** Startort als Attribut `startort` am Reisebeginn und im Event `_gestartet`; Strecke, Fahrzeit,
  Pausenzeit (Zeit seit Start minus Fahrzeit, minütlich aktualisiert) und Ø in Bewegung (in Bewegung gefahrene
  Strecke ÷ Fahrzeit).
- **Erweiterbar:** Der Halt-Datensatz (`TripStop`) nimmt später Fahrtenbuch-Daten auf, ohne bestehende Reisen
  umzubauen.

## 3. Ausgangslage

- Halte und laufende Statistik in `coordinator/trip_log.py`, Anbindung in `coordinator/base.py`.
- Positionen innerhalb von 3 s werden zu einem Punkt zusammengefasst (siehe [feat-03-export.md](feat-03-export.md) 2.2), damit die
  Live-Strecke stimmt.
- Fahrt vom 31.10.2026: Tanken mit zweimal Umparken (D+-Aus von 4, 4 und 7 min am selben Ort) ergab bis v0.1.4 nur
  einen Halt von 7 min, seit v0.1.5 einen Halt von 20 min.
- Ein manueller Export ermittelt keine Halte (D+ wird aus dem Recorder nicht ausgewertet).
- Die einzelnen D+-Aus-Phasen eines Halts werden nicht gespeichert (siehe [feat-06-fahrtenbuch.md](feat-06-fahrtenbuch.md) 3).

## 4. Offene Fragen

1. Sollen auch manuelle Exporte Halte aus der D+-History des Recorders ermitteln?

## 5. Entscheidungen

1. ~~Live-Werte der laufenden Reise~~ – entschieden (09.10.2026, früher 9.19): Startort (Nominatim, einmal bei
   Reisebeginn) als Attribut `startort` am Reisebeginn und im Event `_gestartet`; neue Sensoren Pausenzeit (Zeit
   seit Start minus Fahrzeit, minütlich aktualisiert) und Ø in Bewegung (in Bewegung gefahrene Strecke ÷ Fahrzeit).
2. ~~Halte~~ – entschieden (09.10.2026, früher 9.20): D+ während einer Reise mindestens die Mindestdauer aus = Halt
   mit Ort (Nominatim), von, bis, Dauer. Live als Attribut der Pausenzeit, nach der Reise in Statistik,
   `export.json` und Event `_beendet`. Ein Halt ist so aufgebaut, dass später Fahrtenbuch-Daten daran hängen können.
3. ~~Halte zusammenfassen~~ – entschieden (17.11.2026): Geht D+ während eines Halts kurz an, ohne dass sich das
   Fahrzeug weiter als die Mindestbewegung entfernt, setzt das nächste D+-Aus denselben Halt fort.
