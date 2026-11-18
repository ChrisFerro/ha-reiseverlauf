# Feat-07: Geschützter Download

Stand: 18.11.2026, Fragen geklärt (Abschnitt 5), Umsetzung offen (Etappe 7).
Übergeordnete Anforderungen und Entitäten: [ANFORDERUNGEN.md](../ANFORDERUNGEN.md).

## 1. Ziel

Alle Dateien der Integration lassen sich angemeldet und ohne Umweg aus dem Dashboard herunterladen (siehe 5.1),
einzeln oder je Reise als ZIP. Gemeint sind GPX, Statistik, Rohdaten, Bilder jeder Reise und
die CSV-Datei des Fahrtenbuchs. Sie bleiben geschützt: kein öffentlicher Ordner (`/local`), kein Zugriff ohne
Anmeldung.

## 2. Anforderungen (Entwurf)

- **Nur angemeldet:** Zugriff nur für angemeldete Benutzer von Home Assistant, Links 24 h gültig und stündlich
  erneuert (siehe 5.2, 5.4).
- **Nur eigene Dateien:** ausgeliefert werden nur Dateien im Ausgabeordner der Integration, die in `export.json`
  stehen, und `fahrtenbuch.csv`. Kein Pfad außerhalb (Schutz gegen `../`).
- **Richtiger Dateityp:** GPX, CSV, TXT und JSON mit passendem Inhaltstyp und Dateinamen, damit Handy und PC
  sie öffnen bzw. speichern (z. B. GPX in einer Navigations-App, CSV in Excel).
- **Im Dashboard:** Links je Datei und „Alles als ZIP“ für die letzte Reise und die Export-Auswahl, dazu
  `fahrtenbuch.csv` in der Fahrtenbuch-Ansicht; eine Markdown-Karte genügt (siehe 5.1, 5.3). Push-Nachricht,
  Events und Antworten der Aktionen bleiben unverändert.
- **Kein Bruch:** bestehende Links auf Bilder (`/media/local/...`) funktionieren weiter.

## 3. Ausgangslage (Stand v0.2.1)

- Alle Dateien liegen im lokalen Medienordner (`/media/reiseverlauf/...`, siehe [feat-03-export.md](feat-03-export.md) 5.2).
- Der Medienbrowser von Home Assistant zeigt und liefert nur Bilder, Videos und Audio
  (`media_source/local_source.py`: Prüfung auf `MEDIA_MIME_TYPES`). GPX, Statistik-Text, Rohdaten, `export.json`
  und `fahrtenbuch.csv` erscheinen dort nicht; ihre Links `/media/local/...` liefern „nicht gefunden“.
- Betroffen sind das Attribut `dateien` der letzten Reise, die Event-Daten, die Antwort von
  `fahrtenbuch_csv` sowie Hinweise in README, Dashboard-Texten und [feat-05-dashboard.md](feat-05-dashboard.md).
  Aufgefallen beim Live-Test des Fahrtenbuchs am 18.11.2026.
- Zugriff heute nur über Apps mit Dateizugriff (z. B. Studio Code Server, Advanced SSH & Web Terminal, Samba).

## 4. Offene Fragen (vor der Umsetzung einzeln klären)

1. ~~**Orte:** Wo werden Downloads gebraucht: Dashboard (Liste je Reise), Push-Nachricht (Knopf „GPX“/„Statistik“),
   Medienbrowser, Antworten der Aktionen?~~ – entschieden, siehe 5.1
2. ~~**Gültigkeit der Links:** Wie lange soll ein Link gelten (z. B. 24 h, 30 Tage)? Dauerhafte Links in Events und
   Attributen sind nicht signierbar; ggf. Link auf eine Download-Seite statt direkt auf die Datei.~~ – entschieden,
   siehe 5.2
3. ~~**Umfang:** Einzelne Dateien oder zusätzlich alles einer Reise als ZIP (z. B. für das Fotobuch)?~~ – entschieden,
   siehe 5.3
4. ~~**Berechtigung:** Alle angemeldeten Benutzer oder nur Administratoren?~~ – entschieden, siehe 5.4
5. ~~**Medienbrowser:** Sollen die Dateien auch dort erscheinen (eigene Medienquelle „Reiseverlauf“)? Vorher prüfen,
   wie der Medienbrowser Nicht-Mediendateien öffnet.~~ – entfällt, siehe 5.1

## 5. Entscheidungen

Entscheidungen werden hier mit Datum eingetragen, die Frage in Abschnitt 4 wird dann durchgestrichen.

- **5.1 Orte** (18.11.2026): Downloads nur im **Dashboard**: die Dateien je Reise (letzte Reise und Export-Auswahl)
  und `fahrtenbuch.csv` in der Fahrtenbuch-Ansicht. Keine Knöpfe in der Push-Nachricht, keine eigene Medienquelle,
  keine Links in den Antworten der Aktionen.
- **5.2 Gültigkeit** (18.11.2026): Die Integration signiert die Links selbst; jeder Link gilt **24 h** und wird
  stündlich erneuert. Im Dashboard sind die Links damit immer gültig (eine Markdown-Karte reicht), ein kopierter
  Link höchstens einen Tag. Die Links stehen in einem Attribut, das der Recorder nicht speichert.
- **5.3 Umfang** (18.11.2026): Jede Datei einzeln, dazu je Reise ein Link „Alles als ZIP“ (alle Dateien aus
  `export.json`, z. B. für das Fotobuch). Das ZIP entsteht beim Abruf und wird nicht gespeichert.
- **5.4 Berechtigung** (18.11.2026): Alle angemeldeten Benutzer, die das Dashboard sehen. Ohne gültigen Link gibt
  es nichts; wer den Zugriff einschränken will, schränkt die Sichtbarkeit des Dashboards ein.

## 6. Mögliche Umsetzung (zur Diskussion)

- Eigener HTTP-Endpunkt der Integration (`HomeAssistantView`), z. B.
  `/api/reiseverlauftracker/datei/<eintrag>/<ordner>/<datei>` und `…/zip/<eintrag>/<ordner>`, prüft Pfad und
  `export.json` und liefert die Datei mit `Content-Disposition: attachment`; das ZIP wird gestreamt, nicht
  gespeichert.
- Signatur der Links, zwei Wege (vor der Umsetzung prüfen):
  - `async_sign_path` wie bei Backups; braucht ein Refresh-Token, im Hintergrund also einen eigenen
    Systembenutzer der Integration.
  - Eigenes, stündlich wechselndes Zugriffstoken im Link, wie es Kamera- und Bild-Entitäten für `entity_picture`
    machen; das aktuelle und das vorige Token gelten, insgesamt höchstens 24 h.
- Links in eigenen Attributen (z. B. `downloads` an `sensor.…_letzte_reise`, `select.…_export_auswahl` und
  `sensor.…_fahrtenbuch_eintrag`), vom Recorder ausgenommen (`_unrecorded_attributes`).
- Nicht gewählt: eigene Medienquelle (siehe 5.1); Kopie nach `/config/www` (`/local`), weil ohne Anmeldung abrufbar (siehe [feat-03-export.md](feat-03-export.md)).
