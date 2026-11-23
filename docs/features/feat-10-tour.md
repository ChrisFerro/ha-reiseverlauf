# Feat-10: Tour

Stand: 23.11.2026, umgesetzt (Abschnitt 6 mit den Festlegungen der Umsetzung in Abschnitt 7).
Übergeordnete Anforderungen und Entitäten: [ANFORDERUNGEN.md](../ANFORDERUNGEN.md). Grundlage:
[Reiseerkennung](feat-01-reiseerkennung.md), [Halte](feat-02-halte.md), [Export](feat-03-export.md),
[Fahrtenbuch](feat-06-fahrtenbuch.md), [Nachträge](feat-09-nachtraege.md).

## 1. Ziel

Ein Urlaub besteht aus mehreren Reisen und Standzeiten dazwischen, z. B. Hinreise, eine Woche Campingplatz,
Rückreise; ebenso z. B. die Fahrt zur Werkstatt und nach ein paar Tagen zurück. Die Integration fasst solche Reisen
als **Tour** zusammen und erstellt dafür eine Aufstellung des Reiseverlaufs und aller Kosten, auch als Gesamtbild für
das Fotobuch.

## 2. Anforderungen

- **Zusammenfassung mehrerer Reisen** (automatisch erkannte Fahrten im Sinne von
  [Reiseerkennung](feat-01-reiseerkennung.md)) samt der Standzeiten dazwischen; von Hand im Nachhinein angelegt,
  mit Titel (5.1).
- **Reiseverlauf:** Gesamtkarte aller Reisen, Gesamtstrecke, Fahrzeit, Höhenmeter, Tagesübersicht mit den
  Standorten (z. B. „10.–15.10. · Camping Seeblick · 5 Nächte“, 5.6, 5.7).
- **Kostenaufstellung:** Diesel, Gas und Reisekosten (Maut, Vignette, Fähre, Tunnel, Stellplatz, Sonstiges, siehe
  [Nachträge](feat-09-nachtraege.md) 5.6), gesamt, je Kategorie und je Land; dazu der geschätzte Verbrauch (5.5) und Kilometerstand von/bis.
- **Kosten zwischen den Fahrten:** Auch Kosten, die zu keiner Fahrt gehören (Stellplatzgebühr der Woche, Gas während
  des Stands), gehören zur Tour.
- **Datenquelle:** die gespeicherten Reisen (Rohdaten der Exporte, Fahrtenbuch, Stopps), nicht der Recorder, damit
  auch Touren über 10 Tage vollständig sind; danach die eigenen Rohdaten der Tour (5.8).
- **Ausgabe** wie ein Export: eigener Ordner, Statistik, Gesamtbild, GPX, `export.json`, Auswahl in der
  Export-Auswahl, geschützter Download ([Downloads](feat-07-downloads.md)) und Aufräumen (5.2); Event und
  Push-Nachricht (5.9).

## 3. Ausgangslage (Stand v0.2.4)

- **Fahrten:** Jede Fahrt (D+ an bis Ende nach der Verzögerung) wird automatisch exportiert, mit Rohdaten (Punkte mit
  Zeit, Position, Geschwindigkeit, Höhe) und Halten in `export.json`. Fahrten mit kurzer Pause werden innerhalb des
  Zusammenführungsfensters (Standard 6 h) zu einer zusammengeführt; eine Woche Stand trennt sie.
- **Manueller Export** (`exportieren` mit von/bis): liest aus dem Recorder (standardmäßig nur 10 Tage), ermittelt
  keine Halte und enthält keine Fahrtenbuch-Daten ([Export](feat-03-export.md) 3, [Fahrtenbuch](feat-06-fahrtenbuch.md)
  6.6). Für eine Tour über mehr als 10 Tage fehlen damit die ersten Fahrten.
- **Rohdaten** einer Fahrt werden mit `aufraeumen` (Dateityp „Rohdaten“) gelöscht; danach ließe sich die Fahrt
  nicht mehr in eine Tour aufnehmen.
