---
id: 20261009-state-driven-coordinator
status: accepted
migrated-from: docs/development/DECISIONS.md
---

# Drive the Coordinator by State Changes, Without an API Client

## Context

The integration derives everything from entities that already exist in Home Assistant (D+,
position tracker, speed, altitude). There is no device or service to poll. This supersedes "Separate API
Client from Coordinator" and the polling assumption of "Use DataUpdateCoordinator for All Data Fetching".

## Decision

Keep `DataUpdateCoordinator` for entity plumbing, but without an update interval and without
an `api/` package. State-change listeners and one timer for the detector's next deadline feed a pure
`TripDetector`; the coordinator publishes a snapshot with `async_set_updated_data()`.

## Rationale

- Trip start and end must be detected within seconds, which polling would only approximate
- A pure state machine can be tested exhaustively without Home Assistant
- `CoordinatorEntity` still gives entities a single source and one update path

## Consequences

- `_async_update_data()` only returns the current snapshot; a failed update cannot make entities unavailable
- Every input processes passed deadlines first, so a late timer never reorders events
- Detector state must be persisted and reconciled after a restart (`restore()`)
