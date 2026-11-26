---
id: 20261009-unique-ids
status: accepted
migrated-from: docs/development/DECISIONS.md
---

# Unique IDs: Position Tracker for the Entry, Entry ID for Entities

## Context

The integration has no serial number or account ID. One entry represents one vehicle.

## Decision

The config entry's unique ID is the entity ID of the position tracker. Entity unique IDs are
`{entry_id}_{key}`, all on one service device per entry.

## Rationale

- The tracker is what distinguishes vehicles, so the same vehicle cannot be set up twice
- Entity IDs of other integrations are the only stable handle available

## Consequences

- Renaming the tracker's entity ID does not update the entry; reconfigure sets the new tracker and unique ID
- Renaming an entity description `key` is a breaking change
