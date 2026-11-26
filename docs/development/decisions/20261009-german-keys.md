---
id: 20261009-german-keys
status: accepted
migrated-from: docs/development/DECISIONS.md
---

# German Keys in Events, Attributes and Status Values

## Context

Users write automations and dashboard templates against event data, attributes and the status
sensor. The requirements name these values in German.

## Decision

Status values (`bereit`, `unterwegs`, `pause`, `auswertung`, `zusammenfuehrbar`, `fehler`),
event payload keys and extra attribute keys are German. Code identifiers stay English; the UI shows
translations.

## Rationale

- The values match the requirements and read naturally in the user's automations
- Translations still give English users English labels in the UI

## Consequences

- Changing any of these values breaks user automations
- codespell needs inline ignores for German keys such as `titel`, `ende` and `ordner`
