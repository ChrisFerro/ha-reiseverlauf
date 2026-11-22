# Feat-09: Nachträge (Tankstopp und Reisekosten)

Stand: 20.11.2026, Fragen geklärt (Abschnitt 5); Entwurf der Umsetzung zur Freigabe (Abschnitt 6).
Übergeordnete Anforderungen und Entitäten: [ANFORDERUNGEN.md](../ANFORDERUNGEN.md). Grundlage:
[Fahrtenbuch](feat-06-fahrtenbuch.md), [Export](feat-03-export.md).

## 1. Ziel

Kosten, die nicht im Moment des Halts erfasst werden, lassen sich später nachtragen:

1. **Tankstopp nachtragen:** Unterwegs wird getankt, aber keine Zeit für das Formular. Später (am Abend, nach der
   Reise) wird der Tankbeleg mit Litern und Betrag dem richtigen Halt bzw. Zeitpunkt zugeordnet, sodass
   Kilometerstand, Ø-Verbrauch und Kosten stimmen, als wäre er sofort eingetragen worden.
2. **Reisekosten nachtragen:** Die Mautbox rechnet erst im Folgemonat ab. Die Mautkosten werden dann je Reise und je
   Land eingetragen; ebenso weitere Reisekosten (Vignette, Fähre, Tunnel, Stellplatz). Sie fließen in die Kosten der
   Reise und die Kostensensoren ein.

## 2. Anforderungen

### 2.1 Tankstopp nachtragen

- **Zuordnung zu einem Stopp:** Der Nutzer wählt einen vergangenen Halt oder kurzen Stopp (Zeit, Ort) aus einer
  Liste, z. B. „14.11. 10:42 · Irschenberg“. Hat er schon einen Fahrtenbuch-Eintrag, wird dieser um den Tankstopp
  ergänzt; sonst entsteht ein neuer Eintrag mit Zeit, Ort und Zählerständen des Stopps (5.2).
- **Freie Zeit:** Passt kein Stopp, wird der Zeitpunkt von Hand angegeben; Zählerstände und Position kommen aus der
  Spur der Reise zu diesem Zeitpunkt (5.1).
- **Felder:** Liter und Betrag für Diesel bzw. Gas; der Füllstand gilt zu diesem Zeitpunkt als 100 % (beim Gas
  beide Tanks, siehe [Fahrtenbuch](feat-06-fahrtenbuch.md) 5.3, 5.7). Kilometerstand wird vorgeschlagen
  (fortgeschrieben bis zu diesem Zeitpunkt) und ist korrigierbar.
- **Folgen:** Ø-Verbrauch, Heizung im Stand, Kostensensoren, CSV und der Export der Reise (5.8) rechnen mit dem
  Nachtrag, als wäre er rechtzeitig erfasst worden. Spätere Füllstands-Einträge bleiben unverändert.

### 2.2 Reisekosten nachtragen

- **Je Reise, Kategorie und Land:** z. B. Maut Österreich 23,40 €, Maut Italien 61,10 €, Fähre 85 € (5.4, 5.6).
  Mehrere Einträge je Reise; Korrigieren und Löschen möglich.
- **Länderliste:** Die Integration schlägt die Länder vor, durch die die Reise geführt hat, damit nur noch die
  Beträge einzutragen sind.
- **Auswertung:** Reisekosten zählen im Monat der Reise (5.5) in den Kostensensoren (5.10), in der Statistik der
  Reise (5.8) und in einer CSV-Datei.
- **Erinnerung** an Reisen durch Mautländer ohne Maut-Eintrag (5.9).

### 2.3 Gemeinsam

- Bedienung über das Dashboard (ohne Eintrags-IDs abtippen) und über Dienste (für Automationen).
- Nur Zahlen, kein Beleg-Foto (5.3); alle Beträge in Euro (5.7).
- Die Daten liegen im Fahrtenbuch-Speicher (`.storage`) wie die übrigen Einträge
  ([Fahrtenbuch](feat-06-fahrtenbuch.md) 5.6) und sind damit im HA-Backup enthalten.

