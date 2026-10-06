#!/usr/bin/env python3
"""Exportiert einen Track aus der Home-Assistant-Historie.

Ausgabe: GPX (mit Höhe und Geschwindigkeit), Kartenbild (PNG), Statistik (TXT),
Profil-Diagramm (Höhe und Geschwindigkeit) und ein Gesamtbild mit allem zusammen.

Beispiele:
  python3 ha_track.py --von 2026-09-27 --bis 2026-10-02
  python3 ha_track.py --von "2026-09-27 08:00" --bis "2026-09-30 18:00" --ausgabe /config/www/tracks
  python3 ha_track.py --von 2026-09-27 --bis 2026-10-02 --titel "Dolomiten-Tour 2026"

Das Skript sucht im angegebenen Zeitraum selbst die erste und letzte Bewegung (Abfahrt und
Ankunft) und schneidet Karte, Diagramme und Statistik darauf zu.

Zugang:
  In einer HA-App (z. B. Terminal & SSH) wird SUPERVISOR_TOKEN automatisch genutzt.
  Sonst: export HA_URL=http://192.168.x.x:8123 ; export HA_TOKEN=<Langzeit-Token>

Optional installieren:
  pip install staticmap      (Kartenbild und Profil-Diagramm, bringt Pillow mit)
  apk add font-dejavu        (optional: Umlaute im Profil-Diagramm)

Hinweis zur Geschwindigkeit:
  Ältere Werte des Modbus-Sensors liegen als rohe Float-Bits vor (z. B. 1118656744).
  Das Skript rechnet sie automatisch in km/h um.
"""

import argparse
from bisect import bisect_right
from datetime import UTC, datetime, timedelta
import json
import math
import os
import struct
import sys
import urllib.parse
import urllib.request
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")
STANDARD_TRACKER = "device_tracker.arto88b_gps"
STANDARD_SPEED = "sensor.teltonika_gps_speed"
STANDARD_HOEHE = "sensor.teltonika_gps_altitude"

STILLSTAND_KMH = 3.0  # darunter gilt das Fahrzeug als stehend
MAX_PLAUSIBEL_KMH = 200.0  # darüber wird ein Wert verworfen
MIN_BEWEGUNG_M = 100.0  # Ortsveränderung, ab der Abfahrt bzw. Ankunft erkannt wird
HOEHEN_SCHWELLE_M = 5.0  # Hysterese für die Summe der Höhenmeter


# ----------------------------------------------------------------- Hilfsfunktionen
def parse_zeit(text, ende=False):
    """Datum oder Datum+Uhrzeit (lokale Zeit). Reines Enddatum gilt bis Tagesende."""
    for fmt, nur_datum in (("%Y-%m-%d %H:%M", False), ("%Y-%m-%d", True)):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=TZ)
        except ValueError:
            continue
        if ende and nur_datum:
            dt += timedelta(days=1)
        return dt
    sys.exit(f"Ungültige Zeitangabe '{text}'. Format: 2026-09-27 oder '2026-09-27 08:00'")


