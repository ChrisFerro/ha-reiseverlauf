# Feat-04: Push-Benachrichtigung

Stand: 17.11.2026, umgesetzt (Etappe 4, live seit 09.10.2026).
Übergeordnete Anforderungen und Events: [ANFORDERUNGEN.md](../ANFORDERUNGEN.md).

## 1. Ziel

Nach einer Reise bekommen die Mitreisenden eine Push-Nachricht aufs Handy. Die Nachricht sendet **nicht** die
Integration, sondern eine normale Automation aus einem mitgelieferten Automations-Blueprint (Empfänger und Text
frei änderbar).

## 2. Anforderungen

- Auslöser: Event `reiseverlauftracker_beendet` (Titel, Start, Ende, Strecke_km, Fahrzeit, Dateiliste mit Name und
  URL, Statistiktext, Pfad des Gesamtbilds, Halte); optional `_gestartet` und `_exportiert`.
- Titel „Reise beendet: …“ mit dem Reisetitel, bei Fortsetzung „Reise aktualisiert: …“; Text mit Strecke,
  Fahrzeit und Abfahrt–Ankunft.
- Tippen öffnet eine im Blueprint einstellbare Dashboard-Ansicht.
- Empfänger: ein oder mehrere Geräte der Companion-App.
- Hinweis: Bildanhänge brauchen eine vom Handy erreichbare URL; `/media/local/...` direkt geöffnet ergibt 401.

## 3. Ausgangslage

- Blueprint im Repository, Tests in `tests/blueprints/`.
- Live als Automation aus dem Blueprint eingerichtet (09.10.2026).

## 4. Offene Fragen

Keine.

## 5. Entscheidungen

1. ~~Inhalt der Push-Nachricht~~ – entschieden (09.10.2026, früher 9.13): Titel „Reise beendet: …“ mit dem
   Reisetitel (bei Fortsetzung „Reise aktualisiert: …“), Text mit Strecke, Fahrzeit und Abfahrt–Ankunft.
   Geändert (09.10.2026) nach dem Live-Test mit iPhone: kein Bild in der Nachricht (iOS zeigt das große
   Gesamtbild nicht an), Tippen öffnet eine im Blueprint einstellbare Dashboard-Ansicht (`/media/local/...`
   direkt geöffnet ergibt 401).
2. ~~Empfänger~~ – entschieden (09.10.2026, früher 9.14): Auswahl eines oder mehrerer Geräte der Companion-App im
   Blueprint (keine freien Notify-Dienste), damit Bild und Tippen-Aktion sicher funktionieren.
3. ~~Weitere Benachrichtigungen~~ – entschieden (09.10.2026, früher 9.15): Schalter „Bei Reisebeginn“ (Standard
   an, nicht bei Fortsetzung) und „Nach manuellem Export“ (Standard aus) im Blueprint.
