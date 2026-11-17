# Fahrtenbuch (Etappe 6)

Stand: 17.11.2026, nur Anforderungen, noch keine Umsetzung.
Übergeordnete Anforderungen, Entscheidungen und Begriffe: [ANFORDERUNGEN.md](../ANFORDERUNGEN.md).

## 1. Ziel

Die Integration wird zu einem Fahrtenbuch erweitert. Zu jedem Halt einer Reise (siehe
[ANFORDERUNGEN.md 9.20](../ANFORDERUNGEN.md#9-offene-entscheidungen)) werden Fahrzeug- und Vorratsdaten
festgehalten, Tank- und Gasstopps mit Menge und Kosten. Daraus entstehen Verbrauchs- und Kostenauswertungen.

## 2. Bekannte Anforderungen

- **Je Halt:** Kilometerstand und Füllstand des Kraftstofftanks (0–100 %).
- **Zwei Gasflaschen/-tanks:** jeweils Füllstand 0–100 %, ebenfalls je Halt protokolliert.
- **Tankstopp:** Der Kraftstofftank geht wieder auf 100 %; erfasst werden getankte Liter und der Betrag in €.
- **Gasstopp:** analog für jede der beiden Gasflaschen (Menge und Betrag).
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

1. **Quellen:** Gibt es Kilometerstand, Tankfüllstand und Gasfüllstände schon als Sensoren in Home Assistant
   (z. B. CAN-Bus-Adapter, Victron, Füllstandssensor an der Gasflasche), oder werden sie von Hand eingegeben?
2. **Eingabe:** Bei Handeingabe ein Formular (z. B. Skript mit Feldern wie beim Export). Wann erscheint es: bei
   jedem Halt, nur bei Tankstopps, per Push-Erinnerung?
3. **Tankstopp erkennen:** automatisch über einen Sprung im Füllstand oder ausdrücklich per Knopf/Aktion?
4. **Auswertungen:** Verbrauch je 100 km, Kosten je Reise/Monat, Gasverbrauch je Tag, Export als CSV, Darstellung
   im Dashboard, Aufnahme in die Statistik eines Exports?
5. **Halte ohne Reise:** Sollen auch Einträge außerhalb einer Reise möglich sein (z. B. Gasflasche auf dem
   Campingplatz getauscht)?
6. **Aufbewahrung:** Wo liegen die Fahrtenbuch-Daten dauerhaft (eigener Speicher, Datei im Medienordner) und wie
   werden sie gesichert bzw. gelöscht?

## 5. Entscheidungen

Noch keine. Entscheidungen werden hier mit Datum eingetragen, die Frage in Abschnitt 4 wird dann durchgestrichen
(wie in [ANFORDERUNGEN.md Abschnitt 9](../ANFORDERUNGEN.md#9-offene-entscheidungen)).
