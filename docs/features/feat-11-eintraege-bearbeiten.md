# Feat-11: Einträge bearbeiten

Stand: 23.11.2026, Fragen 1–5 geklärt (Abschnitt 5), Frage 6 offen; Entwurf der Umsetzung zur Freigabe (Abschnitt 6).
Übergeordnete Anforderungen und Entitäten: [ANFORDERUNGEN.md](../ANFORDERUNGEN.md). Grundlage:
[Fahrtenbuch](feat-06-fahrtenbuch.md), [Nachträge](feat-09-nachtraege.md).

## 1. Ziel

Gespeicherte Fahrtenbuch-Einträge lassen sich im Dashboard ändern und löschen, nicht nur über Aktionen. Anlass:
Beim Nachtragen des händisch geführten Fahrtenbuchs (Tour 27.09.–03.10.2026) waren Uhrzeiten vertauscht; korrigieren
ging nur mit `reiseverlauftracker.fahrtenbuch_aendern` und der Eintrags-ID aus einem Attribut.

## 2. Anforderungen

- **Alle Einträge erreichbar**, nicht nur die letzten 10 aus `letzte_eintraege`, auch Nachträge weit zurück.
- **Eintrag wählen** in einer verständlichen Liste (Zeit, Anlass, Ort, Kilometerstand), ohne IDs.
- **Alle Felder ändern:** Zeit, Kilometerstand, Kraftstoff, Gas 1, Gas 2, Diesel und Gas getankt mit Betrag.
- **Löschen** mit Bestätigung.
- Nach dem Ändern wie bisher: CSV neu, Kostensensoren und Ø-Verbrauch neu, Export der betroffenen Reise(n) erneuert
  ([Nachträge](feat-09-nachtraege.md) 5.8).
- Bedienbar auf dem Handy; die bestehenden Formulare (Eintrag, Nachtrag, Reisekosten) bleiben verständlich.
- **„Nicht abgelesen“ erkennbar:** Ein Feld ohne Wert (kein Vorschlag, nicht abgelesen) ist im Formular deutlich von
  0 % zu unterscheiden, beim Erfassen, Nachtragen und Bearbeiten (6.7).

## 3. Ausgangslage (Stand v0.3.0)

- **Aktionen:** `fahrtenbuch_aendern` (eintrag, zeit, kilometerstand, kraftstoff, gas_1, gas_2, diesel_liter,
  diesel_betrag, gas_liter, gas_betrag) und `fahrtenbuch_loeschen` (eintrag); ebenso `reisekosten_aendern` und
  `reisekosten_loeschen` für Reisekosten. Die ID steht im Attribut `letzte_eintraege` von
  `sensor.…_fahrtenbuch_eintrag` (nur die letzten 10) bzw. `reisekosten` der Export-Auswahl.
- **Formular „Eintrag“** (`number.…_fahrtenbuch_*`, Speichern/Verwerfen) füllt den offenen Anlass oder legt einen
  manuellen Eintrag an; **Zeitpunkt** (`select.…_fahrtenbuch_zeitpunkt`) wählt einen Halt oder eine freie Zeit für
  einen Nachtrag. Hat der gewählte Zeitpunkt schon einen Eintrag, ergänzt „Nachtragen“ ihn.
- **Zeit ändern:** `fahrtenbuch_aendern` verschiebt den Eintrag, die gespeicherten Zählerstände (Strecke, Höhenmeter)
  bleiben die der alten Zeit. Für das spätere [Verbrauchsmodell](feat-08-verbrauchsmodell.md) passen sie dann nicht
  mehr zur neuen Zeit.
- **Reisekosten** haben im Dashboard eine Liste je Reise, aber auch nur Ändern und Löschen über Aktionen.
- **Leere Felder:** Ohne Vorschlag (z. B. Nachtrag vor dem ersten Eintrag) zeigt das Formular ein leeres Feld; das
  liest sich leicht als 0 %, gespeichert wird aber „nicht abgelesen“ (`null`). Beim Nachtragen der Tour 27.09.–03.10.
  stand so Gas 1 zweimal leer statt 0 % und wurde mit `fahrtenbuch_aendern` korrigiert (23.11.2026).

