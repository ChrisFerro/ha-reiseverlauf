#!/usr/bin/env python3
"""Hintergrunddienst für den Track-Export per Dashboard.

Läuft in der App "Advanced SSH & Web Terminal" und wartet darauf, dass im Dashboard der
Knopf `input_button.track_generieren` gedrückt wird. Dann liest er die Einstellungen aus den
Helfern, startet `ha_track.py` und meldet Status, Downloads und Statistik als
`sensor.track_export` an Home Assistant zurück.

Zusätzlich löscht er auf Knopfdruck (`input_button.track_aufraeumen`) ausgewählte Dateien eines
Exports (`input_select.track_loeschen` plus fünf `input_boolean.track_del_*` für die Dateitypen)
und meldet das Ergebnis als `sensor.track_aufraeumen`.

Es wird nur die Home-Assistant-API genutzt (kein offener Port, keine Zugangsdaten im Dashboard).

Start zum Testen (Vordergrund):   python3 /config/scripts/track_daemon.py
Dauerhaft: siehe init_commands der App.

Optionale Umgebungsvariablen: HA_URL, HA_TOKEN (nur außerhalb der App nötig),
TRACK_SCRIPT, TRACK_OUT, TRACK_WWW, TRACK_POLL.
"""

from datetime import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

SCRIPT = os.environ.get("TRACK_SCRIPT", "/config/scripts/ha_track.py")
WWW = os.environ.get("TRACK_WWW", "/config/www")
AUSGABE = os.environ.get("TRACK_OUT", os.path.join(WWW, "tracks"))
POLL_SEKUNDEN = float(os.environ.get("TRACK_POLL", "2"))
HEARTBEAT_SEKUNDEN = 60
JOB_TIMEOUT_SEKUNDEN = 1800

SENSOR = "sensor.track_export"
SENSOR_AUFRAEUMEN = "sensor.track_aufraeumen"
OPTIONEN_INTERVALL_SEKUNDEN = 30
ALLE = "★ Alle Exporte"
KEINE = "(keine Exporte vorhanden)"
ENT = {
    "knopf": "input_button.track_generieren",
    "knopf_loeschen": "input_button.track_aufraeumen",
    "auswahl": "input_select.track_loeschen",
    "del_gesamt": "input_boolean.track_del_gesamt",
    "del_karte": "input_boolean.track_del_karte",
    "del_profil": "input_boolean.track_del_profil",
    "del_gpx": "input_boolean.track_del_gpx",
    "del_statistik": "input_boolean.track_del_statistik",
    "start": "input_datetime.track_start",
    "ende": "input_datetime.track_ende",
    "titel": "input_text.track_titel",
    "skala": "input_number.track_skala",
    "rand": "input_number.track_rand_min",
}
DATEI_ZEILE = re.compile(r"^(GPX|Statistik|Karte|Profil|Gesamtbild):\s+(.+)$", re.MULTILINE)
REIHENFOLGE = ["Gesamtbild", "Karte", "Profil", "GPX", "Statistik"]
# Dateiendungen in der Reihenfolge, in der sie geprüft werden (die längeren zuerst)
ENDUNGEN = [
    ("_gesamt.png", "Gesamtbild"),
    ("_profil.png", "Profil"),
    ("_statistik.txt", "Statistik"),
    (".gpx", "GPX"),
    (".png", "Karte"),
]
TYP_HELFER = [
    ("del_gesamt", "Gesamtbild"),
    ("del_karte", "Karte"),
    ("del_profil", "Profil"),
    ("del_gpx", "GPX"),
    ("del_statistik", "Statistik"),
]
RE_ZEIT = re.compile(r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?$")


def log(text):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}", flush=True)


