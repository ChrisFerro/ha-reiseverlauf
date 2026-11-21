# Feat-06: Fahrtenbuch

Stand: 18.11.2026, umgesetzt (Teilschritte 1 bis 5 von 6.7); offen ist der Test mit dem echten Fahrzeug.
Übergeordnete Anforderungen, Entscheidungen und Begriffe: [ANFORDERUNGEN.md](../ANFORDERUNGEN.md).

## 1. Ziel

Die Integration wird zu einem Fahrtenbuch erweitert. Zu jedem Halt einer Reise (siehe
[ANFORDERUNGEN.md 9.20](../ANFORDERUNGEN.md#9-offene-entscheidungen)) werden Fahrzeug- und Vorratsdaten
festgehalten, Tank- und Gasstopps mit Menge und Kosten. Daraus entstehen Verbrauchs- und Kostenauswertungen.

## 2. Bekannte Anforderungen

- **Je Halt:** Kilometerstand und Füllstand des Kraftstofftanks (0–100 %).
- **Zwei fest verbaute Gastanks:** jeweils Füllstand 0–100 % (zwei Anzeigen), ebenfalls je Halt protokolliert.
- **Tankstopp:** Der Kraftstofftank geht wieder auf 100 %; erfasst werden getankte Liter und der Betrag in €.
- **Gasstopp:** Beim Nachfüllen werden immer beide Gastanks befüllt; erfasst werden die getankten Liter Gas
  (gesamt) und der Betrag in €, beide Gastanks gehen auf 100 %.
- **Anknüpfung:** Die Daten hängen am Halt-Datensatz der Reise (`TripStop` mit Zeit, Position, Ort, Dauer).
  Er ist dafür ausgelegt, um weitere Felder ergänzt zu werden, ohne bestehende Reisen umzubauen.

## 3. Ausgangslage (Stand v0.1.5)

- **Halte:** Ein Halt beginnt, wenn D+ während einer Reise ausgeht, und zählt ab der Mindestdauer (Standard 5 min).
  Geht D+ kurz an, ohne dass sich das Fahrzeug weiter als die Mindestbewegung entfernt (z. B. Tanken und
  Umparken), setzt das nächste D+-Aus denselben Halt fort (seit v0.1.5).
- **Noch nicht gespeichert:** die einzelnen D+-Aus-Phasen innerhalb eines Halts. Für Tankstopps kann das nützlich
  sein (Zapfsäule, dann Parkplatz) und gehört zum Ausbau von `TripStop` in dieser Etappe.
- **Manueller Export:** ermittelt keine Halte (D+ wird aus dem Recorder nicht ausgewertet).
- **Strecke:** stimmt seit v0.1.5 mit dem Tacho überein (31.10.2026: 84,2 km laut Integration, 84 km laut Tacho,
  Kilometerstand 34299 → 34383). Der Kilometerstand aus dem Fahrtenbuch kann künftig zur Kontrolle der Strecke
  dienen.

## 4. Offene Fragen (vor der Umsetzung einzeln klären)

1. ~~**Quellen:** Gibt es Kilometerstand, Tankfüllstand und Gasfüllstände schon als Sensoren in Home Assistant
   (z. B. CAN-Bus-Adapter, Victron, Füllstandssensor an der Gasflasche), oder werden sie von Hand eingegeben?~~
   – entschieden, siehe 5.1.
2. ~~**Eingabe:** Bei Handeingabe ein Formular (z. B. Skript mit Feldern wie beim Export). Wann erscheint es: bei
   jedem Halt, nur bei Tankstopps, per Push-Erinnerung?~~ – entschieden, siehe 5.2.
3. ~~**Tankstopp erkennen:** automatisch über einen Sprung im Füllstand oder ausdrücklich per Knopf/Aktion?~~
   – entschieden, siehe 5.3.
4. ~~**Auswertungen:** Verbrauch je 100 km, Kosten je Reise/Monat, Gasverbrauch je Tag, Export als CSV, Darstellung
   im Dashboard, Aufnahme in die Statistik eines Exports?~~ – entschieden, siehe 5.4.
5. ~~**Halte ohne Reise:** Sollen auch Einträge außerhalb einer Reise möglich sein (z. B. Gasflasche auf dem
   Campingplatz getauscht)?~~ – entschieden, siehe 5.5.
6. ~~**Aufbewahrung:** Wo liegen die Fahrtenbuch-Daten dauerhaft (eigener Speicher, Datei im Medienordner) und wie
   werden sie gesichert bzw. gelöscht?~~ – entschieden, siehe 5.6.

## 5. Entscheidungen

Entscheidungen werden hier mit Datum eingetragen, die Frage in Abschnitt 4 wird dann durchgestrichen
(wie in [ANFORDERUNGEN.md Abschnitt 9](../ANFORDERUNGEN.md#9-offene-entscheidungen)).

- **5.1 Quellen** – entschieden (17.11.2026): In der Live-Instanz gibt es keine Sensoren für Kilometerstand,
  Kraftstofftank oder Gasflaschen (am Victron GX hängen nur die Frischwassertanks). Daher:
  - **Kilometerstand** wird fortgeschrieben: letzter eingegebener Stand plus gemessene Strecke der Reise. Der Nutzer
    korrigiert ihn nur bei Bedarf; die Abweichung dient zugleich zur Kontrolle der Strecke (siehe 3).
  - **Füllstände** (Kraftstofftank, zwei Gastanks) werden von Hand eingegeben.
  - Sensoren als Quelle bleiben als spätere Erweiterung möglich.
- **5.2 Eingabe** – entschieden (17.11.2026): Erfassung per Push-Erinnerung mit Formular.
  - **Bei jedem Halt** (ab der Mindestdauer) kommt eine Push-Nachricht. Das Formular zeigt den berechneten
    Kilometerstand zum Korrigieren; Kraftstofftank und beide Gastanks sind mit dem jeweils letzten Wert
    vorbelegt.
  - **Beim Start einer Reise** kommt ebenfalls eine Push-Nachricht, um die letzten Werte zu bestätigen bzw. zu
    korrigieren: Auch im Stand werden Gas und Diesel verbraucht (Heizung), die Werte vom Reiseende stimmen dann
    nicht mehr.
- **5.3 Tankstopp erkennen** – entschieden (17.11.2026): Optionale Felder im Halt-Formular (5.2), je einmal für
  Kraftstoff und für Gas: Menge in Litern und Betrag in €. Sind sie ausgefüllt, gilt der Halt als Tank- bzw.
  Gasstopp; die Füllstände werden dann auf 100 % vorgeschlagen (beim Gas beide Tanks, siehe 5.7). Keine automatische Erkennung über
  den Füllstand, kein eigener Knopf.
- **5.4 Auswertungen** – entschieden (17.11.2026):
  - **Reise-Export:** Statistik und Gesamtbild enthalten zusätzlich Kilometerstand von/bis, Verbrauch (l/100 km)
    und die Tank- und Gaskosten der Reise.
  - **Sensoren im Dashboard:** aktueller Kilometerstand, letzte Füllstände (Kraftstofftank, Gastank 1 und 2),
    Durchschnittsverbrauch, Kosten im laufenden Monat und Jahr.
  - **CSV-Export** des gesamten Fahrtenbuchs (eine Zeile je Eintrag mit allen Werten).
  - Nicht gewünscht: eigene Auswertung „Gasverbrauch je Tag“.
- **5.5 Einträge ohne Reise** – entschieden (17.11.2026): Ja. Ein Dienst bzw. Knopf „Fahrtenbuch-Eintrag“ öffnet
  dasselbe Formular wie am Halt (5.2, 5.3). Ohne laufende Reise wird ein eigener Eintrag mit Zeit und Position
  gespeichert; er zählt in Kosten, Sensoren und CSV mit.
- **5.6 Aufbewahrung** – entschieden (17.11.2026): Die Einträge liegen im internen Speicher der Integration
  (`.storage`) und sind damit in jedem HA-Backup enthalten. Die CSV-Datei (5.4) wird im Ausgabeordner erzeugt bzw.
  aktualisiert. Der Dienst `aufraeumen` fasst das Fahrtenbuch nicht an; einzelne Einträge werden über einen eigenen
  Dienst korrigiert oder gelöscht.
- **5.7 Gasanlage** – entschieden (17.11.2026): zwei fest verbaute, nachfüllbare Gastanks mit je einer Anzeige
  0–100 %. Beim Nachfüllen werden immer beide befüllt; ein Gasstopp hat daher eine Menge (Liter Gas gesamt) und
  einen Betrag, nicht je Tank. Keine Tauschflaschen, keine Eingabe in kg.
- **5.8 Vorschlag für den Kraftstoff-Füllstand** – entschieden (17.11.2026): Liegt ein Ø-Verbrauch vor (ab dem
  zweiten Tankstopp, 6.5), schlägt das Formular den Füllstand berechnet vor: letzter Füllstand − gefahrene km ×
  Ø-Verbrauch ÷ Tankgröße. Neue Einstellung **Tankgröße** (Liter, Standard 90). Vorher bleibt der letzte Wert der
  Vorschlag. Später (siehe 6.6): Höhenmeter bergauf als zweiter Faktor (erst ab etwa 8 Tankstopps mit Höhendaten
  schätzbar) und Herausrechnen des Heizungsverbrauchs im Stand (Differenz zwischen letztem Halt und nächstem
  Reisestart). Für Gas gibt es keinen berechneten Vorschlag (Verbrauch unabhängig von der Strecke).

- **5.9 Knopf in der Push-Nachricht** – entschieden (18.11.2026): Die Erinnerung (6.3) bekommt einen Knopf
  „Übernehmen“, der den Vorschlag ohne Dashboard speichert; Tippen auf die Nachricht öffnet weiterhin das Formular.
  Der Knopf nennt den Anlass (Zeit), damit eine alte Nachricht nichts für einen späteren Anlass oder als manuellen
  Eintrag speichert. Nach dem Speichern ersetzt eine Bestätigung die Erinnerung. Im Blueprint abschaltbar.

## 6. Entwurf der Umsetzung (zur Freigabe)

Stand: 17.11.2026, freigegeben.

### 6.1 Datenmodell und Speicher

- Eigener `Store` je Eintrag der Integration: `reiseverlauftracker.<entry_id>.logbook` (5.6). Er bleibt über
  Reisen hinweg bestehen; der Speicher der laufenden Reise (`trip_log`) wird dagegen nach jeder Reise gelöscht.
- Ein **Fahrtenbuch-Eintrag** (`LogbookEntry`, reines Python wie `trip_detector`):
  - `id`, `zeit`, `anlass` (`reisestart`, `halt`, `manuell`), `reise_start` und `halt_start` (Verknüpfung mit
    Reise und Halt über die Startzeiten), Position und Ort;
  - `kilometerstand`, `kilometerstand_korrigiert` (ob von Hand geändert);
  - `kraftstoff_prozent`, `gas1_prozent`, `gas2_prozent`;
  - optional `diesel_liter`, `diesel_betrag`, `gas_liter`, `gas_betrag` (5.3, 5.7).
- Der Eintrag hängt über die Startzeiten am Halt, statt Felder in `TripStop` zu ergänzen: Der Halt-Datensatz lebt
  nur so lange wie die laufende Reise, das Fahrtenbuch dauerhaft. Abschnitt 2 („Anknüpfung“) wird entsprechend
  angepasst.
- **Kilometerstand fortschreiben (5.1):** Die Integration zählt die gemessene Strecke über alle Reisen hinweg
  (`gesamtstrecke_m`, im Fahrtenbuch-Speicher). Jeder Eintrag merkt sich diesen Zähler. Vorschlag für den nächsten
  Eintrag = letzter Kilometerstand + (Zähler jetzt − Zähler beim letzten Eintrag), gerundet auf ganze km.
  Der allererste Kilometerstand wird von Hand eingegeben.

### 6.2 Formular

Ein Skript-Formular wie beim Export kann seine Felder nicht mit dem berechneten Kilometerstand oder den letzten
Füllständen vorbelegen. Die Integration bringt das Formular daher als eigene Entitäten mit (keine Helfer):

- `number.…_fahrtenbuch_kilometerstand`, `…_fahrtenbuch_kraftstoff`, `…_fahrtenbuch_gas_1`, `…_fahrtenbuch_gas_2`
  (Prozent, Schieberegler);
- `number.…_fahrtenbuch_diesel_getankt`, `…_diesel_betrag`, `…_gas_getankt`, `…_gas_betrag` (Eingabefeld, 0 = kein
  Tank-/Gasstopp; Beträge in der Währung der Instanz);
- `button.…_fahrtenbuch_speichern` und `button.…_fahrtenbuch_verwerfen`;
- `sensor.…_fahrtenbuch_eintrag`: `offen` oder `gespeichert`, Attribute Anlass, Ort, Halt seit und
  `letzte_eintraege` (die 10 neuesten Einträge mit `id`, gebraucht für `fahrtenbuch_aendern`/`_loeschen`).

Bei jedem Anlass (6.3) belegt die Integration die Felder neu vor: berechneter Kilometerstand, Kraftstoff berechnet
aus Strecke und Ø-Verbrauch (5.8), sonst der letzte Wert, Gas mit den letzten Werten, Mengen und Beträge 0. Ein noch offener Entwurf wird dabei ersetzt. Eine Menge über 0 setzt den Vorschlag des
zugehörigen Füllstands auf 100 % (beim Gas beide Tanks). „Speichern“ legt den Eintrag an; ohne offenen Anlass
entsteht ein manueller Eintrag (5.5) mit Position und Ort des Fahrzeugs, während einer Reise mit Bezug auf sie.
Ein Eintrag zu einem Anlass behält den Streckenzähler des Anlasses, auch wenn er erst später gespeichert wird; sonst
ginge die seitdem gefahrene Strecke für den Kilometerstand verloren. Für Automationen gibt es dasselbe als Dienst.

### 6.3 Anlässe, Events, Push

- **Reisestart** (nicht bei fortgesetzter Reise): Formular vorbelegen, Event `reiseverlauftracker_fahrtenbuch`
  mit `anlass: reisestart`. Daten des Events: `entry_id`, `anlass`, `zeit`, `ort`, `reise_start`, `halt_start`,
  `vorschlag` (`kilometerstand`, `kraftstoff`, `gas_1`, `gas_2`).
- **Halt:** sobald ein Halt die Mindestdauer erreicht (nach der Ortsabfrage), Event mit `anlass: halt`, Ort,
  vorgeschlagenem Kilometerstand. Ein fortgesetzter Halt (Tanken, dann Umparken) löst kein
  zweites Event aus. Die Ankunft am Ziel ist ebenfalls ein Halt; bei der Standardverzögerung von 60 min liegt der
  Eintrag in der Regel vor dem Export.
- **Push:** neuer Blueprint `fahrtenbuch.yaml` (Fahrzeug, Empfänger, Dashboard-Ansicht, Schalter für Reisestart und
  Halt, Knopf „Übernehmen“, siehe 5.9). Tippen auf die Nachricht öffnet die Ansicht mit dem Formular. Die
  bestehende Reise-Nachricht bleibt unverändert.

### 6.4 Dienste

- `fahrtenbuch_eintragen` (`zeit`, `kilometerstand`, `kraftstoff`, `gas_1`, `gas_2`, `diesel_liter`,
  `diesel_betrag`, `gas_liter`, `gas_betrag`, alle optional): Eintrag ohne Formular, z. B. aus einer Automation.
  Ohne `kilometerstand` gilt der fortgeschriebene Stand. Antwort: der neue Eintrag.
- `fahrtenbuch_speichern` (`anlass_zeit` optional): speichert das Formular wie der Knopf. Mit `anlass_zeit` (Feld
  `zeit` des Events) nur, solange genau dieser Anlass offen ist, sonst Fehler `logbook_occasion_not_pending`;
  gebraucht für den Knopf in der Push-Nachricht (5.9). Antwort: der neue Eintrag.
- `fahrtenbuch_aendern` (`eintrag`, Felder) und `fahrtenbuch_loeschen` (`eintrag`): Korrekturen (5.6). Liter 0
  entfernen einen Tank-/Gasstopp, ein Betrag allein ändert nur den Betrag.
- `fahrtenbuch_csv`: schreibt `fahrtenbuch.csv` in den Ausgabeordner (UTF-8 mit BOM für Excel). Antwort: Pfad,
  Medien-URL, Anzahl der Einträge. Die Datei wird außerdem nach jeder Änderung neu geschrieben; `aufraeumen` lässt
  sie in Ruhe.

### 6.5 Auswertungen (5.4)

- **Verbrauch l/100 km** nach der Volltank-Methode: getankte Liter ÷ km seit dem vorherigen Tankstopp. Der erste
  Tankstopp ist nur Ausgangspunkt. Durchschnitt über alle Tankstopps (Summe Liter ÷ Summe km). Er enthält
  vorerst auch den Dieselverbrauch der Heizung im Stand.
- **Sensoren:** `sensor.…_kilometerstand` (letzter Stand + seitdem gemessene Strecke), `…_kraftstoff`, `…_gas_1`,
  `…_gas_2` (letzter Eintrag mit diesem Wert), `…_durchschnittsverbrauch` (l/100 km),
  `…_tank_und_gaskosten_monat` und `…_jahr` (Diesel + Gas im laufenden Kalendermonat bzw. -jahr, Ortszeit). Keine
  Langzeitstatistik für Kosten, sie werden aus den Einträgen berechnet.
- **Reise-Export:** Kilometerstand von/bis (von: Eintrag beim Reisestart; bis: fortgeschriebener Stand beim
  Export), getankte Liter, Kosten und Ø-Verbrauch in der Statistik, als zweite Zeile im Kopf des Gesamtbilds, in
  `export.json` (`logbook`) und im Event `_beendet` (`fahrtenbuch`: `kilometerstand_start`, `kilometerstand_ende`,
  `diesel_liter`, `diesel_kosten`, `gas_liter`, `gas_kosten`, `kosten`, `verbrauch_l_100km`). Ohne Einträge im
  Fahrtenbuch bleibt der Export wie bisher. Ein später korrigierter Eintrag ändert einen fertigen Export nicht. (Geplante Änderung: Export wird nach Nachträgen und Korrekturen automatisch aktualisiert, siehe [feat-09-nachtraege.md](feat-09-nachtraege.md) 5.8.)
- **CSV:** eine Zeile je Eintrag, Spalten wie 6.1, Trennzeichen und Dezimalzeichen passend zur Sprache
  (deutsch: `;` und `,`).

### 6.6 Abgrenzung

- Nicht in dieser Etappe: die einzelnen D+-Aus-Phasen innerhalb eines Halts (Abschnitt 3), Sensoren als Quelle
  (5.1), Gasverbrauch je Tag (5.4), Fahrtenbuch-Daten in manuellen Exporten, Höhenmeter im Kraftstoff-Vorschlag
  und Herausrechnen des Heizungsverbrauchs (5.8); die beiden letzten sind als eigenes Feature geplant, siehe
  [feat-08-verbrauchsmodell.md](feat-08-verbrauchsmodell.md).

### 6.7 Teilschritte

Jeder Schritt mit Tests, grünem `script/check` und einem Prüfpunkt in der Entwicklungsumgebung:

1. `logbook`-Modul (Eintrag, Fortschreibung des Kilometerstands, Verbrauch, Kraftstoff-Vorschlag, Kosten, CSV)
   mit Tests.
2. Speicher und Koordinator: Gesamtstrecke zählen, Anlässe Reisestart/Halt, Event. Prüfpunkt: Event in den
   Entwicklerwerkzeugen bei simuliertem D+.
3. Einstellung Tankgröße (Options-Flow), Formular-Entitäten, Dienste, Übersetzungen. Prüfpunkt: Eintrag über das Formular speichern, CSV im Ausgabeordner.
4. Auswertungs-Sensoren und Reise-Export. Prüfpunkt: Testreise mit Tankstopp, Werte in Statistik und Gesamtbild.
5. Blueprint `fahrtenbuch.yaml`, Dashboard-Ansicht als Beispiel in der README (deutsch/englisch).