- **Kosten:** Tank- und Gasstopps hängen an Fahrtenbuch-Einträgen mit Zeitpunkt; Reisekosten sind in
  [Nachträge](feat-09-nachtraege.md) 6.3 mit Datum und optional einer Reise erfasst (5.4).
- **Begriff:** In Entitäten und Oberfläche heißt eine einzelne Fahrt bisher „Reise“ (`reise_aktiv`, `letzte_reise`).

## 4. Offene Fragen (vor der Umsetzung einzeln klären)

1. ~~**Festlegen:** Wie wird eine Tour bestimmt? Von Hand über einen Zeitraum (von/bis bzw. erste und letzte
   Fahrt), über Knöpfe „Tour beginnt“/„Tour endet“, oder automatisch (z. B. Fahrten ab Verlassen bis Rückkehr in
   die Heimatzone)?~~ – entschieden, siehe 5.1 und 5.2.
2. ~~**Begriff:** Bleibt „Reise“ für die einzelne Fahrt und wie heißt die Zusammenfassung, oder wird umbenannt (z. B.
   „Fahrt“ und „Reise“)? Eine Umbenennung ändert Entity-IDs.~~ – entschieden, siehe 5.3.
3. ~~**Kosten-Zuordnung:** Hängen Reisekosten an einer Fahrt, an der Tour oder an einem Datum (Zuordnung dann
   über den Zeitraum)? Betrifft das Datenmodell von [Nachträge](feat-09-nachtraege.md) 6.3.~~ – entschieden, siehe
   5.4.
4. ~~**Welche Kosten zählen:** alle im Zeitraum bezahlten Beträge (auch die Tankfüllung kurz vor der Rückkehr), oder
   der Verbrauch (z. B. anteilig nach gefahrenen km bzw. verbrauchtem Gas)?~~ – entschieden, siehe 5.5.
5. ~~**Inhalt und Layout:** Was soll das Gesamtbild zeigen (eine Seite mit Gesamtkarte, Kennzahlen und Kosten, oder
   zusätzlich eine Seite je Fahrt/Tag)? Soll es eine Tagesübersicht (Tag, Strecke, Standort) geben?~~ – entschieden,
   siehe 5.6.
6. ~~**Standorte:** Wie werden die Standzeiten benannt (Ortsabfrage, eigener Name, z. B. Campingplatz) und ab welcher
   Dauer zählt ein Standort (z. B. über Nacht)?~~ – entschieden, siehe 5.7.
7. ~~**Aufbewahrung:** Sollen Rohdaten von Fahrten, die zu einer Tour gehören, vor `aufraeumen` geschützt
   werden?~~ – entschieden, siehe 5.8.
8. ~~**Benachrichtigung:** Event und Push-Nachricht, wenn eine Tour erstellt ist (wie `_exportiert`), und
   erneut, wenn nachgetragene Kosten (Maut im Folgemonat) die Aufstellung ändern?~~ – entschieden, siehe 5.9.
9. ~~**Laufende Tour:** Sollen während der Tour Zwischenstände sichtbar sein (Sensoren: Tage, Strecke, Kosten
   bisher)?~~ – entfällt (21.11.2026): Die Tour wird erst im Nachhinein angelegt (5.1).

## 5. Entscheidungen

