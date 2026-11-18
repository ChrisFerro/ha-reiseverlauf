# Feat-01: Reiseerkennung

Stand: 17.11.2026, umgesetzt (Etappe 1 und 3).
Übergeordnete Anforderungen, Datenquellen und Entitäten: [ANFORDERUNGEN.md](../ANFORDERUNGEN.md).

## 1. Ziel

Die Integration erkennt **automatisch** über das D+-Signal, wann eine Reise beginnt und endet, und stößt danach den
[Export](feat-03-export.md) an. Halte innerhalb einer Reise beschreibt [feat-02-halte.md](feat-02-halte.md).

## 2. Anforderungen

Eingang: D+-Entität (Auswahl in der Einrichtung; `sensor` oder `binary_sensor`; „Ein“-Wert einstellbar,
Standard `ON`/`on`). `unavailable`/`unknown` (z. B. bei jedem HA-Neustart) gelten nicht als „Aus“.

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
- Bewegungsbeginn/-ende innerhalb der Reise werden aus den Positionen bestimmt (siehe [feat-03-export.md](feat-03-export.md) 2.2).

## 3. Ausgangslage

- Zustandsmaschine `coordinator/trip_detector.py` ohne HA-Abhängigkeiten, Anbindung in `coordinator/base.py`.
- Erste echte Fahrt am 31.10.2026: Start, Ende, kurzes D+-Aus vor dem Ende und Zusammenführungsfenster wurden
  richtig erkannt.

## 4. Offene Fragen

Keine.

## 5. Entscheidungen

1. ~~Reise mit langen Pausen~~ – entschieden (06.10.2026, früher 9.5): automatische Zusammenführung, siehe 2.
2. ~~Manueller Start/Ende~~ – entschieden (09.10.2026, früher 9.8): beide Dienste. `reise_beenden` beendet sofort
   (Endzeit = Aufruf, Mindestbewegung gilt weiter), danach Export und Zusammenführungsfenster wie beim
   automatischen Ende. Geht D+ im Fenster wieder auf „Ein“ (Wechsel Aus → Ein), wird zusammengeführt.
   `reise_starten` startet ohne D+; ohne D+ läuft die Verzögerung ab Start bzw. letzter Bewegung.
3. ~~Statuswerte~~ – entschieden (09.10.2026, früher 9.10): `bereit`, `unterwegs`, `pause` (D+ aus, Verzögerung
   läuft; Attribut voraussichtliches Ende), `auswertung`, `zusammenfuehrbar` (Attribut Fensterende),
   `fehler`. Nach Fensterablauf (oder Fenster 0) wieder `bereit`; letzte Reise bleibt in eigenen
   Entitäten/Attributen. Anzeige über Übersetzungen (z. B. „Pause“, „Fortsetzbar“).
