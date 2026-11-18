# Feat-07: Geschützter Download

Stand: 18.11.2026, geplant (Etappe 7), offene Fragen in Abschnitt 4.
Übergeordnete Anforderungen und Entitäten: [ANFORDERUNGEN.md](../ANFORDERUNGEN.md).

## 1. Ziel

Alle Dateien der Integration lassen sich angemeldet und ohne Umweg herunterladen: aus dem Dashboard, aus der
Push-Nachricht und aus den Antworten der Aktionen. Gemeint sind GPX, Statistik, Rohdaten, Bilder jeder Reise und
die CSV-Datei des Fahrtenbuchs. Sie bleiben geschützt: kein öffentlicher Ordner (`/local`), kein Zugriff ohne
Anmeldung.

## 2. Anforderungen (Entwurf)

- **Nur angemeldet:** Zugriff nur für angemeldete Benutzer von Home Assistant, Links nur zeitlich begrenzt gültig
  (signiert wie bei Backups).
- **Nur eigene Dateien:** ausgeliefert werden nur Dateien im Ausgabeordner der Integration, die in `export.json`
  stehen, und `fahrtenbuch.csv`. Kein Pfad außerhalb (Schutz gegen `../`).
- **Richtiger Dateityp:** GPX, CSV, TXT und JSON mit passendem Inhaltstyp und Dateinamen, damit Handy und PC
  sie öffnen bzw. speichern (z. B. GPX in einer Navigations-App, CSV in Excel).
- **Überall nutzbar:** Links im Attribut `dateien`, im Event `reiseverlauftracker_beendet`/`_exportiert`, in der
  Antwort von `exportieren` und `fahrtenbuch_csv` und im Dashboard.
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

1. **Orte:** Wo werden Downloads gebraucht: Dashboard (Liste je Reise), Push-Nachricht (Knopf „GPX“/„Statistik“),
   Medienbrowser, Antworten der Aktionen?
2. **Gültigkeit der Links:** Wie lange soll ein Link gelten (z. B. 24 h, 30 Tage)? Dauerhafte Links in Events und
   Attributen sind nicht signierbar; ggf. Link auf eine Download-Seite statt direkt auf die Datei.
3. **Umfang:** Einzelne Dateien oder zusätzlich alles einer Reise als ZIP (z. B. für das Fotobuch)?
4. **Berechtigung:** Alle angemeldeten Benutzer oder nur Administratoren?
5. **Medienbrowser:** Sollen die Dateien auch dort erscheinen (eigene Medienquelle „Reiseverlauf“)? Vorher prüfen,
   wie der Medienbrowser Nicht-Mediendateien öffnet.

## 5. Entscheidungen

Noch keine. Entscheidungen werden hier mit Datum eingetragen, die Frage in Abschnitt 4 wird dann durchgestrichen.

## 6. Mögliche Umsetzung (zur Diskussion)

- Eigener HTTP-Endpunkt der Integration (`HomeAssistantView`, `requires_auth`), z. B.
  `/api/reiseverlauftracker/datei/<eintrag>/<ordner>/<datei>`, prüft Pfad und `export.json` und liefert die Datei
  mit `Content-Disposition: attachment`.
- Signierte Links (`async_sign_path`, wie Backups) für Push-Nachricht und Dashboard; ohne Signatur nur mit
  Anmelde-Header (Companion-App, API).
- Optional eine eigene Medienquelle, damit die Dateien im Medienbrowser erscheinen.
- Nicht gewählt: Kopie nach `/config/www` (`/local`), weil ohne Anmeldung abrufbar (siehe [feat-03-export.md](feat-03-export.md)).
