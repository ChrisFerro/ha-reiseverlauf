# Trip History Tracker for Motorhomes

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]

[Deutsche Version](README.md)

This Home Assistant integration detects the trips of a motorhome from its D+ signal (alternator charge
signal, on while the engine runs). After each trip it creates a map, an elevation and speed profile, a GPX file,
statistics and a composite image (for example for a photo book), and announces the end with an event. A bundled
blueprint then sends a push notification with the composite image to your phone.

## Features

- **Automatic trip detection:** a trip starts when D+ turns on and ends when D+ stays off longer than a
  configurable delay (default 60 min). Fuel stops belong to the same trip.
- **Ferries and car trains:** if the vehicle moves while D+ is off, the trip goes on. A ferry crossing is detected
  (or marked by hand), drawn dashed and not counted as distance driven.
- **Merging:** if the journey continues within a window after the end (default 6 h), for example after a long
  wait at the port, the same trip is resumed and exported again.
- **Export:** distance, driving time, top and average speed, altitude and elevation gain; map on OpenStreetMap
  tiles, profiles, GPX with altitude and speed, composite image.
- **Map symbols:** start, end or pitch, stops, fuel and gas stops and ferries as symbols on the map, with a legend in
  the composite image (see [Map symbols and ferries](#map-symbols-and-ferries)).
- **Logbook:** odometer (carried forward from the measured distance), levels of the fuel tank and two gas tanks,
  fuel and gas stops with litres and amount. Push reminder at trip start and at each stop; average consumption,
  costs per month and year, a CSV file and the figures in the trip export.
- **Late entries:** assign a fuel stop later to a stop, a short stop or a time; odometer and consumption come out
  as if it had been entered right away.
- **Travel costs:** toll per trip and country, vignette, ferry, tunnel, pitch; the countries of the trip are
  suggested, and a reminder lists trips through toll countries without a toll entry. Statistics and composite image
  of a trip are renewed after each late entry.
- **Tours:** combine several trips and the stays between them afterwards: overall map, days by place, all costs by
  category and country, estimated consumption, GPX and composite image.
- **Titles with place names:** such as "Hamburg – Kiel, 2026-10-12"; or date only, or places only.
- **Own recording:** the points of each trip are stored, independent of how long the recorder keeps data.
- **Protected storage:** all files are written to the Home Assistant media folder and need a login to open.
- **Downloads in the dashboard:** GPX, statistics, raw points, images, a ZIP of each trip, `fahrtenbuch.csv` and
  `reisekosten.csv` through signed links, valid for 24 h and renewed hourly.
- **UI only:** setup, options, entities and actions; no YAML required.

## Requirements

- Home Assistant 2026.11 or newer
- [HACS](https://hacs.xyz/)
- Entities for:
  - **D+** – a `sensor` (for example with `ON`/`OFF`) or `binary_sensor` that is on while the engine runs
  - **Position** – a `device_tracker` with latitude and longitude
  - **Speed** – a sensor in km/h
  - **Altitude** (optional) – a sensor in metres
- For push notifications: the Home Assistant Companion app on the phone

## Installation

1. Open HACS, top right **⋮ → Custom repositories**.
2. Add `https://github.com/ChrisFerro/ha-reiseverlauf` with the type **Integration**.
3. Search for **Reiseverlauf Tracker für Wohnmobile** and download it.
4. Restart Home Assistant.

[![Open the repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ChrisFerro&repository=ha-reiseverlauf&category=integration)

## Setup

[![Set up the integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=reiseverlauftracker)

**Settings → Devices & services → Add integration → "Reiseverlauf"**, then choose the D+ signal and its "on"
value, the position tracker (it also identifies the vehicle), the speed and optional altitude sensor, and the
output folder inside the media folder (default `reiseverlauf`). Everything can be changed later with
**Reconfigure**.

**Configure** offers the options in four sections: trip detection (end delay, merge window, minimum movement),
export (title format, place-name lookup, image scale, chart margin), thresholds (standstill speed, maximum
GPS inaccuracy, minimum point distance, elevation hysteresis, minimum stop duration) and logbook (tank size,
default 90 l; toll countries, default AT, BE, CH, CZ, ES, FR, HR, HU, IT, NO, PL, PT, SI, SK, where motorhomes over
3.5 t pay distance-based toll). A trip that never got further from its start than
the minimum movement (default 100 m) is discarded.

## Entities

All entities belong to one device named after the entry: trip active, trip status (ready, driving, stopped,
processing, can continue, error), start (with the start place), distance, driving time, stop time (with the list of stops) and average speed while moving of the running trip, title, distance, driving
time, duration and end of the last trip (the title carries the file list with URLs and the statistics as
attributes), an image entity with the composite image, and an export selection used by the cleanup action. In the
export selection, manual exports carry the mark “Manual” (“Manuell” in German); its attribute `exporte` lists every
export with `auswahl`, `ordner`, `art`, `automatisch`, `start`, `ende`, `strecke_km` and `rohdaten`.
For the logbook there are the form (numbers for odometer, fuel, gas 1 and 2, litres and amounts refuelled, buttons to
save and discard), a logbook entry sensor (pending or saved, with the latest entries), and sensors for odometer,
last levels, average consumption, heating while parked (read), all costs of the month and year (fuel, gas and travel
costs, each kind as an attribute) and open toll (finished trips through a toll country without a toll entry). The
logbook time selection, late entry time and late entry button fill the form for an earlier time; the travel cost
category, country, amount, note and date with save and no-toll buttons add travel costs to the trip chosen in the
export selection, whose attribute `reisekosten` lists them. The edit logbook and travel cost entry selections with
their change and delete buttons correct stored entries (see [Changing and deleting entries](#changing-and-deleting-entries));
the logbook clear field selection resets a field to “not read off”, and the logbook entry sensor lists empty fields in
its attribute `nicht_abgelesen`.

For tours, the tour from, tour until and tour title fields with the buttons create tour and update tour combine
trips (see [Tours](#tours)); the binary sensor tour in progress is on while a tour is created, changed or renewed;
with a tour chosen, the export selection has the attributes `art`, `standorte` and
`tourkosten`.

The button mark as ferry (“Als Fähre markieren”) switches the ferry mark of the stop chosen in the logbook time
selection; the button redraw map (“Karte neu zeichnen”) draws the map of the export chosen in the export selection
anew with tiles (see [Map symbols and ferries](#map-symbols-and-ferries)).

## Actions

| Action                                       | Purpose                                                                                                                                           |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `reiseverlauftracker.exportieren`            | Export any period from the recorder, optionally with title, scale and margin; returns the result                                                  |
| `reiseverlauftracker.aufraeumen`             | Delete file types of one export or of all exports; without an export, the export selection applies                                                |
| `reiseverlauftracker.reise_starten`          | Start a trip without D+, or resume the last one within the merge window                                                                           |
| `reiseverlauftracker.reise_beenden`          | End the running trip now and export it                                                                                                            |
| `reiseverlauftracker.fahrtenbuch_speichern`  | Save the logbook form like the button; with `anlass_zeit` only while that occasion is pending                                                     |
| `reiseverlauftracker.fahrtenbuch_eintragen`  | Add a logbook entry without the form; returns the entry                                                                                           |
| `reiseverlauftracker.fahrtenbuch_aendern`    | Change fields of an entry; litres of 0 remove a fuel or gas stop; a new time brings the counters and place of that time                           |
| `reiseverlauftracker.fahrtenbuch_loeschen`   | Delete an entry; its ID is in the attribute `letzte_eintraege`                                                                                    |
| `reiseverlauftracker.fahrtenbuch_csv`        | Write `fahrtenbuch.csv` to the output folder (also done after every change)                                                                       |
| `reiseverlauftracker.fahrtenbuch_nachtragen` | Add a fuel or gas stop for an earlier time; a stop within 5 min of the time is matched                                                            |
| `reiseverlauftracker.reisekosten_eintragen`  | Add a travel cost for a trip (folder, selection entry or start time) or only a date                                                               |
| `reiseverlauftracker.reisekosten_aendern`    | Change a travel cost; its ID is in the attribute `reisekosten` of the export selection                                                            |
| `reiseverlauftracker.reisekosten_loeschen`   | Delete a travel cost                                                                                                                              |
| `reiseverlauftracker.keine_maut`             | Mark a trip as having no toll, or remove the mark with `an: false`                                                                                |
| `reiseverlauftracker.tour_erstellen`         | Combine all trips starting from `von` to `bis` into a tour; optional title and scale                                                              |
| `reiseverlauftracker.tour_aendern`           | Change title, period or place names (`standorte`: list of `nacht` and `name`) and renew the tour                                                  |
| `reiseverlauftracker.faehre_markieren`       | Mark a stop (`halt`: its start or a time during it, optional `reise`) as ferry crossing, or remove it with `faehre: false`                        |
| `reiseverlauftracker.karte_neu_zeichnen`     | Draw map, base map and composite image of one export (trip or tour) anew with tiles; without `export`, the selection applies; not for all exports |

## Storage

Each trip gets its own folder named after its start time (for example `2026-10-12_1000`; manual exports
`2026-10-12_1000-1130`) with the composite image, map, base map (tiles only, for redrawing), profile, GPX, statistics, raw points and an `export.json`
the integration uses to manage the export. Only files listed there are ever deleted. The media browser of Home Assistant shows
only the images; all files can be downloaded from the dashboard.

### Downloads

The entities last trip, export selection and logbook entry have an attribute `downloads`: a list with `typ`, `name`
and `url` for each file, and for trips also `zip` with all files of the trip. A link is valid for 24 h and renewed
every hour and right after a restart, so it always works in the dashboard; a copied link opens without login for
at most a day. The links are not recorded in the history. In a markdown card, write the links as
`<a href="{{ d.url }}" target="_blank">{{ d.name }}</a>`; without `target` the dashboard opens them as a page
instead of downloading them. A full example is in the [German README](README.md#downloads).

## Tours

A tour combines several trips and the stays between them, for example the drive out, a week on a camp site and
the drive home, or a trip to the workshop and back. It is created afterwards from the stored points of the trips,
not from the recorder, so tours longer than 10 days are complete. Manual exports with raw data count as trips too;
if one overlaps an automatically detected trip, the automatic one counts, so no distance counts twice. Choose the first trip in the export selection,
check tour from and tour until, optionally enter a title and press create tour. The tour folder
`tour-<start>-<end>` holds the composite image (key figures, overall map, days by place, costs), map, GPX with one
track per trip, statistics, a CSV with one row per day, raw data and `export.json`. The place of a night is where
the vehicle stands at 3 am, named after the camp site or pitch in OpenStreetMap, else the town. Costs are the refills
and all travel costs dated within the tour, by category and country; the estimated consumption uses the average
consumption. When logbook entries or travel costs in the period change, the tour is renewed after 30 s without
downloading the map again. The push blueprint can report created (default on) and renewed tours (default off).

## Map symbols and ferries

Maps show symbols in coloured circles; the composite image has a legend of the symbols that occur below the map.
Costs are never shown on the map.

- **Trip map:** start, end (or a pitch symbol with its name in the statistics when the arrival is on a camp site),
  stops, fuel and gas stops from the logbook (late entries too) and ferry crossings, dashed in blue with a ship in
  the middle. A refill at a stop replaces the stop symbol; fuel and gas at the same stop stand side by side.
- **Tour map:** start, end, one pitch per run of nights at the same place, fuel and gas stops within the tour and the
  ferries of all trips; no stops.
- **Manual export:** start, end or pitch, fuel and gas stops; no stops and no ferry.

**Ferry:** if the vehicle moves during a stop (D+ off) and the middle of that movement lies on water in
OpenStreetMap, the stop counts as a ferry crossing. To correct it (for example no GPS on board), choose the stop in
the logbook time selection and press mark as ferry; its label then ends in “· Fähre”, a second press removes the
mark. Older stops are marked with the action `faehre_markieren`. The crossing counts neither as distance nor as
driving time nor in the odometer; statistics and composite image list it separately, and the elevation and speed
profile draws it dashed in blue. Marking a ferry later moves the counters of later logbook entries by the ferry
distance and renews the export without downloading tiles.

**Redraw map:** exports from before this version have no symbols yet. Choose the export in the export selection and
press redraw map (or call `karte_neu_zeichnen`). The tiles are downloaded again, a trip has its stops checked once
for ferries and its arrival for a camp site, and map, base map, profile, statistics and composite image are renewed.
One export per call, and only with raw data. If a tile cannot be loaded, the old map stays and you are asked to try
again later.

## Push notification (blueprint)

[![Import the blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FChrisFerro%2Fha-reiseverlauf%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Freiseverlauftracker%2Fbenachrichtigung.yaml)

Import the blueprint, create an automation from it, pick the vehicle and the phones, and set the dashboard view
that opens on tap (default `/dashboard-reiseverlauf`). When a trip ends, the phones get its title, distance,
driving time, departure and arrival.
A resumed trip replaces the previous notification. Notifications on trip start (default on) and after manual
exports (default off) are optional, and the headings can be changed. The blueprint texts are German.

The notification carries no image on purpose: the composite image is sized for a photo book, and iOS does not
show attachments that large.

## Logbook

The logbook keeps the odometer, the levels of the fuel tank and the two gas tanks, and fuel and gas stops. An entry
belongs to an occasion: the **trip start** (to confirm the levels after standing, as the heating uses fuel and gas),
each **stop** of at least the minimum stop duration, or a **manual** entry at any time. For each occasion the form
is prefilled with a suggestion: last odometer plus the measured distance, the last levels, and once an average
consumption is known, a fuel level computed from distance, consumption and tank size. Litres refuelled set the level
to 100 % (for gas both tanks). The average consumption comes from full tanks.

“Heating while parked (read)” estimates the diesel the heating uses per parked day: the drop of the fuel level
between the last entry before a parked period and the next trip start, summed over all parked periods without
refuelling or driving in between, divided by the parked days. As the gauge is read coarsely, the value becomes
meaningful only over many parked periods; it changes neither the average consumption nor the suggestion. Each entry
also keeps the metres driven uphill and downhill so far, as the basis for a later consumption model.

Entries are kept in the integration's storage and are part of every Home Assistant backup. `fahrtenbuch.csv` in the
output folder (German format: semicolon, decimal comma) is rewritten after every change. After a trip, odometer
from/to, litres, costs and consumption are part of the statistics and the composite image.

### Late entries and travel costs

To enter a fuel stop later, choose the stop (or "other time" and set the time) in the logbook time selection; the
form shows the odometer at that time from the recorded track (attribute `geschaetzt` if it is only estimated). Enter
litres and amount and press the late entry button. Stops are kept for 120 days.

Travel costs belong to the trip chosen in the export selection; the date starts at the trip start and the country
selection lists the countries of the trip first. With "all exports" chosen, a cost is saved without a trip on the
chosen date. Costs count in the month of their date, and `reisekosten.csv` is rewritten after every change. The
countries of a trip are looked up after its export along the track (about every 20 km, only with place names on); for older trips at start (last 12 months) or once the trip is chosen.
30 s after any change to a finished trip, its statistics, composite image and `export.json` are renewed; map,
profile, GPX and raw points stay. Toll is usually billed the month after, so "open toll" counts the trips through toll
countries without a toll entry; a trip on country roads only can be marked with "no toll".

### Changing and deleting entries

Stored logbook entries and travel costs can be corrected on the dashboard, without IDs. Choose the trip in the export
selection: **edit logbook** then lists all entries of that trip and the parked time after it until the next trip
(such as “27.09. 17:30 · Late entry · Irschenberg · 33768 km”), **travel cost entry** the costs of that trip. With
“all exports”, they list the 30 newest logbook entries and the costs without a trip. Choosing an entry fills the form
(for the logbook also the late entry time); a pending occasion waits meanwhile. Press **change** to store the values
or **delete** to remove the entry for good; the selection then returns to “New”, and discard returns without a
change. While an entry is chosen, save, late entry and travel cost save are refused, so no second entry arises.

A new time moves the entry: distance and climb are taken for the new time as for a late entry, the odometer stays the
one in the form. CSV, cost sensors, average consumption and the exports of the trips concerned are renewed. Travel
costs keep their trip; the action to change travel costs assigns another one.

An empty field means “not read off”, while 0 % is a reading. The change and delete buttons have the fixed entity IDs
`button.<device>_fahrtenbuch_aendern`, `_fahrtenbuch_loeschen`, `_reisekosten_aendern` and `_reisekosten_loeschen`.
The German README has dashboard examples with a confirmation before deleting.

### Push reminder (blueprint)

[![Import the blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FChrisFerro%2Fha-reiseverlauf%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Freiseverlauftracker%2Ffahrtenbuch.yaml)

Import the blueprint, create an automation from it, pick the vehicle and the phones, and set the dashboard view
with the form (default `/dashboard-reiseverlauf/fahrtenbuch`). At trip start and at each stop the phones get the
suggestion, for example `34439 km · Diesel 72 % · Gas 81 % / 60 %`. The button **Übernehmen** saves it, and a
confirmation replaces the notification; a tap on the notification opens the form to correct it or to add a fuel
stop. An old notification whose occasion was already saved or replaced saves nothing. The blueprint texts are
German and can be changed. On the first of each month at 09:00 (time adjustable), the blueprint also reminds of
open toll while there is any; a tap opens the travel costs view (default `/dashboard-reiseverlauf/reisekosten`).

Dashboard views for the form, the travel costs and the evaluation are shown in the
[German README](README.md#dashboard-ansicht).

## Events

`reiseverlauftracker_tour` (tour created or renewed, `anlass` `erstellt` or `aktualisiert`),
`reiseverlauftracker_gestartet` (trip started or resumed), `reiseverlauftracker_beendet` (export of an ended trip
is ready), `reiseverlauftracker_exportiert` (manual export is ready) and `reiseverlauftracker_fahrtenbuch` (logbook
occasion: trip start or stop, with the suggestion). The payload keys are German, see the
[German README](README.md#events); `fahrtenbuch.kosten` includes the travel costs, listed by category in
`fahrtenbuch.reisekosten`. Each stop in `halte` has `faehre`; `strecke_km` and `fahrzeit_min` exclude the ferry,
which is in `faehre_km` and `faehre_min` (also in the tour event).

## Privacy

Map tiles come from OpenStreetMap, once per trip and on redraw map. For place names and countries, positions are
sent to Nominatim (OpenStreetMap): start, end and stops of a trip, for its countries a point of the track about every
20 km, for the ferry detection one point per stop with movement, and the arrival for a camp site, at
most one request a second. The place-name lookup can be turned off in the options; then neither places nor
countries are looked up. Diagnostics contain no
positions.

## AI-assisted development

> [!NOTE]
> This integration was developed predominantly with AI coding assistants (Claude). Requirements and decisions
> come from the maintainer, and every stage was checked in a development instance. About 380 automated tests
> cover detection, export, logbook, downloads, setup, entities, actions and the blueprints. It has not yet been tested with a real
> vehicle, only with simulated sensors. This is an early 0.x version; settings and entities may still change.

## License

MIT, see [LICENSE](LICENSE). The bundled DejaVu Sans font has its own license. Map data © OpenStreetMap
contributors.

[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/ChrisFerro/ha-reiseverlauf.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/ChrisFerro/ha-reiseverlauf.svg?style=for-the-badge
[releases]: https://github.com/ChrisFerro/ha-reiseverlauf/releases
