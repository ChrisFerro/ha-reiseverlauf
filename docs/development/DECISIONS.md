# Architectural and Design Decisions

This document records significant architectural and design decisions made during the development of this integration.

## Format

Each decision is documented with:

- **Date:** When the decision was made
- **Context:** Why this decision was necessary
- **Decision:** What was decided
- **Rationale:** Why this approach was chosen
- **Consequences:** Expected impacts and trade-offs

> [!NOTE]
> Guidance on _when_ a decision is worth recording here, and a copy-ready entry template, lives in the
> [`ha-planning`](../../.agents/skills/ha-planning/SKILL.md) agent skill.

---

## Decision Log

### Use DataUpdateCoordinator for All Data Fetching

**Date:** 2025-11-29 (Template initialization)

**Context:** The integration needs to fetch data from an external API and share it with multiple entities. Home Assistant provides several patterns for this.

**Decision:** Use `DataUpdateCoordinator` from `homeassistant.helpers.update_coordinator` as the central data management component.

**Rationale:**

- Provides built-in support for update intervals and error handling
- Automatic retry with exponential backoff
- Shared data access prevents duplicate API calls
- Standard pattern recommended by Home Assistant
- Entities automatically become unavailable when coordinator fails

**Consequences:**

- All entities must inherit from `CoordinatorEntity`
- Single update interval applies to all entities
- Data is fetched even if no entities are enabled
- Coordinator manages entity lifecycle and availability

---

### Separate API Client from Coordinator

**Date:** 2025-11-29 (Template initialization)

**Context:** The coordinator needs to fetch data, but business logic should be separated from data transport.

**Decision:** Implement API communication in separate `api/client.py` module, coordinator only orchestrates updates.

**Rationale:**

- Separation of concerns: transport vs. orchestration
- Easier to test API client in isolation
- Simpler to swap API implementation if needed
- Clearer error handling boundaries

**Consequences:**

- Additional abstraction layer
- Coordinator depends on API client
- API client raises custom exceptions for error translation

---

### Platform-Specific Directories

**Date:** 2025-11-29 (Template initialization)

**Context:** Integration supports multiple platforms (sensor, binary_sensor, switch, etc.).

**Decision:** Each platform gets its own directory with individual entity files.

**Rationale:**

- Clear organization as integration grows
- Easier to find specific entity implementations
- Supports multiple entities per platform cleanly
- Follows Home Assistant Core pattern

**Consequences:**

- More files/directories than single-file approach
- Platform `__init__.py` must import and register entities
- Slightly more initial setup overhead

---

### EntityDescription for Static Metadata

**Date:** 2025-11-29 (Template initialization)

**Context:** Entities have static metadata (name, icon, device class) that doesn't change.

**Decision:** Use `EntityDescription` dataclasses to define static entity metadata.

**Rationale:**

- Declarative and easy to read
- Type-safe with dataclasses
- Recommended Home Assistant pattern
- Separates static configuration from dynamic behavior

**Consequences:**

- Each entity type needs an EntityDescription
- Dynamic entities need custom handling
- Static and dynamic properties clearly separated

---

### Draw Images with Pillow and staticmap, Bundle DejaVu Sans

**Date:** 2026-10-06

**Context:** The export draws a route map, an elevation/speed profile and a composite image for a
photo book. Home Assistant OS runs Python 3.14 on Alpine (musl). Labels are German and English.

**Decision:** Charts and the composite image are drawn with Pillow; the map uses `staticmap` with
OpenStreetMap tiles. DejaVu Sans is bundled in `export/fonts/` with its license.

**Rationale:**

- matplotlib has no musl wheels for Python 3.14 and cannot be compiled on Home Assistant OS
- `staticmap` is pure Python and only needs `requests` and Pillow, both shipped with Home Assistant
- Pillow's built-in font (Aileron) has no umlauts, "Ø" or "–", and Home Assistant OS has no system
  fonts; `env_canada` bundles DejaVu Sans for the same reason

**Consequences:**

- The package grows by about 760 KB
- `staticmap` raises after three failed tile attempts without shutting down its thread pool; a
  subclass therefore returns a blank tile for missing or broken tiles instead
- Rendering blocks and needs over 100 MB at scale 2, so it must run in an executor

---

### Drive the Coordinator by State Changes, Without an API Client

**Date:** 2026-10-09

