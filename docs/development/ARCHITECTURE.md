# Architecture Overview

This document describes the technical architecture of the Reiseverlauf Tracker für Wohnmobile custom component for Home Assistant.

The integration fetches nothing from a device or a cloud service. It listens to entities that already
exist (D+ signal, position tracker, speed and altitude sensors), detects trips from them, records the
points of each trip and exports them as images, GPX and statistics into the media folder.

## Directory Structure

```text
custom_components/reiseverlauftracker/
├── __init__.py              # async_setup (actions), setup and unload of an entry
├── config_flow.py           # Config flow entry point required by hassfest
├── const.py                 # Configuration keys, defaults, event names
├── settings.py              # Typed view of entry data and options with defaults
├── data.py                  # Runtime data stored on the config entry
├── diagnostics.py           # Diagnostics with positions redacted
├── coordinator/             # Trip detection, recording and export orchestration
│   ├── base.py              # Push-driven coordinator: state listeners, deadline timer, Store
│   ├── trip_detector.py     # Trip state machine (D+, delay, merge window), no HA imports
│   ├── trip_log.py          # Points of one trip with running distance and driving time, no HA imports
│   ├── models.py            # TripStatus and the TripSnapshot entities read
│   ├── title.py             # Title of an automatic trip (date, place or both)
│   ├── export_runner.py     # Runs export_trip() in the executor, place names, event payload
│   └── exports.py           # Export folders, export.json, listing and cleanup (blocking)
├── export/                  # Trip export library, no HA imports, blocking (run in executor)
│   ├── __init__.py          # Public API: export_trip(), TrackPoint, StepSeries, ExportOptions
│   ├── model.py             # Input data and options
│   ├── track.py             # Accuracy filter, departure/arrival, thinning, speed decoding
│   ├── stats.py             # Distance, driving time, elevation gain, statistics text
│   ├── texts.py             # German and English labels and formatting
│   ├── gpx.py               # GPX output
│   ├── chart.py             # Elevation and speed profile (Pillow)
│   ├── map.py               # Route map on OSM tiles (staticmap)
│   ├── composite.py         # Composite image for the photo book
│   ├── exporter.py          # Runs one export and writes the files
│   └── fonts/               # Bundled DejaVu Sans and its license
├── config_flow_handler/     # Setup, reconfigure and options
│   ├── config_flow.py       # User and reconfigure steps; unique ID is the position tracker
│   ├── options_flow.py      # Options in sections: detection, export, thresholds
│   ├── schemas/             # Voluptuous schemas
│   └── validators/          # Output folder inside the media directory
├── entity/                  # ReiseverlaufEntity: one service device per entry
├── binary_sensor/           # Trip active
├── sensor/                  # Status, running trip, last trip (value_fn descriptions)
├── image/                   # Composite image of the last trip via the image proxy
├── select/                  # Export selection used by the cleanup action
├── service_actions/         # exportieren, aufraeumen, reise_starten, reise_beenden
│   ├── __init__.py          # Schemas and registration in async_setup()
│   ├── entry.py             # Resolve a loaded config entry
│   ├── history.py           # Read a period from the recorder
│   ├── export.py            # Export and cleanup handlers
│   └── trip.py              # Start and end trip handlers
├── utils/
│   ├── geo.py               # Position and great-circle distance
│   └── geocode.py           # Place names from Nominatim
├── icons.json               # Entity, section and action icons
├── manifest.json            # Integration metadata
├── repairs.py               # Repair flow entry point (no issues raised yet)
├── services.yaml            # Action fields and selectors
└── translations/            # de.json and en.json
```

`export/` is an approved exception to the package set in [`AGENTS.md`](../../AGENTS.md): the export is
the integration's core function and too large for `utils/`. There is no `api/` package, because the
integration talks to no device or service of its own.

## Core Components

### Trip detector

**File:** `coordinator/trip_detector.py`

A pure state machine with the phases `idle`, `active` and `ended`. It is fed D+ changes, positions and
clock ticks and returns events (`TripStarted`, `TripResumed`, `TripEnded`, `TripDiscarded`,
`TripClosed`). Every input first processes deadlines that passed before its timestamp, so a late timer
never reorders events. `as_dict()` and the constructor make it persistent; `restore()` reconciles the
stored state with the D+ state found after a restart.

### Coordinator

**File:** `coordinator/base.py`, class `ReiseverlaufDataUpdateCoordinator`

A `DataUpdateCoordinator` without an update interval. It subscribes to the configured entities, feeds
the detector, keeps one timer for `next_deadline()` and publishes a `TripSnapshot` with
`async_set_updated_data()`.

- `unavailable` and `unknown` D+ states are ignored, never treated as "off".
- While a trip runs or can still be merged, positions, speed and altitude go into a `TripLog`.
- Detector state and trip log are persisted in two `Store` files per entry.
- On `TripEnded` it starts the export as an entry task; the status shows `auswertung` meanwhile and
  `fehler` if it fails, until the next trip starts.
- It keeps the list of exports and the current export choice for the select entity and the cleanup action.

### Export

**Files:** `coordinator/export_runner.py`, `coordinator/exports.py`, package `export/`

`async_export()` builds the title (place names from Nominatim when configured), then runs
`export_trip()` in the executor. Each export gets its own folder below
`<media dir>/<output folder>/`:

- automatic trips: `<local start>` such as `2026-10-09_1040`; a merged trip replaces the files there
- manual exports: `<local start>-<local end>`, so they never replace an automatic export