def parse_iso(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def haversine_m(a, b):
    r = 6371000.0
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = p2 - p1
    dl = math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def dekodiere_speed(wert):
    """Rohbits eines 32-Bit-Floats (z. B. 1118656744) in km/h umrechnen.

    Werte unter 100000 gelten als bereits korrekt (Sensor mit data_type float32).
    """
    if wert is None:
        return None
    if wert > 100000:
        try:
            wert = struct.unpack(">f", struct.pack(">I", int(wert)))[0]
        except struct.error, OverflowError, ValueError:
            return None
    if wert < 0 or wert > MAX_PLAUSIBEL_KMH or math.isnan(wert):
        return None
    return wert


# ----------------------------------------------------------------- Home Assistant
def hole_history(url, token, entity, start, ende, minimal=False):
    params = {
        "end_time": ende.astimezone(UTC).isoformat(),
        "filter_entity_id": entity,
        "significant_changes_only": "0",
    }
    if minimal:
        params["minimal_response"] = ""
        params["no_attributes"] = ""
    start_utc = start.astimezone(UTC).isoformat()
    full = f"{url}/api/history/period/{urllib.parse.quote(start_utc, safe='')}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        daten = json.load(resp)
    return daten[0] if daten and daten[0] else []


def hole_punkte(url, token, entity, start, ende, max_genauigkeit):
    punkte = []
    for s in hole_history(url, token, entity, start, ende):
        a = s.get("attributes") or {}
        lat, lon = a.get("latitude"), a.get("longitude")
        if lat is None or lon is None:
            continue
        acc = a.get("gps_accuracy")
        if acc is not None and acc > max_genauigkeit:
            continue
        zeit = parse_iso(s.get("last_updated") or s["last_changed"])
        if zeit < start:
            continue
        punkte.append(
            {"lat": float(lat), "lon": float(lon), "zeit": zeit, "ele": a.get("altitude"), "speed": a.get("speed")}
        )
    punkte.sort(key=lambda p: p["zeit"])
    return punkte


class Reihe:
    """Zeitreihe als Treppenfunktion: Der letzte Wert gilt bis zur nächsten Änderung."""

    def __init__(self, paare):
        paare = sorted(paare, key=lambda p: p[0])
        self.t = [p[0] for p in paare]
        self.v = [p[1] for p in paare]

    def __len__(self):
        return len(self.t)

    def wert(self, zeit):
        i = bisect_right(self.t, zeit) - 1
        return self.v[i] if i >= 0 else None

    def ausschnitt(self, t0, t1):
        """Neue Reihe nur für den Zeitraum t0..t1 (mit dem Wert, der bei t0 gilt)."""
        paare = []
        start_wert = self.wert(t0)
        if start_wert is not None:
            paare.append((t0, start_wert))
        paare += [(t, v) for t, v in zip(self.t, self.v) if t0 < t <= t1]
        return Reihe(paare) if paare else None


def hole_reihe(url, token, entity, start, ende, umrechnung=None):
    """Numerische Sensor-Historie als Reihe. Liefert None, wenn keine Daten da sind."""
    if not entity:
        return None
    paare = []
    for s in hole_history(url, token, entity, start, ende, minimal=True):
        try:
            wert = float(s["state"])
        except KeyError, TypeError, ValueError:
            continue
        if umrechnung:
            wert = umrechnung(wert)
            if wert is None:
                continue
        zeit = parse_iso(s.get("last_changed") or s["last_updated"])
        paare.append((zeit, wert))
    return Reihe(paare) if paare else None


# ----------------------------------------------------------------- Verarbeitung
def ausduennen(punkte, min_abstand_m):
    """Entfernt Punkte, die weniger als min_abstand_m vom letzten behaltenen entfernt sind."""
    if len(punkte) < 3:
        return punkte
    behalten = [punkte[0]]
    for p in punkte[1:-1]:
        if haversine_m(behalten[-1], p) >= min_abstand_m:
            behalten.append(p)
    behalten.append(punkte[-1])
    return behalten


def strecke_km(punkte):
    return sum(haversine_m(a, b) for a, b in zip(punkte, punkte[1:])) / 1000


def hoehenmeter(werte):
    """Summe der Anstiege mit Hysterese, damit Messrauschen nicht mitzählt."""
    if not werte:
        return 0.0, 0.0
    ref, auf, ab = werte[0], 0.0, 0.0
    for w in werte[1:]:
        if w - ref >= HOEHEN_SCHWELLE_M:
            auf += w - ref
            ref = w
        elif ref - w >= HOEHEN_SCHWELLE_M:
            ab += ref - w
            ref = w
    return auf, ab


def fahrzeit(punkte):
    """Zeit in Bewegung, geschätzt aus Position und Zeitabstand."""
    gesamt = timedelta()
    for a, b in zip(punkte, punkte[1:]):
        dt = (b["zeit"] - a["zeit"]).total_seconds()
        if 0 < dt <= 300:
            kmh = haversine_m(a, b) / dt * 3.6
            if kmh >= STILLSTAND_KMH:
                gesamt += timedelta(seconds=dt)
    return gesamt


def finde_bewegung(punkte, min_m):
    """Indizes (Abfahrt, Ankunft) der ersten und letzten Ortsveränderung.

    Abfahrt: letzter Punkt, bevor die Position erstmals mehr als min_m vom Startpunkt abweicht.
    Ankunft: erster Punkt, nach dem die Position nicht mehr als min_m vom Endpunkt abweicht.
    Liefert None, wenn sich das Fahrzeug nie weiter als min_m bewegt hat.
    """
    erster = next((i for i, p in enumerate(punkte) if haversine_m(punkte[0], p) >= min_m), None)
    if erster is None:
        return None
    letzter = next(i for i in range(len(punkte) - 1, -1, -1) if haversine_m(punkte[-1], punkte[i]) >= min_m)
    return max(erster - 1, 0), min(letzter + 1, len(punkte) - 1)


def fmt_zeitraum(t0, t1):
    a, b = t0.astimezone(TZ), t1.astimezone(TZ)
    if a.date() == b.date():
        return f"{a:%d.%m.%Y} · Abfahrt {a:%H:%M} Uhr · Ankunft {b:%H:%M} Uhr"
    return f"Abfahrt {a:%d.%m.%Y} {a:%H:%M} Uhr · Ankunft {b:%d.%m.%Y} {b:%H:%M} Uhr"


def standard_titel(t0, t1):
    a, b = t0.astimezone(TZ), t1.astimezone(TZ)
    if a.date() == b.date():
        return f"Wohnmobil {a:%d.%m.%Y}"
    return f"Wohnmobil {a:%d.%m.%Y} - {b:%d.%m.%Y}"


def fmt_dauer(td):
    s = int(td.total_seconds())
    return f"{s // 3600} h {s % 3600 // 60:02d} min"


def statistik_werte(punkte, speed_reihe):
    """Liste aus (Bezeichnung, Wert) für die Textdatei und die Kopfzeile des Gesamtbilds."""
    werte = [
        ("Zeitraum", fmt_zeitraum(punkte[0]["zeit"], punkte[-1]["zeit"])),
        ("Strecke", f"{strecke_km(punkte):.1f} km"),
        ("Fahrzeit", fmt_dauer(fahrzeit(punkte))),
    ]
    if speed_reihe:
        alle = speed_reihe.v
        fahrend = [v for v in alle if v >= STILLSTAND_KMH]
        werte.append(("Höchstgeschw.", f"{max(alle):.0f} km/h"))
        if fahrend:
            werte.append(("Ø in Bewegung", f"{sum(fahrend) / len(fahrend):.0f} km/h"))
    hoehen = [p["ele"] for p in punkte if p.get("ele") is not None]
    if hoehen:
        auf, ab = hoehenmeter(hoehen)
        werte.append(("Höhe min/max", f"{min(hoehen):.0f} / {max(hoehen):.0f} m"))
        werte.append(("Höhenmeter", f"+{auf:.0f} / -{ab:.0f} m"))
    return werte


def erstelle_statistik(punkte, speed_reihe, name):
    zeilen = [name, "=" * len(name)]
    zeilen += [f"{k + ':':<17}{v}" for k, v in statistik_werte(punkte, speed_reihe)]
    return "\n".join(zeilen)


# ----------------------------------------------------------------- Ausgabe
def schreibe_gpx(punkte, pfad, name):
    zeilen = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="ha_track.py" xmlns="http://www.topografix.com/GPX/1/1">',
        f"  <trk><name>{escape(name)}</name><trkseg>",
    ]
    for p in punkte:
        ele = f"<ele>{float(p['ele']):.1f}</ele>" if p.get("ele") is not None else ""
        zeit = p["zeit"].astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        ext = ""
        if p.get("speed") is not None:
            ext = f"<extensions><speed>{float(p['speed']) / 3.6:.2f}</speed></extensions>"
        zeilen.append(f'    <trkpt lat="{p["lat"]:.6f}" lon="{p["lon"]:.6f}">{ele}<time>{zeit}</time>{ext}</trkpt>')
    zeilen += ["  </trkseg></trk>", "</gpx>"]
    with open(pfad, "w", encoding="utf-8") as f:
        f.write("\n".join(zeilen))