## 3. Ausgangslage (Stand v0.2.4)

- **`fahrtenbuch_eintragen` mit `zeit`** legt zwar einen Eintrag mit früherer Zeit an, nimmt aber Streckenzähler,
  Höhenmeter-Zähler, Position, Ort und laufende Reise von **jetzt**. Der vorgeschlagene Kilometerstand kommt vom
  neuesten Eintrag statt vom letzten Eintrag vor diesem Zeitpunkt (`Logbook.suggest_odometer`). Ein so nachgetragener
  Tankstopp verfälscht damit Kilometerstand und Ø-Verbrauch.
- **`fahrtenbuch_aendern`** kann einem bestehenden Eintrag Liter und Betrag hinzufügen, setzt den Füllstand aber
  nicht auf 100 % und braucht die Eintrags-ID (Attribut `letzte_eintraege`, nur die 10 neuesten).
- **Halte ohne Eintrag:** Wird die Erinnerung nicht beantwortet, ersetzt der nächste Anlass den Entwurf; der Halt
  steht danach nur noch im Export (`export.json`, `stops`: Start, Ende, Ort), ohne Zählerstände. Kurze D+-Aus-Phasen
  unter der Mindestdauer werden gar nicht gespeichert.
- **Spur:** Jeder Export (automatisch und manuell) legt die Rohdaten mit Zeitstempeln im Ordner ab; daraus lässt
  sich die Strecke bis zu einem Zeitpunkt berechnen. Während der Reise liegt die Spur im Speicher der laufenden Reise
  (`trip_log`). Die Zählerstände beim Reisebeginn stehen nur im Eintrag zum Reisestart, falls er gespeichert wurde.
- **Land:** Die Ortsabfrage (Nominatim mit `addressdetails`) liefert schon `country` und `country_code`, genutzt
  wird bisher nur der Ortsname.
- **Kosten:** Nur Diesel und Gas (`LogbookEntry.cost`). Ein fertiger Export wird durch spätere Korrekturen nicht
  geändert ([Fahrtenbuch](feat-06-fahrtenbuch.md) 6.5). Das Gesamtbild (`render_composite`) setzt Karte und Profil
  unter einen Kopf; die Karte liegt als Datei vor, das Profil lässt sich aus den Rohdaten ohne Kachel-Downloads neu
  zeichnen.

## 4. Offene Fragen (vor der Umsetzung einzeln klären)

1. ~~**Tankstopp ohne Halt:** Kommt es vor, dass ein Tankstopp kürzer als die Mindestdauer eines Halts (5 min) ist,
   oder reicht die Auswahl aus den erkannten Halten? (Davon hängt ab, ob „freie Zeit“ mit Spur-Auswertung nötig ist.)~~
   – entschieden, siehe 5.1.
2. ~~**Bedienung Tankbeleg:** Formular im Dashboard mit Auswahlliste der letzten Halte (z. B. `select.…_nachtrag_halt`
   plus die vorhandenen Felder Diesel/Gas getankt und Betrag) oder nur ein Dienst mit Zeit-Feld?~~ – entschieden,
   siehe 5.2.
3. ~~**Beleg als Foto:** Soll ein Foto des Tankbelegs bzw. der Mautabrechnung gespeichert werden (z. B. Upload in
   den Medienordner), oder genügen die Zahlen?~~ – entschieden, siehe 5.3.
4. ~~**Maut-Zuordnung:** Rechnet die Mautbox je Durchfahrt mit Datum ab (dann Zuordnung zur Reise über das Datum
   möglich) oder nur als Monatssumme je Land? Kann eine Abrechnung mehrere Reisen enthalten?~~ – entschieden, siehe
   5.4.
