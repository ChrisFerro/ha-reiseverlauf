# Feat-08: Verbrauchsmodell

Stand: 18.11.2026, geplant (Etappe 8), offene Fragen in Abschnitt 4. Umsetzung erst, wenn genug Fahrtenbuch-Daten
vorliegen.
Übergeordnete Anforderungen und Entitäten: [ANFORDERUNGEN.md](../ANFORDERUNGEN.md). Grundlage:
[Fahrtenbuch](feat-06-fahrtenbuch.md).

## 1. Ziel

Der Kraftstoff-Vorschlag und der Durchschnittsverbrauch des Fahrtenbuchs werden genauer:

1. **Höhenmeter:** Bergauf wird mehr verbraucht. Der Verbrauch einer Reise wird aus Strecke **und** Höhenmetern
   bergauf geschätzt statt nur aus der Strecke.
2. **Heizung im Stand:** Die Dieselheizung verbraucht auch, wenn das Fahrzeug steht. Dieser Anteil wird vom
   Fahrverbrauch getrennt, damit der Ø-Verbrauch je 100 km nicht zu hoch ausfällt und der Vorschlag nach einer
   Standzeit stimmt.

## 2. Anforderungen (Entwurf)

- **Verbrauch im Stand messen:** Differenz zwischen dem Kraftstoff-Füllstand am letzten Eintrag einer Reise
  (Halt/Ankunft) und dem bestätigten Füllstand beim nächsten Reisebeginn, umgerechnet in Liter über die
  Tankgröße; ohne Tankstopp dazwischen. Daraus Liter je Standtag.
- **Fahrverbrauch bereinigen:** Ø-Verbrauch je 100 km ohne den im Stand verbrauchten Diesel.
- **Höhenmeter-Faktor:** Verbrauch ≈ Grundverbrauch je km × Strecke + Zusatzverbrauch je 100 Höhenmeter bergauf,
  geschätzt aus den Tankintervallen (Höhenmeter je Reise aus dem Export).
- **Vorschlag:** Kraftstoff-Vorschlag beim Halt mit Strecke und Höhenmetern der Reise; beim Reisebeginn zusätzlich
  abzüglich des geschätzten Verbrauchs im Stand.
- **Rückfall:** Solange zu wenige Daten vorliegen, bleibt das bisherige Verfahren (Volltank-Methode,
  [feat-06-fahrtenbuch.md](feat-06-fahrtenbuch.md) 5.8). Ein Modell wird erst genutzt, wenn es auf den vorhandenen Daten besser
  schätzt als das bisherige.
- **Nachvollziehbar:** Die geschätzten Werte (Grundverbrauch, Zusatz je Höhenmeter, Verbrauch im Stand je Tag)
  sind als Sensoren oder Attribute sichtbar.

## 3. Ausgangslage (Stand v0.2.1)

- Ø-Verbrauch nach der Volltank-Methode: alle getankten Liter zwischen zwei vollen Tankfüllungen ÷ km
  (`Logbook.average_consumption`). Der Heizungsdiesel ist darin enthalten.
- Kraftstoff-Vorschlag: letzter Füllstand − km × Ø-Verbrauch ÷ Tankgröße (`Logbook.suggest_fuel_percent`).
  Höhenmeter und Standzeit fließen nicht ein; beim Reisebeginn bestätigt der Nutzer den echten Füllstand.
- Daten: Das Fahrtenbuch erfasst seit 18.11.2026 Einträge bei Reisebeginn und jedem Halt (Füllstand in %), Tank-
  stopps mit Litern. Höhenmeter je Reise stehen im Export (`statistik`, Rohdaten mit Höhe); Höhendaten gibt es
  erst seit 04.10.2026.
- Füllstände werden von Hand von der Tankanzeige abgelesen (ganze Prozent, Anzeige ggf. grob); das begrenzt die
  Genauigkeit des Verbrauchs im Stand.
- Zurückgestellt im Fahrtenbuch: [feat-06-fahrtenbuch.md](feat-06-fahrtenbuch.md) 5.8 und 6.6.

## 4. Offene Fragen (vor der Umsetzung einzeln klären)

1. ~~**Heizung:** Zieht die Heizung (z. B. Truma Combi D) den Diesel aus dem Fahrzeugtank oder hat sie einen eigenen
   Tank? Gibt es weitere Verbraucher aus dem Fahrzeugtank (z. B. Standheizung des Fahrerhauses)?~~ – entschieden,
   siehe 5.1.
2. ~~**Heizung als Sensor:** Gibt es in Home Assistant Werte zur Heizung (Betriebszustand, Leistungsstufe, z. B. über
   Truma iNet/CP plus), aus denen sich die Laufzeit statt nur der Standtage ergibt?~~ – entschieden, siehe 5.2.
3. **Tankanzeige:** Wie fein ist die Tankanzeige (Prozent, Achtel, Balken)? Davon hängt ab, ab wie vielen
   Standtagen eine Differenz aussagekräftig ist.
4. **Anzeige:** Welche Werte sollen sichtbar sein (Sensor „Verbrauch im Stand“, bereinigter Ø-Verbrauch, Zusatz je
   Höhenmeter) und wo (Dashboard, Reise-Export)?
5. **Zwischenschritt:** Soll der Sensor „Verbrauch im Stand“ schon vorab kommen, bevor das Modell den Vorschlag
   verändert?

## 5. Entscheidungen

Entscheidungen werden hier mit Datum eingetragen, die Frage in Abschnitt 4 wird dann durchgestrichen.

- **5.1 Heizung am Fahrzeugtank** – entschieden (18.11.2026): Die Heizung bezieht ihren Diesel aus dem
  Fahrzeugtank. Ein sinkender Kraftstoff-Füllstand im Stand ist daher Heizungsverbrauch und wird vom Fahrverbrauch
  getrennt (Abschnitt 2). Weitere Verbraucher aus dem Fahrzeugtank sind nicht bekannt.
- **5.2 Keine Heizungswerte** – entschieden (18.11.2026): In Home Assistant gibt es bisher keine Werte zur Heizung
  (Betriebszustand, Leistung, Laufzeit). Der Verbrauch im Stand wird daher je Standtag geschätzt. Ein späterer
  Heizungssensor (z. B. Truma iNet) bleibt als Erweiterung möglich: dann Verbrauch je Heizstunde.

## 6. Mögliche Umsetzung (zur Diskussion)

- Höhenmeter bergauf je Fahrtenbuch-Intervall aus den gespeicherten Reisepunkten bzw. `export.json` der Reisen
  zwischen zwei Einträgen.
- Schätzung mit kleinster Quadratsumme über die Tankintervalle (zwei Parameter, ohne zusätzliche Bibliothek), nur
  wenn genug Intervalle mit ausreichend unterschiedlichen Höhenmetern vorliegen (Richtwert etwa 8).
- Verbrauch im Stand als Mittelwert der Differenzen Halt → Reisebeginn je Standtag, nur über Paare ohne Tankstopp
  und mit plausiblen Werten (keine Zunahme).
