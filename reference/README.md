# Referenz: bisherige Skripte

Diese Dateien sind der Ist-Zustand vor der Integration. Sie dienen nur als **Vorlage** für die Logik und
werden nicht mit der Integration ausgeliefert.

| Datei             | Inhalt                                                                                                                                                                               |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `ha_track.py`     | Export als Kommandozeilenskript: Positionen/Geschwindigkeit/Höhe aus der HA-History, Bewegungserkennung, Statistik, GPX, Karte, Profil-Diagramm, Gesamtbild (nur Pillow + staticmap) |
| `track_daemon.py` | Hintergrunddienst für die SSH-App: reagiert auf Dashboard-Knöpfe, startet den Export, meldet Status, löscht Dateien nach Auswahl (Aufräumen)                                         |

Aufruf des Skripts (Beispiel):

```bash
python3 ha_track.py --von 2026-09-27 --bis 2026-10-02 --titel "Beispiel" --skala 2 --rand-min 10
```

Zugang zur HA-API: Umgebungsvariablen `HA_URL` und `HA_TOKEN` (oder `SUPERVISOR_TOKEN` in einer HA-App).
Das Skript ist nur gegen simulierte Daten getestet; die Kartenerzeugung lief nur auf dem System des Nutzers.