Besides the images, GPX and statistics, the folder holds `<name>_rohdaten.json` (recorded points) and
`export.json` (title, figures, file list). `export.json` is what the integration reads back: the export
list, the last trip after a restart, and the only files cleanup may delete.

### Entities

All entities sit on one device of type service per config entry and read the `TripSnapshot` only. The
unique ID is `{entry_id}_{key}`.

| Platform        | Keys                                                                                                                                                                        |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `binary_sensor` | `trip_active`                                                                                                                                                               |
| `sensor`        | `trip_status`, `trip_start`, `trip_distance`, `trip_driving_time`, `last_trip_title`, `last_trip_distance`, `last_trip_driving_time`, `last_trip_duration`, `last_trip_end` |
| `image`         | `last_trip_composite`                                                                                                                                                       |
| `select`        | `export_choice`                                                                                                                                                             |

### Service actions

Registered in `async_setup()`, each with a required `config_entry_id`:

- `exportieren` reads a period from the recorder, exports it and fires `reiseverlauftracker_exportiert`.
- `aufraeumen` deletes file types of one export, of all exports, or of the current export choice.
- `reise_starten` and `reise_beenden` call the detector's manual start and end.

### Events

| Event                            | When                                   |
| -------------------------------- | -------------------------------------- |
| `reiseverlauftracker_gestartet`  | A trip starts or resumes (`resumed`)   |
| `reiseverlauftracker_beendet`    | The export of an ended trip is written |
| `reiseverlauftracker_exportiert` | A manual export is written             |

The keys of the payload are German (`titel`, `start`, `ende`, `abfahrt`, `ankunft`, `strecke_km`, `fahrzeit_min`, `ordner`,
`dateien`, `statistik`, `gesamtbild`, `gesamtbild_url`), because users write automations against them.

## Data Flow

```text
 D+ / tracker / speed / altitude state changes        deadline timer
                    │                                       │
                    ▼                                       ▼
          ┌───────────────────────────────────────────────────────┐
          │ Coordinator ──► TripDetector ──► events               │
          │      │                             │                  │
          │      ▼                             ▼                  │
          │   TripLog (Store)        TripEnded ──► export task     │
          └──────┬───────────────────────────────┬────────────────┘
                 │ TripSnapshot                   │ executor: export_trip()
                 ▼                                ▼
        entities (sensor, binary_sensor,   <media>/<folder>/<export>/
        image, select)                     + event reiseverlauftracker_beendet
```

## AI Agent Context

Agent-facing content is layered so each piece is loaded only when it is relevant:

| Layer                             | Loaded                      | Contains                                          |
| --------------------------------- | --------------------------- | ------------------------------------------------- |
| `AGENTS.md`                       | always                      | project identity, workflow rules, validation loop |
| `.agents/instructions/*.md`       | per touched file            | passive style rules for one file type             |
| `.agents/skills/*/SKILL.md`       | when a task matches         | active procedures for a specific kind of work     |
| `docs/development/`, `docs/user/` | when a human or agent reads | explanations, decisions, guides — this document   |

Style rules belong in `.agents/instructions/`, procedures belong in a skill, explanations belong in `docs/`.

One copy of each instruction file serves two agents: GitHub Copilot and VS Code match its `applyTo` glob string,
Claude Code matches the same patterns via `paths` (a YAML list, one pattern per item) and reaches the same files
through the `.claude/rules/instructions` symlink. Codex has no comparable file-triggered mechanism — its nested
`AGENTS.md` support keys off the working directory rather than the file being edited — so it relies on the root
`AGENTS.md` plus the pointers each skill carries.

The skill catalogue, the symlink layout that makes one directory work for every agent vendor, and the rules for writing
a new skill are documented in [`.agents/skills/README.md`](../../.agents/skills/README.md).

For working with AI coding agents in this repository, see [`AI_AGENTS.md`](./AI_AGENTS.md).

## Key Design Decisions

See [DECISIONS.md](./DECISIONS.md) for architectural and design decisions made during development.

## Extension Points

To add new functionality:

### Adding a New Platform

1. Create directory: `custom_components/reiseverlauftracker/<platform>/`
2. Implement `__init__.py` with `async_setup_entry()`
3. Create entity classes inheriting from platform base + `ReiseverlaufEntity`
4. Add platform to `PLATFORMS` in `__init__.py`

### Adding a New Service Action

1. Create service action handler in `service_actions/<service_name>.py`
2. Define service action in `services.yaml` (legacy filename) with schema
3. Register service action in `__init__.py:async_setup()` (NOT `async_setup_entry`)

### Modifying Data Structure

1. Update coordinator data type in `coordinator.py`
2. Adjust API client response parsing in `api/client.py`
3. Update entity property implementations to match new structure

## Testing Strategy

- **Unit tests:** Test individual functions and classes in isolation
- **Integration tests:** Test coordinator with mocked API
- **Fixtures:** Shared test fixtures in `tests/conftest.py`

Tests mirror the source structure under `tests/`.

## Dependencies

Core dependencies (see `manifest.json`):

- `staticmap` - Route map from OpenStreetMap tiles (pure Python; uses `requests` and Pillow)
- `Pillow` - Charts and composite image (shipped with Home Assistant)
- Home Assistant 2025.7.0+ - Platform requirements

Development dependencies (see `requirements_dev.txt`, `requirements_test.txt`).