# ----------------------------------------------------------------- Home-Assistant-API
def _lese_token():
    token = os.environ.get("HA_TOKEN") or os.environ.get("SUPERVISOR_TOKEN")
    if token:
        return token
    for pfad in (
        "/var/run/s6/container_environment/SUPERVISOR_TOKEN",
        "/run/s6/container_environment/SUPERVISOR_TOKEN",
    ):
        try:
            with open(pfad, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            continue
    return None


TOKEN = _lese_token()
if os.environ.get("HA_TOKEN"):
    BASIS_URL = os.environ.get("HA_URL", "http://localhost:8123").rstrip("/")
else:
    BASIS_URL = os.environ.get("HA_URL", "http://supervisor/core").rstrip("/")


def api(methode, pfad, daten=None):
    anfrage = urllib.request.Request(
        f"{BASIS_URL}/api{pfad}",
        method=methode,
        data=None if daten is None else json.dumps(daten).encode("utf-8"),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(anfrage, timeout=20) as antwort:
        return json.load(antwort)


def hole_zustand(entity):
    try:
        return api("GET", f"/states/{entity}")
    except urllib.error.HTTPError as fehler:
        if fehler.code == 404:
            return None
        raise


# ----------------------------------------------------------------- Statusmeldung
class Sensor:
    """Ein von diesem Dienst gepflegter Status-Sensor."""

    def __init__(self, entity, name, icon):
        self.entity, self.name, self.icon = entity, name, icon
        self.status = None
        self.attribute = None
        self.zeit = 0.0

    def melde(self, status, nachricht="", **extra):
        attribute = {
            "friendly_name": self.name,
            "icon": self.icon,
            "nachricht": nachricht,
            "stand": datetime.now().isoformat(timespec="seconds"),
        }
        attribute.update(extra)
        self.status, self.attribute, self.zeit = status, attribute, time.time()
        api("POST", f"/states/{self.entity}", {"state": status, "attributes": attribute})

    def heartbeat(self):
        """Meldet den letzten Status erneut, damit der Sensor einen HA-Neustart übersteht."""
        if self.status and time.time() - self.zeit >= HEARTBEAT_SEKUNDEN:
            api("POST", f"/states/{self.entity}", {"state": self.status, "attributes": self.attribute})
            self.zeit = time.time()


EXPORT = Sensor(SENSOR, "Track-Export", "mdi:map-marker-path")
AUFRAEUMEN = Sensor(SENSOR_AUFRAEUMEN, "Track-Aufräumen", "mdi:delete-sweep")


# ----------------------------------------------------------------- Parameter
def slug(text):
    t = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:60] or None


def lies_parameter():
    def wert(name):
        zustand = hole_zustand(ENT[name])
        if zustand is None:
            raise ValueError(f"Helfer {ENT[name]} existiert nicht")
        return zustand["state"]

    def zeit(name, bezeichnung):
        text = wert(name)
        if not RE_ZEIT.match(text or ""):
            raise ValueError(f"{bezeichnung}: ungültiger Wert '{text}'")
        return text[:16]  # 'YYYY-MM-DD' oder 'YYYY-MM-DD HH:MM'

    def zahl(name, bezeichnung, minimum, maximum, standard):
        try:
            return min(max(float(wert(name)), minimum), maximum)
        except TypeError, ValueError:
            log(f"{bezeichnung}: ungültiger Wert, nehme {standard}")
            return standard

    titel = (wert("titel") or "").strip()
    if titel.lower() in ("unknown", "unavailable"):
        titel = ""
    return {
        "von": zeit("start", "Start"),
        "bis": zeit("ende", "Ende"),
        "titel": titel[:100] or None,
        "skala": zahl("skala", "Skala", 1.0, 4.0, 1.0),
        "rand": zahl("rand", "Rand", 0.0, 120.0, 10.0),
    }


# ----------------------------------------------------------------- Job
def als_url(pfad):
    """Pfad unter /config/www als /local-URL (mit Zeitstempel gegen Browser-Cache)."""
    pfad = os.path.abspath(pfad)
    wurzel = os.path.abspath(WWW) + os.sep
    if not pfad.startswith(wurzel):
        return None
    relativ = pfad[len(wurzel) :].replace(os.sep, "/")
    try:
        version = int(os.path.getmtime(pfad))
    except OSError:
        version = int(time.time())
    return f"/local/{relativ}?v={version}"


def fuehre_job_aus(p):
    cmd = [
        sys.executable,
        SCRIPT,
        "--von",
        p["von"],
        "--bis",
        p["bis"],
        "--ausgabe",
        AUSGABE,
        "--skala",
        f"{p['skala']:g}",
        "--rand-min",
        f"{p['rand']:g}",
    ]
    if p["titel"]:
        cmd += ["--titel", p["titel"]]
        name = slug(p["titel"])
        if name:
            cmd += ["--dateiname", name]
    umgebung = dict(os.environ)
    if TOKEN and not umgebung.get("HA_TOKEN"):
        umgebung["SUPERVISOR_TOKEN"] = TOKEN
    if os.environ.get("HA_URL"):
        umgebung["HA_URL"] = os.environ["HA_URL"]
    log("Starte: " + " ".join(cmd))
    start = time.time()
    try:
        prozess = subprocess.run(cmd, capture_output=True, text=True, env=umgebung, timeout=JOB_TIMEOUT_SEKUNDEN)
    except subprocess.TimeoutExpired:
        EXPORT.melde("fehler", f"Abbruch nach {JOB_TIMEOUT_SEKUNDEN // 60} Minuten (Zeitlimit).")
        return
    ausgabe = (prozess.stdout or "") + (prozess.stderr or "")
    log(f"Ende nach {time.time() - start:.0f} s, Rückgabecode {prozess.returncode}")

    if prozess.returncode != 0:
        zeilen = [z.strip() for z in ausgabe.splitlines() if z.strip()]
        EXPORT.melde("fehler", " | ".join(zeilen[-3:])[:300] or "Unbekannter Fehler (siehe Log).")
        return

    gefunden = {m.group(1): m.group(2).strip() for m in DATEI_ZEILE.finditer(ausgabe)}
    dateien = []
    for bezeichnung in REIHENFOLGE:
        pfad = gefunden.get(bezeichnung)
        url = als_url(pfad) if pfad else None
        if url:
            dateien.append({"name": bezeichnung, "url": url})
    vorschau = next((d["url"] for d in dateien if d["name"] in ("Gesamtbild", "Karte")), None)

    statistik = ""
    if gefunden.get("Statistik"):
        try:
            with open(gefunden["Statistik"], encoding="utf-8") as f:
                statistik = f.read().strip()
        except OSError:
            pass
    bewegung = re.search(r"^Bewegung erkannt:\s*(.+)$", ausgabe, re.MULTILINE)
    nachricht = f"Fertig in {time.time() - start:.0f} s."
    if bewegung:
        nachricht += f" Bewegung erkannt: {bewegung.group(1)}"
    hinweise = [z.strip() for z in ausgabe.splitlines() if z.startswith("Hinweis:")]
    if hinweise:
        nachricht += " | " + " ".join(hinweise)
    EXPORT.melde("fertig", nachricht[:500], dateien=dateien, vorschau=vorschau, statistik=statistik, parameter=p)
    aktualisiere_optionen(erzwingen=True)


def verarbeite_knopfdruck():
    try:
        parameter = lies_parameter()
    except (ValueError, urllib.error.URLError) as fehler:
        EXPORT.melde("fehler", str(fehler))
        return
    titel = parameter["titel"] or "ohne Titel"
    EXPORT.melde(
        "läuft",
        f"{titel}: {parameter['von']} bis {parameter['bis']}, Skala {parameter['skala']:g}. "
        "Das kann bis zu einer Minute dauern.",
        parameter=parameter,
    )
    os.makedirs(AUSGABE, exist_ok=True)
    try:
        fuehre_job_aus(parameter)
    except Exception as fehler:  # nichts darf den Dienst beenden
        log(f"Fehler im Job: {fehler!r}")
        EXPORT.melde("fehler", f"Interner Fehler: {fehler}"[:300])


# ----------------------------------------------------------------- Aufräumen
def scanne_exporte():
    """Alle Exporte im Ausgabeordner: {Basisname: {"dateien": {Typ: Pfad}, "mtime": Zeit}}."""
    exporte = {}
    try:
        namen = os.listdir(AUSGABE)
    except OSError:
        return exporte
    for name in namen:
        pfad = os.path.join(AUSGABE, name)
        if not os.path.isfile(pfad):
            continue
        for endung, typ in ENDUNGEN:
            if name.endswith(endung) and len(name) > len(endung):
                eintrag = exporte.setdefault(name[: -len(endung)], {"dateien": {}, "mtime": 0.0})
                eintrag["dateien"][typ] = pfad
                eintrag["mtime"] = max(eintrag["mtime"], os.path.getmtime(pfad))
                break
    return exporte


def baue_optionen(exporte):
    if not exporte:
        return [KEINE]
    optionen = []
    for basis, eintrag in sorted(exporte.items(), key=lambda kv: kv[1]["mtime"], reverse=True):
        datum = datetime.fromtimestamp(eintrag["mtime"]).strftime("%d.%m.%Y %H:%M")
        optionen.append(f"{basis} ({len(eintrag['dateien'])} Dateien, {datum})")
    return optionen + [ALLE]


OPTIONEN = {"letzte": None, "fehler_gemeldet": False}


def aktualisiere_optionen(erzwingen=False):
    """Schreibt die Liste der vorhandenen Exporte in input_select.track_loeschen (nur bei Änderung)."""
    optionen = baue_optionen(scanne_exporte())
    if optionen == OPTIONEN["letzte"] and not erzwingen:
        return
    try:
        api("POST", "/services/input_select/set_options", {"entity_id": ENT["auswahl"], "options": optionen})
        OPTIONEN["letzte"] = optionen
        OPTIONEN["fehler_gemeldet"] = False
    except urllib.error.HTTPError as fehler:
        if not OPTIONEN["fehler_gemeldet"]:
            log(f"Auswahlliste nicht aktualisierbar ({fehler.code}). Existiert {ENT['auswahl']}?")
            OPTIONEN["fehler_gemeldet"] = True


def im_ausgabeordner(pfad):
    wurzel = os.path.realpath(AUSGABE) + os.sep
    return os.path.realpath(pfad).startswith(wurzel)


def fmt_groesse(byte):
    return f"{byte / 1024 / 1024:.1f} MB" if byte >= 1024 * 1024 else f"{byte / 1024:.0f} KB"


def url_zu_pfad(url):
    relativ = url.split("?", 1)[0]
    if not relativ.startswith("/local/"):
        return None
    return os.path.join(WWW, relativ[len("/local/") :])


def bereinige_ergebnis():
    """Entfernt gelöschte Dateien aus dem Ergebnis des letzten Exports (Downloads, Vorschau)."""
    attribute = EXPORT.attribute
    if EXPORT.status != "fertig" or not attribute:
        return
    dateien = [
        d
        for d in attribute.get("dateien", [])
        if (url_zu_pfad(d["url"]) or "") and os.path.exists(url_zu_pfad(d["url"]))
    ]
    if len(dateien) == len(attribute.get("dateien", [])):
        return
    if not dateien:
        EXPORT.melde("bereit", "Warte auf Knopfdruck im Dashboard.")
        return
    urls = [d["url"] for d in dateien]
    vorschau = attribute.get("vorschau")
    if vorschau not in urls:
        vorschau = next((d["url"] for d in dateien if d["name"] in ("Gesamtbild", "Karte")), None)
    statistik = attribute.get("statistik", "") if any(d["name"] == "Statistik" for d in dateien) else ""
    EXPORT.melde(
        "fertig",
        attribute.get("nachricht", ""),
        dateien=dateien,
        vorschau=vorschau,
        statistik=statistik,
        parameter=attribute.get("parameter"),
    )


def lies_helfer(name):
    zustand = hole_zustand(ENT[name])
    if zustand is None:
        raise ValueError(f"Helfer {ENT[name]} existiert nicht")
    return zustand["state"]


def verarbeite_aufraeumen():
    try:
        exporte = scanne_exporte()
        auswahl = lies_helfer("auswahl")
        typen = [typ for schluessel, typ in TYP_HELFER if lies_helfer(schluessel) == "on"]
    except (ValueError, urllib.error.URLError) as fehler:
        AUFRAEUMEN.melde("fehler", str(fehler))
        return
    if not typen:
        AUFRAEUMEN.melde("fehler", "Kein Dateityp gewählt. Es wurde nichts gelöscht.")
        return
    if auswahl == ALLE:
        ziele = list(exporte)
    elif auswahl in (KEINE, "", "unknown", "unavailable"):
        AUFRAEUMEN.melde("fehler", "Kein Export ausgewählt. Es wurde nichts gelöscht.")
        return
    else:
        basis = auswahl.rsplit(" (", 1)[0]
        if basis not in exporte:
            aktualisiere_optionen(erzwingen=True)
            AUFRAEUMEN.melde("fehler", "Dieser Export existiert nicht mehr. Die Liste wurde aktualisiert.")
            return
        ziele = [basis]

    geloescht, fehler_liste, frei = [], [], 0
    for basis in ziele:
        for typ in typen:
            pfad = exporte[basis]["dateien"].get(typ)
            if not pfad:
                continue
            if not im_ausgabeordner(pfad):
                fehler_liste.append(f"{os.path.basename(pfad)}: außerhalb des Ausgabeordners")
                continue
            try:
                groesse = os.path.getsize(pfad)
                os.remove(pfad)
                frei += groesse
                geloescht.append((basis, typ))
                log(f"Gelöscht: {pfad}")
            except OSError as fehler:
                fehler_liste.append(f"{os.path.basename(pfad)}: {fehler.strerror}")

    if not geloescht and not fehler_liste:
        nachricht = "Nichts zu löschen: Für diese Auswahl gibt es keine passenden Dateien."
        status = "bereit"
    else:
        status = "fehler" if fehler_liste and not geloescht else "gelöscht"
        betroffen = sorted({b for b, _ in geloescht})
        if len(betroffen) == 1:
            arten = ", ".join(t for _, t in geloescht)
            nachricht = f"{len(geloescht)} Datei(en) von {betroffen[0]} gelöscht ({arten}), {fmt_groesse(frei)} frei."
        else:
            nachricht = f"{len(geloescht)} Dateien aus {len(betroffen)} Exporten gelöscht, {fmt_groesse(frei)} frei."
        if fehler_liste:
            nachricht += " Fehler: " + "; ".join(fehler_liste)
    AUFRAEUMEN.melde(status, nachricht[:500], geloescht=[f"{b}: {t}" for b, t in geloescht])
    aktualisiere_optionen(erzwingen=True)
    bereinige_ergebnis()


# ----------------------------------------------------------------- Hauptschleife
KNOEPFE = {"knopf": verarbeite_knopfdruck, "knopf_loeschen": verarbeite_aufraeumen}


def main():
    if not TOKEN:
        sys.exit("Kein Zugangstoken gefunden (SUPERVISOR_TOKEN bzw. HA_TOKEN).")
    log(f"Dienst gestartet. API: {BASIS_URL}, Skript: {SCRIPT}, Ausgabe: {AUSGABE}")
    letzte = {}  # zuletzt gesehener Zustand der Knöpfe
    fehlend = set()  # Helfer, deren Fehlen schon gemeldet wurde
    naechste_optionen = 0.0
    while True:
        try:
            if EXPORT.status is None:
                EXPORT.melde("bereit", "Warte auf Knopfdruck im Dashboard.")
            if AUFRAEUMEN.status is None:
                AUFRAEUMEN.melde("bereit", "Export und Dateitypen wählen, dann auf Löschen tippen.")
            for schluessel, aktion in KNOEPFE.items():
                zustand = hole_zustand(ENT[schluessel])
                if zustand is None:
                    if schluessel not in fehlend:
                        fehlend.add(schluessel)
                        log(f"Helfer {ENT[schluessel]} existiert nicht.")
                        if schluessel == "knopf":
                            EXPORT.melde("fehler", f"Helfer {ENT[schluessel]} existiert nicht.")
                    continue
                fehlend.discard(schluessel)
                aktuell = zustand["state"]
                if schluessel not in letzte:
                    letzte[schluessel] = aktuell  # Ausgangszustand merken, nicht auslösen
                    if schluessel == "knopf" and EXPORT.status == "fehler":
                        EXPORT.melde("bereit", "Warte auf Knopfdruck im Dashboard.")
                elif aktuell != letzte[schluessel]:
                    letzte[schluessel] = aktuell
                    if aktuell not in ("unknown", "unavailable"):
                        log(f"Knopfdruck erkannt: {ENT[schluessel]}")
                        aktion()
                        neu = hole_zustand(ENT[schluessel])
                        if neu:
                            letzte[schluessel] = neu["state"]  # Drücke während des Laufs ignorieren
            if time.time() >= naechste_optionen:
                aktualisiere_optionen()
                naechste_optionen = time.time() + OPTIONEN_INTERVALL_SEKUNDEN
            EXPORT.heartbeat()
            AUFRAEUMEN.heartbeat()
        except (urllib.error.URLError, OSError, ValueError) as fehler:
            log(f"Home Assistant nicht erreichbar oder Fehler: {fehler!r}")
            time.sleep(10)
        time.sleep(POLL_SEKUNDEN)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Dienst beendet.")
