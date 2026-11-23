# Feat-12: Kartensymbole

Stand: 23.11.2026, alle Fragen geklärt (Abschnitt 5); Entwurf der Umsetzung zur Freigabe (Abschnitt 6).
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
- **Gespeicherte Exporte:** Die Halte in `export.json` haben nur von, bis und Ort, **keine Position**. Die Rohdaten
  einer automatischen Reise (`TripLog.as_dict`) enthalten die Halte aber mit `lat`/`lon`; manuelle Exporte haben in
  den Rohdaten keine Halte. Fahrtenbuch-Einträge haben ihre Position im Fahrtenbuch. Fehlen die Rohdaten
  (aufgeräumt), kann die Karte nicht neu gezeichnet werden.
- **Erneuern ohne Kacheln:** `refresh_export` (nach Nachträgen) schreibt Statistik und Gesamtbild neu, verwendet aber
  das vorhandene Kartenbild und lädt keine Kacheln.
- **Strecke bei D+ aus:** `TripLog.add_position` zählt jede Bewegung, auch bei D+ aus. Eine Fährfahrt mit GPS geht
  heute in Strecke, Fahrzeit (ab Stillstandsschwelle) und die Zählerstände des Fahrtenbuchs (Ø-Verbrauch) ein.
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
- **5.10 Strecke auf der Fähre** (23.11.2026): Eine erkannte oder von Hand markierte Fähre zählt **nicht** zu
  Strecke, Fahrzeit und den Zählerständen des Fahrtenbuchs (Ø-Verbrauch, Verbrauchsmodell). Die Statistik zeigt sie
  getrennt („Fähre: 18 km, 45 min“), ebenso Gesamtbild, `export.json` und Event `_beendet` (neue Felder
  `faehre_km`, `faehre_min`), bei einer Tour summiert. Gilt ab dieser Version; ändert sich die Markierung nachträglich,
  werden Strecke und Zählerstände beim Erneuern neu berechnet. Hinweis in den Release-Notes.
- **5.11 Grundkarte speichern** (23.11.2026): Jeder Export mit Karte speichert zusätzlich die Karte ohne Symbole
  (Grundkarte) und ihre Projektion (6.5). Erneuern zeichnet die Symbole darauf neu, ohne Kacheln zu laden; die
  zusätzliche Datei (bei Skala 2 einige MB) wird in Kauf genommen.

## 6. Entwurf der Umsetzung (zur Freigabe)

### 6.1 Datenmodell

- **Halt** (`TripStop`, `export.model.Stop`, `RecordedStop`): neues Feld `ferry` (`None` = nicht geprüft,
  `"auto"` = erkannt, `"hand"` = von Hand markiert, `"kein"` = Markierung von Hand entfernt). `Stop` in `export.json`
  bekommt zusätzlich `lat`/`lon`, damit spätere Karten ohne Rohdaten-Suche auskommen. Alte Dateien ohne die Felder
  bleiben lesbar (Halt ohne Fähre, Position aus den Rohdaten).
- **Kartensymbol** (`export.model.MapMarker`): Art (`start`, `ziel`, `stellplatz`, `halt`, `diesel`, `gas`,
  `faehre`), Position und Zeit. Die Integration stellt die Liste je Export zusammen, die Exportbibliothek zeichnet
  nur, was sie bekommt (bleibt ohne Home Assistant testbar).
- **Fährstrecke** (`FerryLeg`): von, bis und die Punkte dazwischen; ohne Punkte die Positionen vor und nach der Fähre.
- **Ziel auf Stellplatz** (5.7): `export.json` bekommt `arrival_stay` (Name oder `null`).

### 6.2 Fähre erkennen (5.2)

- Beim Ende eines Halts (D+ an) prüft die Integration, ob sich das Fahrzeug während des Halts weiter als die
  Mindestbewegung bewegt hat (mindestens zwei brauchbare Punkte). Nur dann folgt die Prüfung „auf dem Wasser“.
- **Auf dem Wasser:** Eine Ortsabfrage (Nominatim, wie bei den Halten, eigener User-Agent, 1 Anfrage/s) am Punkt auf
  halber Strecke der Bewegung. Fähre, wenn Nominatim dort keine Adresse liefert (offene See) oder eine Wasserfläche
  (`natural=water|bay|strait`, `waterway`, `place=sea`) bzw. eine Fährlinie (`route=ferry`). Eine Anfrage je Halt
  mit Bewegung; ohne Ortsabfrage (ausgeschaltet, Fehler) keine automatische Erkennung, die Markierung von Hand
  bleibt.
- Das Ergebnis steht am Halt (`ferry="auto"`), in den Rohdaten, im Attribut `halte` (neu `faehre: true`), in
  Statistik und Event `_beendet` („Fähre 10:15–11:40, Puttgarden → Rødby“).