def erzeuge_karte(punkte, breite, hoehe, linienbreite):
    """Kartenbild mit Route als Pillow-Bild (None, wenn nicht möglich)."""
    try:
        from staticmap import CircleMarker, Line, StaticMap
    except ImportError:
        print("Hinweis: Kartenbild übersprungen (pip install staticmap).")
        return None
    try:
        karte = StaticMap(
            breite, hoehe, padding_x=60, padding_y=60, headers={"User-Agent": "ha_track.py (privates Fotobuch)"}
        )
        koords = [(p["lon"], p["lat"]) for p in punkte]
        karte.add_line(Line(koords, "#ffffff", linienbreite + 4))
        karte.add_line(Line(koords, "#d62828", linienbreite))
        marker = round(linienbreite * 22 / 6)
        karte.add_marker(CircleMarker(koords[0], "#2a9d8f", marker))
        karte.add_marker(CircleMarker(koords[-1], "#1d3557", marker))
        return karte.render()
    except Exception as fehler:  # z. B. keine Verbindung zu den Kartenkacheln
        print(f"Hinweis: Kartenbild fehlgeschlagen ({fehler}).")
        return None


SCHRIFT_PFADE = [
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/noto/NotoSans-Regular.ttf",
    "DejaVuSans.ttf",
]
UMLAUTE = {
    "ä": "ae",
    "ö": "oe",
    "ü": "ue",
    "ß": "ss",
    "Ä": "Ae",
    "Ö": "Oe",
    "Ü": "Ue",
    "–": "-",
    "Ø": "Schnitt",
    "·": "-",
}


