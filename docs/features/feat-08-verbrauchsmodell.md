# Feat-08: Verbrauchsmodell

Stand: 18.11.2026, Fragen geklärt (Abschnitt 5). Zwischenschritt (5.5) zuerst; das Modell erst, wenn genug
Fahrtenbuch-Daten vorliegen.
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

- **Verbrauch im Stand schätzen:** in erster Linie aus den getankten Litern zwischen zwei vollen Tankfüllungen,
  zusammen mit Strecke und Höhenmetern (Standtage als dritter Faktor, siehe 5.3). Die Differenz der abgelesenen
  Füllstände zwischen letztem Halt und nächstem Reisebeginn dient nur zur Kontrolle.
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
3. ~~**Tankanzeige:** Wie fein ist die Tankanzeige (Prozent, Achtel, Balken)? Davon hängt ab, ab wie vielen
   Standtagen eine Differenz aussagekräftig ist.~~ – entschieden, siehe 5.3.
4. ~~**Anzeige:** Welche Werte sollen sichtbar sein (Sensor „Verbrauch im Stand“, bereinigter Ø-Verbrauch, Zusatz je
   Höhenmeter) und wo (Dashboard, Reise-Export)?~~ – entschieden, siehe 5.4.
5. ~~**Zwischenschritt:** Soll der Sensor „Verbrauch im Stand“ schon vorab kommen, bevor das Modell den Vorschlag
   verändert?~~ – entschieden, siehe 5.5.

## 5. Entscheidungen

Entscheidungen werden hier mit Datum eingetragen, die Frage in Abschnitt 4 wird dann durchgestrichen.

- **5.1 Heizung am Fahrzeugtank** – entschieden (18.11.2026): Die Heizung bezieht ihren Diesel aus dem
  Fahrzeugtank. Ein sinkender Kraftstoff-Füllstand im Stand ist daher Heizungsverbrauch und wird vom Fahrverbrauch
  getrennt (Abschnitt 2). Weitere Verbraucher aus dem Fahrzeugtank sind nicht bekannt.
- **5.2 Keine Heizungswerte** – entschieden (18.11.2026): In Home Assistant gibt es bisher keine Werte zur Heizung
  (Betriebszustand, Leistung, Laufzeit). Der Verbrauch im Stand wird daher je Standtag geschätzt. Ein späterer
  Heizungssensor (z. B. Truma iNet) bleibt als Erweiterung möglich: dann Verbrauch je Heizstunde.
- **5.3 Ablesegenauigkeit der Tankanzeige** – entschieden (18.11.2026): Die Tankanzeige ist ein Zeiger zwischen leer
  und voll mit knapp 90° Drehbereich; abgelesen wird in Schritten von etwa 5 bis 10 % (bei 90 l etwa 4,5 bis 9 l).
  Die Heizung verbraucht typischerweise wenige Liter am Tag, eine einzelne Standzeit liegt daher meist unter der
  Ablesegenauigkeit. Grundlage der Schätzung sind deshalb die genau gemessenen Liter an der Zapfsäule zwischen zwei
  vollen Tankfüllungen (Abschnitt 6); die abgelesenen Füllstände dienen nur zur Kontrolle und für den Vorschlag.
- **5.4 Anzeige** – entschieden (18.11.2026): Alle drei Werte des Modells werden angezeigt, jeweils als Sensor und im
  Reise-Export (Statistik und Gesamtbild):
  - **Grundverbrauch** in l/100 km (ohne Heizung und Steigungen),
  - **Zusatz für Steigungen** in l je 1000 Höhenmeter bergauf,
  - **Heizung im Stand** in l je Tag.
    Solange das Modell noch nicht genug Daten hat, sind die Sensoren „unbekannt“ und der Export zeigt die Werte nicht.
- **5.5 Zwischenschritt** – entschieden (18.11.2026): Vorab kommt ein Sensor „Heizung im Stand (abgelesen)“ in l je
  Tag aus den abgelesenen Füllständen: Summe der Abnahmen zwischen letztem Eintrag einer Reise und nächstem
  Reisebeginn (ohne Tankstopp dazwischen) ÷ Summe der Standtage, über alle Standzeiten. Er ist grob (5.3) und
  verändert weder Ø-Verbrauch noch Vorschlag. Sobald das Modell genug Daten hat, ersetzt dessen Wert „Heizung im
  Stand“ (5.4) ihn in Export und Vorschlag; der abgelesene Wert bleibt als Kontrolle.

## 6. Mögliche Umsetzung (zur Diskussion)

- Höhenmeter bergauf je Fahrtenbuch-Intervall aus den gespeicherten Reisepunkten bzw. `export.json` der Reisen
  zwischen zwei Einträgen.
- Schätzung mit kleinster Quadratsumme über die Tankintervalle: getankte Liter ≈ a × km + b × Höhenmeter bergauf
  - c × Standtage (drei Parameter, ohne zusätzliche Bibliothek). Nur wenn genug Intervalle vorliegen, die sich in
    Höhenmetern und Standtagen ausreichend unterscheiden (Richtwert etwa 8 bis 10).
- Zur Kontrolle: Summe der Füllstands-Differenzen Halt → Reisebeginn über viele Standzeiten (einzelne Differenzen
  liegen meist unter der Ablesegenauigkeit).
