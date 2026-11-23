# Feat-12: Kartensymbole

Stand: 23.11.2026, alle Fragen geklärt (Abschnitt 5); Entwurf der Umsetzung folgt (Abschnitt 6).
Übergeordnete Anforderungen und Entitäten: [ANFORDERUNGEN.md](../ANFORDERUNGEN.md). Grundlage:
[Halte](feat-02-halte.md), [Export](feat-03-export.md), [Fahrtenbuch](feat-06-fahrtenbuch.md),
[Nachträge](feat-09-nachtraege.md), [Tour](feat-10-tour.md).

## 1. Ziel

Die Karten (Kartenbild und Gesamtbild einer Reise und einer Tour) zeigen mit Symbolen, was unterwegs passiert ist:
wo eine Pause war, wo Diesel getankt wurde, wo Gas nachgefüllt wurde, wo das Fahrzeug auf einem Stellplatz oder
Campingplatz stand und weitere Ereignisse. So lässt sich die Reise auf einen Blick nachvollziehen (auch im Fotobuch).

## 2. Anforderungen

- **Symbole auf der Karte** für:
  - **Pause / Halt** (D+ während der Reise mindestens die Mindestdauer aus, [Halte](feat-02-halte.md)).
  - **Tankstopp Diesel** (Fahrtenbuch-Eintrag mit getankten Litern Kraftstoff, [Fahrtenbuch](feat-06-fahrtenbuch.md)).
  - **Gasstopp** (Fahrtenbuch-Eintrag mit getanktem Gas).
  - **Stellplatz / Campingplatz** (Übernachtungsplatz bzw. Standort einer Tour, [Tour](feat-10-tour.md) 5.7).
  - **Start und Ziel** (bisher farbige Punkte) und **Fähre** (5.1).
- **Keine Kosten auf der Karte** (5.1).
- **Unterscheidbar** auch ohne Farbe (Form oder Piktogramm), gut lesbar in allen Skalen (1, 2, 4).
- **Legende** auf dem Gesamtbild, damit die Symbole ohne Erklärung verständlich sind (5.5).
- **Überlagerung:** Fällt ein Halt mit einem Tank- oder Gasstopp zusammen, entsteht kein Durcheinander aus mehreren
  Symbolen am selben Ort (5.4).
- **Nachträge und Änderungen** (Tankstopp nachgetragen, Eintrag geändert, Standortname geändert) erscheinen auf der
  Karte, sobald der Export erneuert wird ([Nachträge](feat-09-nachtraege.md) 5.8, [Einträge bearbeiten](feat-11-eintraege-bearbeiten.md)).
- Zeichnen nur mit Pillow/`staticmap` (kein matplotlib), außerhalb des Event-Loops wie bisher.
- Keine zusätzlichen Kachelabrufe; ein erneuerter Export zeichnet die Karte nur neu, wenn sich Symbole ändern.

## 3. Ausgangslage (Stand v0.3.4)

- **Karte der Reise:** `export/map.py` `render_map` zeichnet die Strecke (rot mit weißem Rand) sowie Start (grün)
  und Ziel (dunkelblau) als Kreise. Halte, Tank- und Gasstopps sind nicht eingezeichnet.
- **Karte der Tour:** `render_route_map` zeichnet alle Reisen und die Übernachtungsorte (`places`) als kleine
  orange Kreise, ohne Unterscheidung nach Art.
- **Daten mit Position:**
  - Halte (`TripStop`): `lat`, `lon`, Ort, von, bis.
  - Fahrtenbuch-Einträge (`LogbookEntry`): `lat`, `lon`, Ort, `fuel` (Liter, Betrag), `gas` (Liter, Betrag).
  - Tour-Standorte: Position um 3 Uhr, Name (Camping-/Stellplatz aus OpenStreetMap, `camp_site`/`caravan_site`).
  - Reisekosten (`TravelCost`, z. B. Maut, Fähre, Stellplatz) haben **keine Position**, nur Reise, Datum und Land.
- **Gespeicherte Exporte:** Die Halte im Export (`coordinator/exports.py`) haben nur von, bis und Ort, **keine
  Position**; die Position lässt sich aber aus den Rohdaten (Punkte) zur Startzeit des Halts bestimmen. Fahrtenbuch-
  Einträge haben ihre Position im Fahrtenbuch. Fehlen die Rohdaten (aufgeräumt), kann die Karte nicht neu
  gezeichnet werden.
- Die Kartenbilder werden mit dem Export gespeichert; das Gesamtbild setzt Karte und Profil bzw. Tabellen zusammen
  (`export/composite.py`).

## 4. Offene Fragen (vor der Umsetzung einzeln klären)

1. ~~**Umfang der Symbole:** Welche Ereignisse bekommen ein Symbol? Vorschlag: Start, Ziel, Halt, Tankstopp Diesel,
   Gasstopp, Übernachtung/Stellplatz. Sollen auch Reisekosten (Maut, Fähre) erscheinen, obwohl sie keine Position
   haben (dann nur über den Ort eines Halts zur gleichen Zeit)?~~ – entschieden, siehe 5.1.