Entscheidungen werden hier mit Datum eingetragen, die Frage in Abschnitt 4 wird dann durchgestrichen
(wie in [ANFORDERUNGEN.md Abschnitt 9](../ANFORDERUNGEN.md#9-offene-entscheidungen)).

- **5.1 Festlegen von Hand im Nachhinein** – entschieden (21.11.2026): Das Wohnmobil hat mehrere Orte als Zuhause,
  eine Heimatzone taugt daher nicht zur automatischen Erkennung. Der Nutzer legt die Tour im Nachhinein
  an: über einen Zeitraum (von/bis) bzw. die erste und letzte Fahrt. Keine automatische Erkennung, keine Knöpfe
  „Tour beginnt/endet“, keine laufende Tour.
  - **Titel:** Die Tour bekommt einen frei wählbaren Titel (z. B. „Südtirol Sommer 2027“), der in
    Statistik, Gesamtbild, Export-Auswahl und Dateinamen erscheint; ohne Titel ein Vorschlag aus Zeitraum und
    Zielort. Der Titel lässt sich später ändern.
- **5.2 Verwaltung wie bei Fahrten** – entschieden (21.11.2026): Touren werden wie die Exporte einzelner
  Fahrten verwaltet ([Export](feat-03-export.md), [Downloads](feat-07-downloads.md)):
  - eigener Ordner im Ausgabeordner mit `export.json`, Auswahl in `select.…_export_auswahl` (als Tour
    gekennzeichnet);
  - `downloads` mit signierten Links an der Export-Auswahl;
  - Löschen über `aufraeumen` mit der Export-Auswahl bzw. `export`, auch einzelne Dateitypen. Gelöscht werden nur
    die Dateien der Tour, nicht die der enthaltenen Fahrten.
- **5.3 Begriff „Tour“** – entschieden (21.11.2026): „Reise“ bleibt der Begriff für die einzelne, automatisch
  erkannte Fahrt (Entity-IDs, Dienste und Events unverändert). Die Zusammenfassung mehrerer Reisen heißt **Tour**
  (englisch „Tour“), nicht „Urlaubsreise“: Sie kann ein Urlaub sein, aber auch z. B. die Fahrt zur Werkstatt und
  nach ein paar Tagen zurück. Bezeichner z. B. `tour_erstellen`, Ordner `tour-<Start>-<Ende>`.
- **5.4 Kosten mit Datum, Reise optional** – entschieden (21.11.2026): Jede Reisekosten-Position hat ein Datum.
  - Maut, Tunnel, Fähre usw. werden wie in [Nachträge](feat-09-nachtraege.md) 5.4 einer Reise zugeordnet; das Datum
    ist dann standardmäßig der Reisebeginn und lässt sich ändern (z. B. Datum der Durchfahrt bei einer Reise über
    den Monatswechsel).
  - Kosten ohne Reise (Stellplatz, Sonstiges während einer Standzeit) werden nur mit Datum eingetragen.
  - Eine Tour enthält alle Kosten, deren Datum in ihren Zeitraum fällt, dazu die Tank- und Gasstopps in diesem
    Zeitraum.
  - Die Monats- und Jahressensoren (`reisekosten_monat`/`_jahr`, [Nachträge](feat-09-nachtraege.md) 5.10) zählen
    jede Position im Monat ihres Datums.
- **5.5 Bezahlt und Verbrauch** – entschieden (21.11.2026): Die Aufstellung einer Tour zeigt beides.
  - **Bezahlt:** alle Tank- und Gasstopps und Reisekosten mit Zeitpunkt bzw. Datum im Zeitraum der Tour (5.4), je
    Kategorie und gesamt. Das sind die Summen der Aufstellung.
  - **Verbrauch (Kennzahl):** Diesel = gefahrene km der Tour × Ø-Verbrauch
    ([Fahrtenbuch](feat-06-fahrtenbuch.md) 6.5, später das [Verbrauchsmodell](feat-08-verbrauchsmodell.md)), in
    Litern und als Betrag mit dem Ø-Literpreis der Tankstopps der Tour (ohne Tankstopp: der letzte bekannte Preis).
    Gas aus den Füllständen am Anfang und Ende der Tour und den Gasstopps dazwischen, nur wenn diese Werte vorliegen.
    Gekennzeichnet als geschätzt („ca.“).
  - Ohne Ø-Verbrauch (weniger als zwei volle Tankfüllungen) entfällt die Kennzahl.
- **5.6 Inhalt des Exports** – entschieden (21.11.2026):
  - **Gesamtbild der Tour:** Titel, Zeitraum, Gesamtkarte aller Reisen der Tour, Kennzahlen (Strecke, Fahrzeit,
    Tage, Höhenmeter, Verbrauch) und Kostentabelle (5.5). **Kein** Höhen-/Geschwindigkeitsprofil über alle Reisen.
  - **Tagesübersicht** in der Statistik und als CSV: Datum, gefahrene km, Standort (Übernachtung) und Kosten; Tage
    ohne Fahrt (Standzeit) sind enthalten. Mehrere Tage am selben Standort werden zusammengefasst (5.7).
  - Keine Seite je Tag oder je Reise; für die Details dienen die vorhandenen Gesamtbilder der Reisen.
  - Dazu wie bei einer Reise: GPX (alle Reisen als eigene Abschnitte) und `export.json`.
- **5.7 Standorte** – entschieden (21.11.2026):
  - **Bestimmung:** Standort eines Tages ist der Platz, an dem das Fahrzeug über Nacht steht (Position um 3 Uhr
    Ortszeit). Längere Halte tagsüber bleiben Halte der Reise.
  - **Name:** Ortsabfrage mit höherer Genauigkeit; liegt die Position auf einem in OpenStreetMap eingetragenen
    Campingplatz oder Stellplatz, dessen Name (z. B. „Camping Seeblick“), sonst der Ortsname wie bei den Halten.
    Jeder Standortname lässt sich in der Tour von Hand ändern; die Tour wird danach neu erstellt.
  - **Zusammenfassen:** In der Übersicht (Statistik, Gesamtbild) werden aufeinanderfolgende Nächte am selben
    Standort (ohne Ortswechsel) zu einer Zeile zusammengefasst, z. B. „10.–15.10. · Camping Seeblick · 5 Nächte“,
    mit den Kosten dieser Tage. „Derselbe Standort“: Positionen innerhalb der Mindestbewegung bzw. einiger hundert
    Meter (bei der Umsetzung festlegen). Fahrtage bleiben einzelne Zeilen; Ausflüge, die zum selben Standort
    zurückführen, unterbrechen die Zusammenfassung nicht, ihre km stehen in der Zeile.
  - Das CSV der Tagesübersicht behält eine Zeile je Tag (zum Weiterrechnen).
- **5.8 Eigene Rohdaten der Tour** – entschieden (21.11.2026): Beim Erstellen speichert die Tour die zusammengefassten
  Rohdaten in ihrem Ordner (Punkte aller Reisen, Halte, Standorte, Zählerstände; Dateityp „Rohdaten“ wie bei einer
  Reise). Neu erstellt wird sie (z. B. nach nachgetragener Maut, geändertem Titel oder Standortnamen) aus diesen
  Rohdaten und den aktuellen Fahrtenbuch- und Kostendaten, nicht mehr aus den Reisen.
  - Die Reisen lassen sich danach unabhängig aufräumen; ihre Rohdaten werden nicht geschützt.
  - Ein geänderter Zeitraum der Tour liest die Reisen erneut ein; fehlen deren Rohdaten, meldet die Integration das
    und behält für den bisherigen Zeitraum die Rohdaten der Tour.
  - Löscht `aufraeumen` die Rohdaten der Tour, bleibt ihr fertiger Export erhalten, sie lässt sich dann aber nur noch
    aus den Reisen neu erstellen.
- **5.9 Event und Push** – entschieden (21.11.2026): Nach dem Erstellen und nach jeder Neuerstellung löst die
  Integration das Event `reiseverlauftracker_tour` aus (Anlass `erstellt` oder `aktualisiert`, Titel, Zeitraum,
  Strecke, Kosten gesamt, Dateien mit Links, Pfad des Gesamtbilds). Der vorhandene Blueprint für die Reise-Nachricht
  ([Push-Benachrichtigung](feat-04-push-benachrichtigung.md)) bekommt Schalter für Touren, getrennt für „erstellt“
  und „aktualisiert“ (z. B. „Tour Südtirol: Maut nachgetragen, Kosten jetzt 1.245 €“).

## 6. Entwurf der Umsetzung (umgesetzt)

Stand: 21.11.2026, an die Entscheidungen 5.1–5.9 angepasst; freigegeben und umgesetzt am 23.11.2026 (Abweichungen und
Festlegungen in Abschnitt 7). Setzt [Nachträge](feat-09-nachtraege.md) 6.1 (Stopps,
Zählerstände je Reise) und 6.3 (Reisekosten mit Datum) voraus.

### 6.1 Datenmodell

- **Tour** (reines Python, `export/tour.py`): `titel`, `start`, `ende`, die enthaltenen Reisen (Ordner und Start),
  Standorte (Nacht, Position, Name, `name_geaendert`), Zählerstände am Anfang und Ende. Gespeichert in
  `export.json` des Tour-Ordners mit `art: tour` (Reise-Exporte bekommen `art: reise`, ältere ohne Feld gelten als
  Reise). Die Export-Verwaltung liest beide Arten.
- **Rohdaten der Tour (5.8):** eine Datei mit den Punkten aller Reisen (je Reise ein Abschnitt), Halten, Stopps und
  Standorten; Format wie die Rohdaten einer Reise, ergänzt um die Abschnitte.

### 6.2 Erstellen und Ändern

- **Formular im Dashboard** wie beim manuellen Export: `datetime.…_tour_von`, `…_tour_bis`, `text.…_tour_titel`,
  `button.…_tour_erstellen`. Vorbelegt: von = Beginn der Reise in der Export-Auswahl, bis = jetzt.
- **Dienst `tour_erstellen`** (`von`, `bis`, `titel` optional, `skala` optional): nimmt alle Reisen, die im Zeitraum
  beginnen, und liest deren Rohdaten (nicht den Recorder). Fehlen Rohdaten einer Reise, bricht der Dienst mit
  Hinweis ab. Antwort: Ordner und Dateien wie bei `exportieren`.
- **Dienst `tour_aendern`** (`export`, `titel`, `von`, `bis`, `standorte` als Liste Nacht → Name): ändert und erstellt
  neu. Neuer Zeitraum liest die Reisen erneut ein (5.8). Im Dashboard: Titel über `text.…_tour_titel` mit der Tour in
  der Export-Auswahl und Knopf `button.…_tour_aktualisieren`; Standortnamen per Dienst (Liste im Attribut
  `standorte` der Export-Auswahl).
- **Titel-Vorschlag** ohne Titel: Zielort (Standort mit den meisten Nächten) und Zeitraum, z. B. „Camping Seeblick ·
  10.–17.10.2026“.
- **Ordner** `tour-<Start>-<Ende>` (5.3), Dateinamen mit dem Titel wie bei Reisen.

### 6.3 Auswertung

- **Standorte (5.7):** Position je Nacht um 3 Uhr Ortszeit aus Punkten und Stopps (letzte Position vor 3 Uhr);
  Name über Nominatim mit höherem Zoom, bevorzugt `tourism=camp_site`/`caravan_site` aus der Antwort, sonst Ortsname.
  Gleicher Standort: Abstand unter 500 m (Vorschlag, bei der Umsetzung prüfen).
- **Tagesübersicht (5.6, 5.7):** je Kalendertag km (aus den Punkten), Standort der Nacht, Kosten mit Datum bzw.
  Zeitpunkt des Tages. Für Statistik und Gesamtbild zusammengefasst nach Standort; CSV `<Titel>-tage.csv` je Tag.
- **Kosten (5.4, 5.5):** bezahlt = Tank- und Gasstopps mit Zeitpunkt im Zeitraum + Reisekosten mit Datum im Zeitraum,
  je Kategorie und je Land (Länder der Tankstopps aus der Ortsabfrage). Verbrauch als Kennzahl: km × Ø-Verbrauch,
  Ø-Literpreis der Tour, Gas aus Füllständen; „ca.“.
- **Kennzahlen:** Strecke, Fahrzeit, Tage, Nächte, Höhenmeter bergauf/bergab, Kilometerstand von/bis, Länder.

### 6.4 Ausgabe

- **Gesamtbild:** Kopf mit Titel und Zeitraum, Kennzahlen, Gesamtkarte aller Reisen (Kacheln einmalig je Lauf,
  eigener User-Agent), Tagesübersicht zusammengefasst, Kostentabelle; kein Profil (5.6). Rendern im Executor.
- **Statistik** (Text wie bei Reisen, um Tagesübersicht und Kosten ergänzt), **GPX** (je Reise ein `trk`),
  **Rohdaten** (6.1), **`export.json`**, **CSV** der Tage.
- **Neu erstellen** nach Änderungen an Kosten oder Fahrtenbuch-Einträgen im Zeitraum (wie
  [Nachträge](feat-09-nachtraege.md) 6.4, zusammengefasst nach 30 s) aus den Rohdaten der Tour; die Karte wird dabei
  nicht neu geladen, nur Kopf und Tabellen.
- **Verwaltung (5.2):** Export-Auswahl (Label mit Kennzeichen „Tour“), `downloads`, `aufraeumen`; Sensoren „Letzte
  Reise“ bleiben bei Reisen.

### 6.5 Event und Push (5.9)

- Event `reiseverlauftracker_tour` mit `anlass` (`erstellt`, `aktualisiert`), `titel`, `start`, `ende`,
  `strecke_km`, `kosten`, `dateien` (Name, URL), `gesamtbild`, `ordner`.
- Blueprint `benachrichtigung.yaml`: neue Eingaben „Bei Tour erstellt“ und „Bei Tour aktualisiert“ (Standard: an
  bzw. aus); Text mit Titel, Zeitraum, Strecke, Kosten, Bild als Anhang wie bei Reisen.

### 6.6 Abgrenzung

- Keine automatische Erkennung, keine laufende Tour (5.1).
- Kein Profil über alle Reisen, keine Seite je Tag oder Reise (5.6).
- Keine Recorder-Daten; Reisen ohne Rohdaten lassen sich nicht aufnehmen.

### 6.7 Teilschritte

Jeder Schritt mit Tests, grünem `script/check` und einem Prüfpunkt in der Entwicklungsumgebung:

1. `Tour`-Modell, Standorte, Tagesübersicht und Kosten als reines Python mit Tests auf Testdaten.
2. Export-Verwaltung für zwei Arten (`art`), Tour-Ordner, Rohdaten, Gesamtbild ohne Profil, GPX, CSV. Prüfpunkt:
   Tour aus zwei Test-Reisen mit einer Standzeit, Bild ansehen.
3. Dienste, Formular-Entitäten, Übersetzungen, Neuerstellen nach Änderungen. Prüfpunkt: Tour anlegen, Maut
   nachtragen, Tour aktualisiert sich.
4. Event, Blueprint, README (deutsch/englisch). Prüfpunkt: Push in der Entwicklungsumgebung.

## 7. Festlegungen der Umsetzung (23.11.2026)

- **Code:** reines Python in `export/tour.py` (Standorte, Tagesübersicht, Kosten, Schätzung) und
  `export/tour_export.py` (Statistik, CSV, Tabellenbild, Gesamtbild, GPX, Karte); die Integration in
  `coordinator/tours.py` (Erstellen, Ändern, Neuerstellen, Event) und `coordinator/tour_form.py` (Formular).
- **Gleicher Standort (5.7):** Abstand bis 500 m zur ersten Nacht der Zeile. Ein von Hand geänderter Name gilt für alle
  Nächte der Zeile und trennt sie von Nächten mit anderem Namen. Bei geändertem Zeitraum übernehmen Nächte am selben
  Platz (500 m) die bisherigen Namen.
- **Zeilen der Tagesübersicht:** Ein Tag gehört zur Zeile seiner folgenden Nacht; die Zeile reicht bis zum Morgen nach
  der letzten Nacht („10.–15.10. · 5 Nächte“), km und Kosten sind die dieser Tage. Der letzte Tag (ohne Nacht in der
  Tour) bekommt eine eigene Zeile mit dem Ankunftsort (Ortsabfrage des letzten Punkts).
- **Ortsabfrage (5.7):** Nominatim mit Zoom 18; Typ `camp_site`/`caravan_site` liefert dessen Namen, sonst den Ort.
  Eine Abfrage je Zeile ohne Namen, höchstens eine pro Sekunde, nur mit eingeschalteten Ortsnamen.
- **Länder je Land (6.3):** Tank- und Gasstopps über die Ortsabfrage ihrer Position (einmal je Eintrag, in
  `export.json` gespeichert), Reisekosten mit ihrem Land; Kosten ohne Land unter „ohne Land“.
- **Gas-Schätzung (5.5):** Summe beider Füllstände am Anfang minus am Ende plus die Gasstopps. Gasstopps werden über
  „Liter je Prozentpunkt“ umgerechnet, ermittelt aus allen Gasstopps mit einer Ablesung davor (Liter ÷ aufgefüllte
  Prozentpunkte). Ohne diese Angabe nur der Prozentwert, wenn es keinen Gasstopp gab.
- **Reisen der Tour:** Reisen und manuelle Exporte, die im Zeitraum beginnen; Reisen ohne Bewegung entfallen.
  Manuelle Exporte zählen seit 0.3.2 mit (23.11.2026: die Reisen vor der Installation liegen nur als manuelle Exporte
  vor). Überschneiden sich zwei, zählt nur einer: die Kopie in der Tour vor einer automatischen Reise, eine
  automatische Reise vor einem manuellen Export, ein früherer manueller Export vor einem späteren. Ein manueller Export
  ohne Rohdaten entfällt; fehlen die Rohdaten einer automatischen Reise, bricht das Erstellen ab.
  Der Ordner bleibt bei Änderungen gleich; Dateinamen folgen dem Titel. Die Karte wird nur neu gezeichnet, wenn sich
  die Reisen der Tour ändern.
- **Export-Auswahl:** Label `<Start>–<Ende> · Tour · <Titel>`; Attribute `art`, `standorte` (Zeilen mit `nacht`,
  `bis`, `naechte`, `name`, `geaendert`) und `tourkosten`; `reisekosten` ist bei einer Tour leer. Mit einer Tour in der
  Auswahl speichert das Reisekosten-Formular Kosten ohne Reise (wie bei „Alle Exporte“).
- **Formular:** `datetime.…_tour_von`, `…_tour_bis`, `text.…_tour_titel`, `button.…_tour_erstellen`,
  `…_tour_aktualisieren`. Mit einer Reise in der Auswahl: von = Reisebeginn, bis = jetzt, Titel leer (Vorschlag). Mit
  einer Tour: deren Zeitraum und Titel; „Tour aktualisieren“ übernimmt sie. Nach dem Erstellen wählt die
  Export-Auswahl die neue Tour.
- **Rückmeldung (23.11.2026):** `binary_sensor.…_tour_in_arbeit` (Gerätetyp „läuft“) ist an, solange eine Tour
  erstellt, geändert oder nach einer Kostenänderung neu erstellt wird, auch bei einem Fehler nur bis zu dessen
  Meldung. Das Dashboard zeigt damit „Tour wird erstellt …“; der Knopf selbst gibt bis zum Ende keine Rückmeldung.
- **Dateityp:** neuer Typ `days` (`<titel>_tage.csv`) für „Exporte aufräumen“.
- **Push (6.5):** wie bei Reisen ohne Bildanhang (das Gesamtbild ist für iOS zu groß); Tippen öffnet das Dashboard.