5. ~~**Maut-Monat:** Zählen die Mautkosten in den Kostensensoren im Monat der Reise oder im Monat der Abrechnung?~~
   – entschieden, siehe 5.5.
6. ~~**Weitere Kosten:** Nur Maut, oder auch Vignetten, Fähren, Tunnel, Stellplatz/Campingplatz – also eine
   allgemeine Kostenart „Reisekosten“ mit Kategorie?~~ – entschieden, siehe 5.6.
7. ~~**Währung:** Immer Euro (Mautbox rechnet in € ab), oder auch Fremdwährungen (CHF, NOK …)?~~ – entschieden,
   siehe 5.7.
8. ~~**Export aktualisieren:** Sollen Statistik, Gesamtbild und `export.json` einer fertigen Reise nach einem
   Nachtrag neu erstellt werden (z. B. Knopf „Statistik aktualisieren“ oder automatisch), oder bleibt der Export
   unverändert und die Nachträge stehen nur im Fahrtenbuch/CSV?~~ – entschieden, siehe 5.8.
9. ~~**Erinnerung:** Soll die Integration an fehlende Angaben erinnern (z. B. Halt mit Tankstelle ohne Tankeintrag,
   Reise durch Mautländer ohne Maut nach Monatsende)?~~ – entschieden, siehe 5.9.
10. ~~**Vorhandene Kostensensoren:** Werden `sensor.…_tank_und_gaskosten_monat`/`_jahr` zu „Reisekosten“ umbenannt
    (neue Entity-IDs, Dashboard anpassen) oder bleiben sie und die Reisekosten-Sensoren kommen dazu (5.6)?~~ –
    entschieden, siehe 5.10.

## 5. Entscheidungen