def _schrift(groesse):
    """Liefert (Schrift, Umlaute_moeglich).

    Ohne installierte TrueType-Schrift (z. B. 'apk add font-dejavu') nutzt Pillow seine
    Standardschrift, die keine Umlaute kann. Dann werden Texte ohne Umlaute geschrieben.
    """
    from PIL import ImageFont

    for pfad in SCHRIFT_PFADE:
        try:
            return ImageFont.truetype(pfad, groesse), True
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=groesse), False
    except TypeError, OSError, ValueError:
        return ImageFont.load_default(), False


def _schriften(k=1.0):
    """Titel- und Textschrift für die Diagramme: (Titel, Text, Umlaute_moeglich)."""
    titel, uml = _schrift(round(52 * k))
    text, _ = _schrift(round(34 * k))
    return titel, text, uml


def _text(s, umlaute_ok):
    if umlaute_ok:
        return s
    for k, v in UMLAUTE.items():
        s = s.replace(k, v)
    return s


def _schritt(spanne, ziel=6):
    """Rundet auf einen schönen Achsenabstand (1, 2, 5 mal 10^n)."""
    if spanne <= 0:
        return 1.0
    roh = spanne / ziel
    zehner = 10 ** math.floor(math.log10(roh))
    for faktor in (1, 2, 5, 10):
        if roh <= faktor * zehner:
            return faktor * zehner
    return 10 * zehner