- Eine laufende Reise zeigt die Fähre im Attribut `halte`, sobald der Halt endet.
- **Strecke ohne Fähre (5.10):** Wird ein Halt als Fähre erkannt, zieht `TripLog` die Strecke (und eine dabei
  gezählte Fahrzeit) zwischen Beginn und Ende der Fähre von Strecke, Fahrzeit und Zählerständen ab; Höhenmeter auf
  der Fähre zählen ebenfalls nicht. Die Fährstrecke steht getrennt im Log.
- **Fahrtenbuch-Einträge an Bord:** Der Anlass „Halt“ entsteht schon nach der Mindestdauer, also während der
  Überfahrt. Ein Eintrag, dessen Zeit in einer Fähre liegt, bekommt die Zählerstände vom Beginn der Fähre; Einträge
  danach die Zählerstände ohne Fährstrecke. Wird eine Fähre später von Hand markiert oder entfernt, verschiebt die
  Integration die Zählerstände der späteren Einträge derselben Reise und der folgenden um die Fährstrecke (wie eine
  Korrektur; der abgelesene Kilometerstand bleibt unverändert).

### 6.3 Fähre von Hand (5.2)

- **Neue Aktion** `reiseverlauftracker.faehre_markieren` (`config_entry_id`, `export`, `halt` = Startzeit des Halts,
  `faehre` = an/aus). Ohne `export` gilt die Export-Auswahl. Ändert Halt in Rohdaten und `export.json` und erneuert den
  Export (6.7); bei einer Tour mit dieser Reise wird nichts automatisch neu erstellt (wie bei Nachträgen).
- **Im Dashboard:** Die Halte einer Reise stehen bereits in der Zeitpunkt-Auswahl des Nachtrags
  (`select.…_fahrtenbuch_zeitpunkt`). **Neu:** `button.…_als_faehre_markieren` schaltet die Markierung des dort
  gewählten Halts um; die Auswahl zeigt eine markierte Fähre im Label („· Fähre“). Halte, die nicht mehr in der
  Auswahl stehen (älter als die Aufbewahrung), gehen über die Aktion.
- Ohne GPS an Bord verbindet die Fährstrecke die letzte Position vor und die erste nach dem Halt (5.3).

### 6.4 Symbole zeichnen (5.3, 5.4)

- **Neues Modul** `export/symbols.py`: Piktogramme mit Pillow aus Formen, vierfach überabgetastet und verkleinert
  (glatte Kanten). Jeder Kreis mit weißem Rand und Schatten; Durchmesser abhängig von der Linienbreite (wie heute).
  Vorschlag Farben: Start Grün, Ziel Dunkelblau, Stellplatz Petrol, Halt Grau, Diesel Schwarz, Gas Orange, Fähre
  Blau. Piktogramme: Fahne (Start), Zielflagge (Ziel), Wohnmobil (Stellplatz), Pause-Balken (Halt), Zapfsäule
  (Diesel), Gasflasche (Gas), Schiff (Fähre).
- **Karte** (`export/map.py`): Die Fahrstrecke zeichnet wie bisher `staticmap`. Danach zeichnet Pillow mit der
  Projektion der gerenderten Karte (Zoom und Mitte von `staticmap`) die Fährstrecken gestrichelt in Blau mit weißem
  Rand und die Symbole. Die Abschnitte der Fahrstrecke enden an der Fähre, damit keine rote Linie übers Wasser läuft.
- **Reihenfolge:** Halte, dann Stellplatz, Diesel, Gas, Fähre, zuletzt Start und Ziel (oben).
- **Zusammenfallen:** Diesel/Gas und Halt am selben Ort (Fahrtenbuch-Eintrag zum Halt oder Abstand unter der
  Mindestbewegung): nur Diesel/Gas; beide zusammen nebeneinander. Symbole, die sich im Bild überdecken würden, rücken
  um einen Durchmesser zur Seite (einfache Verdrängung, keine Optimierung).
- **Kartenausschnitt:** Symbole und Fährstrecke liegen innerhalb der Strecke; der Ausschnitt bleibt wie bisher.

### 6.5 Karte ohne Kacheln erneuern (5.9)

- Beim Zeichnen mit Kacheln speichert der Export zusätzlich das **Kartenbild ohne Symbole** (Grundkarte) und die
  Projektion (Zoom, Mitte, Größe) in `export.json`. Erneuern (Nachtrag, Eintrag geändert, Fähre markiert) zeichnet
  Symbole und Fährstrecken auf die Grundkarte, **ohne Kacheln zu laden**.
- Die Grundkarte ist ein eigener Dateityp (`karte_basis`, Name `<Titel>_karte_basis.png`), nicht in den Downloads und
  nicht im Event; `aufraeumen` löscht sie mit der Karte.
- Alte Exporte ohne Grundkarte: Erneuern lässt die Karte wie sie ist (Hinweis im Log); Symbole gibt es dort über
  „Karte neu zeichnen“ (6.8).

### 6.6 Welche Symbole wo (5.5–5.8)

