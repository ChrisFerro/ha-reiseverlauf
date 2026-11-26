---
id: 20261009-own-trip-points
status: accepted
migrated-from: docs/development/DECISIONS.md
---

# Record Trip Points in the Integration and Keep Them With the Export

## Context

The recorder keeps ten days by default, and a trip can last longer or be exported later.

## Decision

While a trip runs or can still be merged, the coordinator records positions, speed and
altitude in a `Store` per entry. After the export the points are written as `<name>_rohdaten.json` into
the export folder and stay there until the cleanup action deletes them. Manual exports store the points
they read from the recorder in the same format.

## Rationale

- Exports of automatic trips do not depend on recorder retention
- One raw data format for both kinds of exports keeps a later re-export simple

## Consequences

- The trip log store grows with the trip (thousands of points per day); it is saved with a delay
- Raw data is a file type of its own in the cleanup action
- Re-exporting from raw data is not implemented yet; manual exports read the recorder only