Entscheidungen werden hier mit Datum eingetragen, die Frage in Abschnitt 4 wird dann durchgestrichen
(wie in [ANFORDERUNGEN.md Abschnitt 9](../ANFORDERUNGEN.md#9-offene-entscheidungen)).

- **5.1 Tankstopp ohne Halt** – entschieden (20.11.2026): Kommt vor, manchmal ist das Tanken kürzer als die
  Mindestdauer eines Halts. Neben der Auswahl aus den erkannten Halten wird daher auch ein Nachtrag mit freier
  Uhrzeit benötigt. Streckenzähler, Höhenmeter-Zähler und Position werden dann aus der Spur zu diesem Zeitpunkt
  ermittelt (laufende Reise: `trip_log`, fertige Reise: Rohdaten des Exports), der Ort über die Ortsabfrage.
- **5.2 Bedienung Tankbeleg** – entschieden (20.11.2026): Formular im Dashboard.
  - **Auswahlliste** der letzten Halte (Datum, Uhrzeit, Ort), neueste zuerst; letzter Punkt „Andere Uhrzeit …“ mit
    einem Feld für Datum und Uhrzeit (5.1).
  - **Kurze Stopps:** Auch D+-Aus-Phasen unter der Mindestdauer eines Halts werden mit Zeit, Position und Zählern
    gemerkt und erscheinen in der Liste (gekennzeichnet als kurzer Stopp). Sie lösen keine Erinnerung aus und zählen
    nicht als Halt der Reise (Pausenzeit, Halte-Attribut, Export bleiben unverändert).
  - **Felder:** die vorhandenen Formularfelder Diesel/Gas getankt und Betrag, dazu Kilometerstand (vorgeschlagen
    für den gewählten Zeitpunkt, korrigierbar); Knopf „Nachtragen“.
  - Für Automationen gibt es dasselbe als Dienst.
- **5.3 Kein Beleg-Foto** – entschieden (20.11.2026): Es werden nur die Zahlen erfasst (Liter, Betrag, Mautbetrag),
  kein Foto oder Upload von Tankbeleg oder Mautabrechnung.
- **5.4 Maut-Zuordnung** – entschieden (20.11.2026): Die Abrechnung der Mautbox (monatlich, im Folgemonat) listet
  jede Durchfahrt mit Datum und Land. Der Nutzer ordnet die Durchfahrten über das Datum der Reise zu und trägt je
  Reise und Land die Summe ein; eine Abrechnung kann mehrere Reisen enthalten. Keine Eingabe einzelner Durchfahrten,
  keine automatische Aufteilung einer Monatssumme.
- **5.5 Maut-Monat** – entschieden (20.11.2026): Mautkosten zählen im Monat (und Jahr) der Reise, maßgeblich ist
  der Reisebeginn (Ortszeit), nicht der Monat der Abrechnung oder des Nachtrags. Ein Nachtrag ändert damit den
  Monats- bzw. Jahreswert eines vergangenen Zeitraums nachträglich. Ebenso zählt ein nachgetragener Tankstopp im
  Monat seines Zeitpunkts. Ergänzt durch [Tour](feat-10-tour.md) 5.4: Jede Kosten-Position hat ein Datum (bei
  Zuordnung zu einer Reise standardmäßig deren Beginn), und sie zählt im Monat dieses Datums.
- **5.6 Allgemeine Reisekosten** – entschieden (20.11.2026): Statt nur Maut gibt es eine allgemeine Kostenart
  **Reisekosten** mit Kategorie: `maut`, `vignette`, `faehre`, `tunnel`, `stellplatz`, `sonstiges`. Ein Eintrag hat
  Reise, Kategorie, Betrag, optional Land und Notiz; Maut wird je Reise und Land eingetragen (5.4). Die Kosten
  zählen im Monat der Reise (5.5). Kostensensoren für alle Kosten (Diesel, Gas, Reisekosten) mit den einzelnen
  Arten als Attribute; die vorhandenen Tank- und Gaskosten-Sensoren werden ersetzt (5.10).
- **5.7 Währung** – entschieden (20.11.2026): Alle Beträge in der Währung der Instanz (Euro), wie bei Tank- und
  Gasstopps. Keine Fremdwährung, kein Umrechnungskurs; Beträge in Fremdwährung rechnet der Nutzer vor dem Eintragen
  um.
- **5.8 Export aktualisieren** – entschieden (20.11.2026): Nach jedem Nachtrag zu einer Reise (Tankstopp,
  Reisekosten, auch Ändern und Löschen) aktualisiert die Integration deren Export automatisch: Statistik,
  `export.json` (`logbook`, Reisekosten) und Gesamtbild werden neu erstellt, Karte, Profil, GPX und Rohdaten
  bleiben. Abweichend von [Fahrtenbuch](feat-06-fahrtenbuch.md) 6.5 („ein später korrigierter Eintrag ändert einen
  fertigen Export nicht“) gilt das für alle Fahrtenbuch-Änderungen an Einträgen einer fertigen Reise.
  - Das Gesamtbild wird aus der vorhandenen Karte und dem Profil zusammengesetzt, ohne neue Kachel-Downloads;
    Rendern außerhalb des Event-Loops.
  - Fehlen Dateien (z. B. nach `aufraeumen`), wird nur aktualisiert, was noch vorhanden ist.
  - Das Event `reiseverlauftracker_beendet` wird nicht erneut ausgelöst (keine zweite Push-Nachricht).
- **5.9 Maut-Erinnerung** – entschieden (20.11.2026): Nur für die Maut, keine Hinweise auf fehlende Tankstopps.
  - Ein Sensor `sensor.…_maut_offen` zählt die fertigen Reisen, die durch ein Mautland führten (Länder der Reise aus
    Halten und Spur, siehe 6.2) und noch keinen Maut-Eintrag haben; Attribut mit der Liste dieser Reisen (Titel, Start, Länder).
  - Eine Reise lässt sich mit „keine Maut“ abhaken (z. B. nur Landstraße gefahren).
  - Push-Nachricht am Monatsanfang, solange Reisen offen sind; im Blueprint abschaltbar.
  - Welche Länder als Mautland gelten, ist eine Einstellung im Options-Flow (Ländercodes); der Standard wird bei der
    Umsetzung festgelegt.
- **5.10 Kostensensoren ersetzen** – entschieden (20.11.2026): `sensor.…_tank_und_gaskosten_monat`/`_jahr` werden
  durch `sensor.…_reisekosten_monat`/`_jahr` ersetzt (alle Kosten: Diesel, Gas und Reisekosten nach Kategorie).
  - **Neue `unique_id`** (nicht nur neuer Name), damit auch die Entity-ID neu ist; Home Assistant behält sonst die
    alte Entity-ID. Die alten Einträge entfernt die Integration beim Update aus der Entitätsregistrierung.
  - **Breaking Change:** Commit als `feat!`, die Release-Notes nennen die zu ersetzenden Entity-IDs. Das Dashboard
    des Nutzers wird danach angepasst (nur nach Freigabe, siehe [CLAUDE.md](../../CLAUDE.md)).
  - **Bedeutung:** Der Zustand enthält alle Kosten; Diesel, Gas und jede Kategorie stehen als Attribute dabei
    (Diesel + Gas allein z. B. für bisherige Auswertungen).
  - Kein Verlust an Daten: Kosten haben keine Langzeitstatistik und werden aus den Einträgen berechnet; die neuen
    Sensoren zeigen sofort die Summen, auch für vergangene Zeiträume.
- **5.11 Stopps in der Auswahl** – entschieden (21.11.2026): Gespeichert werden alle Stopps der letzten 120 Tage
  (6.1), ohne Obergrenze. Die Auswahl im Formular bietet zwei Wege:
  - **Unterwegs:** die 30 neuesten Stopps (auch der laufenden Reise) oder „Andere Uhrzeit …“; liegt ein
    gespeicherter Stopp wenige Minuten um die Uhrzeit, wird er zugeordnet.
  - **Später:** alle Stopps der Reise, die in der Export-Auswahl gewählt ist (wie bei den Reisekosten).
  - Die 30 begrenzen nur die Anzeige, es wird nichts verworfen.

## 6. Entwurf der Umsetzung (zur Freigabe)

Stand: 20.11.2026, an die Entscheidungen 5.1–5.11 angepasst.

### 6.1 Stopps merken

- **Stopp-Liste** im Fahrtenbuch-Speicher (`stopps`): jede D+-Aus-Phase während einer Reise mit Start, Ende,
  Position, Ort, Strecken- und Höhenmeter-Zählern beim Beginn des Stopps. Die Art (Halt ab der Mindestdauer,
  kurzer Stopp darunter, 5.2) ergibt sich aus der Dauer.
  Ein fortgesetzter Halt (Tanken, dann Umparken) bleibt ein Eintrag. Kurze Stopps lösen kein Event und keine
  Erinnerung aus und ändern Pausenzeit, Halte-Attribut und Export nicht.
- **Ort kurzer Stopps** wird wie beim Halt abgefragt, aber erst nach dem Export der Reise im Hintergrund (Nominatim:
  höchstens eine Anfrage je Sekunde).
- **Aufbewahrung:** Stopps der letzten 120 Tage (Maut kommt im Folgemonat, dazu Puffer); ältere werden beim Start
  entfernt. Fahrtenbuch-Einträge bleiben davon unberührt.
- **Zählerstände je Reise:** Beim Reisebeginn speichert die Integration Strecken- und Höhenmeter-Zähler in der Reise
  und in `export.json` (`counter_start`). Damit lassen sich die Zähler zu jedem Zeitpunkt der Spur berechnen (6.2).

### 6.2 Tankstopp nachtragen

- **`Logbook` für frühere Zeitpunkte:** `suggest_odometer`, der Vergleich „Kilometerstand korrigiert“ und der
  Kraftstoff-Vorschlag beziehen sich auf den letzten Eintrag **vor** dem Zeitpunkt des Nachtrags, nicht auf den
  neuesten. Die Auswertungen (Ø-Verbrauch, Heizung im Stand) rechnen bereits nach Zeit sortiert.
- **Zähler aus der Spur (5.1):** Zählerstand beim Reisebeginn (6.1) plus Strecke bzw. Höhenmeter der Spur bis zum
  Zeitpunkt, mit denselben Filtern wie die Reisestrecke (3-s-Zusammenfassung, GPS-Genauigkeit, Punktabstand,
  Höhen-Hysterese). Quelle: laufende Reise (`trip_log`) oder Rohdaten des Exports. Für ältere Reisen ohne
  `counter_start` gilt der Zähler des Reisestart-Eintrags; fehlt auch der, wird zwischen den Einträgen davor und
  danach nach Zeit interpoliert und der Kilometerstand muss bestätigt werden.
- **Formular (5.2):** Das vorhandene Fahrtenbuch-Formular bekommt eine Auswahl `select.…_fahrtenbuch_zeitpunkt`:
  - erster Punkt „Aktuell“ (offener Anlass bzw. manueller Eintrag jetzt, wie bisher),
  - danach die Stopps (5.11), neueste zuerst (`14.11. 10:42 · Irschenberg`, kurze Stopps mit Zusatz „kurz“): die
    30 neuesten Stopps über alle Reisen (auch die laufende) und zusätzlich alle Stopps der Reise, die in
    `select.…_export_auswahl` gewählt ist; doppelte nur einmal,
  - zuletzt „Andere Uhrzeit …“ mit `datetime.…_fahrtenbuch_nachtrag_zeit`.
  - Bei Auswahl eines früheren Zeitpunkts belegt die Integration die Felder mit dem vorhandenen Eintrag dieses
    Stopps oder dem Vorschlag für den Zeitpunkt vor. Ein offener Entwurf zum aktuellen Anlass bleibt erhalten und
    kehrt mit „Aktuell“ zurück; nach dem Speichern springt die Auswahl auf „Aktuell“.
  - Knopf `button.…_fahrtenbuch_nachtragen` speichert für den gewählten Zeitpunkt (ergänzt den vorhandenen Eintrag
    oder legt einen an, Anlass `nachtrag`); „Speichern“ bleibt für den aktuellen Anlass.
- **Dienst `fahrtenbuch_nachtragen`** (`zeit`, `diesel_liter`, `diesel_betrag`, `gas_liter`, `gas_betrag`,
  `kilometerstand` optional): wie der Knopf; ein Stopp bis 5 Minuten um `zeit` wird automatisch zugeordnet. Sind die
  Zähler zu `zeit` nur geschätzt, ist `kilometerstand` Pflicht. Antwort: der neue bzw. geänderte Eintrag.
- **Zeit zwischen zwei Reisen** (entschieden 22.11.2026): Die Zähler ändern sich nur während der Fahrt; es gilt der
  Stand am Ende der Reise davor (gleich dem Stand beim Beginn der nächsten Reise).
- **Kennzeichen „geschätzt“:** `select.…_fahrtenbuch_zeitpunkt` zeigt in den Attributen `zeit`, `ort` und `geschaetzt`
  (Kilometerstand bestätigen).
- **Füllstand:** Liter über 0 setzen Kraftstoff bzw. beide Gastanks an diesem Eintrag auf 100 %, wie im Formular.

### 6.3 Reisekosten

- **Datensatz** `TravelCost` (reines Python, im Fahrtenbuch-Speicher, [Tour](feat-10-tour.md) 5.4): `id`, `datum`
  (Pflicht), optional `reise_start` (Verknüpfung mit der Reise; dann ist `datum` standardmäßig der Reisebeginn),
  `kategorie` (`maut`, `vignette`, `faehre`, `tunnel`, `stellplatz`, `sonstiges`), `betrag`, optional `land`
  (ISO-Code, z. B. `AT`) und `notiz`, `erfasst` (Zeitpunkt der Eingabe). Je Reise zusätzlich das Kennzeichen
  `keine_maut` (5.9).
- **Länder der Reise:** Nach dem Export ermittelt die Integration die Länder aus Start, Halten, Ende und Spurpunkten
  etwa alle 20 km (Punkte unter 1 km Abstand entfallen; Nominatim mit `zoom=3`, Abstand 1 s, im Hintergrund, nur
  mit eingeschalteten Ortsnamen) und speichert sie in `export.json` (`countries`, ISO-Codes in Reihenfolge).
  Für ältere Exporte wird das nachgeholt, sobald die Reise im Formular gewählt ist (einmal je Start von HA).
- **Formular:** Reise über die vorhandene `select.…_export_auswahl`; dazu `select.…_reisekosten_kategorie`,
  `select.…_reisekosten_land` (Länder der Reise zuerst, dann die Mautländer der Einstellung, „ohne Land“; Standard
  ist das erste Mautland der Reise, auch nach dem Wechsel der Reise), `number.…_reisekosten_betrag`, `text.…_reisekosten_notiz`,
  `date.…_reisekosten_datum`, Knöpfe `button.…_reisekosten_speichern` und `button.…_keine_maut` (schaltet um).
  Nach dem Speichern werden Betrag und Notiz geleert, Kategorie und Land bleiben (nächstes Land schnell
  eingetragen). Das Attribut `reisekosten` an der Export-Auswahl listet die Einträge der gewählten Reise (mit `id`),
  die Summe je Kategorie (`summen`) und gesamt (`summe`), `laender` und `keine_maut`.
- **Datum im Formular** (entschieden 22.11.2026): `date.…_reisekosten_datum` springt bei Wahl einer Reise auf
  deren Beginn (Ortszeit) und ist änderbar. Steht die Export-Auswahl auf „Alle Exporte“, wird die Position ohne
  Reise mit diesem Datum gespeichert.
- **Dienste:** `reisekosten_eintragen` (`datum`, `reise` als Startzeit oder Ordner, beide optional, aber eines nötig;
  `kategorie`, `betrag`, `land`, `notiz`),
  `reisekosten_aendern` (`eintrag`, Felder), `reisekosten_loeschen` (`eintrag`), `keine_maut` (`reise`, an/aus).
- **CSV:** eigene Datei `reisekosten.csv` im Ausgabeordner (eine Zeile je Eintrag: Datum, Reise, Titel, Kategorie,
  Land, Betrag, Notiz), Format wie `fahrtenbuch.csv`, neu geschrieben nach jeder Änderung, im geschützten Download
  ([Downloads](feat-07-downloads.md)); `aufraeumen` lässt sie in Ruhe.

- **Zusammenhang mit [Tour](feat-10-tour.md) 5.4:** Kosten zwischen zwei Reisen (z. B. Stellplatz einer Woche)
  gehören zu keiner Reise; sie werden nur mit Datum eingetragen („ohne Reise“ in der Reise-Auswahl des Formulars
  bzw. ohne `reise` im Dienst). Eine Tour sammelt alle Kosten, deren Datum in ihren Zeitraum fällt.

### 6.4 Export aktualisieren (5.8)

- Nach jeder Änderung an Fahrtenbuch-Einträgen oder Reisekosten einer fertigen Reise: Statistik, `export.json`
  (`logbook` mit Reisekosten je Kategorie und Gesamtkosten) und Gesamtbild neu erstellen. Mehrere Änderungen
  kurz hintereinander werden zusammengefasst (z. B. 30 s warten).
- Gesamtbild aus der vorhandenen Kartendatei und dem aus den Rohdaten neu gezeichneten Profil (ohne Titel, wie beim
  Export); in einem Executor, nie im Event-Loop. Kopfzeile wie bisher, Kosten inklusive Reisekosten.
- Fehlen Dateien (nach `aufraeumen`), wird nur erneuert, was vorhanden ist; ohne `export.json` gar nichts.
- Kein erneutes Event `_beendet`. Sensoren „Letzte Reise“ und die Bild-Entität zeigen danach den neuen Stand.

### 6.5 Kostensensoren und Erinnerung

- **`sensor.…_reisekosten_monat` und `…_jahr` (5.10):** Summe aus Diesel, Gas und Reisekosten im laufenden
  Kalendermonat bzw. -jahr (Ortszeit); Tank- und Gasstopps nach ihrem Zeitpunkt, Reisekosten nach ihrem Datum
  (5.5). Attribute `diesel`, `gas` und je Kategorie (`maut`, `vignette` …). Neue `unique_id`; die alten Entitäten
  `…_tank_und_gaskosten_monat`/`_jahr` werden beim Start aus der Entitätsregistrierung entfernt.
- **`sensor.…_maut_offen` (5.9):** Anzahl der fertigen Reisen der letzten 12 Monate mit mindestens einem Mautland,
  ohne Maut-Eintrag und ohne `keine_maut`; Attribut `reisen` (Titel, Start, Länder, Ordner).
- **Einstellung „Mautländer“** im Options-Flow (Abschnitt Fahrtenbuch, Mehrfachauswahl; umgesetzt in Teilschritt 4).
  Standard: `AT`, `BE`, `CH`, `CZ`, `ES`, `FR`, `HR`, `HU`, `IT`, `NO`, `PL`, `PT`, `SI`, `SK` (streckenabhängige
  Maut oder Gebühr für Wohnmobile über 3,5 t; nicht `DE`, Wohnmobile sind von der Lkw-Maut befreit).
- **Blueprint:** Der Fahrtenbuch-Blueprint bekommt eine abschaltbare Monats-Erinnerung (am 1. des Monats, wenn
  `maut_offen` über 0), Tippen öffnet die Dashboard-Ansicht mit dem Reisekosten-Formular.

### 6.6 Abgrenzung

- Kein Abruf der Mautabrechnung beim Anbieter (keine Schnittstelle bekannt); Eingabe von Hand.
- Kein Beleg-Foto (5.3), keine Texterkennung (OCR), keine Fremdwährungen (5.7).
- Keine Hinweise auf fehlende Tankstopps (5.9).
- Kurze Stopps zählen nicht als Halte der Reise (Pausenzeit, Export), siehe 6.1.

### 6.7 Teilschritte

Jeder Schritt mit Tests, grünem `script/check` und einem Prüfpunkt in der Entwicklungsumgebung:

1. `Logbook` für frühere Zeitpunkte (6.2, erster Punkt) und `TravelCost` mit Kosten je Zeitraum und CSV (6.3),
   reines Python mit Tests. – umgesetzt 21.11.2026
2. Stopp-Liste und Zählerstände je Reise (6.1), Zähler aus der Spur (6.2). Prüfpunkt: simulierte Reise mit kurzem
   Stopp, Stopp mit Zählerständen im Speicher. – umgesetzt 21.11.2026
3. Tankstopp nachtragen: Auswahl, Knopf, Dienst, Übersetzungen. Prüfpunkt: Tankstopp einer vergangenen Reise
   nachtragen, Ø-Verbrauch und Kilometerstand stimmen. – umgesetzt 22.11.2026
4. Reisekosten: Länder der Reise, Formular, Dienste, CSV. Prüfpunkt: Maut für zwei Länder eintragen.
   – umgesetzt 22.11.2026
5. Export aktualisieren (6.4). Prüfpunkt: Statistik und Gesamtbild zeigen die nachgetragenen Kosten.
6. Kostensensoren ersetzen und Erinnerung (6.5), Blueprint, README (deutsch/englisch), Release-Notes für den
   Breaking Change. Danach (nach Freigabe) Dashboard des Nutzers anpassen.