- **Reise:** Start, Ziel bzw. Stellplatz (5.7), Halte und Fähren aus den Halten der Reise, Diesel und Gas aus den
  Fahrtenbuch-Einträgen der Reise (Zeitraum wie `trip_figures`: Reisebeginn bis Ende der Reise). Einträge ohne
  Position bekommen die Position aus den Rohdaten zu ihrer Zeit, sonst kein Symbol.
- **Ziel auf Stellplatz:** Nach dem Ende einer Reise eine Ortsabfrage für das Ziel (`async_stay_name`, wie die
  Standorte der Tour, 1 s nach der Titelabfrage). Statistik: Zeile „Stellplatz: Camping Seeblick“.
- **Manueller Export:** Start, Ziel bzw. Stellplatz, Diesel und Gas aus dem Fahrtenbuch im Zeitraum; keine Halte,
  keine Fähre.
- **Tour:** Start, Ziel, Übernachtungen (Stellplatz-Symbol statt oranger Punkte; aufeinanderfolgende Nächte am selben
  Standort ein Symbol), Diesel und Gas aus dem Fahrtenbuch im Tour-Zeitraum, Fähren aus den Halten der Reisen (Rohdaten
  der Tour). Keine Halte.
- **Legende** (5.5): `render_composite` bekommt die vorkommenden Arten und zeichnet unter der Karte eine Zeile mit
  Symbol und Name (`texts.py`, de/en: Start, Ziel, Stellplatz, Halt, Diesel, Gas, Fähre). Bei der Tour ebenso.

### 6.7 Erneuern

- Der vorhandene Ablauf (`ExportRefresher`, `async_refresh`) zeichnet die Symbole neu (6.5), wenn sich Fahrtenbuch-
  Einträge mit Tanken, die Fähren-Markierung oder `arrival_stay` ändern. Die Tour zeichnet ihre Symbole bei
  „Tour aktualisieren“ neu, ebenfalls auf der Grundkarte (`reuse_map` wie bisher).

### 6.8 Karte neu zeichnen (5.9)

- **Neue Aktion** `reiseverlauftracker.karte_neu_zeichnen` (`config_entry_id`, `export`; ohne `export` die
  Export-Auswahl) und **neu** `button.…_karte_neu_zeichnen`. Zeichnet Karte (mit Kacheln), Grundkarte und Gesamtbild
  eines Exports (Reise oder Tour) aus den Rohdaten neu; Statistik, GPX und Profil bleiben bzw. werden wie beim
  Erneuern geschrieben. Je Aufruf genau ein Export; mit „Alle Exporte“ Fehler mit Hinweis.
- Bei alten Reisen ohne Fähren-Prüfung (`ferry=None`) prüft „Karte neu zeichnen“ die Halte mit Bewegung einmal auf
  Fähre (6.2) und fragt das Ziel einmal nach einem Stellplatz ab (5.7).
- Fehlen die Rohdaten: Fehler „Keine Rohdaten mehr vorhanden, Karte kann nicht neu gezeichnet werden“; der Export
  bleibt unverändert. Kein Event `_beendet`.

### 6.9 Abgrenzung

- Keine Kosten auf der Karte (5.1); keine Symbole im Kartenbild der laufenden Reise (es gibt keins).
- Keine Wegpunkte im GPX für Halte und Tankstopps (wäre ein eigenes kleines Feature).
- Keine Neuzeichnung aller Exporte auf einmal (5.9).

### 6.10 Zur Entscheidung vor der Umsetzung

1. ~~**Strecke auf der Fähre:** herausrechnen oder nur einzeichnen?~~ – entschieden, siehe 5.10.
2. ~~**Grundkarte speichern** (6.5): ja oder nein?~~ – entschieden, siehe 5.11.

### 6.11 Teilschritte

1. Datenmodell (6.1) und Symbole zeichnen (6.4) in der Exportbibliothek, mit Tests auf Testdaten (Bilder: Größe,
   Pixel an Symbolpositionen, Fährstrecke gestrichelt); Grundkarte und Projektion (6.5).
2. Reise: Symbole aus Halten und Fahrtenbuch, Ziel auf Stellplatz, Legende im Gesamtbild (6.6), Erneuern (6.7).
3. Fähre erkennen (6.2) und von Hand markieren (6.3), Strecke ohne Fähre (5.10), mit Tests.
4. Tour: Symbole und Legende (6.6).
5. „Karte neu zeichnen“ (6.8): Aktion, Knopf, Übersetzungen, Tests.
6. README (de/en), Release-Notes, Feature-Dokumente; Prüfpunkt in `script/develop` mit simulierter Reise (Halt,
   Tankstopp, Gasstopp, Fähre) und Kartenbild ansehen.

Neue Entitäten: 2 Knöpfe (`als_faehre_markieren`, `karte_neu_zeichnen`); neue Aktionen: `faehre_markieren`,
`karte_neu_zeichnen`. Kein Breaking Change im Sinne der Entitäten; Strecke, Fahrzeit und Ø-Verbrauch von Reisen mit Fähre ändern sich
(5.10, Release-Notes).