## 4. Offene Fragen (vor der Umsetzung einzeln klären)

1. ~~**Umfang:** Nur Fahrtenbuch-Einträge, oder auch Reisekosten im selben Schritt?~~ – entschieden, siehe 5.1.
2. ~~**Formular:** Eigenes Formular „Eintrag bearbeiten“ (eigene Entitäten), oder das vorhandene Fahrtenbuch-Formular
   mit einem Modus „Bearbeiten“ (Zeitpunkt-Auswahl um gespeicherte Einträge erweitert, Knopf „Ändern“)?~~ –
   entschieden, siehe 5.2.
3. ~~**Auswahl:** Wie werden alle Einträge erreichbar, ohne dass die Liste unübersichtlich wird (z. B. die Reise aus
   der Export-Auswahl filtert, sonst die neuesten 30; oder Filter nach Monat)?~~ – entschieden, siehe 5.3.
4. ~~**Zeit ändern:** Sollen die Zählerstände bei einer neuen Zeit aus der aufgezeichneten Strecke neu bestimmt werden
   (wie beim Nachtrag), und der Kilometerstand nur, wenn er nicht von Hand eingetragen war?~~ – entschieden, siehe
   5.4.
5. ~~**Löschen:** Knopf mit Bestätigung im Dashboard reicht, oder zusätzlich „Rückgängig“ (z. B. letzter gelöschter
   Eintrag wiederherstellbar)?~~ – entschieden, siehe 5.5.
6. **Leere Felder:** Wie wird „nicht abgelesen“ im Formular sichtbar (z. B. Hinweis im Formular-Text „Gas 1: nicht
   abgelesen“ über ein Attribut der Formular-Entität, Rückfrage beim Speichern mit leeren Feldern), und lässt sich
   ein Wert wieder auf „nicht abgelesen“ zurücksetzen?

## 5. Entscheidungen

- **5.1 Umfang** (23.11.2026): Fahrtenbuch-Einträge **und** Reisekosten bekommen Ändern und Löschen im Dashboard,
  mit gleicher Bedienung.
- **5.2 Formular** (23.11.2026): Die vorhandenen Formulare (Fahrtenbuch, Reisekosten) bekommen je eine Auswahl
  „Eintrag“ mit „Neu“ und den gespeicherten Einträgen. Einen Eintrag wählen lädt seine Werte ins Formular; „Ändern“
  speichert sie, „Löschen“ entfernt ihn. Mit „Neu“ verhalten sich die Formulare wie bisher (Speichern, Nachtragen).
- **5.3 Auswahl** (23.11.2026): Die Export-Auswahl filtert, wie bei den Stopps im Nachtrag. Mit einer Reise: alle
  Fahrtenbuch-Einträge dieser Reise und der Standzeit danach bis zum Beginn der nächsten Reise, bzw. die Reisekosten
  dieser Reise. Mit „Alle Exporte“: die neuesten 30 Fahrtenbuch-Einträge bzw. die Reisekosten ohne Reise.
- **5.4 Zeit ändern** (23.11.2026): Bei einer neuen Zeit bestimmt die Integration die Zählerstände (Strecke,
  Höhenmeter bergauf und bergab) für diese Zeit neu, wie beim Nachtrag ([Nachträge](feat-09-nachtraege.md) 6.2). Der
  Kilometerstand bleibt der im Formular, denn er ist ein abgelesener Wert; er lässt sich im selben Schritt
  korrigieren. Gilt ebenso für die Aktion `fahrtenbuch_aendern`.
- **5.5 Löschen** (23.11.2026): Sicherheitsabfrage im Dashboard („Eintrag 27.09. 17:30 löschen?“), dann endgültig;
  kein Wiederherstellen. Notnagel sind die Datensicherung von Home Assistant und die CSV-Dateien.

## 6. Entwurf der Umsetzung (zur Freigabe)

### 6.1 Zählerstände bei neuer Zeit (5.4)

