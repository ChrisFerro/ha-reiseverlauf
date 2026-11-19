# Feat-07: Geschützter Download

Stand: 19.11.2026, umgesetzt (Etappe 7, Abschnitt 6).
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

- **5.5 Signatur** (19.11.2026): `async_sign_path` mit dem schreibgeschützten Systembenutzer „Home Assistant
  Content“, den Home Assistant selbst anlegt (`use_content_user=True`); kein eigener Benutzer, kein eigenes Token.
  Der Signierschlüssel liegt nur im Arbeitsspeicher, nach einem Neustart sind alte Links ungültig.
- **5.6 Kein Cache** (19.11.2026): Alle Downloads senden `Cache-Control: no-store, private`. Beim Test lieferte der
  Browser einen alten Link nach dem Neustart sonst aus dem Cache, ohne den Server zu fragen.

## 6. Umsetzung

- `download.py`: drei Views (`HomeAssistantView`, Anmeldung per Header oder signiertem Link):
  - `/api/reiseverlauftracker/<eintrag>/datei/<ordner>/<datei>`: eine Datei, nur wenn der Ordner ein bekannter
    Export ist und `export.json` die Datei nennt; der Pfad wird nachgeschlagen, nie aus der Anfrage
    zusammengesetzt. `../` weist schon der Sicherheitsfilter von Home Assistant ab.
  - `/api/reiseverlauftracker/<eintrag>/zip/<ordner>`: alle vorhandenen Dateien des Exports als ZIP im
    Unterordner `<ordner>/`, im Executor in eine temporäre Datei geschrieben (bis 8 MB im Speicher) und gestreamt;
    Bilder ungepackt, Text komprimiert.
  - `/api/reiseverlauftracker/<eintrag>/fahrtenbuch`: `fahrtenbuch.csv`.
  - Antwort mit passendem Inhaltstyp (GPX `application/gpx+xml`, Text und CSV mit `charset=utf-8`),
    `Content-Disposition: attachment` (Dateiname auch mit Umlauten) und `Cache-Control: no-store, private`.
- `coordinator/download_links.py`: Pfade und `DownloadLinks`, das jeden Link bis zur nächsten Erneuerung
  zwischenspeichert, damit sich die Attribute nicht bei jedem Schreiben ändern; der Koordinator erneuert stündlich.
- Attribut `downloads` (Liste mit `typ`, `name`, `url`, bei Reisen zusätzlich `zip`) an `sensor.…_letzte_reise`,
  `select.…_export_auswahl` (gewählter Export, leer bei „Alle Exporte“) und `sensor.…_fahrtenbuch_eintrag`
  (sobald es Einträge gibt), jeweils in `_unrecorded_attributes`.
- Das Attribut `dateien` und die Event-Daten bleiben unverändert (`/media/local/...`).
- Dashboard: Markdown-Karte mit `<a href="…" target="_blank">`; ohne `target` fängt das Frontend Links auf dieselbe
  Adresse ab und öffnet sie als Dashboard-Seite (README, Abschnitt „Downloads“).
- Nicht gewählt: eigene Medienquelle (siehe 5.1); eigenes wechselndes Token wie bei `entity_picture` (unnötig, siehe
  5.5); Kopie nach `/config/www` (`/local`), weil ohne Anmeldung abrufbar (siehe [feat-03-export.md](feat-03-export.md)).
