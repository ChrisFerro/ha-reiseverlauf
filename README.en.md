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
- **Ferries and car trains:** if the vehicle moves while D+ is off, the trip goes on.
- **Merging:** if the journey continues within a window after the end (default 6 h), for example after a long
  wait at the port, the same trip is resumed and exported again.
- **Export:** distance, driving time, top and average speed, altitude and elevation gain; map on OpenStreetMap
  tiles, profiles, GPX with altitude and speed, composite image.
- **Titles with place names:** such as "Hamburg – Kiel, 2026-10-12"; or date only, or places only.
- **Own recording:** the points of each trip are stored, independent of how long the recorder keeps data.
- **Protected storage:** all files are written to the Home Assistant media folder and need a login to open.
- **UI only:** setup, options, entities and actions; no YAML required.

## Requirements

- Home Assistant 2026.8 or newer
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

**Configure** offers the options in three sections: trip detection (end delay, merge window, minimum movement),
export (title format, place-name lookup, image scale, chart margin) and thresholds (standstill speed, maximum
GPS inaccuracy, minimum point distance, elevation hysteresis). A trip that never got further from its start than
the minimum movement (default 100 m) is discarded.

## Entities

All entities belong to one device named after the entry: trip active, trip status (ready, driving, stopped,
processing, can continue, error), start, distance and driving time of the running trip, title, distance, driving
time, duration and end of the last trip (the title carries the file list with URLs and the statistics as
attributes), an image entity with the composite image, and an export selection used by the cleanup action.

## Actions

| Action                              | Purpose                                                                                            |
| ----------------------------------- | -------------------------------------------------------------------------------------------------- |
| `reiseverlauftracker.exportieren`   | Export any period from the recorder, optionally with title, scale and margin; returns the result   |
| `reiseverlauftracker.aufraeumen`    | Delete file types of one export or of all exports; without an export, the export selection applies |
| `reiseverlauftracker.reise_starten` | Start a trip without D+, or resume the last one within the merge window                            |
| `reiseverlauftracker.reise_beenden` | End the running trip now and export it                                                             |

## Storage

Each trip gets its own folder named after its start time (for example `2026-10-12_1000`; manual exports
`2026-10-12_1000-1130`) with the composite image, map, profile, GPX, statistics, raw points and an `export.json`
the integration uses to manage the export. Only files listed there are ever deleted.

## Push notification (blueprint)

[![Import the blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FChrisFerro%2Fha-reiseverlauf%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Freiseverlauftracker%2Fbenachrichtigung.yaml)

Import the blueprint, create an automation from it and pick the vehicle and the phones. When a trip ends, the
phones get its title, distance, driving time and time span with the composite image; tapping opens the image.
A resumed trip replaces the previous notification. Notifications on trip start (default on) and after manual
exports (default off) are optional, and the headings can be changed. The blueprint texts are German.

The phone loads the image through its connection to Home Assistant, so on the road it needs remote access (for
example Home Assistant Cloud).

## Events

`reiseverlauftracker_gestartet` (trip started or resumed), `reiseverlauftracker_beendet` (export of an ended trip
is ready) and `reiseverlauftracker_exportiert` (manual export is ready). The payload keys are German, see the
[German README](README.md#events).

## Privacy

Map tiles come from OpenStreetMap; for place names the start and end position are sent to Nominatim
(OpenStreetMap), once per trip. The place-name lookup can be turned off in the options. Diagnostics contain no
positions.

## AI-assisted development

> [!NOTE]
> This integration was developed predominantly with AI coding assistants (Claude). Requirements and decisions
> come from the maintainer, and every stage was checked in a development instance. About 200 automated tests
> cover detection, export, setup, entities, actions and the blueprint. It has not yet been tested with a real
> vehicle, only with simulated sensors. This is an early 0.x version; settings and entities may still change.

## License

MIT, see [LICENSE](LICENSE). The bundled DejaVu Sans font has its own license. Map data © OpenStreetMap
contributors.

[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/ChrisFerro/ha-reiseverlauf.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/ChrisFerro/ha-reiseverlauf.svg?style=for-the-badge
[releases]: https://github.com/ChrisFerro/ha-reiseverlauf/releases