def _zeit_ticks(x0, x1):
    """Zeitmarken (Epoch-Sekunden, Beschriftung) in lokaler Zeit."""
    spanne = x1 - x0
    intervall = 86400 * 2
    for kandidat in (600, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800):
        if spanne / kandidat <= 7:
            intervall = kandidat
            break
    start = datetime.fromtimestamp(x0, TZ)
    t = start.replace(hour=0, minute=0, second=0, microsecond=0)
    schritt = timedelta(seconds=intervall)
    while t.timestamp() < x0:
        t += schritt
    fmt = "%H:%M" if spanne <= 86400 else "%d.%m. %H:%M"
    ticks = []
    while t.timestamp() <= x1:
        ticks.append((t.timestamp(), t.strftime(fmt)))
        t += schritt
    return ticks


def _zeichne_panel(
    draw,
    ox,
    oy,
    breite,
    hoehe,
    titel,
    y_label,
    x_label,
    xs,
    ys,
    x_ticks,
    linie,
    schriften,
    flaeche=None,
    y_min=None,
    k=1.0,
):
    S = lambda v: max(1, round(v * k))
    f_titel, f_text, uml = schriften
    titel, y_label, x_label = _text(titel, uml), _text(y_label, uml), _text(x_label, uml)
    px0, px1 = ox + S(190), ox + breite - S(70)
    py0, py1 = oy + S(130), oy + hoehe - S(150)
    x0, x1 = xs[0], xs[-1]
    if x1 <= x0:
        x1 = x0 + 1
    schritt = _schritt(max(ys) - min(ys))
    ymin = y_min if y_min is not None else math.floor(min(ys) / schritt) * schritt
    ymax = math.ceil(max(ys) / schritt) * schritt
    if ymax <= ymin:
        ymax = ymin + schritt

    def X(x):
        return px0 + (x - x0) / (x1 - x0) * (px1 - px0)

    def Y(y):
        return py1 - (y - ymin) / (ymax - ymin) * (py1 - py0)

    y = ymin
    while y <= ymax + 1e-9:
        yy = Y(y)
        draw.line([(px0, yy), (px1, yy)], fill="#dddddd", width=S(2))
        text = f"{y:.0f}"
        draw.text((px0 - S(15) - draw.textlength(text, font=f_text), yy - S(18)), text, fill="#333333", font=f_text)
        y += schritt
    for xv, label in x_ticks:
        if x0 <= xv <= x1:
            xx = X(xv)
            draw.line([(xx, py0), (xx, py1)], fill="#eeeeee", width=S(2))
            draw.text((xx - draw.textlength(label, font=f_text) / 2, py1 + S(15)), label, fill="#333333", font=f_text)

    punkte = [(X(x), Y(y)) for x, y in zip(xs, ys)]
    if flaeche:
        draw.polygon(punkte + [(px1, py1), (px0, py1)], fill=flaeche)
    draw.line(punkte, fill=linie, width=S(5), joint="curve")
    draw.rectangle([px0, py0, px1, py1], outline="#555555", width=S(2))
    draw.text((px0, oy + S(25)), titel, fill="#111111", font=f_titel)
    draw.text((px0, py0 - S(48)), y_label, fill="#555555", font=f_text)
    draw.text(
        ((px0 + px1) / 2 - draw.textlength(x_label, font=f_text) / 2, py1 + S(70)), x_label, fill="#555555", font=f_text
    )