2. ~~**Darstellung:** Piktogramme (Zapfsäule, Gasflasche, Pause-Zeichen, Wohnmobil/Zelt) in farbigen Kreisen, oder
   einfache Formen (Kreis, Quadrat, Dreieck) mit Buchstaben (P, D, G, S)? Piktogramme brauchen eine Schrift mit
   Symbolen oder selbst gezeichnete Bildchen. Dazu: Wird die Strecke auf der Fähre anders gezeichnet (z. B.
   gestrichelt) und steht das Fähren-Symbol am Anleger der Abfahrt oder in der Mitte der Überfahrt?~~ – entschieden, siehe 5.3.
3. ~~**Zusammenfallende Ereignisse:** Halt mit Tankstopp → nur das Tank-Symbol, beide Symbole nebeneinander, oder ein
   kombiniertes Symbol?~~ – entschieden, siehe 5.4.
4. ~~**Legende:** Auf dem Kartenbild selbst, nur auf dem Gesamtbild, oder gar nicht?~~ – entschieden, siehe 5.5.
5. ~~**Welche Karten:** Reise und Tour, oder zunächst nur eine? Auf der Tour-Karte auch die Halte aller Reisen (kann
   bei langen Touren voll werden), oder nur Tank-/Gasstopps und Übernachtungen?~~ – entschieden, siehe 5.6.
6. ~~**Stellplatz bei einer Reise:** Bei einer einzelnen Reise gibt es keine Übernachtungsorte. Soll das Ziel ein
   Stellplatz-Symbol bekommen, wenn es auf einem Camping-/Stellplatz liegt (zusätzliche Ortsabfrage), oder nur auf
   der Tour-Karte?~~ – entschieden, siehe 5.7.
7. ~~**Abschalten:** Option im Options-Flow (Symbole ein/aus) oder immer an? Gilt sie auch für den manuellen Export
   (der keine Halte kennt, [Halte](feat-02-halte.md) 3)?~~ – entschieden, siehe 5.8.
8. ~~**Bestehende Exporte:** Sollen vorhandene Reisen und Touren neu gezeichnet werden (z. B. über einen Dienst oder
   beim nächsten Erneuern), oder gelten die Symbole nur für neue Exporte?~~ – entschieden, siehe 5.9.

9. ~~**Fähre erkennen:** Woher kennt die Integration Ort und Zeit einer Fährfahrt (5.1)? Möglichkeiten: automatisch
   aus der Spur (Halt, während dem sich das Fahrzeug weit bewegt, bzw. Strecke über Wasser), aus einer Reisekosten-
   Buchung der Kategorie Fähre (nur als Hinweis auf die Fährfahrt, ohne Betrag auf der Karte), oder von Hand
   markiert.~~ – entschieden, siehe 5.2.

## 5. Entscheidungen

- **5.1 Umfang der Symbole** (23.11.2026): Symbole für Start, Ziel, Halt, Tankstopp Diesel, Gasstopp,
  Übernachtung/Stellplatz und zusätzlich **Fähre**. **Keine Kosten** in der Kartendarstellung (weder Beträge noch
  Symbole für Maut, Vignette, Tunnel oder Stellplatzgebühren). Wie die Fähre erkannt wird, klärt Frage 9.
- **5.2 Fähre erkennen** (23.11.2026): automatisch aus der Spur, von Hand als Ersatz.
  - **Automatisch:** Ein Halt (D+ aus) gilt als Fähre, wenn währenddessen GPS-Punkte vorliegen und das Fahrzeug sich
    laut Karte auf dem Wasser befindet. Beginn ist das D+-Aus beim Auffahren; **Ende ist das nächste D+-An** beim
    Herunterfahren vom Schiff. Die Fährfahrt ist damit ein Halt mit Art „Fähre“, kein eigener Datensatz.
  - **Von Hand:** Wird eine Fähre nicht erkannt (z. B. kein GPS-Empfang an Bord, Lücke in der Spur), lässt sich der
    Halt nachträglich als Fähre markieren (und umgekehrt die Markierung entfernen).
  - **Bei der Umsetzung festlegen:** Wie „auf dem Wasser“ bestimmt wird (z. B. Ortsabfrage über Nominatim mit
    Wasserfläche bzw. ohne Adresse, oder Nähe zu einer Fährlinie `route=ferry` aus OpenStreetMap), ab wie vielen Punkten
    bzw. welcher Strecke auf dem Wasser, und wo die Markierung von Hand bedient wird (Fahrtenbuch-Formular, Aktion).
  - Die Reise endet auf der Fähre nicht: Bewegt sich das Fahrzeug bei D+ aus, läuft die Verzögerung ab der letzten
    Bewegung neu ([Reiseerkennung](feat-01-reiseerkennung.md) 2). Ein kurzes D+-An an Bord (z. B. Motor kurz
    gestartet) beendet die Fährfahrt nach dieser Regel bereits; reicht das in der Praxis nicht, wird nachgebessert.