- `fahrtenbuch_aendern` und das Formular bestimmen bei geänderter Zeit Position und Zählerstände wie der Nachtrag
  (`late_form.async_point_at`: laufende Reise, Rohdaten des Exports, sonst zwischen den Nachbarn geschätzt).
- Der Kilometerstand bleibt; Kraftstoff und Gas ebenso. Der Ort wird für die neue Position neu nachgeschlagen.
- Gehört der Eintrag danach zu einer anderen Reise, werden beide Exporte erneuert (wie bisher).

### 6.2 Fahrtenbuch: Eintrag wählen, ändern, löschen

- **Neu:** `select.…_fahrtenbuch_bearbeiten` mit „Neu“ und den Einträgen nach 5.3, z. B. „27.09. 17:30 · Nachtrag ·
  33768 km“, neueste zuerst.
- Einen Eintrag wählen füllt Kilometerstand, Kraftstoff, Gas 1/2, Diesel und Gas getankt mit Betrag sowie die Zeit
  (`datetime.…_fahrtenbuch_nachtrag_zeit`). Leere Werte (z. B. Gas 1 nicht abgelesen) bleiben leer, solange sie nicht
  geändert werden. Ein offener Anlass wartet währenddessen, wie beim Nachtrag.
- **Neu:** `button.…_fahrtenbuch_aendern` speichert die Werte, `button.…_fahrtenbuch_loeschen` löscht den Eintrag;
  danach springt die Auswahl auf „Neu“. „Speichern“ und „Nachtragen“ sind bei gewähltem Eintrag gesperrt (Fehler mit
  Hinweis), damit kein zweiter Eintrag entsteht.
- Attribute der Auswahl: `eintrag` (Daten des gewählten Eintrags) für die Anzeige im Dashboard.

### 6.3 Reisekosten: Eintrag wählen, ändern, löschen

- **Neu:** `select.…_reisekosten_eintrag` mit „Neu“ und den Kosten nach 5.3, z. B. „28.09. · Maut AT · 23,40 €“.
- Einen Eintrag wählen füllt Kategorie, Land, Betrag, Notiz und Datum. Die Reise bleibt die der Export-Auswahl; Kosten
  einer anderen Reise zuordnen geht weiter über `reisekosten_aendern`.
- **Neu:** `button.…_reisekosten_aendern` und `button.…_reisekosten_loeschen`, wie in 6.2.

### 6.4 Dashboard und Dokumentation

- README (de/en): Abschnitt „Einträge ändern und löschen“, Entitäten-Tabelle, Dashboard-Beispiele mit den Knöpfen
  (Sichtbarkeit nach Auswahl, Bestätigung beim Löschen).
- Live-Dashboard erst nach dem Release und nach Freigabe.

### 6.5 Abgrenzung

- Kein Wiederherstellen gelöschter Einträge (5.5).
- Anlass eines Eintrags (Reisebeginn, Halt, Manuell, Nachtrag) bleibt unveränderlich.

### 6.6 Teilschritte

1. Zählerstände bei neuer Zeit (6.1) mit Tests.
2. Fahrtenbuch-Auswahl, Ändern und Löschen (6.2): Entitäten, Übersetzungen, Tests.
3. Reisekosten-Auswahl, Ändern und Löschen (6.3).
4. README, Release-Notes, Feature-Dokumente; Prüfpunkt in `script/develop`.

Die Anzeige leerer Felder (6.7) kommt in Teilschritt 2 dazu, sobald Frage 6 geklärt ist.

Neue Entitäten: 2 Auswahlen und 4 Knöpfe (44 → 50). Kein Breaking Change; `fahrtenbuch_aendern` bestimmt bei neuer
Zeit zusätzlich die Zählerstände neu (Release-Notes).

### 6.7 Leere Felder (offen, Frage 6)

Ein leeres Feld bedeutet „nicht abgelesen“ und bleibt beim Speichern leer; 0 % ist ein abgelesener Wert. Wie das
Formular den Unterschied zeigt, wird mit Frage 6 vor Teilschritt 2 entschieden.