**Context:** The integration derives everything from entities that already exist in Home Assistant (D+,
position tracker, speed, altitude). There is no device or service to poll. This supersedes "Separate API
Client from Coordinator" and the polling assumption of "Use DataUpdateCoordinator for All Data Fetching".

**Decision:** Keep `DataUpdateCoordinator` for entity plumbing, but without an update interval and without
an `api/` package. State-change listeners and one timer for the detector's next deadline feed a pure
`TripDetector`; the coordinator publishes a snapshot with `async_set_updated_data()`.

**Rationale:**

- Trip start and end must be detected within seconds, which polling would only approximate
- A pure state machine can be tested exhaustively without Home Assistant
- `CoordinatorEntity` still gives entities a single source and one update path

**Consequences:**

- `_async_update_data()` only returns the current snapshot; a failed update cannot make entities unavailable
- Every input processes passed deadlines first, so a late timer never reorders events
- Detector state must be persisted and reconciled after a restart (`restore()`)

---

### Record Trip Points in the Integration and Keep Them With the Export

**Date:** 2026-10-09

**Context:** The recorder keeps ten days by default, and a trip can last longer or be exported later.

**Decision:** While a trip runs or can still be merged, the coordinator records positions, speed and
altitude in a `Store` per entry. After the export the points are written as `<name>_rohdaten.json` into
the export folder and stay there until the cleanup action deletes them. Manual exports store the points
they read from the recorder in the same format.

**Rationale:**

- Exports of automatic trips do not depend on recorder retention
- One raw data format for both kinds of exports keeps a later re-export simple

**Consequences:**

- The trip log store grows with the trip (thousands of points per day); it is saved with a delay
- Raw data is a file type of its own in the cleanup action
- Re-exporting from raw data is not implemented yet; manual exports read the recorder only

---

### One Folder per Export With export.json as the Source of Truth

**Date:** 2026-10-09

**Context:** Exports live in the media folder, which users can also browse and change. The integration
must list them, show the last trip after a restart, and delete files without touching anything else.

**Decision:** Each export gets its own folder named after its local start time (manual exports: start and
end). `export.json` in the folder lists title, figures and file names. Listing, the last trip and cleanup
read only this file; cleanup deletes only the files named there.

**Rationale:**

- A merged trip replaces its files in the same folder instead of leaving an outdated export behind
- No second index to keep in sync with the folder contents
- Files a user adds to a folder are never deleted

**Consequences:**

- Folders without a readable `export.json` are ignored
- Two exports with the same start minute share a folder; the later one replaces the earlier one
- Changing the folder naming later leaves old folders as they are

---

### Unique IDs: Position Tracker for the Entry, Entry ID for Entities

**Date:** 2026-10-09

**Context:** The integration has no serial number or account ID. One entry represents one vehicle.

**Decision:** The config entry's unique ID is the entity ID of the position tracker. Entity unique IDs are
`{entry_id}_{key}`, all on one service device per entry.

**Rationale:**

- The tracker is what distinguishes vehicles, so the same vehicle cannot be set up twice
- Entity IDs of other integrations are the only stable handle available

**Consequences:**

- Renaming the tracker's entity ID does not update the entry; reconfigure sets the new tracker and unique ID
- Renaming an entity description `key` is a breaking change

---

### German Keys in Events, Attributes and Status Values

**Date:** 2026-10-09

**Context:** Users write automations and dashboard templates against event data, attributes and the status
sensor. The requirements name these values in German.

**Decision:** Status values (`bereit`, `unterwegs`, `pause`, `auswertung`, `zusammenfuehrbar`, `fehler`),
event payload keys and extra attribute keys are German. Code identifiers stay English; the UI shows
translations.

**Rationale:**

- The values match the requirements and read naturally in the user's automations
- Translations still give English users English labels in the UI

**Consequences:**

- Changing any of these values breaks user automations
- codespell needs inline ignores for German keys such as `titel`, `ende` and `ordner`

---

## Future Considerations

### Re-Export From Raw Data

**Status:** Not yet implemented

`exportieren` reads the recorder only. Reading `<name>_rohdaten.json` instead would allow exports older than
the recorder retention.

### Altitude From the Router

**Status:** Open (requirements 9.6)

The altitude is set by a script on the router. The integration could read it itself instead.

---

## Decision Review

These decisions should be reviewed periodically (suggested: quarterly or when major features are added) to ensure they still serve the integration's needs.
