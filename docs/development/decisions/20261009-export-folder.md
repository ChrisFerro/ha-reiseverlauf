---
id: 20261009-export-folder
status: accepted
migrated-from: docs/development/DECISIONS.md
---

# One Folder per Export With export.json as the Source of Truth

## Context

Exports live in the media folder, which users can also browse and change. The integration
must list them, show the last trip after a restart, and delete files without touching anything else.

## Decision

Each export gets its own folder named after its local start time (manual exports: start and
end). `export.json` in the folder lists title, figures and file names. Listing, the last trip and cleanup
read only this file; cleanup deletes only the files named there.

## Rationale

- A merged trip replaces its files in the same folder instead of leaving an outdated export behind
- No second index to keep in sync with the folder contents
- Files a user adds to a folder are never deleted

## Consequences

- Folders without a readable `export.json` are ignored
- Two exports with the same start minute share a folder; the later one replaces the earlier one
- Changing the folder naming later leaves old folders as they are