- **5.3 Darstellung** (23.11.2026):
  - **Piktogramme in farbigen Kreisen** mit weißem Rand: Pausenzeichen (Halt), Zapfsäule (Diesel), Gasflasche (Gas),
    Wohnmobil (Übernachtung/Stellplatz), Schiff (Fähre); Start und Ziel ebenfalls als Symbol statt einfacher Punkte.
    Die Piktogramme werden mit Pillow selbst gezeichnet (Formen), nicht aus einer Schrift, damit sie unabhängig von den
    installierten Schriften und in jeder Skala scharf sind.
  - **Fährstrecke** gestrichelt und in einer eigenen Farbe (nicht Rot wie die Fahrstrecke); das Fähren-Symbol steht
    in der Mitte der Überfahrt (Punkt auf halber Strecke der Fährfahrt). Ohne GPS-Punkte an Bord (von Hand markiert)
    verbindet die gestrichelte Linie Abfahrt und Ankunft direkt.
  - Farben und Größen bei der Umsetzung festlegen; Symbole sind auch ohne Farbe am Piktogramm unterscheidbar.
- **5.4 Zusammenfallende Ereignisse** (23.11.2026): Pro Ort nur das wichtigste Symbol. Tank- und Gasstopp gehen vor
  dem Halt (das Pausenzeichen entfällt dann). Wurden Diesel und Gas am selben Halt getankt, stehen beide Symbole dicht
  nebeneinander. Liegen Symbole verschiedener Ereignisse so nah, dass sie sich überdecken würden, werden sie leicht
  versetzt (Abstand bei der Umsetzung festlegen).
- **5.5 Legende** (23.11.2026): Nur auf dem Gesamtbild, als schmale Zeile unter der Karte (Symbol und Name, z. B.
  „Halt · Diesel · Gas · Stellplatz · Fähre“, in der Sprache der Instanz). Das Kartenbild selbst bleibt ohne Legende.
  Aufgeführt werden nur die Symbole, die auf der Karte vorkommen.
- **5.6 Welche Karten** (23.11.2026): Reise und Tour bekommen Symbole.
  - **Reisekarte:** alle Symbole (Start, Ziel, Halt, Diesel, Gas, Fähre).
  - **Tour-Karte:** ohne Halte; Start, Ziel, Diesel, Gas, Übernachtung/Stellplatz und Fähre aller Reisen der Tour.
    Die bisherigen orangen Punkte der Übernachtungsorte werden durch das Stellplatz-Symbol ersetzt.
- **5.7 Stellplatz auf der Reisekarte** (23.11.2026): Am Ende einer Reise fragt die Integration einmal den Ort des
  Ziels ab, wie bei den Standorten der Tour ([Tour](feat-10-tour.md) 5.7: höhere Genauigkeit, `camp_site`/
  `caravan_site`). Liegt das Ziel auf einem Camping- oder Stellplatz, zeigt die Karte statt des Ziel-Symbols das
  Stellplatz-Symbol, und der Name des Platzes (z. B. „Camping Seeblick“) steht in Statistik und `export.json`.
  Schlägt die Abfrage fehl oder ist die Ortsabfrage ausgeschaltet, bleibt das Ziel-Symbol.
- **5.8 Abschalten und manueller Export** (23.11.2026): Symbole sind immer an, keine eigene Option. Der manuelle
  Export (`exportieren`) zeigt Start, Ziel (ggf. Stellplatz, 5.7) und die Diesel- und Gasstopps aus den
  Fahrtenbuch-Einträgen im gewählten Zeitraum; Halte und Fähre zeigt er nicht, weil er D+ nicht auswertet
  ([Halte](feat-02-halte.md) 3).
- **5.9 Bestehende Exporte** (23.11.2026): Keine Neuzeichnung aller Exporte auf einmal (OpenStreetMap: nur einzelne
  Läufe).
  - **Beim Erneuern:** Wird ein Export ohnehin neu erstellt (Nachtrag, geänderter Eintrag, Tour aktualisiert),
    zeichnet die Integration die Karte mit Symbolen neu.
  - **Gezielt von Hand:** Eine neue Aktion (und ein Knopf zur Export-Auswahl) zeichnet den gewählten Export (Reise
    oder Tour) neu: Karte und Gesamtbild aus den Rohdaten, je Aufruf ein Export. Fehlen die Rohdaten, meldet die
    Integration das verständlich und lässt den Export unverändert. Name der Aktion und des Knopfs bei der Umsetzung
    festlegen.

## 6. Entwurf der Umsetzung

Folgt; vor der Umsetzung zur Freigabe vorlegen.