def erzeuge_profil(punkte, speed_reihe, titel=None, zeitraum=None, skala=1.0):
    """Diagramm als Pillow-Bild: Höhe über der Strecke und Geschwindigkeit über der Zeit."""
    hat_hoehe = sum(1 for p in punkte if p.get("ele") is not None) >= 2
    hat_speed = speed_reihe is not None and len(speed_reihe) >= 2
    if not (hat_hoehe or hat_speed):
        return None
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Hinweis: Profil-Diagramm übersprungen (Pillow fehlt, kommt mit staticmap).")
        return None

    schriften = _schriften(skala)
    breite, panel_h = round(2400 * skala), round(900 * skala)
    panels = int(hat_hoehe) + int(hat_speed)
    bild = Image.new("RGB", (breite, panel_h * panels), "white")
    draw = ImageDraw.Draw(bild)
    reihe = 0

    if hat_hoehe:
        km, hoehen, summe, vorher = [], [], 0.0, None
        for p in punkte:
            if vorher is not None:
                summe += haversine_m(vorher, p) / 1000
            vorher = p
            if p.get("ele") is not None:
                km.append(summe)
                hoehen.append(float(p["ele"]))
        schritt = _schritt(km[-1] - km[0])
        ticks = [(i * schritt, f"{i * schritt:.0f}") for i in range(int(km[-1] / schritt) + 1)]
        _zeichne_panel(
            draw,
            0,
            reihe * panel_h,
            breite,
            panel_h,
            f"{titel} - Höhenprofil" if titel else "Höhenprofil",
            "Höhe (m)",
            "Strecke (km)",
            km,
            hoehen,
            ticks,
            linie="#023047",
            schriften=schriften,
            flaeche="#bde0f2",
            k=skala,
        )
        reihe += 1

    if hat_speed:
        t0, t1 = zeitraum or (punkte[0]["zeit"], punkte[-1]["zeit"])
        aktuell = speed_reihe.wert(t0)
        if aktuell is None:
            aktuell = speed_reihe.v[0]
        xs, ys = [t0.timestamp()], [aktuell]
        for t, v in zip(speed_reihe.t, speed_reihe.v):
            if t0 < t <= t1:
                xs += [t.timestamp(), t.timestamp()]
                ys += [ys[-1], v]
        xs.append(t1.timestamp())
        ys.append(ys[-1])
        _zeichne_panel(
            draw,
            0,
            reihe * panel_h,
            breite,
            panel_h,
            "Geschwindigkeit",
            "km/h",
            "Uhrzeit",
            xs,
            ys,
            _zeit_ticks(xs[0], xs[-1]),
            linie="#d62828",
            schriften=schriften,
            y_min=0,
            k=skala,
        )

    return bild


def erzeuge_gesamt(karte, profil, titel, werte, skala=1.0):
    """Gesamtbild: Kopfzeile mit Kennzahlen, darunter Karte und Profil-Diagramme."""
    if karte is None and profil is None:
        return None
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    S = lambda v: round(v * skala)
    breite, kopf_h, luecke = S(2400), S(380), S(40)
    teile = []
    for t in (karte, profil):
        if t is not None:
            if t.width != breite:
                t = t.resize((breite, round(t.height * breite / t.width)), Image.LANCZOS)
            teile.append(t.convert("RGB"))
    hoehe = kopf_h + sum(t.height for t in teile) + luecke * len(teile)
    bild = Image.new("RGB", (breite, hoehe), "white")
    draw = ImageDraw.Draw(bild)

    f_titel, uml = _schrift(S(72))
    f_klein, _ = _schrift(S(36))
    f_label, _ = _schrift(S(30))
    draw.text((S(80), S(50)), _text(titel, uml), fill="#111111", font=f_titel)
    zeitraum = dict(werte).get("Zeitraum")
    if zeitraum:
        draw.text((S(80), S(150)), _text(zeitraum, uml), fill="#666666", font=f_klein)
    draw.line([(S(80), S(225)), (breite - S(80), S(225))], fill="#cccccc", width=S(3))

    felder = [(k, v) for k, v in werte if k != "Zeitraum"]
    if felder:
        feld_breite = (breite - S(160)) / len(felder)
        texte = [_text(v, uml) for _, v in felder]
        # eine gemeinsame Schriftgröße: die größte, bei der alle Werte in ihre Spalte passen
        f_wert = None
        for groesse in (56, 48, 42, 36, 30, 26):
            f_wert, _ = _schrift(S(groesse))
            if all(draw.textlength(t, font=f_wert) <= feld_breite - S(30) for t in texte):
                break
        for i, ((k, _), wert) in enumerate(zip(felder, texte)):
            x = S(80) + i * feld_breite
            draw.text((x, S(255)), wert, fill="#111111", font=f_wert)
            draw.text((x, S(335)), _text(k, uml), fill="#777777", font=f_label)

    y = kopf_h
    for t in teile:
        bild.paste(t, (0, y))
        y += t.height + luecke
    return bild


# ----------------------------------------------------------------- Hauptprogramm
def main():
    ap = argparse.ArgumentParser(description="HA-Track als GPX, Karte und Statistik exportieren")
    ap.add_argument("--von", required=True, help="Start, z. B. 2026-09-27 oder '2026-09-27 08:00'")
    ap.add_argument("--bis", required=True, help="Ende (reines Datum = inkl. diesem Tag)")
    ap.add_argument("--entity", default=STANDARD_TRACKER, help="device_tracker mit Position")
    ap.add_argument("--speed-entity", default=STANDARD_SPEED, help="Geschwindigkeits-Sensor ('' = aus)")
    ap.add_argument("--hoehe-entity", default=STANDARD_HOEHE, help="Höhen-Sensor ('' = aus)")
    ap.add_argument("--ausgabe", default=".", help="Zielordner (Standard: aktuelles Verzeichnis)")
    ap.add_argument("--min-abstand", type=float, default=15.0, help="Mindestabstand der Punkte in m")
    ap.add_argument("--max-genauigkeit", type=float, default=50.0, help="Punkte mit gps_accuracy darüber ignorieren")
    ap.add_argument("--breite", type=int, default=2400)
    ap.add_argument("--hoehe", type=int, default=1600)
    ap.add_argument("--linie", type=int, default=6, help="Linienbreite in Pixeln")
    ap.add_argument("--titel", default=None, help="Titel für Gesamtbild, Profil und GPX (Standard: Wohnmobil + Datum)")
    ap.add_argument(
        "--min-bewegung",
        type=float,
        default=MIN_BEWEGUNG_M,
        help="Ortsveränderung in m, ab der Abfahrt/Ankunft erkannt wird (Standard: 100)",
    )
    ap.add_argument(
        "--rand-min",
        type=float,
        default=10.0,
        help="Minuten vor Abfahrt und nach Ankunft im Geschwindigkeitsdiagramm (Standard: 10)",
    )
    ap.add_argument(
        "--skala",
        type=float,
        default=1.0,
        help="Auflösungsfaktor für Karte, Diagramme und Gesamtbild (Standard: 1, z. B. 2 = doppelte Pixelzahl)",
    )
    ap.add_argument("--dateiname", default=None, help="Dateiname ohne Endung (Standard: track_<von>_<bis>)")
    ap.add_argument("--ohne-gesamt", action="store_true", help="Kein Gesamtbild (Karte + Profile) erzeugen")
    args = ap.parse_args()

    url = os.environ.get("HA_URL")
    token = os.environ.get("HA_TOKEN")
    if not token and os.environ.get("SUPERVISOR_TOKEN"):
        token, url = os.environ["SUPERVISOR_TOKEN"], url or "http://supervisor/core"
    if not token:
        sys.exit("Kein Token gefunden. Setze HA_URL und HA_TOKEN.")
    url = (url or "http://homeassistant.local:8123").rstrip("/")

    start = parse_zeit(args.von)
    ende = parse_zeit(args.bis, ende=True)
    if ende <= start:
        sys.exit("Das Ende muss nach dem Start liegen.")

    roh = hole_punkte(url, token, args.entity, start, ende, args.max_genauigkeit)
    print(f"{len(roh)} Positionen im Zeitraum gefunden.")
    if len(roh) < 2:
        sys.exit("Zu wenige Punkte. Zeitraum und Entity prüfen.")

    rand = timedelta(minutes=max(args.rand_min, 0))
    speed_reihe = hole_reihe(url, token, args.speed_entity, start - rand, ende + rand, dekodiere_speed)
    hoehe_reihe = hole_reihe(url, token, args.hoehe_entity, start, ende)
    print(f"Geschwindigkeit: {'%d Werte' % len(speed_reihe) if speed_reihe else 'keine Daten'}")
    print(f"Höhe:            {'%d Werte' % len(hoehe_reihe) if hoehe_reihe else 'keine Daten'}")

    # Sensorwerte vor dem Ausdünnen den Positionen zuordnen
    for p in roh:
        if speed_reihe and p.get("speed") is None:
            p["speed"] = speed_reihe.wert(p["zeit"])
        if hoehe_reihe and p.get("ele") is None:
            p["ele"] = hoehe_reihe.wert(p["zeit"])

    # Erste und letzte Bewegung im Zeitraum suchen und alles darauf zuschneiden
    bewegung = finde_bewegung(roh, args.min_bewegung)
    if bewegung is None:
        sys.exit(f"Keine Bewegung (mehr als {args.min_bewegung:.0f} m) im Zeitraum gefunden.")
    gesamt_anzahl = len(roh)
    roh = roh[bewegung[0] : bewegung[1] + 1]
    t_ab, t_an = roh[0]["zeit"], roh[-1]["zeit"]
    print(f"Bewegung erkannt: {fmt_zeitraum(t_ab, t_an)} ({len(roh)} von {gesamt_anzahl} Positionen)")
    # Statistik nur für die Fahrt, das Geschwindigkeitsdiagramm zusätzlich mit etwas Rand
    speed_diagramm = speed_reihe.ausschnitt(t_ab - rand, t_an + rand) if speed_reihe else None
    diagramm_zeitraum = (t_ab - rand, t_an + rand)
    if speed_reihe:
        speed_reihe = speed_reihe.ausschnitt(t_ab, t_an)

    punkte = ausduennen(roh, args.min_abstand)
    print(f"Nach dem Ausdünnen: {len(punkte)} Punkte.")

    os.makedirs(args.ausgabe, exist_ok=True)
    dateiname = (
        os.path.basename(args.dateiname)
        if args.dateiname
        else f"track_{start:%Y%m%d}_{(ende - timedelta(seconds=1)):%Y%m%d}"
    )
    basis = os.path.join(args.ausgabe, dateiname)
    name = args.titel or standard_titel(t_ab, t_an)

    schreibe_gpx(punkte, basis + ".gpx", name)
    print(f"GPX:        {basis}.gpx")

    stat = erstelle_statistik(punkte, speed_reihe, name)
    with open(basis + "_statistik.txt", "w", encoding="utf-8") as f:
        f.write(stat + "\n")
    print(f"Statistik:  {basis}_statistik.txt")

    skala = min(max(args.skala, 0.5), 4.0)
    karte = erzeuge_karte(punkte, round(args.breite * skala), round(args.hoehe * skala), round(args.linie * skala))
    if karte is not None:
        karte.save(basis + ".png")
        print(f"Karte:      {basis}.png")
    profil = erzeuge_profil(punkte, speed_diagramm, name, diagramm_zeitraum, skala)
    if profil is not None:
        profil.save(basis + "_profil.png")
        print(f"Profil:     {basis}_profil.png")
    if not args.ohne_gesamt:
        profil_ohne_titel = erzeuge_profil(punkte, speed_diagramm, None, diagramm_zeitraum, skala)
        gesamt = erzeuge_gesamt(karte, profil_ohne_titel, name, statistik_werte(punkte, speed_reihe), skala)
        if gesamt is not None:
            gesamt.save(basis + "_gesamt.png")
            print(f"Gesamtbild: {basis}_gesamt.png")

    print()
    print(stat)


if __name__ == "__main__":
    main()
